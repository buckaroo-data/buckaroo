# Known issues: post-processing × scope-merged `merged_sd`

> PR #785 deferral note. The PR keeps today's post-processing handling
> structurally intact for the scope-merged `merged_sd`, but does not add
> exhaustive coverage for every post-processing method × scope
> interaction. This file documents what's working, what's punted, and
> why the punt is safe.

## Status quo in this PR

`_compute_scope_df(scope)` applies the active `post_processing_method`
on top of each scope's base df, *after* per-scope chain ops have run:

- `raw` scope: `sampled_df` → post-processing → SD computed against it.
- `clean` scope: `sampled_df` → clean ops → post-processing → SD.
- `filt` scope: `processed_df` directly (post-processing is already
  baked in upstream).

`_scope_cache_key` folds `post_processing_method` into the cache hash
so a pp method swap invalidates cached scope SDs.

Coverage that *does* exist:

- `test_hide_column_config_post_processing` (pre-existing, in
  `tests/unit/dataflow/`) — exercises `hide_post` end-to-end against
  `merged_sd['column']` column metadata. Still passes under this PR's
  scope-merged shape.
- `test_add_analysis` — exercises the basic
  post-processing-shapes-merged-sd path.

## What's punted

A general "every pp method × every scope" matrix. Specifically:

1. **PP methods that drop columns.** If pp drops column `a`, the raw
   scope SD (computed *before* pp drops it under the current code, but
   actually after — see "subtle"  below) should reflect what the user
   sees in the grid. Current code applies pp first, so the SD won't
   carry stats for the dropped column. But: bare keys for column `a`
   may already be present in `merged_sd` from `init_sd` or
   `cleaned_sd`, and the layering in `_merged_sd` doesn't remove them.
   Probably fine; not pinned by a test.
2. **PP methods that aggregate (group-by, agg).** Raw-scope `length`
   should arguably be the *raw* length (50K), not the post-aggregation
   length (5). Today's behaviour: bare `length` reflects the
   post-pp-aggregation length because `_compute_scope_df` returns the
   post-pp frame. Whether that's right or wrong is a UX call we
   haven't made.
3. **PP methods that add/rename columns.** Bare keys for a renamed
   column appear under the new name in raw scope; under the old name
   in `init_sd`-derived bare keys. The `_merged_sd` merge order
   determines which wins. Not pinned.
4. **Multiple PP methods chained.** Today the dataflow allows only one
   active `post_processing_method`, so this is hypothetical. If it
   changes, the per-scope pp application would need to apply the chain
   in order.

Subtle: re-read `_compute_scope_df` if you're touching this — the
order is (scope base) → (clean ops if clean scope) → (pp). The cache
key hashes `(chain, sampled_df_id, post_processing_method)` so any
combination of these mutating invalidates. A pp method that depends on
*state external to the dataflow* (env vars, global registry) would not
invalidate correctly. None exist today.

## Why the punt is safe

- **PP is rarely used.** The codebase ships `hide_post` and a couple
  of trivial pp methods; no aggregation pp, no rename pp.
- **The mechanism is structurally sound.** Cache key invalidation is
  in place; per-scope application is in place. Future pp methods that
  surface bugs will be caught by tests written *with* the method, not
  by speculative coverage written now.
- **The fallback if a pp method misbehaves is "bare keys look like the
  raw, not-pp'd dataset"** — surprising but not incorrect; the user
  can still see what's going on.

## How this slots in cleanly

When a future pp method needs coverage:

1. Add the pp method to the project's pp registry as today.
2. Write a test in `tests/unit/dataflow/scoped_summary_stats_test.py`
   exercising that method × each scope. Pattern matches the existing
   `test_hide_column_config_post_processing`.
3. If the test reveals a bug, the fix is almost certainly localized to
   either `_compute_scope_df` (per-scope application order) or the
   layering inside `_merged_sd`. No architectural change.

The cache-key + per-scope-application architecture is the right
abstraction for any pp method that's deterministic in its inputs
(`sampled_df` + `post_processing_method`). Non-deterministic pp would
need a new invalidation signal, but no such method exists or is on the
roadmap.

## What un-punting looks like

If we ever care to systematically cover this:

1. Enumerate the project's pp methods.
2. For each, decide what bare-key `length`, `mean`, etc. should mean
   when the method transforms the frame shape.
3. Write a test matrix.
4. Fix any bugs (likely in `_compute_scope_df` or `_merged_sd`).

Estimated cost: small if pp methods stay sparse; grows linearly with
each new pp method.

## Related

- Plan: `plans/0785-cleaning-scope-known-issues.md` — `cleaned_*` scope
  uses the same per-scope-application pattern and is similarly
  deferred.
- Plan: `plans/0785-codex-p2-analysis-klasses.md` — another deferred
  cache-key correctness item.
