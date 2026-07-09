# Follow-up: make `analysis_klasses` an observable traitlet

> PR #789 follow-up note. #789 fixes Codex P2 by folding
> `id(self.analysis_klasses)` into `_scope_cache_key`, but the PR body
> explicitly punts on the deeper issue: ``analysis_klasses`` is a plain
> Python class attribute, not a traitlet, so the
> ``@observe('analysis_klasses')`` decorators on the dataflow don't
> fire when it's reassigned. The cache *key* now changes on swap; the
> cache *observer* still doesn't run. This file outlines what fixing
> the deeper issue would look like.

## Status quo

`CustomizableDataflow.analysis_klasses` is declared at
`buckaroo/dataflow/dataflow.py:301`:

```python
analysis_klasses: List[Type[ColAnalysis]] = [StylingAnalysis]
```

That's a plain class attribute with a PEP 526 type hint. It is *not* a
traitlets `List(...)`. Setting `dfc.analysis_klasses = new_list`
shadows the class attribute on the instance but does **not** fire the
``@observe`` callbacks declared on:

- `_summary_sd` (`@observe('processed_result', 'analysis_klasses')`)
- `_populate_sd_cache` (`@observe('summary_sd', 'operations', 'analysis_klasses')`)

The only existing caller that mutates the field is
`DataFlow.add_analysis` (dataflow.py:654-669), which calls
`self._handle_widget_change({})` at the end to force a recomputation.
That works *because* `add_analysis` knows it has to manually trigger.
Any other code path that sets `analysis_klasses` directly silently
fails to invalidate downstream state — including the new scope cache
from #785.

## Why #789's fix is partial

#789 makes ``_scope_cache_key`` depend on ``id(analysis_klasses)``.
That ensures a key collision can no longer happen across distinct
analysis-klass lists. But the observer that *populates* the cache
still doesn't fire on a direct ``analysis_klasses`` reassignment, so:

- ``add_analysis`` works (it manually triggers the cascade).
- ``dfc.analysis_klasses = [...]`` from external code does not (no
  observer fires; the cache stays at its old contents under its old
  keys, and the pointer traits still point at those old keys).

The cache-key contract is the load-bearing invariant for *correctness
under collision*, but observer firing is the invariant for
*propagation under user mutation*. Today only the first is fixed.

PR #789's test acknowledges this — it asserts at the
``_scope_cache_key`` level, not end-to-end through ``merged_sd``,
because it can't observe the propagation it would otherwise want to
test.

## The fix

Convert `analysis_klasses` from a plain class attribute to a traitlet:

```python
from traitlets import List as TList, Type as TType
# ...
analysis_klasses = TList(trait=TType(klass=ColAnalysis)).tag(config=True)
```

Set the default via `__init__` instead of class-level assignment so the
trait validation runs:

```python
def __init__(self, orig_df, debug=False, ..., analysis_klasses=None):
    super().__init__(...)
    if analysis_klasses is None:
        analysis_klasses = [StylingAnalysis]
    self.analysis_klasses = analysis_klasses
```

Once it's a traitlet, ``dfc.analysis_klasses = [...]`` fires the
existing ``@observe`` callbacks naturally. ``add_analysis`` no longer
needs the manual ``_handle_widget_change({})`` trigger.

## Subtleties

1. **Subclass overrides.** A subclass that overrides
   ``analysis_klasses = [...]`` at class level (see
   `ScopedDataflow.analysis_klasses` in `scoped_summary_stats_test.py`,
   and others sprinkled in `customizations/`) is using the old class-
   attribute mechanism. After conversion, those overrides need to move
   to `__init__` defaults or use `traitlets.default` decorators. ~6
   call sites to update across the test + customizations tree.
2. **Type/List trait validation.** `traitlets.Type(klass=ColAnalysis)`
   accepts subclasses of `ColAnalysis`. Today nothing in the codebase
   enforces this — `analysis_klasses` is a list of classes by
   convention only. The conversion would tighten that, which is good
   but may surface latent test fixtures that pass non-`ColAnalysis`
   objects (e.g. stat-group classes without the `ColAnalysis`
   ancestor).
3. **Observer fan-out cost.** Two observers fire on the new traitlet:
   ``_summary_sd`` and ``_populate_sd_cache``. Both already fire on
   ``processed_result`` / ``summary_sd``. A traitlet swap that doesn't
   also change ``processed_df`` would now trigger a redundant
   ``_summary_sd`` pass. Probably fine (analysis-klass swaps are
   rare), but worth measuring.

## Recommended path

**Defer for now.** #789 covers the correctness case (cache-key
collision). The propagation gap exists in theory but in practice
nobody mutates ``analysis_klasses`` outside ``add_analysis``. The
conversion is a 1–2-hour change with non-trivial test-fixture churn
across the customizations directory. Wait until either:

- A user-facing bug surfaces from someone setting
  ``analysis_klasses`` directly, or
- A separate refactor of ``CustomizableDataflow`` initialization is
  happening anyway (good time to fold this in).

## If/when we do it

- **Failing test (one CI run):** end-to-end version of #789's
  ``test_analysis_klasses_change_invalidates_scoped_sd`` that sets
  ``dfc.analysis_klasses = [...]`` and asserts a new stat klass's
  output appears in ``merged_sd``. Today it asserts at the cache-key
  level only; with the traitlet conversion it can assert at the
  ``merged_sd`` level.
- **Fix commit:** the traitlet declaration + `__init__` default +
  subclass override migration.
- **Regression coverage:** unchanged behaviour for
  ``add_analysis`` (it still works; the manual
  ``_handle_widget_change({})`` becomes redundant but stays harmless).

## Estimated scope

- ~20 lines in `dataflow.py`.
- ~6 subclass override sites to migrate (test fixtures + customizations).
- ~30 lines of new test.
- Total: half a day with the test-fixture churn, less if
  customizations are left alone (only the test fixtures move).
