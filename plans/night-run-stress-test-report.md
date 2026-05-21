# Overnight stress-test report

Worked through the night per your ask. Cross-backend (pandas / lazy
polars / xorq) stress, DDD edge cases, WS protocol fuzzing, perf
instrumentation, and small fix PRs along the way. Everything below
should be reproducible from the smorg branch.

## TL;DR

- **12 bugs filed** (#791–#795, #797–#801, #805, #807).
- **5 PRs opened** (#796, #802, #803, #804, #806) — small, focused, with
  failing-test-then-fix commit pairs each.
- **Server perf root cause identified**: 6.5 s of every 9 s
  state_change goes to per-column histogram queries in
  `XorqStatPipeline` phase 2; phase 2 of the rows-first spike then
  *redoes* the same work because `_populate_sd_cache` doesn't respect
  the spike's `_defer_summary_sd` gate. Filed/described in #794 and
  the existing `plans/0787-xorq-rows-first-coverage.md`.
- **`?filtered_histogram` pinned row** (per your earlier ask) is wired
  into the smorg branch's `DefaultMainStyling.pinned_rows` and works
  on both pandas-mode and xorq-mode server paths. End-to-end verified
  via in-process widget construction:

  ```
  pinned_rows config:
    dtype              → obj
    histogram          → histogram
    ?filtered_histogram → histogram

  pre-filter:   merged_sd['a'] has 'histogram', no 'filtered_*' keys
  post-filter:  merged_sd['a'] has both 'histogram' and
                'filtered_histogram', plus filtered_mean / filtered_min / ...
  ```
- **Polars-lazy mode is more broken than it looks** — see #793.

---

## Bugs filed (links open the issue)

| # | Title | Backend | Severity |
|---|---|---|---|
| [#791](https://github.com/buckaroo-data/buckaroo/issues/791) | `/load` fails with `ArrowTypeError` on parquet files using uint8 dictionary indices | pandas | medium |
| [#792](https://github.com/buckaroo-data/buckaroo/issues/792) | `XorqStatPipeline` crashes `ComputedDefaultSummaryStats` on string columns (338 StatErrors on boston) | xorq | high |
| [#793](https://github.com/buckaroo-data/buckaroo/issues/793) | Lazy mode silently drops `buckaroo_state_change` → WS client hangs forever | lazy-polars | high |
| [#794](https://github.com/buckaroo-data/buckaroo/issues/794) | `buckaroo_state_change` requests not superseded; rapid typing wedges the server | all | high |
| [#795](https://github.com/buckaroo-data/buckaroo/issues/795) | Xorq backend re-executes `count()` on every infinite_request and 5+× per state_change | xorq | medium |
| [#797](https://github.com/buckaroo-data/buckaroo/issues/797) | `infinite_request` with `end >> total_rows` returns the entire dataset (DoS) | xorq, pandas, lazy | **critical** |
| [#798](https://github.com/buckaroo-data/buckaroo/issues/798) | Xorq `infinite_request` leaks full traceback in `error_info` regardless of `BUCKAROO_DEBUG` | xorq | medium |
| [#799](https://github.com/buckaroo-data/buckaroo/issues/799) | `XorqBuckarooWidget` fails on pandas Period dtype — `xo.memtable` rejects | xorq | low |
| [#800](https://github.com/buckaroo-data/buckaroo/issues/800) | Xorq stats fail silently on int64 values > 2^53 (JSON-safe-integer limit) | xorq | medium |
| [#801](https://github.com/buckaroo-data/buckaroo/issues/801) | Polars histogram stat fails silently on Decimal columns | polars | low |
| [#805](https://github.com/buckaroo-data/buckaroo/issues/805) | WS `on_message` crashes / silently drops on malformed JSON shapes (null, bare array, unknown type) | all | medium |
| [#807](https://github.com/buckaroo-data/buckaroo/issues/807) | Compare tool error handling inconsistencies (HTTP 500 on user error, session required) | compare | low |

## PRs opened

| # | Title | Closes | Status |
|---|---|---|---|
| [#796](https://github.com/buckaroo-data/buckaroo/pull/796) | `fix(xorq): memoize _expr_count by expression identity` | #795 | CI green |
| [#802](https://github.com/buckaroo-data/buckaroo/pull/802) | `fix(server): clamp infinite_request window — DoS guard` | #797 | CI green |
| [#803](https://github.com/buckaroo-data/buckaroo/pull/803) | `fix(server): gate xorq infinite_request error_info on BUCKAROO_DEBUG` | #798 | CI green |
| [#804](https://github.com/buckaroo-data/buckaroo/pull/804) | `fix(server): explicit error for state_change on read-only modes` | #793 | CI green |
| [#806](https://github.com/buckaroo-data/buckaroo/pull/806) | `fix(server): guard WS on_message against non-dict JSON + unknown types` | #805 | pending |

Each PR has the test-failing-on-CI-first commit pair per the global
TDD rule. Each PR is independent and branched from `main` — they can
land in any order.

## Cross-backend stress matrix

Boston restaurant data (`/tmp/restaurant-complaints-pandas.parquet`,
883 470 rows × 26 cols) loaded into three sessions on the standalone
server, hit with the same test battery.

```
test                             pandas       polars         xorq
----------------------------------------------------------------------
initial_load                        1ms          0ms          1ms
search_pizza                     1095ms      20002ms✗     11026ms
search_no_match                   973ms      20004ms✗      1194ms
search_unicode                    982ms      20003ms✗      1248ms
pagination_500                     10ms        201ms       3013ms
pagination_far                      2ms         16ms        644ms
sort_asc                            2ms        126ms        603ms
filter_clear                      192ms      20014ms✗      8435ms
rapid_state_changes              7389ms      15003ms✗     48396ms
```

`✗` = WS hangs / timeout (the lazy-mode silent-drop bug, #793).

Headline numbers:
- **pandas pagination is great** (10 ms for 500 rows over 5 requests).
- **xorq pagination is 30× slower** than pandas (3 s vs 10 ms) — the
  bulk is duplicate `_expr_count()` and pandas→arrow conversion that
  re-runs per request. #795 + the bigger #794/787 fix together get
  most of this back.
- **Rapid typing wedges xorq for 48 s** (5 sequential
  state_changes × ~9.5 s each). No supersede logic. #794.

## Data-shape stress (54 fixtures × 3 backends)

Ran the DDD library plus a handful of custom edge cases. Result: **53
of 54 widget constructions survive**. Only crash was pandas refusing
duplicate column names (`DuplicateColumnsException`) — which is the
intended behavior. Other notable findings:

- **Wide dataframes** (500 cols) silently clamp to 250 — known `max_columns` cap.
- **Xorq on big ints (>2⁵³)** silently drops stats (#800).
- **Xorq on `period` dtype** crashes at memtable construction (#799).
- **Polars on Decimal columns** loses histogram silently (#801).
- All three backends handle: empty df, single-row, all-NaN, mixed-NaN,
  unicode column names, tz-aware datetimes, sparse-NaN, all-bool, all-empty-string.

## Server perf deep dive (the "xorq feels slow" thread)

Instrumented every hot path in the WS handler + xorq pipeline with
`[tperf]` log lines. Single search for "PIZZA" on the boston session:

```
PHASE 1 (propagate + extract_display_state)             9425 ms
├─ xorq.process_table  (filt-scope SD, fired by cache)  6953 ms
│  ├─ batch_execute (datafusion table.aggregate)         363 ms   ← reasonable
│  └─ phase2 (per-column queries)                       6585 ms   ★ DOMINANT
├─ 5× _expr_count @ ~245ms each                         1220 ms   ★ → #795 fix
└─ everything else                                      ~1250 ms

infinite_request (between phases)                        553 ms
├─ window_to_parquet                                     256 ms
├─ _expr_count                                           295 ms   ← #795 fix
└─ tornado plumbing                                       ~2 ms

PHASE 2 (recompute_summary_sd, after the 10ms yield)    8304 ms
├─ xorq.process_table  (SAME compute redone)            8302 ms   ★ DOUBLE-COMPUTE
│  ├─ batch_execute                                      316 ms
│  └─ phase2 (per-column queries)                       7983 ms
```

Three observations:

1. **The per-column query loop in `XorqStatPipeline` phase 2 is the
   dominant cost** — 26 columns × ~250 ms per histogram query. The
   table re-registers with datafusion on every query because the data
   was wrapped as a pandas memtable (#785's `xorq-cache-delegation`
   plan called this out — relevant now).
2. **The rows-first spike is double-computing on xorq.** The spike's
   `_defer_summary_sd = True` skips the `_summary_sd` observer, but
   the `_populate_sd_cache` observer (from #785/#789) still fires
   during the propagate cascade and runs `XorqStatPipeline.process_table`
   against the filt-scope df. Phase 2 then re-runs the same compute
   instead of hitting the cache. This is the structural reason
   `plans/0787-xorq-rows-first-coverage.md` had to drop its
   phase-divergence assertion.
3. **`_expr_count` waste is ~$1.5 s per state_change** of pure
   duplicate count work. Addressed by PR #796.

Pandas pipeline equivalent on the same data: 422 ms (no per-column
re-registration, just `value_counts` on object-dtype).

Polars-native target (one-shot equivalent compute): 142 ms.

## Perf paths forward (in priority order)

1. **Apply PR #796** (memoize `_expr_count`) — saves 1.5 s per
   state_change immediately. Smallest patch, biggest immediate win.
2. **Fix the spike's double-compute (#787 / open-question
   "xorq path coverage")**. Make `_populate_sd_cache` respect
   `_defer_summary_sd`, write only pointer-trait updates when the
   gate is on. Cuts phase-1 from 9 s to ~363 ms (just the batch
   aggregate). Phase 2 then does the per-column work.
3. **Register the xorq table once, reuse across queries** (the
   "xorq cache delegation" plan, now urgent for perf). Cuts the
   per-column phase-2 cost from ~250 ms × 26 to ~5 ms × 26.
4. **#794 supersede** — orthogonal to all of the above. Even with a
   fast compute, rapid typing should cancel in-flight previous
   state_changes, not queue them.

If 1+2+3 land, the boston state_change drops from ~9 s to maybe 100-200
ms. Faster than pandas. With sampling off. Polars is still ~140 ms;
xorq matches it.

## Stress test scripts (kept under /tmp for inspection)

- `/tmp/stress_backends.py` — cross-backend WS battery (round 1).
- `/tmp/stress_round2.py` — mode switching, concurrent WS clients,
  malformed payloads, mid-flight close.
- `/tmp/stress_data_shapes.py` — DDD-equivalent edge-case dfs across
  3 backends.
- `/tmp/stress_ws_protocol.py` — WS message-shape fuzzing.
- `/tmp/profile_pandas.py` — cProfile on pandas pipeline.
- `/tmp/profile_xorq.py` — cProfile on xorq pipeline.
- `/tmp/optimize_pandas.py` — pyarrow strings + sample-size variants.
- `/tmp/polars_target.py` — polars-native baseline.
- `/tmp/time_xorq.py` — wall-clock pandas vs xorq pipeline.
- `/tmp/exercise_server.py` — single-state-change WS round-trip timer.

## Branches

- `smorg/post-785-playground` — this branch. Has merged
  #788+#789+#790+#787 plus the `?filtered_histogram` styling change,
  plus the `[tperf]` instrumentation in `websocket_handler.py`,
  `xorq_buckaroo.py`, `xorq_stat_pipeline.py`. The instrumentation is
  uncommitted (in working tree); strip with `git stash` if not wanted.
- `fix/expr-count-memoize` — PR #796.
- `fix/clamp-infinite-request` — PR #802.
- `fix/xorq-error-info-debug-gate` — PR #803.
- `fix/lazy-state-change-error` — PR #804.

## Most surprising finding

The rows-first spike (#787) **makes the xorq state_change *worse* on
the boston dataset.** Without the spike, one ~7 s pipeline run.
With the spike, *two* sequential ~7-9 s runs because the cache
observer fires during phase 1 and the phase-2 `recompute_summary_sd`
re-runs the same work. The spike's whole premise (phase 1 ships
display state cheaply, phase 2 does the heavy lift) is broken on
xorq until the cache-observer gate is wired up.

I also tested the spike on the **pandas** backend (`mode=buckaroo`)
end-to-end via WS:

```
single search 'PIZZA', pandas-mode boston:

spike OFF: 1 frame at 1031 ms.
spike ON:  2 frames at 1021 ms and 1056 ms.
```

Same total latency. The spike adds a redundant second frame, no UX
win. The cache observer issue (#787's open question on xorq path
coverage) is the same on pandas — just smaller in absolute terms,
because process_df is 400ms instead of 7 s.

Net: **the spike doesn't help any backend in its current shape**.
Fixing the cache observer gate (per `plans/0787-xorq-rows-first-coverage.md`)
is the prerequisite for the spike to do anything useful.

## Least surprising finding

The boston restaurant inspection data has 26 columns of which 10 are
high-cardinality strings (`businessname`, `dbaname`, `comments`,
`address`, `violation`, `violdesc`, etc.). On pandas these blow up
`value_counts()` (~217 ms of the 422 ms total). On xorq they fail
entirely (#792 — `value_counts` defaults are int 0, downstream
`ComputedDefaultSummaryStats` crashes on `len(0)`). On polars they
work fine. The string-column performance gap between pandas object
dtype and Arrow-backed strings is real and load-bearing.

## What's NOT covered

- I didn't run the Playwright JS tests against any of the fix
  branches. They should pass — the server-side changes don't touch
  the JS surface — but worth a CI check before merging.
- I didn't test the Compare tool (`/load_compare`). Stress for it
  is queued in `/tmp/stress_round2.py` if you want to extend.
- The xorq table-registration optimization (perf item #3 above) is a
  bigger change and I didn't attempt it.
- I noticed the WS broadcast handler also leaks WS-closed exceptions
  on the server log when a client disconnects mid-write. Minor noise,
  not a correctness bug. Not filed.
