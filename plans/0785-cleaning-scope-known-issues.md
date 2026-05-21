# Known issues: `cleaned_*` scope deferral + `filter_active` gate bug

> PR #785 deferral note. The PR ships scope-merged `merged_sd` with
> raw + filt scopes; the third scope (`clean`) is *computed and cached*
> but not yet *layered into* `merged_sd`. The `filter_active` gate that
> chooses when to emit `filtered_*` keys has a known bug that is
> coupled to this deferral. Both punts travel together.

## Status quo in this PR

**What works:**
- `_populate_sd_cache` computes the `clean` scope SD and writes it to
  `summary_stats_cache` under `clean_sd_key`.
- The cache key includes `(chain, sampled_df_id, post_processing_method)`
  per scope, so the clean scope's entry invalidates correctly when its
  inputs change.
- `_compute_scope_df('clean')` runs the cleaning interpreter against
  `sampled_df`, applies post-processing, returns the cleaned df.

**What doesn't work:**
- `_merged_sd` reads the raw scope and (conditionally) the filt scope.
  It does not read the clean scope. There are no `cleaned_*` keys in
  `merged_sd` even when cleaning is active.
- The `filter_active` gate that chooses when to emit `filtered_*` keys
  is wrong when cleaning is active and search isn't.

## The `filter_active` gate bug

`_merged_sd` currently decides whether to emit `filtered_*` with:

```python
filter_active = self.filt_sd_key != self.raw_sd_key and self.filt_sd_key != ''
```

When **cleaning is active but no search filter is**:
- `raw` chain: `[]`
- `clean` chain: `[<cleaning ops>]`
- `filt` chain: `[<cleaning ops>]` (no quick-command ops)

So `filt_sd_key != raw_sd_key`, the gate fires, and the cleaning-affected
stats are mislabelled as `filtered_*` keys in `merged_sd`.

The failing test `test_cleaning_only_does_not_emit_filtered_keys` in
`tests/unit/dataflow/scoped_summary_stats_test.py` pins this. The test
must be `xfail`'d or skipped in this PR.

### Right fix

The gate should be on the chain-shape difference between `filt` and
`clean`, not between `filt` and `raw`. Once `cleaned_*` is also being
layered into `merged_sd`, the natural formulation is:

```python
filter_active = (
    split_chain_by_scope(self.operations)['filt']
    != split_chain_by_scope(self.operations)['clean']
)
cleaning_active = (
    split_chain_by_scope(self.operations)['clean']
    != split_chain_by_scope(self.operations)['raw']
)
```

…and `_merged_sd` layers in order: bare keys (raw), then `cleaned_*`
when `cleaning_active`, then `filtered_*` when `filter_active`.

Without `cleaned_*` in the picture, the gate has no clean reference
point — that's why the two punts are coupled.

## Why both punts are safe

- **Cleaning is rarely used.** The bare-keys path (raw scope) carries
  the dataset stats and works without cleaning. Most users never
  trigger the `cleaned_*` code path.
- **The `filtered_*` mislabel only fires when cleaning is on.** Users
  who don't clean don't see the bug. Users who do clean see something
  labelled `filtered_*` that's actually post-cleaning — confusing but
  not wrong stats, just wrong namespace.
- **The mechanism for `cleaned_*` is in place.** Cache, pointer trait,
  `_compute_scope_df('clean')` — all working. The only missing piece
  is `_merged_sd` reading + layering it.

## How this slots in cleanly

A follow-up PR needs three things:

### 1. Layer `cleaned_*` into `_merged_sd`

```python
# After raw bare keys are merged:
cleaning_active = (chains['clean'] != chains['raw'])
if cleaning_active and clean_sd:
    for col, stats in clean_sd.items():
        col_dict = base.setdefault(col, {})
        for stat_name, val in stats.items():
            col_dict[f'cleaned_{stat_name}'] = val
```

Mirrors the existing `filtered_*` layering. ~6 lines.

### 2. Fix the `filter_active` gate

Replace the key-inequality check with the chain-shape diff against the
clean scope (see "Right fix" above). ~3 lines.

### 3. Un-xfail the test

`test_cleaning_only_does_not_emit_filtered_keys` becomes a real pass.

Total scope of the follow-up PR: maybe 15 lines of dataflow.py plus a
test or two for `cleaned_*` (parallel to the existing `filtered_*`
tests). No architectural change, no new files, no JS.

## Frontend

#777's `?key` optional-pinned-row mechanism already handles arbitrary
prefixed keys. `cleaned_mean` / `cleaned_length` / etc. render the
same way `filtered_mean` does. No JS change needed.

## What un-punting looks like

A follow-up PR titled "feat(scoped-sd): wire cleaned_* into merged_sd"
that does the three things above and un-xfails the test. Should be a
short, focused PR — the substrate is already in place.

## Related

- Plan: `plans/0785-post-processing-known-issues.md` — same
  per-scope-application pattern, also deferred.
- Plan: `plans/0785-codex-p2-analysis-klasses.md` — another deferred
  cache-key correctness item.
