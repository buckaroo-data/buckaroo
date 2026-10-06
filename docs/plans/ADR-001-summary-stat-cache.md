# ADR: A summary-stat cache keyed by data identity and per-stat hashes

- **Status:** Approved (2026-10-06). The design was settled in a review session on 2026-10-05. D8 is implemented in the same PR as this ADR (#1040, which absorbed #1041). The cache (D1–D7, D9–D12) is #1042.
- **Affected code:** `buckaroo/pluggable_analysis_framework/xorq_stat_pipeline.py` (`_execute_cached`, `_process_table_impl`), `buckaroo/customizations/xorq_stats_v2.py`, `buckaroo/pluggable_analysis_framework/stat_func.py` and `stat_pipeline.py` (type marker, dependency checks), `buckaroo/server/handlers.py` (`data_id` on `/load_expr`), `buckaroo/server/xorq_loading.py`. In tallyman, `src/tallyman_companion/buckaroo_lifecycle.py`.
- **Related tickets:** #1037 (warm re-POST with equal config re-runs the pipeline), #1038 (stats run on the IOLoop), #1039 (wire layout for `all_stats`), #943, #944 and #951 (cache telemetry), buckaroo-data/tallyman#177 (stat-cache wipe on every klass reload).

## Terms

- **data_id**: the identity of the rows a load reads, before any buckaroo-side transform.
- **scope_id**: the identity of the rows the stats actually run over, i.e. `data_id` plus the post-processing step.
- **stat_hash**: the identity of one stat's implementation.
- **cell**: one `(column, stat)` value.
- **part**: one parquet file of cells written by one fill.
- **data-touching stat**: a stat that issues a query. Either it has an `XorqColumn` parameter and is folded into the batch aggregate, or it has `XorqExpr`/`XorqExecute` parameters and runs its own query (histograms).
- **computed stat**: a stat derived only from other stats (`non_null_count`, `nan_per`, `distinct_per`, `histogram_bins`, `typing_stats`, `_type`).

## Problem

We want three properties from the summary-stat cache:

1. **Additive.** If a column already has 30 stats cached and a 31st stat is added, only the 31st is computed.
2. **Column-bisectable.** Stats for 10 of 25 columns can be computed, then the next 10, then the last 5, with each step computing only its own columns.
3. **Fast.** A warm load reads its stats from disk in a few milliseconds. Today it takes about 500ms.

### How it works today

`/load_expr` returns early, in about 2ms, when the session id, `build_dir` and `cache_dir` match a loaded session and the body carries none of the config fields listed at `handlers.py:442`. Tallyman adds `column_config_overrides` to the body whenever an entry has a saved display config (`buckaroo_lifecycle.py:505`). For those entries every open runs `load_expr_build_dir`, then the whole `XorqServerDataflow` traitlet cascade, then `XorqStatPipeline.process_table`, then metadata. #1037 covers that part.

The stat cache works per query. `_execute_cached` (`xorq_stat_pipeline.py:180`) calls xorq's `ParquetSnapshotCache.calc_key(query)`. When `letsql_cache-snapshot-<key>.parquet` exists, it reads the file with `pd.read_parquet`. A 27-column entry issues 28 queries:

- One batch `table.aggregate(...)`. It folds every `XorqColumn` stat for every column into a single query (`xorq_stat_pipeline.py:405`). On the NFL entry that is 115 expressions.
- One histogram query per column.

Because the key is a hash of the query, adding stat #31 changes the batch query's key, and all 115 scalar stats recompute. Computing 10 more columns does the same. Histograms happen to be per column, but an edit to the histogram code changes every histogram key.

The polars side has the same problems in a different form. `PAFColumnExecutor.get_execution_args` (`buckaroo/file_cache/paf_column_executor.py:59`) checks stat key names, not implementations, so editing a stat's code leaves stale results in place. When a column is missing any expected key, it re-runs every analysis class for that column. And if no class declares `provides_defaults`, any column with any cached stats counts as complete.

## Investigation

All numbers below are from the tallyman NFL contracts entry (52,814 rows, 27 columns, 28 snapshot files, every one a hit). They were measured on main (bf3edd8e) with xorq 0.3.25, polars 1.35.2, pyarrow 21.0.0 and pandas 2.2.3, on macOS. The probe scripts lived in a session scratchpad and are not committed.

### Where a warm load spends its time

A fresh server process with all 28 snapshots hitting took 410–690ms over four runs, counting `expr_load` plus the dataflow.

| piece | fresh process | warm process |
|---|---|---|
| `calc_key` × 28 (dask-tokenizes each query graph under `SnapshotStrategy`) | 198–220ms (7.1–7.9ms each) | 107ms (3.8ms each) |
| `stat.xorq.batch_aggregate` span: building 115 expressions, key, read | 108ms | 28ms |
| per-column phase (27 histograms: build query, key, read) | 330ms | 205ms |
| `pd.read_parquet` × 28 (part of the two rows above) | 44–90ms | 21–24ms |
| `load_expr_build_dir` (yaml → expression) | 50–100ms | 36–41ms |
| `count()` for metadata | 5–11ms (once 109ms, see open questions) | 4–5ms |
| `_merged_sd`, styling and `sd_to_parquet_b64` | ~12ms | ~12ms |

A reload in the same process with config in the body takes 250–290ms.

Most of the cost is identity work. On every load, the source expression's identity is re-derived 28 times, inside 28 different query graphs, and roughly 140 ibis expressions are built only so they can be hashed. Hashing the source expression once takes 1.3–4ms. Reading the same 28 files with `pq.read_table` takes 12.7ms in total, against 44–90ms with pandas.

The tallyman cache written on 2026-10-02 missed 28 of 28 against current main. Once a fresh run rewrote the snapshots, later fresh processes hit all 28. So keys are stable across processes, but something between those two dates changed every key. It is either stat code changes or the xorq version (the build recorded 0.3.26; the probe venv had 0.3.25). This was not isolated.

### Storage formats

The test data is the real NFL SD (582 cells) plus synthetic widenings at 31 stats per column, written and read with polars and pyarrow.

**Long format with JSON values**, `(col, stat, value_json)`:

| | 27 cols | 1000 cols |
|---|---|---|
| write | 0.5ms | 2.9ms |
| read | 0.4ms | 0.9ms |
| decode to SD dict (`json.loads` per cell) | 0.6ms | 32ms |

It's fast, but every value goes through JSON, which loses types.

**One row, one parquet column per cell** (the shape `sd_to_parquet_b64` uses on the wire):

| | parquet cols | size | write | read → SD |
|---|---|---|---|---|
| 27 cols | 609 | 181 KiB | 15ms | 3.0ms |
| 100 cols | 3,200 | 955 KiB | 75ms | 14ms |
| 1000 cols | 32,000 | 9.6 MiB | 748ms | 150ms |

Parquet charges per column (chunk headers, footer metadata, statistics), so this layout pays that cost once per cell.

**Variant layout**: one row per dataframe column, and one parquet column per `(stat, value type)`, where the type is chosen from each value:

| | parquet cols | size | write | read → SD |
|---|---|---|---|---|
| 27 cols | 33 | 27 KiB | 1.3ms | 1.05ms |
| 100 cols | 44 | 40 KiB | 3.0ms | 1.75ms |
| 1000 cols | 44 | 125 KiB | 34ms | 10ms |

Both typed layouts round-trip all 582 NFL cells exactly. Ints stay ints, and categorical and numeric histogram shapes are preserved.

A simpler typed-wide layout, with one parquet column per stat and the type inferred over all of that stat's values, fails the round trip. `pa.array` promotes ints to double when any value in the column is a float. It also merges `{name, population}` and `{name, cat_pop}` histogram bins into a single `struct<cat_pop, name, population>`, so every categorical bin comes back with `population: None`. That happened to 27 of 27 histograms.

**Append-only parts**: a read of three typed-wide parts (two column halves and one part adding a new stat), followed by `pl.concat(how="diagonal_relaxed")` and a per-column coalesce, took 2.7ms at 27 columns and 4.0ms at 1000.

## Decisions

### D1. A cell's key separates data identity from stat identity

A cell is keyed by `(scope_id, col, stat_hash)`. Each stat has its own hash. A hash over the whole list of analysis classes would change whenever a class was added, which brings back the batch-aggregate problem. The class list decides which cells are required, and each class's hash keys its own cells. With this key, every cell's key is known before any ibis expression is built.

### D2. `data_id` comes from the caller, with a fallback derived from the build

`/load_expr` takes an optional `data_id`. Without one, buckaroo uses `calc_key(source_expr)`, computed once per load, which costs 1.3–4ms and keeps today's invalidation semantics.

Tallyman sends the digest of the entry's current snapshot: `unfaithful_heal_digest` when set ("the content digest of the file the last unfaithful heal wrote", `tallyman_core/manifest.py:82`), else `result_digest`, else `content_hash` for entries with no digest. `content_hash` alone isn't enough: it's a hash of the recipe. An entry that isn't reproducible can re-materialize different rows under the same `content_hash`, which is the unfaithful-heal case. xorq's snapshot key has the same blind spot, since `snapshot_normalize_read` (`xorq/caching/strategy.py:39`) normalizes a Read by path identity only. A digest-based `data_id` changes when the rows change.

### D3. `scope_id` covers post-processing; filtered scopes are not persisted

`scope_id = hash(data_id, post_processing_hash)`, where `post_processing_hash` follows the same rule as `stat_hash` (D4) and is empty for the untransformed view. Post-processing views are a small set that users switch between, so persisting them keeps switches fast after a restart.

Scopes filtered through `quick_command_args` are not persisted. Every filter value makes a new op chain, and those entries would rarely hit again. They stay in the in-process `summary_stats_cache` (`buckaroo/dataflow/sd_cache.py`). Live search in the server filters row windows only and never runs stats (`xorq_loading.py:576`), so it doesn't come up here.

### D4. `stat_hash` is derived automatically

- Built-in stats hash the source of their defining module plus the xorq and xorq_datafusion versions. Function source alone isn't enough: `histogram` calls module-level helpers (`_numeric_histogram`, `_categorical_histogram`) and reads module constants (`CATEGORICAL_HISTOGRAM_SAMPLE_ROWS`). The engine versions are included because `approx_median` and `approx_nunique` belong to the engine.
- Project stats (one per `stats/*.py` file) hash the file content, which `_compile_project_stat` already reads.
- Each stat folds in the hashes of the stats it depends on, a Merkle hash over the typed DAG. Editing `min` invalidates `histogram` and leaves `null_count` alone.

Nothing has to be bumped by hand. A dev edit invalidates the stats in the edited module and the stats that depend on them. Editing a project stat invalidates only that stat.

### D5. Only data-touching stats are persisted

Computed stats recompute from cached inputs on every load. That takes microseconds, and they need no stored hash.

### D6. Storage is append-only parquet parts inside the directory tallyman already wipes

Parts live at `<cache_storage_path>/parquet/v1/<scope_id>/part-<ulid>.parquet`. Each fill writes one new part through a temp file and a rename. A load reads every part of its scope with one glob.

Compaction runs on write once a scope has more than 8 parts. It merges them, keeps the newest row per `(col, stat_hash)`, and drops hashes the current DAG no longer references. Two processes compacting the same scope at once can delete each other's input; the lost cells are recomputed on the next load, which is acceptable for a cache.

The `parquet/` prefix means tallyman's existing wipes still clear the new layout: `_clear_stat_cache` (`buckaroo_lifecycle.py:396`) removes `parquet/` on a klass reload, and `_verify_self_heal` (`tallyman_xorq/result_cache.py:466`) removes the whole `.buckaroo_stat_cache` after an unfaithful heal. A tallyman that hasn't upgraded stays correct. Existing `letsql_cache-snapshot-*.parquet` files are left in place and never read.

SQLite was the alternative: upserts with no compaction, and `SQLiteFileCache` as a precedent in the repo. Parquet won because you can inspect it with `pl.read_parquet`, and because writes that always create a new file can't lose each other's data. The compaction code is the cost.

### D7. Layout: one row per dataframe column, one parquet column per (stat, value type)

A part has a `col` column, a `__computed` column (the list of stat ids computed for that row), and one column per `(stat, value type)`. Variant names come from the value's own type, e.g. `min@<hash>#int`, `min@<hash>#float`, `histogram@<hash>#list:name,population`, `histogram@<hash>#list:cat_pop,name`. Each row has at most one non-null variant per stat.

Values are stored as native parquet types, including `list<struct>` for histograms, with no JSON inside parquet. The type is chosen per value, not per stat, for the reasons under "Storage formats". `__computed` tells "computed, and the value is `None`" (e.g. `distinct_count` on float columns) apart from "never computed". After a diagonal concat, those two would otherwise look the same.

The number of parquet columns is roughly the number of stats times the value types per stat, however wide the dataframe is.

### D8. Value-preserving stats keep the column's type (separate PR, first)

Today `min` and `max` are declared `-> float` and cast to `float64` (`xorq_stats_v2.py:160–167`). An int32 column's min comes back as `0.0`. The typed DAG assigns one Python type per stat key and checks dependents with `isinstance` (`stat_pipeline.py:114`).

This PR adds a return-type marker, `ColumnValue`, meaning "same type as the column". The boundary type check skips it. The xorq `min` and `max` use it and drop the cast. The xorq stats have no `mode` or `most_freq`; on the pandas side, `mode`, `min`, `max` and `most_freq`…`5th_freq` move from `Any` to `ColumnValue`, with no change in behavior. `mean` and `std` stay float. `median` also stays float, because an even count gives a non-integer median and `approx_median` is approximate anyway. The dependents (`histogram`, `histogram_bins`) declare `min: ColumnValue` and `max: ColumnValue` and convert to float for the bucket math. Declaring `int | float` instead would reject any other numeric type a column's min can have.

It ships ahead of the cache so that the cache's round-trip tests can assert that an int column's `min` comes back as an int.

### D9. The load algorithm builds nothing on a full hit

1. Compute `scope_id` and the `stat_hash` of every data-touching stat that is required. Read all parts and coalesce them.
2. The missing set is the required `(col, stat_hash)` cells minus the cells already present.
3. For missing batch stats, build one aggregate restricted to the missing stats on the missing columns. For missing per-column stats, run only those queries. Write one part.
4. Run computed stats.

A full hit builds no ibis expressions and runs no queries. Metadata rows come from the cached `length` instead of `count()`.

### D10. Column bisect is a capability, with no driver yet

The pipeline takes `stat_columns`, which restricts which columns get computed. Nothing decides on the next batch yet. A server-driven progressive load would run stats in the background and needs #1038 first.

### D11. Batch failures are isolated, and errors are cached only when the stat is at fault

Today, if one batch expression fails during execution, every batched stat for every column fails with it (`xorq_stat_pipeline.py:410`), and every load retries the whole batch. Under D9 those cells would stay missing forever.

On a batch failure, each stat is retried as its own aggregate over the missing columns. Successes are cached. A stat's error is cached under `(scope_id, col, stat_hash)` only when that stat failed while other stats in the same run succeeded, which shows the backend was up. The error clears when the stat's code changes, because its `stat_hash` changes. Failures that look environmental (everything failing, timeouts, out of memory) aren't cached.

### D12. Telemetry keeps its field names

`cache_status`, `cache_hits`, `cache_misses` and the other `cache_*` attrs keep their names, and `status` keeps its values (`hit`, `miss`, `mixed`). The unit changes from queries to cells. New fields: `cache_parts_read`, `cache_parts_written`, `cache_errors_cached`. Tallyman's only consumer, `LogPage.tsx`, renders these attrs generically.

### D13. Scope: the xorq server path, in a format the polars path can adopt

This work covers the xorq server only. The key leaves room for a per-column data identity, so that the polars `ColumnExecutor` path, which keys on `series_hash`, can move to this format later. That move would also fix its two gaps described under "Problem".

## Out of scope

- The wire format for `all_stats`. It stays `sd_to_parquet_b64` (5ms at 27 columns). The variant layout on the wire is #1039; it only matters for wide frames.
- `load_expr_build_dir`, which takes 40–100ms. Deferring it would move the wait to the first row window rather than remove it, and speeding it up is xorq work.
- The warm re-POST with an equal config (#1037).
- A driver for progressive column bisect (D10, after #1038).
- Persisting filtered scopes (D3).

## Delivery

1. **PR 1, type system (D8).** The tests asserting that `min`/`max` of an int column are ints go in a separate commit, run on CI and fail there, before the fix lands. Opened as #1041 and merged into this ADR's PR (#1040).
2. **PR 2, the cache (D1–D7, D9–D12).** The failing structural tests land first, as one commit. Then the implementation.
3. **PR 3, tallyman.** Send `data_id`. Drop the wipe on klass reload (`_clear_stat_cache`, called from `reload_project_sessions`), which closes tallyman#177. Keep the wipe in `_verify_self_heal`: a heal changes `data_id`, so every cell misses anyway, and the wipe removes the scope directory nothing will read again. Pin the buckaroo release that contains PR 2.

Until PR 3 lands, tallyman's klass-reload wipe deletes every cached stat whenever a project stat is added. For tallyman users, additivity arrives with PR 3.

## Testing

Unit tests in `tests/unit/` assert structure, not wall-clock time. Runner speed varies, and #982 already had to loosen a timing threshold.

- A full hit calls zero `XorqColumn` stat functions and runs zero backend queries. Today both fail: a full hit builds about 140 expressions in order to hash them, and metadata runs `count()`.
- After a stat is added, only that stat's expressions are built, inside one aggregate.
- Going from 10 to 20 to 25 columns, each step's queries touch only the new columns, and each step writes one part.
- Editing a module (simulated by changing its hash) invalidates that module's stats and their dependents and nothing else.
- A changed `data_id` misses everything. A changed `post_processing` misses only its own scope.
- A poison stat is isolated, its error is cached, and the next load doesn't retry it. When everything fails, nothing is cached.
- Round trip: int min stays int (after PR 1), histogram shapes are preserved, and a `None` value stays distinct from a cell that was never computed.

A bench in `scripts/perf/`, next to `perf_xorq.py`, reports cold, warm-process and fresh-process numbers on an entry shaped like NFL without asserting on them. The PR 2 description quotes before and after.

## Alternatives considered

- **Keep query-level keys and make `calc_key` cheaper**, by memoizing or by tokenizing only the source. The batch aggregate would still put every stat for every column under one key, so this is neither additive nor bisectable.
- **One hash over the whole class list.** Adding any class invalidates everything (D1).
- **Long format with JSON values.** Fast, but lossy for dates, decimals and timedeltas, and decoding is 3–4× slower at 1000 columns.
- **One row with a column per cell.** 11–25× slower to write and 3–15× slower to read than the variant layout. 9.6 MiB at 1000 columns.
- **One file per `(scope, stat)`.** Additive by stat, but a column bisect has to rewrite the file, and reading many small files brings back the per-file overhead (12.7–90ms for 28 files).
- **SQLite** (D6).
- **Version stats with the buckaroo release number, or with explicit `@stat(version=N)`.** The first recomputes everything on every release and serves stale results in dev. The second relies on people remembering to bump the version (D4).
- **Never cache errors, or cache every error.** The first leaves an entry with one broken project stat on the slow path forever. The second would treat a transient outage as a permanent stat failure (D11).

## Consequences

- A full-hit load costs about 2ms for keys (0 when `data_id` is supplied), about 1–3ms to read and coalesce, about 1ms to decode, and about 12ms for styling and wire. That's against 230–450ms of stats work today. `expr_load` is unchanged.
- Adding a stat computes only that stat's cells. Adding columns computes only those columns.
- PR 1 recomputes the xorq built-ins once, because `xorq_stats_v2.py` changes. That's expected.
- Cache telemetry now counts cells rather than queries.
- Cache directories hold old snapshot files, and scope directories orphaned by a changed `data_id` or post-processing klass, until tallyman wipes them. Buckaroo does no cross-scope garbage collection.
- A cached categorical histogram keeps whichever sample the first run drew, as it does today, since the DataFusion backend doesn't support `seed`.

## Open questions

- In one of five fresh processes, the first DataFusion query took about 110ms against about 10ms; it was always the first process in a batch. The suspicion is page-cache residency of the DataFusion native library. Running `sudo purge` and then re-timing would settle it. With D9 in place, a full hit runs no query, so this only affects misses.
- Why the 2026-10-02 cache missed 28 of 28 (stat code or xorq version). It doesn't change the design, but it would say how often a version bump will invalidate tallyman caches under D4.
