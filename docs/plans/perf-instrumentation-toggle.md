# Plan: toggleable perf instrumentation for the stats pipeline + first data pull

## Goal

A perf-logging layer we can flip **on for an investigation and off for normal
use**, covering the two places that actually hurt:

1. **The stats pipeline** — for all three backends (pandas, polars, xorq), not
   just xorq.
2. **The first data pull** — time-to-first-payload, both in-process (widget
   construction → first serialization) and over the server (`/load_expr` →
   first WebSocket parquet frame).

Default off ⇒ zero behavioral change and negligible overhead. On ⇒ structured,
greppable timing lines plus an end-of-run summary.

## Current state (what's already on `main`)

- `StatPipeline` (shared by pandas **and** polars via `DfStatsV2` /
  `PlDfStatsV2`) already has an opt-in `record_timings` flag that fills
  `pipe.timings` with `(column, stat_name, seconds)` tuples —
  `buckaroo/pluggable_analysis_framework/stat_pipeline.py:198,242-249,275`.
  Today this is **offline-only**: the sole consumer is
  `scripts/perf/perf_bench.py:35`. Nothing logs it, nothing toggles it at
  runtime, and it never runs in the live widget/server path.
- `XorqStatPipeline` has **no** timing instrumentation at all
  (`xorq_stat_pipeline.py`). Its two cost phases are the batch aggregate
  (one `table.aggregate(agg_exprs)`, ~lines 593-653) and the per-column
  post-batch stats / histogram re-scans (~lines 655-679). It already logs
  cache hit/miss/bytes via `_log_cache_stats()` (~363-373).
- Server first-data-pull path: `LoadExprHandler.post()`
  (`server/handlers.py:408-563`) → `XorqServerDataflow` construction (runs the
  stat pipeline) → first `DataStreamHandler` payload
  (`server/websocket_handler.py:192-240`) → `window_to_parquet()`
  (`xorq_buckaroo.py:257-299`). No latency instrumentation here today.
- Existing toggle convention: `_BUCKAROO_DEBUG =
  os.environ.get("BUCKAROO_DEBUG", "")...` (`handlers.py:21`,
  `websocket_handler.py:22`) — used only for error verbosity. Server logs to
  `~/.buckaroo/logs/server.log` (`server/__main__.py:122`).
- `scripts/perf/` bench harness and `docs/perf-testing-guide.md` already exist.

So this PR is **not** green-field: it promotes the existing offline
`record_timings` scaffolding into a runtime-toggleable logging layer and
extends the same idea to xorq and to the first-pull path.

## Design

### 1. One shared toggle + perf module

New `buckaroo/pluggable_analysis_framework/perf_log.py` (single source of truth,
imported by both the pure-python pipelines and the server):

- `PERF_ENABLED` — module-level bool from `BUCKAROO_PERF` env var, same parse as
  `_BUCKAROO_DEBUG` (`"1"/"true"`). Also flippable programmatically
  (`perf_log.enable()/disable()`) so notebook investigations and tests don't
  need env vars.
- A dedicated logger `buckaroo.perf` (INFO). Off by default, so even when other
  loggers are noisy this stays quiet unless enabled.
- `@contextmanager perf_span(label, **fields)` — when enabled, measures
  `time.perf_counter()` delta and logs one `key=value` line
  (`perf span=load_expr.total secs=0.214 rows=883000 backend=xorq ...`); when
  disabled, a no-op with a single bool check (cheap enough for hot-ish call
  sites, not for per-cell loops).
- `PerfRecorder` — accumulator the pipelines append `(phase, column, stat,
  secs)` rows to, with a `.summary()` that emits a top-N-slowest table and
  per-phase totals at end of a run. This is what makes the per-stat data
  actionable instead of a wall of lines.

Guard principle: the **per-stat** inner loops check a captured local bool (as
`StatPipeline` already does at `:242`), never re-read env or call the logger
when disabled.

### 2. Stats pipeline — uniform coverage across all three backends

**pandas + polars (`StatPipeline`)** — already has the `(col, stat, secs)`
capture. Changes:
- Default `record_timings` to `PERF_ENABLED` when not explicitly passed, so the
  live widget path records when the toggle is on (today it only records when a
  script asks).
- After `process_df`, route `self.timings` into the shared `PerfRecorder` and
  emit the summary via `buckaroo.perf` instead of leaving it in-memory only.
- Keep `pipe.timings` intact so `scripts/perf/perf_bench.py` keeps working.

**xorq (`XorqStatPipeline`)** — new instrumentation mirroring the same shape:
- Wrap **phase 1** (the single batch `table.aggregate`) in a `perf_span`
  (`stat.xorq.batch_aggregate`) — this is usually the dominant query.
- Wrap **phase 2** per-column post-batch execution, recording one row per
  `(column, stat)` so the histogram re-scan cost is visible per column.
- Time `_create_base_table` / materialization (`_maybe_materialize`,
  `_ensure_cache_materialization`) as its own span — the cold-cache
  materialization is a known first-pull cost (commits 19abae89, 43ffc92f).
- Fold the existing `_log_cache_stats` counters into the same summary so cache
  hit/miss sits next to the timings.

Net: the same `(phase, column, stat, secs)` schema for all three backends, one
summary format, so a polars run and an xorq run are read the same way.

### 3. First data pull — both in-process and server

**Server path** — `perf_span`s, all keyed by a per-request id so concurrent
loads don't interleave confusingly:
- `load_expr.total` around `LoadExprHandler.post()`.
- `load_expr.dataflow_construct` around `XorqServerDataflow(...)` (this is where
  the stat pipeline runs — nests the stats spans above).
- `load_expr.first_payload` around the first `window_to_parquet()` +
  WebSocket send in `DataStreamHandler`.

**In-process path** (makes it "generally applicable" to the pandas/polars
widgets, per the request) — a `perf_span` around widget construction →
first `_df_to_obj` / serialization for `BuckarooWidget`,
`PolarsBuckarooWidget`, and their infinite variants, so a plain
`BuckarooWidget(df)` in a notebook with `BUCKAROO_PERF=1` prints the same
breakdown the server emits.

### 4. Output / consumption

- Lines go to the `buckaroo.perf` logger. In the server they land in
  `~/.buckaroo/logs/server.log` (already configured); in a notebook they go to
  stderr once enabled.
- Structured `key=value` so they're greppable and so the **tallyman perf
  integration tests** can assert on `secs=` for a named span (the server is the
  integration surface — there are no `tallyman` refs in this repo, so the
  contract is "these log lines exist and are parseable").
- End-of-run `PerfRecorder.summary()` prints top-N slowest stats + per-phase
  totals.

## Files touched

- **new** `buckaroo/pluggable_analysis_framework/perf_log.py` — toggle, logger,
  `perf_span`, `PerfRecorder`.
- `buckaroo/pluggable_analysis_framework/stat_pipeline.py` — default
  `record_timings` to toggle, emit summary via recorder.
- `buckaroo/pluggable_analysis_framework/xorq_stat_pipeline.py` — new spans for
  batch aggregate, per-column phase, materialization; fold in cache stats.
- `buckaroo/xorq_buckaroo.py` — span around `window_to_parquet` and
  `_get_summary_sd`.
- `buckaroo/server/handlers.py`, `buckaroo/server/websocket_handler.py` —
  first-pull spans, reuse the `BUCKAROO_PERF` toggle.
- `buckaroo/buckaroo_widget.py` / polars widget — in-process first-pull span.
- `docs/perf-testing-guide.md` — document the runtime toggle + xorq coverage
  (today the guide only mentions the offline `record_timings`).

## Tests

Skipped for this PR — this is opt-in, default-off instrumentation with no
behavioral change. Verify by running with `BUCKAROO_PERF=1` and eyeballing the
emitted spans/summary. Keep `scripts/perf/perf_bench.py` working (don't break
`pipe.timings`).

## Open questions

1. ~~Toggle name / granularity~~ — **decided: single boolean `BUCKAROO_PERF=1`**
   turns on everything (stats spans for all backends + first-pull spans). Add
   levels later only if the output proves too noisy.
2. **Per-stat overhead when on** — for very wide frames the per-`(col,stat)`
   `perf_counter` pair is cheap but nonzero; acceptable since it's opt-in. Worth
   a note in the guide that headline numbers should be taken with the toggle
   *off*.
3. **Was a richer logging variant removed before?** The offline `record_timings`
   is the only surviving piece I found; if an earlier verbose-logging version
   existed and was reverted, worth grepping its branch before reimplementing so
   we match the prior shape.
