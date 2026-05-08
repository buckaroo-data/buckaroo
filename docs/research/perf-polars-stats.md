# Polars stats pipeline perf — investigation

Date: 2026-05-07
Branch: `perf/polars-stats-instrumentation`
Harness: `scripts/perf/perf_bench.py`
Raw data: `docs/research/perf-polars-stats-100k-500k.json`

User-reported impression: "polars buckaroo feels slower than pandas
sometimes". Goal of this run: instrument the v2 stat pipeline, run on
synthetic 100k / 500k row data with int / float / bool / string (unique,
low-card, med-card, high-card) columns, attribute time per (column,
stat_func), and identify hotspots.

## TL;DR

1. **`_pl_vc_to_pd` is the single biggest hotspot** in the polars stats
   pipeline. It converts a polars value_counts result to a pandas Series
   via `.to_list()`, which materializes Python objects for every row.
   Switching to `.to_numpy()` is **~9× faster** on int columns, ~3.5×
   faster on string columns. Pure win, no semantic change.

2. At 100k rows the polars pipeline is ~1.5× slower than pandas
   (103 ms vs 70 ms). At 500k rows the pipeline numbers cross over
   (384 ms polars vs 411 ms pandas) but in the actual widget both are
   downsampled to 50k by `FAST_SUMMARY_WHEN_GREATER`, so the relevant
   user-perceived size is around 100k.

3. End-to-end widget construction at 100k after warmup is essentially
   the same for pandas and polars (~105 ms each). The "polars feels
   slower" impression is almost certainly from **first-render cold
   start** (heavier import + DAG build) rather than steady-state.

4. `pl_base_summary_stats` accounts for **~80% of polars stats time**.
   It always computes value_counts, which is fine — the cost is the
   pandas conversion, not the value_counts call itself.

## How to reproduce

```bash
.venv/bin/python scripts/perf/perf_bench.py --rows 100000 500000 \
    --json /tmp/perf.json
```

Pipeline timings come from a new opt-in flag on `StatPipeline`:

```python
pipe = StatPipeline(stat_funcs, record_timings=True)
pipe.process_df(df)
pipe.timings  # list of (column, stat_name, seconds)
```

Default behavior is unchanged when the flag is off.

## Numbers @ 100k rows (8 columns, mixed kinds)

```
pandas pipeline total: 70 ms     polars pipeline total: 103 ms     ratio: 1.47x
```

Per-column total (ms):

| col | kind | pandas | polars | polars/pandas |
| --- | --- | --- | --- | --- |
| int_col | int (~uniform 0..1M) | 11.2 | **37.0** | **3.29x** |
| float_col | float | 13.8 | 15.8 | 1.14x |
| float_with_nan | float (5% nan) | 13.5 | 14.9 | 1.10x |
| bool_col | bool | 1.3 | 3.0 | 2.39x |
| str_unique | string unique | 17.0 | 20.7 | 1.22x |
| str_low_card | string low-card (10) | 3.2 | 2.2 | 0.67x |
| str_med_card | string med-card (1k) | 3.2 | 2.3 | 0.71x |
| str_high_card | string high-card (50k) | 6.4 | 5.9 | 0.91x |

Per stat func, polars (ms summed across cols):

| stat | ms |
| --- | --- |
| `pl_base_summary_stats` | **83.4** |
| `pl_histogram_series` | 6.4 |
| `computed_default_summary_stats` | 5.8 |
| `histogram` | 2.9 |
| `pl_numeric_stats` | 2.3 |
| `pl_typing_stats` | 0.9 |
| `_type` | 0.1 |

Polars's slowest cells are all `pl_base_summary_stats` on the
high-cardinality columns (`int_col`, `str_unique`, `float_col`,
`float_with_nan`).

## The `_pl_vc_to_pd` hotspot

`buckaroo/customizations/pl_stats_v2.py:63`:

```python
def _pl_vc_to_pd(ser: pl.Series) -> pd.Series:
    vc = ser.drop_nulls().value_counts(sort=True)
    col_name = ser.name
    return pd.Series(vc['count'].to_list(), index=vc[col_name].to_list())
```

Micro-bench on `int_col` @ 100k rows (5 reps, min):

| step | ms |
| --- | --- |
| `ser.value_counts(sort=True)` (raw) | 1.58 |
| `_pl_vc_to_pd` current implementation | **15.15** |
| same, swap `.to_list()` for `.to_numpy()` | **1.68** |
| pandas equivalent: `ser_pd.value_counts()` | 2.42 |

On `str_unique` @ 100k:

| step | ms |
| --- | --- |
| `_pl_vc_to_pd` current | 11.35 |
| `.to_numpy()` variant | 3.27 |
| pandas equivalent | 10.27 |

The `to_list()` calls are ~9× slower than `to_numpy()` on numeric
columns and ~3.5× slower on strings. With the `to_numpy()` change
polars actually beats pandas at the value_counts step, including the
conversion.

There is one wrinkle: the `count` column comes back as `u32`. pandas
indexing assumes int64 in a few places downstream — the existing
`.to_list()` path lossily upcasted via Python ints. `.to_numpy()`
preserves `u32`. We should confirm that
`computed_default_summary_stats` (`pd_stats_v2.py:152`) handles a
`u32` count column without issue. (`vc[vc == 1]` and `len(vc)` are
fine. The value passed back as `value_counts` itself is consumed by
`pd_cleaning_stats` and `histogram` / `categorical_histogram`, all of
which should be checked.)

## Why "polars sometimes feels slower"

End-to-end widget construction with warmup (3 reps, min):

| rows | pandas widget | polars widget |
| --- | --- | --- |
| 100k | 104.2 ms | 101.1 ms |
| 500k | 135.8 ms | 124.8 ms |

Without warmup, the *first* widget construction is much higher
(seen 237 ms pandas vs 117 ms polars in one run; 148 ms vs 137 ms in
another). That cold-start cost is dominated by:

- module import (`buckaroo.polars_buckaroo`, `pd_stats_v2`,
  `pl_stats_v2` and the styling klasses)
- StatPipeline construction (DAG build + unit_test against
  `PERVERSE_DF`)

The 500k widget number is misleading: `DfStatsV2.get_operating_df`
samples down to 50 000 rows when `rows * cols > 1_000_000`. So at 500k
rows × 8 cols the pipeline only ever sees a 50k sample. The same
applies to `PlDfStatsV2`. This is why the 500k widget timings are
*lower* than the 100k pipeline numbers and why both pandas/polars are
roughly tied there.

The likely user-felt failure mode is the very first polars widget
construction in a kernel, where a few hundred ms of import + DAG cost
land on top of the slower `_pl_vc_to_pd`. Subsequent widgets in the
same kernel are fast.

## Other observations

- `pl_typing_stats` is 8× faster than pandas's `typing_stats` at 100k
  (0.9 ms vs 2.3 ms across 8 cols). Polars dtype API is cheap.
- `pl_numeric_stats` is fine — `mean/std/median` on polars are faster
  than pandas at 500k.
- `pl_histogram_series` already calls `meat.to_numpy()` for the
  histogram — that path is healthy.
- `bool_col` is 2.4× slower in polars (1.3 ms vs 3.0 ms at 100k). Tiny
  in absolute terms; not worth chasing.
- `pl_base_summary_stats` always computes mode via
  `ser.drop_nulls().mode().item(0)`. For huge unique-value columns
  this is ~0.7 ms / col. Could be made conditional but not urgent.

## Real CSVs in the wild

Re-ran the per-stat instrumentation on two real CSVs from `~/Downloads`
to make sure the synthetic findings hold up:

`Fielding.csv` (Lahman baseball, 174,332 rows × 18 cols — mostly
numeric with 4 string ID cols):

```
pandas total: 96.1 ms     polars total: 66.7 ms     ratio: 0.69x
```

Polars is **faster** here. Per-stat winner is still
`pl_base_summary_stats` (33 ms), and `pl_histogram_series` (20 ms).
String ID columns (`teamID`, `lgID`, `POS`) are 0.5x of pandas — polars
crushes low-cardinality string value_counts.

`tmpzyxhlh1w.csv` (Boston restaurant inspections, 883,470 rows × 26
cols — almost all strings, including a long-form `comments` column):

```
pandas total: 764.9 ms    polars total: 573.2 ms    ratio: 0.75x
```

Also faster. The hot column on both engines is `comments` (long free
text, ~118 ms pandas / 125 ms polars — only column where polars loses,
by 6%). Notable cells:

| col | pandas | polars |
| --- | --- | --- |
| `comments` (long text) | 118 ms | 125 ms |
| `licenseno` (int high-card) | 17 ms | **21 ms** |
| `dbaname` (mostly null) | 11 ms | **0.8 ms** |

The `licenseno` int column reproduces the synthetic
high-cardinality-int regression from the 100k-row test.

End-to-end widget construction at 883k rows × 26 cols (this triggers
the >1M-cell downsample to 50k rows in `DfStatsV2.get_operating_df`),
warmed up, best of 3:

```
BuckarooWidget(pandas):       741 ms
PolarsBuckarooWidget(polars): 433 ms
```

Polars wins by ~40% on this real dataset.

### What this means for the user-facing impression

The "polars feels slower than pandas" report is real but narrow. The
combinations where polars actually loses today:

- **Small to medium datasets (~50k–200k rows) with high-cardinality
  numeric or unique-id string columns** — the synthetic 100k case
  showed `int_col` 3.3× slower in polars purely because of the
  `_pl_vc_to_pd` conversion.
- **First widget construction in a fresh kernel** — heavier imports
  plus the `unit_test=True` default in `StatPipeline.__init__`.
- **Long-text columns where the value_counts result is itself huge**
  — the `comments` column above, where pandas-style value_counts and
  the index conversion is dominated by raw string handling.

For everything else (most numeric workloads, mixed real-world string
columns with reasonable cardinality, anything past the >1M-cell
downsample threshold) polars is already faster end-to-end.

## cProfile of widget construction — two real bombs

Profiling `BuckarooInfiniteWidget(boston_df)` (883k×26, after warmup,
total 755 ms) — `tottime` view:

```
ncalls  tottime  function
     2    0.586  array_ops.py:113(comp_method_OBJECT_ARRAY)
    46    0.042  algorithms.py:963(value_counts_arraylike)
    50    0.014  missing.py:305(_isna_string_dtype)
     1    0.143  dataflow.py:199(_summary_sd)        # full stats pipeline
   276    0.114  stat_pipeline.py:58(_execute_stat_func)
```

**78% of the runtime (586 ms) is two object-array `==` comparisons.**
The stats pipeline that I'd been chasing all morning is only 143 ms —
not the bottleneck.

Walking the call chain with `print_callers`:

```
comp_method_OBJECT_ARRAY  <- comparison_op
                          <- frame.py:7894 (DataFrame._cmp_method)
                          <- arraylike.py:38 (DataFrame.__eq__)
                          <- common.py:62 (new_method)
                          <- traitlets.py:689 (set)     ← 2 calls, 586 ms
```

**`traitlets.set` is comparing the old vs new DataFrame value with
`==` to decide whether to fire `@observe` callbacks.** For an 883k×26
object-dtype frame, that's ~23M element comparisons in pure Python,
twice. Two of the `Any()` traits in `dataflow.py` get assigned
DataFrames during construction (candidates: `raw_df`, `sampled_df`,
`cleaned`, `processed_result`, `widget_args_tuple`, etc. — any
DataFrame-bearing `Any()`).

This scales linearly with cells:

| dataset | cells | comp_method_OBJECT_ARRAY (2 calls) |
| --- | --- | --- |
| synth 100k × 8 (pandas) | 800k | 13 ms |
| Boston 883k × 26 (pandas) | 23M | 586 ms |

Polars dodges this entirely. A polars `df == df2` returns a polars
DataFrame, and traitlets's `bool(...)` of that either raises or short-
circuits before doing element-wise work — the polars profile shows
zero time in any object-array comparison path. That's the **single
biggest reason `BuckarooInfiniteWidget(pandas)` feels slow at large
N**, and the reason polars *outperforms* pandas end-to-end on real
wide CSVs.

### Polars main-widget gotcha: `df.to_pandas()` for serialization

Profile of `PolarsBuckarooWidget(boston_df)` (430 ms):

```
ncalls  tottime  function
     1    0.253  pandas_compat.py:780(table_to_dataframe)   # pyarrow→pandas
     1    0.193  PyDataFrame.to_pandas                       # polars→pyarrow
     1    0.039  polars_buckaroo.py:63(_df_to_obj)
```

`_df_to_obj` calls `df.to_pandas()` on the 50k-sampled polars frame,
then `pd_to_obj` for JSON. **447 ms is spent crossing the
polars→pyarrow→pandas boundary** for serialization, when polars's
own native serialization (already used by the infinite path via
`to_parquet`) would be faster.

Comparison:

| widget | total | hot path |
| --- | --- | --- |
| `PolarsBuckarooInfiniteWidget` | 134 ms | sample_n 24 ms · value_counts 18 ms · `_pl_vc_to_pd` 43 ms |
| `PolarsBuckarooWidget` | 671 ms | **`to_pandas` round-trip 447 ms** + everything from infinite |

The infinite variant skips main serialization, which is why it's 5×
faster. If `PolarsBuckarooWidget._df_to_obj` could use polars-native
JSON (or parquet-b64 like the stats already do), the main widget
would close the gap.

### Where the original `_pl_vc_to_pd` finding sits

On the Boston profile of `PolarsBuckarooInfiniteWidget`:

```
26    0.043    cumtime  pl_stats_v2.py:63(_pl_vc_to_pd)
52    0.006    tottime  PySeries.to_list
```

43 ms cumulative on this file (about 1/3 of the 134 ms widget total).
Still real, still worth fixing, but **decisively smaller than the
traitlets and to_pandas issues** — and only matters on the polars side
where it isn't already dwarfed by other costs.

## xorq backends — datafusion and duckdb

`scripts/perf/perf_xorq.py` smoke-tests `XorqBuckarooWidget` /
`XorqBuckarooInfiniteWidget` with `xo.connect()` (datafusion, default)
and `xo.duckdb.connect()`. The same datasets as the other harnesses.
Black-box: register the table once with `con.create_table('t', df)`,
then time widget construction (best of 3) and a 200-row execute pull.

### Widget construction (warm, best of 3) — across all four engines

| dataset | xorq[datafusion] | xorq[duckdb] | pandas (post-#706) | polars |
| --- | --- | --- | --- | --- |
| synth 100k × 8 | 320 ms | 364 ms | 105 ms | 99 ms |
| synth 500k × 8 | 437 ms | 396 ms | 135 ms | 125 ms |
| Fielding 174k × 18 | 555 ms | 690 ms | 101 ms | 60 ms |
| Boston 883k × 26 | 793 ms | 744 ms | 758 ms | 430 ms |

Infinite variant on the same data:

| dataset | xorq[df] inf | xorq[duckdb] inf | pandas inf | polars inf |
| --- | --- | --- | --- | --- |
| synth 100k | 326 ms | 336 ms | 87 ms | 74 ms |
| synth 500k | 409 ms | 376 ms | 121 ms | 48 ms |
| Fielding 174k | 522 ms | 651 ms | 84 ms | 32 ms |
| Boston 883k | 732 ms | 680 ms | 715 ms | 96 ms |

### `create_table` (one-time, not in widget timing)

| dataset | datafusion | duckdb |
| --- | --- | --- |
| synth 100k | 20 ms | 40 ms |
| synth 500k | 63 ms | 99 ms |
| Fielding 174k | 28 ms | 56 ms |
| Boston 883k | 617 ms | 1104 ms |

### What this tells us

1. **xorq backends are 3–15× slower than pandas/polars for widget
   construction.** Intrinsic to the design: every stat is a SQL query
   pushed to the engine. The v2 stat pipeline runs ~7 stats × ~N cols,
   so several dozen round-trips per widget. Each query is fast in
   isolation but the count adds up.
2. **Datafusion edges out duckdb** for widget construction at small N
   and string-heavy data; duckdb catches up on synth 500k. For
   `create_table`, datafusion is **~2× faster** across the board —
   pandas→arrow ingestion is significantly cheaper there.
3. **Infinite vs main widget: xorq sees little win.** The infinite
   path skips main serialization, but for xorq backends serialization
   isn't the cost — the stats SQL queries are. So both variants land
   near the same number.
4. **200-row execute pull is fast.** 2–5 ms for both backends. SQL
   `LIMIT … OFFSET` round-trips are not a hotspot.
5. **Boston 883k duckdb create_table at ~1.1 s is the worst single
   number** in any of the harnesses — pandas DataFrame → duckdb table
   ingestion of a 376 MB string-heavy frame.

### Update — #709 fix landed (PR #710)

Profiling confirmed it's per-query overhead, not SQL execution. Three
fixes (`_summary_sd` dedupe, `XorqDfStatsV2` and
`verify_analysis_objects` both pass `unit_test=False`) cut the query
count by ~80% and the wall time by 2.3-3.9×:

| dataset | xorq[df] PRE | xorq[df] POST | xorq[duckdb] PRE | xorq[duckdb] POST |
| --- | --- | --- | --- | --- |
| synth 100k × 8 | 320 ms | **81 ms** (3.9×) | 364 ms | **103 ms** (3.5×) |
| synth 500k × 8 | 437 ms | **133 ms** (3.3×) | 396 ms | **118 ms** (3.4×) |
| Fielding 174k × 18 | 555 ms | **209 ms** (2.7×) | 690 ms | **269 ms** (2.6×) |
| Boston 883k × 26 | 793 ms | **318 ms** (2.5×) | 744 ms | **325 ms** (2.3×) |

Post-fix query count: 4 (3-col fixture), 9 (8 cols), 27 (26 cols).
Remaining is 1 batched aggregate + 1 histogram per column.

Still TODO: fold histograms into the batched aggregate to drop the
count to 1-2 regardless of column count. Numeric histograms can use
the already-computed min/max via a 2-pass batch; categorical top-K
is harder to batch in ibis.

## Updated picture of "polars feels slower"

Three independent issues, in descending order of impact:

1. **Pandas widgets eat huge object-array `==` from traitlets equality
   checks.** Hits any DataFrame-bearing `Any()` trait assignment.
   586 ms on Boston pandas alone. Polars dodges it.
2. **Polars main widget pays a `df.to_pandas()` round-trip.** 447 ms
   on Boston polars (only the main, not infinite). The pandas widget
   has a similar JSON-encoding cost but no double-conversion.
3. **`_pl_vc_to_pd` uses `.to_list()` instead of `.to_numpy()`.**
   Tens of ms in the worst cases, single-digit ms otherwise.

## Proposed next steps (not yet applied)

1. **Fix `_pl_vc_to_pd`**: replace `.to_list()` with `.to_numpy()`.
   Verify all consumers of `value_counts` handle the resulting
   numpy-backed pd.Series with `u32` count dtype.
   - Expected impact: polars 100k pipeline drops from 103 ms toward
     ~50 ms (sub-pandas). Eliminates the int/float gap.

2. **Re-run the bench** after the fix to confirm the gap closes and
   nothing regresses on pandas.

3. **Cold-start**: profile the first-widget construction (imports +
   unit_test on PERVERSE_DF). The `unit_test=True` default in
   `StatPipeline.__init__` runs the full pipeline against PERVERSE_DF
   on every construction — that's pure overhead at runtime. Consider
   caching the unit_test result per `(stat_funcs id-tuple)` or
   defaulting to `unit_test=False` for the widget construction path
   and only running it in tests / `add_stat`.

4. **Defer or memoize** `pl_base_summary_stats` mode calculation when
   the value_counts is already known — currently mode is computed
   independently via a second `drop_nulls().mode()` pass. We have the
   value_counts; mode is just the first index.

I'd recommend tackling (1) first, landing it as a single small PR with
a regression test and the bench numbers attached, then revisit (3) and
(4) separately.
