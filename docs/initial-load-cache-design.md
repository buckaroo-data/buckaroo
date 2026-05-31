# Initial-load cache — serve the first render without touching the data

## Status
Design only. Branch `feat/initial-load-cache`, PR #877. All decisions below were
locked in a design review (the grill). Follow-ups split out: #880 (trim the
summary-stats *wire* payload to what the frontend reads) and #881 (DFViewer
transport abstraction — JSON / b64-parquet / binary per embedding).

## Problem

Buckaroo's first render is expensive. For a xorq expression the cost is *executing
it*: a normal load reconstructs the expr once, then computes summary stats as **one
batched `expr.aggregate(...)` plus one histogram query per column** — ≈ N+1 executions
(`xorq_stat_pipeline.py:157`, the "N+1 filter evaluations" the code optimizes around)
— plus a window query and a row count. That work repeats on every session open even
when neither the data nor the configuration changed.

The driving consumer is xorq desktop / pydata-app, where an expression has a stable,
content-based identity. Such a host can hand Buckaroo a precomputed first-render
bundle and skip the pipeline — *provided the bundle provably matches the widget's
configuration*.

## Measured cost (pydata test-1 catalog, xorq 0.3.26, warm process)

| step | cost | calls |
|---|---|---|
| `load_expr` (build-dir reconstruction) | **~15–18 ms, flat** across 0.5–158 MB | once |
| summary stats (batched aggregate + per-column histograms) | tens of ms → **~85 ms** (158 MB) warm; more cold/wide | **≈ N+1** expr executions |
| first window (`limit` pushdown) + row `count` | ~4 ms warm | 2 |

So a cold first load ≈ `load(1) + (1+N) stat executions + window(2)`. The bundle
replaces all of that with a cache read, leaving only a one-time ~17 ms `load_expr` to
re-warm the expr for later scrolling. `load_expr` is *not* the cost — the per-column
stat executions are, and they scale with width.

## Three-layer cache

```
buckaroo initial-load bundle   ← NEW: hit = first paint with zero execution
   ↓ miss
xorq ParquetSnapshotCache      ← unchanged (cache_storage_path); per-stat-query snapshots
   ↓ miss
live expr execution
```

The existing `.buckaroo_stat_cache/parquet/letsql_cache-snapshot-*.parquet` files
(≈ columns+1 per entry) are the xorq snapshot layer. The new bundle sits above it: a
bundle hit never even reaches the snapshot cache.

## The handshake — validate, never blindly trust

The backend provides an **optional** bundle alongside the df/expr (which is held but
not executed):

```
widget computes its OWN config_id from its live analysis_klasses + config,
and reads its live schema (df.columns/dtypes, or get_expr_hash — no execution)
        │
   ┌────┴───────────────────────────────┐
   │ config_id + schema + version match  │ → hydrate from bundle; df/expr NEVER touched
   └────┬───────────────────────────────┘
        │ any mismatch
        ▼
   warnings.warn(reason) + cache:{status:"mismatch",reason} → normal pipeline (execute)
```

The widget computes `config_id` itself and compares — it never reads-and-trusts the
bundle's claim. A stale/foreign bundle costs a warning + a normal compute, never a
wrong render. For xorq the `get_expr_hash` match already implies the schema, so the
config_id (analysis klasses) check is the load-bearing one.

## Entry points

```python
# buckaroo/cache/initial_cache.py
def get_initial_cache_data(df_or_expr, *, analysis_klasses=None, styling_klasses=None,
    sampling_klass=None, init_sd=None, skip_stat_columns=None, window=1000,
    data_id=None, cache_version=None) -> tuple[str, InitialCacheData]:
    """Producer: run the pipeline ONCE, snapshot first window + stats + config."""

def cache_mismatch_reason(bundle, *, analysis_klasses, sampling_klass, init_sd,
    skip_stat_columns, schema) -> str | None:   # None ⇒ safe to use
def apply_initial_cache(target, bundle) -> None: # set df_data_dict/display_args/meta
```

The **consumer** is the server's `/load_expr` path running the handshake against its
in-memory store (below). The widget gets the same handshake (mechanism, not a driver).

## Keying & storage

- **xorq `data_id` = `get_expr_hash(expr)`** (`xorq/.../provenance_utils.py:18-25`):
  canonicalize → `SnapshotStrategy` tokenize → truncate. Content-based,
  path-independent; the build-dir basename already *is* this hash. Verified safe:
  `ExprLoader.load_expr` reads only named files (`compiler.py:663-684`) and never
  re-verifies a content hash (`:655-657`), so it's *technically* safe to write into a
  build dir — but we don't (build dirs are packageable + reproducibility-checked;
  keep them pristine).
- **Store: server-managed, keyed by `data_id`, OUTSIDE the build/catalog dir.**
  Persistent (survives restart), with an **in-memory LRU** over it. Lazy-on-miss
  populates it; `prewarm(dir)` loads it eagerly at startup.
- **pandas/polars:** the host supplies `data_id` (path+mtime+size, or a content hash).
  Buckaroo never fingerprints a frame itself.

## config_id — the handshake key

Stable cross-process fingerprint (`module.qualname`, not `id()`), over the
data-touching computation only:

| In the key | Out (replay-time display; regenerated from the bundle) |
|---|---|
| `analysis_klasses` (ordered) | `column_config_overrides` |
| `sampling_klass` params | `component_config` |
| `init_sd`, `skip_stat_columns` | `extra_grid_config`, `pinned_rows` |
| `INITIAL_CACHE_VERSION` (+ optional `cache_version`) | `styling_klasses` |

Re-theming or overriding a column never invalidates the cache.

## The bundle — `InitialCacheData`

Persisted as parquet (binary) + a JSON manifest. No b64 on disk.

```python
{
  'cache_format_version': int, 'config_id': str, 'data_id': str | None,
  'df_meta': dict,                       # columns, rows_shown, total_rows, filtered_rows
  'column_schema': {'columns': [...], 'index': {...}, 'dtypes': [...]},
  'sd_parquet': '<file>',                # merged_sd MINUS value_counts, lossless type-tagged
  'first_window_parquet': '<file>',      # to_parquet(rows[0:window]) — window IS cached, not stats-only
  'first_window': {'start': 0, 'end': int, 'total_rows': int},
  'df_display_args': dict,               # prerender for the zero-override common case
  'buckaroo_options': dict, 'command_config': dict,
  'styling_klasses': [str, ...],
}
```

The `all_stats` wire payload is derived from `sd_parquet` at serve time (matching
today's `parquet_b64` in `initial_state` — server delivery unchanged; #880 trims it).

### Stats codec (no pickle, cross-backend)

`value_counts` is **dropped** — nothing at replay recomputes from it (and it's the
`pd.Series` that made round-tripping hard). The remaining values round-trip via a
**type-tagged** cell codec extending the lossy `sd_to_parquet_b64` encoder
(`serialization_utils.py:361-394`), tagging the non-JSON-native types so they
reconstruct exactly. The type surface differs per backend, so the round-trip is
**tested across pandas/polars/xorq**:

| type | pandas | polars | xorq |
|---|---|---|---|
| `pd.Timestamp`/`pd.Timedelta` | ✓ | — | — |
| stdlib `datetime`/`date`/`time`/`timedelta` | — | ✓ (`pl_stats_v2.py:86,91,92`) | via `_to_python_scalar` |
| `Decimal`, `bytes` | — | ✓ | — |
| `np.datetime64` | mode→Timestamp | — | →`datetime.date` |

## Styling stays configurable

`get_dfviewer_config(sd, df)` reads only the summary dict + column/index *structure*,
never a row value (`styling_core.py:422-473`, `customizations/styling.py:70-142`). So
a **zero-row DataFrame** rebuilt from `column_schema` regenerates `df_display_args`
exactly — feeding `merge_column_config` (`styling_core.py:231-254`) the same
`old_col_new_col` mapping. With no display knobs passed, the prerendered
`df_display_args` is used directly; with knobs, regenerate — frame never built either
way. Refactor: lift the assembly loop (`dataflow.py:705-723`) into a module-level
`build_df_display_args(...)` shared by the live path and the cache path.

## Serving & the warm path

- `/load_expr` (default-on): `load_expr` (cheap) → compute `data_id` → store lookup.
  **Hit** (handshake passes) → serve cached first paint, no stats, no window
  execution. **Miss** → full compute + store.
- After a hit: write the cached response, then `IOLoop.current().add_callback(warm)` —
  `warm` is the **cheap `load_expr` + wire `(expr, cached merged_sd)`** onto the
  session (~17 ms, synchronous, no `async def`, respects the no-async constraint). The
  first scroll is then a ~4 ms window pushdown; the N+1 stat queries never re-run.
- `serve_window` predicate: `start==0 ∧ end≤window ∧ no sort ∧ no search`; anything
  else falls through to the live `handle_infinite_request_xorq` pushdown.

## Observability & metadata

- **Correlation id:** the POST carries `request_id`; buckaroo echoes it and stamps it
  on every log line for that load. `/load_expr` returns `cache: {status, reason}`
  (`hit|miss|mismatch`). Lets the host align its logs with buckaroo's.
- **`/cache` endpoint:** cache introspection — `[{expr_hash, data_id, bytes,
  last_used, hits}]`, totals, LRU capacity, hit/miss rate. Broader session/server
  enumeration is #860.

## Integration — additive

- **Server:** `/load_expr` (+ `/load`) accept an `initial_cache` flag — **default ON
  for `/load_expr`**, a POST field (`initial_cache: false`) turns it off (full compute,
  skip store). `/load` (pandas/polars) is default-off unless the host passes a
  `data_id`. Server-managed store (LRU) + `prewarm(dir)` + `/cache` endpoint +
  correlation-id logging. Session already retains `build_dir` (`session.py:18-36`) for
  the unexecuted-fallback.
- **Widget (Jupyter):** `initial_cache=` kwarg + handshake + `apply_initial_cache` in
  the shared `BuckarooWidgetBase.__init__` (`buckaroo_widget.py:125`) — the *same* code
  path as the server, so parity is guaranteed. **No Jupyter store / driver / prewarm
  built now** (per scope).

## Scope

In: `buckaroo/cache/` (producer, handshake, `apply_initial_cache`, type-tagged SD
codec, `config_fingerprint`); `build_df_display_args` refactor; server store + LRU +
`prewarm` + `/cache` + `/load_expr` default-on integration + correlation-id; widget
`initial_cache` mechanism; tests.

Out: trimming the stats *wire* payload (#880); transport abstraction / binary stats on
the server (#881); a Jupyter store/driver; pandas/polars auto-fingerprinting; caching
past the first window (sort/filter/scroll/ops stay on the source); writing sidecars
into build dirs; live-source staleness detection (delegated to xorq — see risks).

## Files

1. `buckaroo/cache/{__init__,initial_cache,fingerprint}.py` *(new)* — producer,
   handshake, `apply_initial_cache`, `config_fingerprint` (uses `get_expr_hash` for
   xorq `data_id`), `INITIAL_CACHE_VERSION`.
2. `buckaroo/cache/store.py` *(new)* — server-managed `{data_id: bundle}` LRU store,
   disk persistence, `prewarm(dir)`.
3. `buckaroo/serialization_utils.py` — type-tagged lossless SD↔parquet codec (drops
   `value_counts`).
4. `buckaroo/dataflow/dataflow.py` — extract `build_df_display_args`; pure refactor.
5. `buckaroo/buckaroo_widget.py` — `initial_cache` kwarg + handshake.
6. `buckaroo/server/{handlers,app,session,websocket_handler}.py`, `data_loading.py` —
   `/load_expr` default-on + opt-out, store wiring, `serve_window` fast path, `/cache`
   endpoint, correlation-id.
7. `tests/unit/cache/` + `tests/unit/test_sd_codec.py` *(new)*.

## Implementation order (TDD — failing tests, then fix)

1. **Refactor.** Extract `build_df_display_args`; existing suite stays green. Own commit.
2. **Failing tests** (one commit):
   - `config_fingerprint` stable cross-process; differs when an analysis class changes.
   - **SD codec cross-backend round-trip** (temporal/`Decimal`/`bytes`/histogram via
     pandas/polars/xorq; `value_counts` absent).
   - `get_initial_cache_data` → bundle whose `initial_state` / `df_display_args` /
     first-window parquet equal a live `XorqServerDataflow`'s, **with the expr raising
     on execution** (prove the hit path + `serve_window({0,1000})` never execute it).
   - **handshake mismatch:** wrong `analysis_klasses` (config_id) or schema ⇒
     `warnings.warn` + `cache.status=="mismatch"` + a normal compute (expr *is*
     executed). Assert both.
   - **replay-override parity:** capture with no overrides, replay with non-trivial
     `component_config` + `column_config_overrides`; `df_display_args` byte-equal to a
     live dataflow with the same knobs, frame untouched.
   - `serve_window` returns `None` for sort / search / `start>0` / `end>window`.
   - server `/load_expr` default-on: first call (miss) executes + stores; second call
     (hit) serves without executing; `initial_cache:false` always executes.
   - `prewarm(dir)` loads bundles; `/cache` reports them.
   Push, watch CI fail.
3. **Fix.** Cache module + store + codec + refactor wiring + widget kwarg + server
   integration. Push, watch green.

## Open questions / risks

- **Live-source staleness.** `get_expr_hash` is *structural* — an expr over a mutable
  source can keep its hash while the data changes. v1 scopes the cache to pinned/built
  exprs (the catalog model). For live sources, detection is delegated to xorq's cache
  invalidation when the real expr is next touched (error if invalid). Dependency: I'll
  confirm `ParquetSnapshotCache`/`SnapshotStrategy` exposes that signal when building
  the scroll/miss path — not a v1 first-paint blocker (the hit path never executes).
- **Eager vs deferred stat execution.** Instrumenting `XorqStatPipeline._execute`
  showed 0 calls for some no-`cache_storage` constructs, i.e. the stat queries
  defer/short-circuit on that path. The N+1 cost model (from the code + snapshot-file
  count) is authoritative; the precise eager/deferred timing can be pinned by
  instrumenting `process_table` if a number is needed.
- **Non-deterministic sampling** (`data_loading.py:28-38`, unseeded `df.sample` for
  >1M-row frames) — we snapshot one realization; consider a seed.
- **MultiIndex** — the zero-row df must reproduce the exact `old_col_new_col` mapping;
  test with a MultiIndex fixture.
