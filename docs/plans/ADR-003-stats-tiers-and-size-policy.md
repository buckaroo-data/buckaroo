# ADR: Ordered stat tiers and a size policy for degrading summary stats

- **Status:** Proposed (2026-10-06). The decisions below are recommendations and 13 of them are open for the maintainer (see "Open decisions"). The parked PRs implement a three-tier subset (`schema`, `scalar`, `full`) with a policy module; the `approx` tier, per-stat declaration and the footer provider are not implemented anywhere.
- **Affected code:** `buckaroo/pluggable_analysis_framework/stat_func.py`, `typed_dag.py` (`build_typed_dag`, `build_column_dag`), `stat_pipeline.py`, `df_stats_v2.py`, `xorq_stat_pipeline.py`, `buckaroo/customizations/pd_stats_v2.py`, `pl_stats_v2.py`, `xorq_stats_v2.py`, `buckaroo/dataflow/dataflow.py` (`_get_summary_sd`, `_summary_sd`, `_populate_sd_cache`, `add_analysis`), `buckaroo/server/stats_policy.py` (new), `handlers.py`, `session.py`, and the client states for `not_computed`.
- **Implementing PRs (the three-tier subset):** #1019 (policy module, not wired), #1023 (calibrated thresholds), #1029 (policy wire contract and handler plumbing), #1031 (xorq scalar tier units), #1033 (limits override, cost guard, demand scan), #1034 (sort and search guards for huge sources), and the client PRs #1032 (`not_computed` states and compute control) and #1036 (request a scalar target, track the tier reached).
- **Related:** #911 (exact below a size, approximate above), #1016 and #1017 (closed: `@stat(max_rows=)`), #808 and #809 (open, stale: `@stat(cost=)`), #1000 and #1005 (closed: eager-polars stopgaps), ADR-001 (stat cache), ADR-002 (how stats reach the client).

## Terms

- **tier**: one of `schema < scalar < approx < full`. A session runs at a tier T; a stat runs at T if its effective tier is at most T.
- **effective tier of a stat**: its declared tier, raised to the highest effective tier among the stats it requires.
- **exact / approximate / omitted**: what a stat is at a given session tier. An omitted stat is absent from the column dict.
- **`StatsLimits`**: the table that maps backend, source kind and size to the highest tier that runs.
- **ceiling**: a size above which a tier is refused to every caller, including an explicit request.
- **footer provider**: reads row count and per-column `null_count`, `min` and `max` from a parquet footer without reading data.

## Problem

Nothing on main decides, from the size of a dataframe, how much of the stats pipeline to run. What exists is a set of hard-coded gates, none configurable by the host and none reported to the user:

- Above `FAST_SUMMARY_WHEN_GREATER = 1_000_000` cells (`pluggable_analysis_framework/utils.py`), `DfStatsV2` and `PlDfStatsV2` run every stat on a 50,000-row sample.
- `pre_limit` replaces the served frame before stats: 100,000 rows for `Sampling`, 1,000,000 for `PdSampling` and the server samplers, off for `PLSampling` and `XorqSampling`.
- xorq samples categorical histograms above 100,000 rows and always uses HyperLogLog for `distinct_count`.
- The lazy executor has no gate.

**The 50,000-row sample applies to exact stats too.** On a 200,000 x 10 int64 frame with one value planted at -5 and one at 2,000,000,000 per column, both pandas and polars report `length` 50,000, and `min` and `max` are wrong in every column whose extreme row is not in the sample. So `length`, `null_count`, `min` and `max` are wrong for any pandas or polars frame with more than 1M cells and more than 50,000 rows. A frame over 1M cells with 50,000 rows or fewer is a full shuffled copy and stays exact.

**Stats cost grows with the data and sometimes cannot finish interactively.** Three tallyman loads of 44-column xorq entries took 74.9 s (42.3M rows), 114.1 s (54.1M) and 215.1 s (78.0M, of which the batch aggregate was 162.5 s). On a 78M x 43 polars `scan_parquet` the scalars plus approximate distinct ran in 2.6 s and 4.9 GB, exact distinct in 4.4 s and 13.7 GB, and approximate distinct plus median, tails and histogram in 34.2 s and 18.3 GB. Eager polars holds about 6.7 GB at 10.8M x 43 and cannot hold 78M.

**A stat has no tier, cost or size field.** `StatFunc` has name, func, requires, provides, needs_raw, column_filter, quiet and default. Dropping a stat today means catching an error: a failed provider becomes `UpstreamError` for every dependent, and a provider removed from the list raises `DAGConfigError` at construction.

The destination for polars `/load` is an out-of-core `scan_parquet` backend. Its stats must be chosen by size, because it reads the whole file for any stat it runs.

## Decisions

### D1. Four ordered tiers

| Tier | Contents | Exact? |
|---|---|---|
| `schema` | dtype, `_type`, `is_*` flags, column names, row count where a probe is cheap | n/a |
| `scalar` | `length`, `null_count`, `non_null_count`, `nan_per`, `min`, `max`, `mean`, `std`, `empty_count` where it is one pass; computed on the whole frame the stats class receives | exact |
| `approx` | everything in `full`, each expensive stat replaced by its cheaper implementation: sampled `value_counts`, `mode`, `most_freq`, sampled median and quantiles, `approx_n_unique`, a histogram from sampled inputs | scalars exact, the rest approximate |
| `full` | today's exact stats | exact |

`scalar` is named after the xorq batch's scalar aggregates: one pass, no sort, hash or sample. `median`, `distinct_count` and `unique_count` return one value per column but sit above it. Stats with no safe approximation (`unique_count`, and the `unique` and `longtail` buckets of the categorical histogram, which come from `value_counts == 1` and which a sample inflates) are left out at `approx`.

The parked PRs use `TIERS = ("schema", "scalar", "full")` in the policy module, `STATS_TIERS = ("full", "schema")` on the dataflow and `UNIT_TIERS = ("scalar", "full")` for stat runs. None has `approx`.

### D2. Exact scalars never read the 50,000-row sample

`length`, `null_count`, `min` and `max` stay exact at every tier above `schema`, over the frame the stats class receives. The sample feeds only `approx` implementations and is seeded.

On pandas and polars `/load` that frame is already `pre_limit`-sampled (1,000,000 rows for `PdSampling` and the server samplers, 100,000 for base `Sampling`), so these stats are exact up to the `pre_limit` row count and describe the pre-limit sample above it. Removing `pre_limit` for polars was rejected with #1000. This changes numbers users see today (`length` stops reading 50,000), so it needs the maintainer's confirmation (decision 4).

### D3. A stat declares its tier, and may supply an approximate implementation

`StatFunc` gains `tier` and `approx`. The decorator validates both at decoration time.

```python
def value_counts_sampled(ser: SampledSeries) -> pd.Series: ...   # undecorated; @stat copies value_counts's provides onto it

@stat(tier="scalar")
def null_count(ser: RawSeries) -> int: ...

@stat(tier="full", approx=value_counts_sampled)
def value_counts(ser: RawSeries) -> pd.Series: ...
```

For a session at tier T:

1. If the stat's effective tier is at most T, run the exact implementation.
2. Otherwise, if T is `approx` or higher and the stat has an `approx` implementation, or it has no raw-marker parameter and every input that is not exact at T ran an approximate implementation, run it and record its keys in `approx_keys`. A derived stat that combines an exact `length` with a sampled `value_counts` takes the sample size, or it reports the wrong fraction. `approx=False` marks a stat that must not run on approximate inputs (`unique_count`, `unique_per`).
3. Otherwise omit it and record the key in `omitted_keys`.

No stat declares `approx`; it exists only as a session level. A stat that declares a lower tier than its inputs gets a DAG-build warning and takes the maximum. A stat with no declared tier is `full` if it takes a raw-data marker (`RawSeries`, `SampledSeries`, `RawDataFrame`, `XorqColumn`, `XorqExpr`, `XorqExecute`), otherwise the maximum of its providers' tiers. The default is therefore fail closed: an unclassified or runtime-added raw-data stat runs only at `full`. #808's default of `scalar` would let a runtime-added stat run at 78M rows (decision 2).

Multi-key stats split so tiers apply per key. `base_summary_stats` (about 70 to 73% of pipeline time on pandas and polars in the 1M x 43 runs) becomes `length`, `null_count`, `min`, `max` at `scalar` and `value_counts`, `mode` at `full`. `numeric_stats` becomes `mean`, `std` at `scalar` and `median` at `full`.

### D4. The filter lives at the start of `build_column_dag`, and omission is absence

Dropping a key is done by not computing it, never by catching an error. The filter sits at the start of `build_column_dag`, beside `column_filter`, after `build_typed_dag` has validated the full list. Filtering the list before `StatPipeline(...)` raises `DAGConfigError` for any dependent of a dropped stat. An omitted key is absent from the column dict, not `None`, `NaN`, `0` or a `default=`: `merge_column` lets a `None` or `NaN` in `summary_sd` overwrite a value from `init_sd` or `cleaned_sd`, and on the wire both become a parquet null that reads as a computed null.

xorq needs two more rules. `XorqStatPipeline.EXTERNAL_KEYS` pre-populates accumulator entries (`length`, `min`, `max`, `distinct_count`, `dtype`) that count as provided, so dropping their provider leaves dependents running on placeholders (with `min` and `max` dropped, `histogram` came back `[]` with no error). Omission removes the key from the accumulator and passes `build_column_dag` an external set without it. And both the batch pass and the per-column pass take the same filtered list, or a skipped batch stat reappears in the per-column pass as `DAGConfigError`.

### D5. One `StatsLimits` table, with a fixed configuration order

`StatsLimits` is the frozen dataclass of seven thresholds from #1023 (`full_auto_rows`, `full_auto_cells`, `scalar_auto_cells`, `ceiling_full_rows`, `ceiling_full_cells`, `ceiling_scalar_cells`, `polars_route_rows`), extended with a per-backend sub-table and `stat_tiers`. Cells are the main key, with row limits where memory matters, because xorq scalar is about 4.5x cheaper than full on parquet and about 18x on CSV, and rows alone cannot see a wide table.

Configuration order, lowest precedence first:

1. Library default, `StatsLimits()`.
2. Environment, `BUCKAROO_STATS_*`, read on every call.
3. Widget or dataflow class attribute `stats_limits`, and a `stats_tier` constructor argument.
4. Per-load request: `stats_tier` and `stats_limits` in the `/load` and `/load_expr` bodies.
5. Per-stat override: `StatsLimits.stat_tiers = {"distinct_count": "full"}`.

The later layer wins, except that `ceiling_*` is read only from layers 1 to 3: a request can lower a threshold or a tier and cannot raise a ceiling. A `stat_tiers` entry may raise a stat's tier freely and may lower it only to the tier its inputs reach, and never so that the stat runs past `ceiling_full_*`.

Starting values assume a 3 s stats budget on the reference machine (decision 1) and are replaced by the phase-0 measurements. Per backend:

| Backend | `full` up to | `scalar` up to |
|---|---|---|
| polars eager | 100M cells | the eager memory limit (about 8M rows) |
| polars `scan_parquet` | 100M cells | about 4B cells (0.78 ms per Mcell measured once) |
| xorq parquet | 520M cells and 12M rows (#1023) | 1.0B cells |
| xorq CSV | placeholder (about 52M cells at 3 s) | placeholder |
| pandas | today's 1M-cell gate, as a placeholder | placeholder |

`approx` is the same as `full` on xorq at first, because its distinct count and median are already approximate and its categorical histogram already samples. Ceilings start at #1023's values (1.0B cells for `full`, 4.0B for `scalar`, 25M rows for `full`), which are extrapolations.

### D6. The server resolves the policy after the schema-tier dataflow and the row count exist

`resolve_stats_policy(backend, source_kind, rows, cols, ...)` is a pure function returning `{tier_target, auto_request, requestable, reason, estimate}`. The ceiling is applied inside the function for every caller (load, `/reload_expr`, `stats_request {force}`), so the result is the lower of the requested tier and the ceiling tier, with `reason: "ceiling"`. A host can lower the tier freely and raise it only to the ceiling. The `stats_request` handler enforces `requestable`, the ceiling and the cost pause, so a client bug cannot run a forbidden tier.

With `stats_tier="auto"` (the default once enabled) the server decides from cheap signals: dtypes (about 0.2 ms), a parquet footer's `num_rows` (0.4 ms on 4M rows), xorq's cached `_expr_count`, and a host `row_count`. This protects hosts that send nothing, including the standalone server and the MCP tool. Pandas and polars `/load` resolve to `full` until the scan backend lands.

Delivery of the result is ADR-002's: a deferred session reports `not_computed` with the policy fields, and a client with the `stats_ondemand` capability bit (`?caps=stats_update,stats_ondemand`) gets the policy applied at connect. Other clients get complete stats synchronously.

### D7. The result reports what was left out or approximated

`df_meta.stats` carries `tier` (reached), `tier_target`, `reason` (`size`, `host`, `ceiling`, `cost`), `omitted_keys`, `approx_keys`, and from the policy `auto_request` (absent means true), `requestable` (absent means `["full"]`), `estimate` and `demand_columns`. Both key lists are sorted lists.

- `omitted_keys` is the union over columns of the provides of the column DAG after `column_filter` and cascade but before the tier filter, minus the provides of the tiered DAG, computed per scope with the scope's prefix. A text column without `mean` is not "omitted" because `column_filter` removed it.
- `approx_keys` is the keys produced by approximate implementations plus the keys of stats that require them (`most_freq` from sampled `value_counts`).
- They live on the stats object and in `df_meta.stats`, not in the per-column summary dict, and `df_meta.stats` is written where the stats run because `populate_df_meta` does not run when `analysis_klasses` changes.

Display, first version: the server prunes the pinned rows whose key is in `omitted_keys`, once, after `df_display_args` is assembled in `_handle_widget_change`, including rows that came from the `dataflow.pinned_rows` override. The client needs no change and no empty pinned row appears. A client label ("not computed at this size", a marker on approximate values) needs a `buckaroo-js-core` release and waits (decision 3). Marking omittable pins with a `?` prefix on `primary_key_val`, which makes `extractPinnedRows` skip the row, is the client-side alternative that also needs no release.

### D8. On-demand compute, cost pause and demand columns

The summary view with no stats shows "Stats: not computed (12.4M rows). Compute". The control sends `stats_request {tier, force: true}`, with a `columns` form per column. A request over the ceiling is answered `stats_update {final: true, status: "not_computed", reason: "ceiling"}` without running. `force` sets a session override that survives a dataflow-field change for the unfiltered scope only.

When an automatic unit exceeds the budget, the server records `cost_paused` on the session and answers the next request with `reason: "cost"`; the client offers "Continue", which sends `force`. The pause is held on the session so it survives a `stats_gen` bump and `/reload_expr`, which a client-side budget would not.

Demand columns: after the schema-tier dataflow builds `column_config`, the server scans each `color_map_config` with `color_rule == "color_map"` and collects its `val_column`; those columns need `min` and `max`. The scan covers rules in the overrides and rules that klasses add at style time. It runs no query at load: it becomes an automatic scoped `stats_request` under the same policy, ceiling and cost pause.

### D9. Sort and search get guards on huge sources

Skipping stats does not make windows cheap. On xorq at 10.8M rows a window takes 15 to 26 ms, a sort 210 to 384 ms and a search 504 to 1063 ms, with a fresh `count()` per searched request because the filtered expression misses `_expr_count`'s cache. Above a threshold separate from the stats ones, `df_meta` carries `sort` and `search` flags, a final pass in `style_columns` sets `ag_grid_specs: {sortable: false}` so klasses and overrides cannot bypass it, and a sorted `infinite_request` is refused with `error_code: "sort_disabled"`. The filtered count is memoized on `(base expression identity, term)`.

### D10. The parquet footer is the bottom rung

For a parquet source the footer holds row count and, per column chunk, `null_count`, `min` and `max`. It costs no data, so it fills `length`, `null_count` and numeric `min` and `max` before any tier runs, and the scalar tier skips those columns. Row count and `null_count` were exact on all four writers probed (pyarrow, polars, DuckDB, pandas). `min` and `max` are exact for integers, bool, date, timestamp and dictionary columns. Floats with NaN, strings over 256 bytes (DuckDB) or 4096 bytes (pyarrow) and nested columns break it, and polars itself reads only `len()` from the footer. Open and parse cost about 1 ms at 40 row groups and 45 ms at 10,000.

Rules, each stat reported as exact, approximate or omitted:

1. Answer only top-level flat columns, matching chunks by `path_in_schema`.
2. `length` is the sum of `num_rows` over files, unfiltered scope only.
3. Ignore row groups with `num_rows == 0`.
4. `null_count` is exact when every chunk has one. It is the parquet null count, so for pandas float columns (where `isna()` also counts NaN) it is valid only on the polars scan backend.
5. `min` and `max` for integers, floats, bool, date, time and timestamp are exact when every chunk with non-null rows has them. Decimals decode from `min_raw` with the logical scale.
6. A chunk without min and max is skipped only if its null count equals its `num_values`. Otherwise omit the column's min and max and let the next rung compute them. Never aggregate over only the chunks that have statistics.
7. Strings are approximate when an exactness flag is readable and false, and otherwise exact only for writers verified at pyarrow 21 (Polars, parquet-cpp-arrow).
8. NaN-bearing float chunks look like a missing statistic and are treated as unavailable.
9. Skip the rung when the estimated Python cost exceeds about 30 ms (0.09 ms per file plus 3.6 us per column chunk).
10. A column absent from a file contributes `num_rows` to `null_count` only with `missing_columns='insert'`; hive partition keys are never answered from footers; multi-file bounds are normalised to the dataset schema first.

### D11. Tier is part of every cache key, and only complete runs write the full cache

`_summary_sd_cache_key = (id(df), id(klasses))` and `_scope_cache_key` ignore tier today, so a lower-tier summary could be cached and served as complete. Tier and a hash of the limits join both. Only `full` runs write `summary_stats_cache`; scalar and column-scoped runs send fragments and assign nothing.

ADR-001's `stat_id = <key>@<hash>` must not let an approximate value of a stat share a cell with its exact value. The hash covers the approximate implementation's identity and the sample parameters (size, seed), and `stat_hashes` is computed over the DAG as resolved for the session. xorq on DataFusion cannot seed a sample, so xorq sampled histograms are reported as approximate and not cached as exact.

### D12. A stat added at runtime follows the same rules

A stat added at runtime follows D3: a raw-data stat runs only at `full` unless it declares `tier=`, so it cannot run by surprise on a large table. A host can promote one it trusts with `stat_tiers`. When a tier hides it, its key lands in `omitted_keys` and its pinned row is pruned with the others. The runtime-add path itself is broken on main for six widget families (`DataFlow.analysis_klasses` is a plain attribute, so the `_summary_sd` observer never fires after `add_analysis`), and fixing it ships as its own PR ahead of the tier work.

## Consequences

- The scalar fix changes visible numbers. Frames above 1M cells and 50,000 rows stop reporting `length` 50,000.
- Above the full limit `heuristic_fracs` and the cleaning stats do not run, so autoclean finds no `cleaning_ops` where today it runs on the 50,000-row sample (inferred from reading the code, not run).
- Time to a first summary improves for large entries and some pinned rows are blank or approximate. `approx` and `omitted` states need a way to tell the user, first by pruning, later by a client label.
- A new `StatFunc` field, a split of two shipped multi-key stats, and a filter in the DAG touch every stats backend, so the early phases ship with the default tier at `full` and change nothing until the table is wired.
- Thresholds are proposals. They rest on one machine (14 cores, 48 GB), one polars script that varied from 8.2 to 15.2 s between runs for an unknown reason, and extrapolations above 12M rows on parquet. Measurements come before the table is trusted.

## Alternatives considered

- **A per-stat row cutoff with no tier scale** (#1016, #1017, closed). It cannot express "run nothing" or on-demand, and xorq's batch includes `length`, so batch members cannot be gated without a pre-count.
- **A time budget as the first mechanism.** Results would depend on machine speed, and it needs a cost model that does not exist. A scheduler that runs stat groups cheapest first until a budget runs out can sit on top of tiers later; the 3 s figure here only sizes the table.
- **`@stat(cost=)` with `scalar` as the default** (#808, #809). The shape is adopted (a field validated at decoration, one filter at the loop points, a back-compatible default). The vocabulary is not: there `median`, `distinct_count` and `value_counts` are `scalar`.
- **Host decides, no server policy.** Nothing protects hosts that send nothing.
- **Adaptive client.** It cannot prevent the first expensive unit. Its useful part, the cost pause, is D8.

## Open decisions

1. **Stats budget.** 3 s on the reference machine; a per-load request can lower it, not exceed it (recommended).
2. **Default for an untagged or runtime-added stat.** Fail closed, `full` only (recommended), or fail open at `scalar`.
3. **Display of omitted and approximate keys.** Prune pinned rows on the server first (recommended), or label in the client.
4. **Exact scalars.** Accept that `length`, `null_count`, `min` and `max` become exact up to `pre_limit` (recommended), and accept the pandas scalar cost at 10M rows.
5. **Null convention for approximate distinct.** Polars `n_unique` counts null as a value and xorq `nunique` does not (24,895 against 24,894 on one column). No recommendation until the accuracy runs.
6. **`unique_count`.** Blank from `approx` upward (recommended), or dropped from the default pinned rows.
7. **Natively approximate xorq stats** (`distinct_count`, `median`): list them in `approx_keys` at every tier (recommended), or only when the tier forces the approximation.
8. **MCP and server route for adding stats.** A path plus reload with a startup token, an Origin and Host check and the endpoint off unless the host enables it (recommended), source over HTTP, or none.
9. **`histogram_bins`.** One definition across backends. Only the min and max arithmetic form is cheap at `scalar`, and on xorq it needs `distinct_count` dropped. No recommendation yet.
10. **Lazy executor.** Tier it with a class attribute now (recommended), or migrate it to `@stat` first.
11. **Cache identity for a notebook-defined stat.** Keep ADR-001's `marshal.dumps(code)` fallback, which misses in a new kernel and never hits wrongly (recommended), or skip caching such stats.
12. **Project directory convention for pandas and polars.** Subdirectories as in the closed #1010, matching xorq's `stats/` layout (recommended), or the marker of the closed #1008.
13. **Base of the work.** Build on main and lift `stats_policy.py` (#1023) and the scalar pipeline pieces (#1031) (recommended), or build on the rows-first branches. Under the first, #1019 and #1023 are closed rather than rebased once the table lands.

## Not decided here

- **The `scan_parquet` backend** (paging, search, sort, memory). This ADR covers its stats half.
- **When stats are delivered** (ADR-002).
- **A scheduler** that orders stat groups against a time budget.
