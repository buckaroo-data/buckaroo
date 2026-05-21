# Follow-up: lean on xorq's expression cache for xorq-backed scopes

> PR #785 follow-up note. The PR ships a Python-internal
> `summary_stats_cache` that works the same way regardless of backend.
> For the xorq backend specifically, xorq's own expression cache
> already memoizes aggregation results — duplicating the cache layer in
> Python is partial redundancy. Refining this is a follow-up; this file
> captures the design space.

## What's in this PR

`_populate_sd_cache` writes per-scope SDs into `summary_stats_cache`
keyed by `_scope_cache_key`. Same path for pandas, polars, xorq. SD
dicts are stored directly (no parquet-b64 wire format — that was
removed when the cache went un-synced).

This works for all backends. It's just *suboptimal* for xorq.

## Why it's redundant for xorq

xorq evaluates ibis expressions lazily and has expression-level caching
built in — when you call `.execute()` on an expression that's been
executed before with the same inputs, xorq can serve the result from
its cache without re-running the engine query. `XorqStatPipeline` is
the path that builds + executes the aggregation expression for
`summary_sd`.

So when buckaroo's `_populate_sd_cache` does:

1. Compute `_scope_cache_key` for the scope's chain.
2. Check `summary_stats_cache` — miss.
3. Call `_get_summary_sd(scope_df)` to compute the SD.
4. Inside that, `XorqStatPipeline.compile_batch_expr` builds the
   aggregation expression and executes it.
5. **xorq's own cache decides whether to actually run the query or
   serve a cached result.**
6. Store the SD dict in `summary_stats_cache`.

Steps 1, 2, and 6 are buckaroo's cache layer. Step 5 is xorq's cache
layer. The two coexist; xorq's invalidation may differ from buckaroo's
(xorq invalidates on expression-content change; buckaroo invalidates on
chain + sampled_df identity + post-processing).

## Two paths to clean this up

### Thin path: leave as-is

Buckaroo's cache is small (dict of SD dicts, not the data itself).
Memory cost is negligible. xorq's cache handles the heavy lifting
under the hood. The double layer is wasteful but not harmful.

Recommended unless we run into a concrete problem.

### Lean path: skip the Python cache for xorq scopes

For xorq-backed dataflows, `_populate_sd_cache` could skip the
`summary_stats_cache` write (and the corresponding read in
`_merged_sd`) entirely, letting xorq's expression cache handle reuse.

Pointer traits (`raw_sd_key` / `clean_sd_key` / `filt_sd_key`) would
still get updated for downstream consistency — `_merged_sd` reads them
to decide what's in scope, even if it then reaches through to compute
the SD live (which hits the xorq cache).

Mechanics:

```python
def _populate_sd_cache(self, _change):
    if self.processed_df is None:
        return
    chains = split_chain_by_scope(self.operations)
    keys = {scope: self._scope_cache_key(chain)
            for scope, chain in chains.items()}

    # Always update pointer traits.
    self.raw_sd_key  = keys['raw']
    self.clean_sd_key = keys['clean']
    self.filt_sd_key = keys['filt']

    if self._cache_is_external():   # ← new hook
        return  # xorq handles its own cache

    # ... existing pandas/polars cache fill ...
```

`_cache_is_external()` would be `False` on `DataFlow`, `True` on
`XorqServerDataflow` (or any backend with engine-level caching).

`_merged_sd` then needs to handle the "no cache, compute live" path
for xorq scopes — which on xorq is cheap because xorq's cache catches
the repeat.

### What it costs to switch to lean

- A `_cache_is_external()` hook on the dataflow.
- `_merged_sd` learns to compute live when the hook says external.
- One test pinning that xorq scopes work without `summary_stats_cache`.
- Removing the Python-side cache invalidation worry for xorq (its own
  cache handles correctness).

Estimated cost: ~30 lines + one test. Defer until we have a reason to
care (memory pressure, observability gain, or a correctness mismatch
between the two cache layers).

## When to revisit

Concrete triggers:

1. **Memory pressure.** `summary_stats_cache` grows monotonically.
   For a long xorq session with many filter states, we hold
   thousands of SD dicts in process. If this surfaces as a problem,
   pruning xorq writes is the cleanest fix.
2. **Stale-cache mismatch.** If buckaroo's invalidation diverges from
   xorq's (e.g. buckaroo thinks the chain is the same but xorq's
   expression changed for some other reason), the Python cache might
   serve stale SDs that xorq would correctly recompute. Hypothetical
   today.
3. **Project-stats workflow churn.** PR #784's project stats path
   loads `extra_klasses` per session. If a host swaps a project stat
   file mid-session and the session is reloaded, both caches need to
   invalidate together. Xorq's cache invalidates correctly on
   expression-content change; buckaroo's might not (see also the
   Codex P2 note: `plans/0785-codex-p2-analysis-klasses.md`).

## Related

- Plan: `plans/0785-codex-p2-analysis-klasses.md` — `analysis_klasses`
  identity in cache key; relevant if project stats change mid-session.
- Plan: `plans/0785-cleaning-scope-known-issues.md` — cleaned scope
  deferral; same cache substrate.
- Plan: `plans/0785-post-processing-known-issues.md` — post-processing
  in cache key; another correctness item for the Python cache.
