# Buckaroo perf-testing guide (for agents)

How to redo a performance pass on the buckaroo widget pipeline. Aimed
at a future Claude (or human) starting cold. Don't trust *previous*
findings — re-measure, then compare.

## Workflow at a glance

1. **Synthetic bench** — fixed shape, controllable knobs, cheap to
   re-run while iterating on a fix.
2. **Real-CSV bench** — same harness, real data shapes (high cardinality,
   long text, mixed types) to confirm the synthetic story.
3. **Black-box widget timing** — instantiate the public widget classes
   end-to-end, including the infinite variants and a 200-row data pull.
4. **cProfile** — *only* once you know which widget+dataset combo is
   slow. Walk callers (`print_callers`) to find the actual hotspot,
   not just the leaf C function.

Skip steps 1–3 only if you already know the question. Don't profile
something you haven't black-box-timed first.

## The scripts

All under `scripts/perf/`:

| script | purpose |
| --- | --- |
| `perf_data.py` | Synthetic dataframes with knobs for size and column kind (int / float / float-with-nan / bool / unique-string / low/med/high-card-string). Pandas + polars from the same arrays. |
| `perf_bench.py` | Synthetic StatPipeline timings @ 100k / 500k. Per-column, per-stat-func breakdown. JSON output via `--json`. |
| `perf_bench_real.py` | Same per-stat breakdown but on a real CSV. Pass any `.csv`. Loads with both pandas and polars. |
| `perf_widgets.py` | Black-box smoke test of all widget variants (`BuckarooWidget`, `BuckarooInfiniteWidget`, `PolarsBuckarooWidget`, `PolarsBuckarooInfiniteWidget`) on synthetic + real data. Includes a 200-row serialization pull. **No internals patched** — public API only. |
| `perf_profile.py` | cProfile harness. Prints both `cumulative` (filtered to in-tree) and `tottime` (any module). After a hit, manually edit to add `print_callers('<symbol>')` and re-run to walk the call chain. |

Run from the repo root with the project venv:

```bash
.venv/bin/python scripts/perf/perf_bench.py --rows 100000 500000
.venv/bin/python scripts/perf/perf_bench_real.py ~/Downloads/some.csv
.venv/bin/python scripts/perf/perf_widgets.py
.venv/bin/python scripts/perf/perf_profile.py
```

## Instrumentation already in the code

### Runtime toggle — `BUCKAROO_PERF`

The fastest way to see where time goes in a live run (no bench script,
no profiler) is the `BUCKAROO_PERF` toggle
(`buckaroo/pluggable_analysis_framework/perf_log.py`). Default off, zero
overhead. Turn it on and every stat-pipeline run and first-data-pull
emits structured lines to the `buckaroo.perf` logger:

```bash
BUCKAROO_PERF=1 .venv/bin/python your_script.py     # spans + summary on stderr
```

```python
from buckaroo.pluggable_analysis_framework import perf_log
perf_log.enable()                # or BUCKAROO_PERF=1 in the env
BuckarooWidget(df)               # pandas / polars / xorq — same output shape
perf_log.disable()
```

It covers all three stat backends and the first pull uniformly:

- **Stats pipeline** — per-`(phase, column, stat, seconds)` rows plus a
  top-N-slowest summary. pandas/polars run as one `pandas/polars`
  phase; xorq splits into `stat.xorq.batch_aggregate` (the single folded
  aggregate query), `stat.xorq.materialize` (cold-cache source landing),
  and `xorq/per-column` (histogram re-scans — usually the dominant cost),
  with cache hit/miss folded into the summary label. Note the summary's
  `total=` sums the per-column rows only; the `stat.xorq.materialize` and
  `stat.xorq.batch_aggregate` phases are reported as their own `perf span=`
  lines, not folded into that total.
- **First data pull** — `firstpull.summary_stats`,
  `firstpull.window_to_parquet`, and the server-side spans that decompose a
  `/load_expr` into the three numbers a perf harness wants: `firstpull.expr_load`
  (expression build, just `load_expr_build_dir`), `firstpull.dataflow_construct`
  (stats run — the `stat.xorq.*` spans break it down further), and
  `firstpull.metadata`, all nested under the outer `firstpull.load_expr` total;
  plus `firstpull.ws_first_payload` (time-to-first-rows — the parquet encode and
  frame send of the first `infinite_request`, emitted once per session). The
  server spans carry `session=` so they correlate across concurrent loads. In
  the server these land in `~/.buckaroo/logs/server.log`.

Lines are `key=value` and greppable (`grep 'perf span=' server.log`),
so external harnesses can parse `secs=` for a named span. The
`PERVERSE_DF` DAG self-check that runs on every pipeline construction is
suppressed, so the only output is real data pulls.

Take *headline* numbers with the toggle **off** — the per-`(col,stat)`
`perf_counter` pairs are cheap but nonzero on very wide frames.

### Offline `record_timings` (bench scripts)

`StatPipeline` also has the lower-level `record_timings` flag it's built
on. When `BUCKAROO_PERF` is set it defaults on; pass it explicitly to
capture `pipe.timings` without logging (this is what
`scripts/perf/perf_bench.py` does):

```python
pipe = StatPipeline(stat_funcs, record_timings=True)
pipe.process_df(df)
pipe.timings  # list of (col, stat, secs)
```

## Datasets to reach for

Synthetic (already wired in `perf_data.py`):
- 100k rows × 8 cols mixed kinds — the cheap default
- 500k rows × 8 cols — exercises the >1M-cell downsample path

Real CSVs that worked well last time:
- `~/Downloads/lahman_1871-2025_csv/Fielding.csv` — 174k × 18,
  mostly numeric, 4 string IDs
- `~/Downloads/tmpzyxhlh1w.csv` — 883k × 26, almost all strings,
  one long-form `comments` column
- (from kaggle, free) NYC taxi yellow trips, NOAA GHCN daily — pick
  anything ≥ 1M rows × 20+ cols if the above aren't present

If you need a fresh source, prefer a CSV ≥ 5M cells and ≥ 20 columns
with at least one long-text and one high-cardinality numeric column.
That combination is what shook the most bugs out.

## How to actually run a perf pass

1. **Branch.** `git checkout -b perf/<thing>` off main.
2. **Warmup matters.** First widget construction in a process eats a
   few hundred ms of import + `unit_test=True` DAG validation.
   Always warm up on a tiny df before measuring. `perf_widgets.py`
   already does this.
3. **Best of N, not single runs.** Use `min` of 3+ for headline
   numbers, `avg` for stability check. The harness scripts already
   report both.
4. **Black-box first.** Time `Widget(df)` end-to-end before reaching
   for a profiler. Compare pandas vs polars; compare main vs infinite.
5. **cProfile when you have a target.** Read the `tottime` view, not
   `cumtime` — `tottime` tells you where work is actually spent. Then
   use `print_callers('<symbol>')` (and walk up several levels) to
   find the real caller. Don't stop at "it's slow in pandas internals."
6. **Look at call counts.** A 586 ms hit in 2 calls is a different
   problem from 586 ms in 50 000 calls. The traitlets bug we found in
   May 2026 was 2 calls — that pattern is unmistakable in the profile.
7. **Confirm on a second dataset before declaring victory.** A fix
   that helps 100k synthetic but blows up on 1M-row real strings is
   not a fix.

## Common traps

- **Sampling kicks in at 1M cells.** `DfStatsV2.get_operating_df` and
  the polars equivalent downsample to 50k rows when `rows × cols >
  FAST_SUMMARY_WHEN_GREATER`. Numbers from 500k synthetic and 100k
  synthetic are *not directly comparable* because of this.
- **`unit_test=True` is on by default in `StatPipeline.__init__`.**
  Every widget construction runs the full pipeline against
  `PERVERSE_DF` to validate the DAG. Adds tens of ms; especially
  visible in cold-start tests.
- **Traitlets `Any()` traits do `==` comparisons on assignment.**
  Assigning a 1M-row pandas DataFrame to an `Any()` trait will trigger
  a full element-wise comparison via `traitlets.set` →
  `DataFrame.__eq__`. This is the exact failure mode that ate 586 ms
  on Boston pandas. Polars dodges it because polars `==` doesn't
  reduce to bool. Issue #N tracks this.
- **`.to_list()` on a polars Series is much slower than `.to_numpy()`**
  for any N > a few hundred. Materializes Python objects per element.
- **`pl.DataFrame.to_pandas()` is expensive at scale** because of the
  pyarrow round-trip. Avoid in the hot path; use polars-native parquet
  serialization where possible (the infinite widget already does this).
  Note: polars `to_json` is not flexible enough to feed the buckaroo
  frontend directly — the to_pandas round-trip in
  `PolarsBuckarooWidget._df_to_obj` is currently the workaround.

## What "good" looks like

Rough numbers from May 2026 baseline, after warmup, best of 3:

| widget | dataset | total |
| --- | --- | --- |
| `BuckarooWidget` (pandas) | 100k × 8 synth | ~105 ms |
| `BuckarooInfiniteWidget` | 100k × 8 synth | ~85 ms |
| `PolarsBuckarooWidget` | 100k × 8 synth | ~100 ms |
| `PolarsBuckarooInfiniteWidget` | 100k × 8 synth | ~75 ms |
| `BuckarooInfiniteWidget` | Boston 883k × 26 | ~715 ms ⚠ traitlets bug |
| `PolarsBuckarooInfiniteWidget` | Boston 883k × 26 | ~95 ms |

Snapshots in `docs/research/perf-polars-stats.md` and
`docs/research/perf-profile-output.txt`.

## After a fix

1. Re-run the same harness on the same datasets.
2. Compare to the saved baseline (`perf-polars-stats-100k-500k.json`,
   `perf-profile-output.txt`). Save the new run alongside.
3. Update `docs/research/perf-polars-stats.md` with the new numbers
   and a one-line "what changed" entry.
4. Don't delete the baseline — keep history so future regressions
   show up.
