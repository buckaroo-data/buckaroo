# Known issue: `analysis_klasses` not in scope cache key (Codex P2)

> PR #785 deferral note. Codex's review of #783 flagged two cache-key
> correctness issues: P1 (`raw_df` swap invalidation) and P2
> (`analysis_klasses` change invalidation). This PR fixes P1. P2 is
> deferred — documented here because the fix is mechanical and slots in
> cleanly when needed.

## The bug

`_scope_cache_key(chain)` currently hashes:

```python
hash_chain(chain, extra=f"{id(sampled_df)}|{post_processing_method}")
```

It does **not** include any identity for `analysis_klasses`. If a
developer mutates `analysis_klasses` on a live dataflow:

```python
dataflow.analysis_klasses = [DefaultSummaryStats, MyNewStat]
```

…and the op chain hasn't changed (and `sampled_df` and pp haven't
changed), `_populate_sd_cache` sees the same `_scope_cache_key()` for
each scope and reuses the existing cache entries. The new stat in
`MyNewStat` is silently absent from the cached SD.

## Why this is P2, not P1

- **P1 (`raw_df` swap)** fires on a normal user interaction:
  `dataflow.raw_df = new_df`. It's a UI-facing surface — broken P1 is a
  user-visible bug. Fixed in this PR.
- **P2 (`analysis_klasses` change)** fires only when a developer
  mutates `analysis_klasses` after dataflow construction. That's a
  developer / customization workflow, not a user interaction. No UI
  path exposes it.

In production today, `analysis_klasses` is set once at dataflow
construction via the class attribute or `extra_klasses` (see PR #784).
Mutation mid-session is a possibility for dev workflows but not for
end-user paths.

## The fix (when we get to it)

Same fold-into-`extra` pattern as P1. One line change in
`_scope_cache_key`:

```python
def _scope_cache_key(self, chain):
    sampled_id = id(self.sampled_df) if self.sampled_df is not None else 0
    pp = self.post_processing_method or ''
    klasses_id = id(self.analysis_klasses)   # ← new
    return hash_chain(chain, extra=f"{sampled_id}|{pp}|{klasses_id}")
```

`id(self.analysis_klasses)` is the cheap option — works because the
list/tuple is replaced wholesale on mutation. If we wanted to detect
in-place mutations (`analysis_klasses.append(...)`), we'd need a
content hash:

```python
klasses_id = tuple(id(k) for k in self.analysis_klasses)
```

`id()`-based is fine for the foreseeable use cases.

## Test

`tests/unit/dataflow/scoped_summary_stats_test.py` already has the
shape — `test_raw_df_change_invalidates_scoped_sd` covers P1. A
parallel test for P2:

```python
def test_analysis_klasses_change_invalidates_scoped_sd():
    """Codex P2: mutating analysis_klasses must invalidate cached SDs."""
    dfc = _build_dataflow()
    sd_before = dict(dfc.merged_sd['a'])
    # Add a new stat klass that contributes a new key
    dfc.analysis_klasses = [
        StylingAnalysis, DefaultSummaryStats, NewStatKlass,
    ]
    sd_after = dict(dfc.merged_sd['a'])
    assert 'new_stat_key' in sd_after, (
        "after analysis_klasses swap, the new stat's key should "
        "appear; otherwise we're reading a stale cache entry"
    )
```

## Why it slots in cleanly

- `hash_chain` already takes an `extra` arg (added in #785 for P1).
- `_scope_cache_key` is the single point where the hash is computed.
- No other observer or cache path changes.
- No JS change.

Estimated cost of the fix: one line, one test. Bundle into the next
PR that touches the dataflow cache (could be the cleaning-scope PR).

## Related

- Plan: `plans/0785-cleaning-scope-known-issues.md` — natural carrier
  for this fix in its follow-up PR.
- Plan: `plans/0785-post-processing-known-issues.md` — same family
  (cache-key correctness).
