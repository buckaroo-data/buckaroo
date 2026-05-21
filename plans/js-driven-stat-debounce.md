# JS-driven per-stat-group debouncing

> Proposal for fixing the "xorq feels sluggish" UX without first solving
> the underlying compute-cost problem. Splits the stats pipeline into
> cost classes; ships cheap stats immediately; lets JS schedule the
> expensive ones with an adaptive debounce (default: 2× last observed
> compute time for that group). Subsumes the rows-first spike (#787)
> and the supersede gap (#794).

## The problem

A single `buckaroo_state_change` triggers the whole pipeline:

- scalar stats (length, null_count, distinct_count, mean, min, max, …):
  10–50 ms total per scope
- top-K value_counts (for `most_freq`, `2nd_freq`, …): 100–300 ms
- per-column histograms: **~250 ms × N columns** on xorq, much less on polars/pandas

On the boston dataset (26 columns) the histograms alone cost ~6.5s.
That's most of the 9s state_change. The first three are fast and
*always* finish before the histograms do.

Today both pieces run synchronously and ship in one frame. Result: the
whole UX waits for the slowest thing.

## Today's broken attempt

The rows-first spike (#787) tried to split this with a server-side
`call_later(10ms)` between phase 1 (skeleton) and phase 2 (stats). But:

- `_populate_sd_cache` observer fires during phase 1's propagate
  cascade, computing the filt-scope SD via `XorqStatPipeline.process_table`
  — phase 1 ends up running the same heavy work the spike was
  supposed to defer.
- Phase 2 then re-runs the same compute via `recompute_summary_sd`
  (cache observer fired but the recompute path doesn't hit the cache).
- The 10 ms `call_later` is a localhost-only timing knob that breaks
  under any real network RTT.

Net: the spike makes state_change slower on every backend (verified
in `plans/night-run-stress-test-report.md`). Server-side orchestration
of "ship cheap first" is too entangled with the observer cascade to
work cleanly.

## The proposal: move orchestration to JS

JS is already the side that knows about user intent (typing cadence,
dwell time, focus). It has a native event loop with timers, cancellation,
and back-pressure. Use it.

### New WS protocol

Add **three new message types** on top of the existing protocol:

```ts
// Client → server
{ type: "state_change",                  // renamed from buckaroo_state_change
  state_token: 42,                       // bumped on every send
  new_state: { ... }                     // unchanged
}

// Client → server
{ type: "compute_stat_group",
  state_token: 42,                       // must match latest; else reject
  scope: "filt" | "clean" | "raw",
  group: "scalar" | "aggregate"          // cost class
}

// Server → client (in response to state_change)
{ type: "state_ack",
  state_token: 42,
  fast_stats: { ... },                   // scalar group, all scopes
  meta: { ... },                         // df_meta, df_display_args
  // NOTE: no aggregate stats here — those come via compute_stat_group
}

// Server → client (in response to compute_stat_group)
{ type: "stat_group_result",
  state_token: 42,                       // mirrors the request
  scope: "filt",
  group: "aggregate",
  elapsed_ms: 6483,                      // JS uses this for adaptive debounce
  stats: { col_a: { histogram: [...], ... }, ... }
}

// Server → client (when an in-flight compute is superseded)
{ type: "stat_group_aborted",
  state_token: 41,                       // the stale token
  scope: "filt",
  group: "aggregate"
}
```

The existing `state_change` / `initial_state` flow stays as fallback for
JS that hasn't opted in (feature flag on the client side).

### Stat grouping

Two cost classes, declared per stat func:

```python
@stat(cost="scalar")     # default
def length(ser: RawSeries) -> int: ...

@stat(cost="scalar")
def null_count(ser: RawSeries) -> int: ...

@stat(cost="aggregate")  # opt-in
def histogram(...): ...

@stat(cost="aggregate")
def value_counts(ser: RawSeries) -> pd.Series: ...
```

Default is "scalar" so existing stats work without churn. Only the
known-expensive ones get explicitly marked.

This is **orthogonal to** the `pushdown=` decorator from #788 — that's
about engine routing, this is about cost. A stat can be both
`pushdown=("xorq",)` and `cost="aggregate"`.

### Server: split `process_table` by cost

```python
class XorqStatPipeline:
    def process_table_scalars(self, table) -> tuple[SDType, list]:
        """Phase 1 of process_table — only scalar-cost funcs."""

    def process_table_aggregates(self, table) -> tuple[SDType, list]:
        """Phase 2 — the expensive funcs, batched per DAG. Cached by
        (table identity, scope chain hash, stat_group)."""
```

`StatPipeline` (pandas) and `PolarsStatPipeline` (#769) get the same
split.

Existing `process_table()` becomes `scalars() + aggregates()` — same
result, two entry points. No regression risk for callers that want
"give me everything synchronously."

### JS orchestrator (sketch)

```ts
class BuckarooStateOrchestrator {
  private token = 0;
  private aggregateTimers: Map<string, number> = new Map();
  // per scope, last observed aggregate compute time in ms
  private lastAggregateMs: Map<string, number> = new Map();
  private readonly minDebounceMs = 200;
  private readonly maxDebounceMs = 3000;
  private readonly debounceMultiplier = 2;  // user's "2×" heuristic

  onStateChange(newState: BuckarooState) {
    const token = ++this.token;

    // Cancel any pending aggregate computes for the previous state.
    for (const t of this.aggregateTimers.values()) clearTimeout(t);
    this.aggregateTimers.clear();

    // Send the state_change — server replies with fast_stats only.
    this.ws.send({ type: "state_change", state_token: token, new_state: newState });

    // Schedule the aggregate compute for each scope that has user-visible
    // pinned rows depending on aggregate stats. For now: just filt scope
    // when a filter is active (raw + clean rarely change once cached).
    if (this.filterIsActive(newState)) {
      const last = this.lastAggregateMs.get("filt") ?? 500;
      const delay = clamp(last * this.debounceMultiplier,
                          this.minDebounceMs, this.maxDebounceMs);
      const tid = window.setTimeout(() => {
        this.ws.send({
          type: "compute_stat_group",
          state_token: token,
          scope: "filt",
          group: "aggregate",
        });
      }, delay);
      this.aggregateTimers.set("filt", tid);
    }
  }

  onStatGroupResult(msg: StatGroupResult) {
    if (msg.state_token !== this.token) return;  // stale
    this.lastAggregateMs.set(msg.scope, msg.elapsed_ms);
    this.mergeIntoMergedSd(msg.scope, msg.group, msg.stats);
  }
}
```

A few things this does for free:

- **Rapid typing**: every keystroke clears the previous timer. The
  expensive compute only fires once the user stops typing long enough.
- **Adaptive**: if histograms get cheaper (more rows match, smaller
  data, better cache hits), debounce shrinks automatically. If they
  get slower, debounce grows. No magic numbers to tune per dataset.
- **Cancellation**: token mismatch silently drops stale responses.
- **Network RTT-aware**: the debounce includes round-trip time
  naturally because `elapsed_ms` is measured on the server, but the
  client only fires the next request after the previous one resolves.

### What the user sees

```
t=0     user types "P"      → state_change sent
t=20    fast_stats arrive   → rows + scalar pinned rows update
t=80    user types "PI"     → state_change sent, prior aggregate timer cancelled
t=100   fast_stats arrive   → rows + scalar pinned rows update
t=180   user types "PIZ"    → state_change sent, prior aggregate timer cancelled
...
t=4000  user stops typing
t=5000  (1s = 2× last 500ms scalar measurement, until we have an aggregate baseline)
        compute_stat_group fired → histograms compute on the server
t=11500 stat_group_result arrives → histogram pinned rows update
t=11500 lastAggregateMs["filt"] = 6500
```

The user sees rows and scalar stats updating live while typing. The
histograms catch up a few seconds after they stop typing. Net effect:
the UI never feels stuck.

## Edge cases

1. **First state_change has no baseline.** Use a sane default (500ms)
   until we've observed at least one aggregate compute. Persist
   `lastAggregateMs` in localStorage so it survives reloads on the
   same dataset.

2. **State changes faster than the debounce.** Token-based cancellation
   handles this — server checks `state_token` before sending
   `stat_group_result`; client checks it before merging. Stale results
   get dropped both sides.

3. **Server-side abort.** When server receives `compute_stat_group`
   with a stale token, it sends `stat_group_aborted` rather than
   silently dropping — easier client-side bookkeeping.

4. **Cache hits on the aggregate.** If the filt-scope's chain hashes to
   an entry already in `summary_stats_cache` (e.g. backspace + retype
   same term), the server can return `stat_group_result` instantly. JS
   updates `lastAggregateMs` with the (tiny) value, so the next
   debounce shrinks to the minimum.

5. **Multi-window pagination during the debounce.** Unchanged —
   `infinite_request` is independent of stat groups. Pagination keeps
   working at scalar-stat speed.

6. **JS not on board (older builds).** Server still accepts the
   existing `buckaroo_state_change` and ships everything synchronously.
   New protocol is feature-detected on the client.

## What this subsumes

- **#787 (rows-first spike).** The spike's *whole goal* — ship cheap
  stuff first, expensive stuff later — is exactly this. Replaces the
  broken server-side `call_later` with client-side scheduling that
  actually works.

- **#794 (state_change supersede).** Token-based cancellation
  inherently solves the supersede gap. Server doesn't need separate
  abort logic; the existing token check handles it.

- **`plans/0787-xorq-rows-first-coverage.md`.** That plan documented
  the open questions for the spike's xorq path. This proposal makes
  most of those moot — the cache-observer-double-compute bug becomes
  irrelevant because the server only computes one group per request.

## What this does NOT solve

- The absolute cost of one aggregate compute is still 6.5s on
  xorq-with-boston. Debouncing makes the UI tolerable; it doesn't
  make xorq fast. Closing the compute gap needs the
  `plans/0785-xorq-cache-delegation.md` work (register the arrow table
  once, reuse across queries).

- The 338 `StatError`s on xorq string columns (#792) is independent.

## Migration path

Phase 1 (server, ~1 day):
- Add `cost="scalar" | "aggregate"` to the `@stat` decorator and
  `StatFunc` dataclass. Default scalar.
- Mark `histogram`, `value_counts`-derived stats, etc. as
  `cost="aggregate"`. ~5 sites.
- Add `process_table_scalars` / `process_table_aggregates` (renamed
  internals). Existing `process_table` becomes their composition.
- Add WS message handlers for `compute_stat_group` /
  `stat_group_aborted`.
- Token check at the boundary.

Phase 2 (client, ~1 day):
- `BuckarooStateOrchestrator` class.
- Feature flag: opt in via `component_config.use_progressive_stats: true`.
- Wire the existing `BuckarooView` to consume `state_ack` +
  `stat_group_result` instead of one `initial_state`.
- Cap debounce, persist baseline.

Phase 3 (validation, ~half day):
- Measure on boston-xorq, polars-lazy, pandas. Compare to current
  state_change wall-clock. Expect: scalar stats arrive in ~50 ms;
  aggregates arrive in `2 × engine_time` after typing stops.

Total: ~2-3 days. Worth it.

## Open questions

1. **Is "2×" really the right multiplier?** It's the user's
   suggestion; defensible because it gives the user a window of
   "you'll see the result within twice the time you saw last time."
   But: 2× a 6s compute = 12s of debounce, which is awful when the
   user has typed once and is waiting. Maybe `min(2 × last,
   user-action-recency-aware-cap)`. Worth a UX call.

2. **Three cost classes instead of two?** `scalar` / `aggregate` /
   `per_column_query`. The third would be the per-column histogram
   path (one query per column). Lets JS schedule independently —
   show batched aggregates after `2 × last_aggregate_ms`, show
   histograms after `2 × last_histogram_ms × n_columns`. Maybe later.

3. **Multi-client coordination.** Two browser tabs on the same
   session: do they share the aggregate baseline? Probably not — it's
   a per-client UX heuristic. Keep `lastAggregateMs` in the
   `BuckarooStateOrchestrator` instance only.

4. **Where to declare cost class.** Today's `@stat` decorator is the
   natural place. But cost is empirical (varies by backend, data
   shape) — a stat that's "scalar" on polars might be "aggregate" on
   xorq with 26 string columns. Future: server measures and tags at
   runtime. For now: static declaration is enough.

5. **What about post-processing / cleaning state changes?** Same
   pattern. Post-processing usually changes the *whole* dataset shape,
   so all scopes change. Cleaning changes only clean + filt. The
   orchestrator can be smart about which scopes to schedule.

## Recommendation

Build this. It's the right architectural answer to the perf problem
even if we eventually also fix the xorq compute cost. The protocol is
clean, the server changes are surgical (cost decorator + a couple of
new WS handlers), and JS event-loop scheduling is the natural home
for the orchestration.

Suggested branching:
- `feat/stat-cost-decorator` — phase 1's `cost=` field on `@stat`,
  pure plumbing, lands independently.
- `feat/progressive-stats-server` — `process_table_scalars` /
  `_aggregates` split + new WS message types. Server side.
- `feat/progressive-stats-js` — `BuckarooStateOrchestrator` + WS
  message handlers + feature flag.
- `feat/progressive-stats-rollout` — flip the default flag once the
  three above are stable.

Last branch is the easy revert if anything goes wrong.
