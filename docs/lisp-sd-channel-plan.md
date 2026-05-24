# Plan: sd as a first-class channel in the jlisp interpreter

## Goal

Extend the jlisp interpreter so a Command can interact with the running
summary-stats dict (`sd`) alongside the dataframe. Three transform
shapes must all work and compose freely in the same op pipeline:

1. **df-only (legacy).** `transform(df, ...) -> df`. All current Commands.
   No knowledge of sd. Must keep working unchanged.
2. **SDResult-return.** `transform(df, ...) -> SDResult(df, sd_updates)`.
   `sd_updates` is a partial `SDType` (`{col: {key: value}}`); the
   interpreter merges it into the running sd.
3. **sd-as-arg (read-only).** `transform(df, sd, ...) -> df`. The
   Command's `command_default` lists `s('sd')` right after `s('df')`;
   the interpreter passes a **read-only view** of the current sd
   (reflecting all upstream ops' mutations). To write, return
   `SDResult(...)` from the same call — sd-as-arg + SDResult-return
   together gives the read-then-write pattern.

A Command picks whichever shape(s) it needs. Combinations are allowed
(sd-as-arg + SDResult-return is the natural "read sd, decide, write
sd" pattern).

## Branch

Fresh branch off `main`: `feat/jlisp-sd-channel`. No dependency on PR
#744 (`feat/jlisp-transform-sd-updates`) — this PR supersedes #744
and the follow-up branches will rebase onto it.

## Mechanism

One mutable sd dict lives in the lisp env, bound to two names:

- `sd` → `MappingProxyType(sd_dict)`. This is what `s('sd')` resolves
  to inside transforms. Top-level mutations (`sd[col] = ...`,
  `sd.update(...)`, `del sd[col]`) raise `TypeError`. (Nested mutation
  via `sd[col]['note'] = ...` slips through the proxy — documented
  edge case; sd-as-arg is contractually read-only.)
- `apply-result!` → a per-call closure built inside `buckaroo_transform`.
  Captures `sd_dict` (the mutable underlying) by reference. Wraps each
  form's return value: if it's an `SDResult`, the closure merges
  `result.sd_updates` into `sd_dict` and returns `result.df`; otherwise
  passes through unchanged.

`apply-result!` is per-call (not a primitive registered at
`configure_buckaroo` time) precisely so the closure has access to the
mutable dict while the rest of the lisp env only sees the proxy.

`wrap_set_df` wraps each form:
```
(set! df (apply-result! sd <form>))
```

Each shape lights up through this:

- **df-only**: transform returns df. `apply-result!` passes it through.
  `set! df` updates the binding. Existing behavior.
- **SDResult-return**: transform returns `SDResult`. `apply-result!`
  merges sd_updates into the live dict, returns the bare df.
  `set! df` updates the binding.
- **sd-as-arg**: `s('sd')` in `command_default` resolves to the proxy.
  Transform reads from it. To write, transform returns `SDResult` and
  the SDResult-return path handles it.

## SDResult class

```python
# buckaroo/jlisp/configure_utils.py
from dataclasses import dataclass
from typing import Any
from .lisp_utils import SDType  # or wherever SDType lives

@dataclass(frozen=True)
class SDResult:
    """Return type for a Command transform that contributes sd_updates
    alongside the new df. The interpreter merges `sd_updates` into the
    running sd dict; downstream ops in the same pipeline see the merged
    state."""
    df: Any
    sd_updates: SDType
```

Re-exported from each `Command`-defining module so authors get it
alongside their Command import:

```python
# buckaroo/customizations/polars_commands.py
from ..jlisp.configure_utils import SDResult  # noqa: F401 (re-export)
```

Same pattern in `all_transforms.py`, `pandas_commands.py`,
`auto_clean/cleaning_commands.py`. Command authors write
`from buckaroo.customizations.polars_commands import Command, SDResult`.

Dispatch is `isinstance(result, SDResult)` — no tuple-shape heuristic.
A future `PivotResult` would just be another `@dataclass(frozen=True)`
in `configure_utils.py` with its own handler branch in `apply-result!`.

## Public API

```python
# buckaroo/jlisp/configure_utils.py
def buckaroo_transform(instructions, df, initial_sd):
    """Run `instructions` against `df`. `initial_sd` seeds the in-env sd
    dict (deep-copied — caller's nested dicts are untouched). Transforms
    interact with sd via two channels: returning SDResult (write) or
    listing s('sd') in command_default for a read-only view.

    Returns (df_after, sd_after). `sd_after` is the framework's
    deep-copied dict, with all op mutations applied."""

# buckaroo/dataflow/autocleaning.py
def _run_df_interpreter(self, df, operations, initial_sd):
    """Same contract — returns (df, sd)."""
```

Both arguments are required (no `=None` default — callers pass `{}` if
they have nothing to seed). `initial_sd` is **deep-copied** at the
boundary; caller-owned nested dicts can't leak op mutations back.

## Call-site updates

- `handle_ops_and_clean`:
  ```python
  cleaning_ops, cleaning_sd = self.produce_cleaning_ops(df, cleaning_method)
  ...
  cleaned_df, cleaning_sd = self._run_df_interpreter(df, final_ops, cleaning_sd)
  merged_cleaned_df = self.make_origs(df, cleaned_df, cleaning_sd)
  ```
  Pass `cleaning_sd` as `initial_sd` so sd-as-arg readers see autocleaning
  analysis state (`orig_col_name`, `_type`, `add_orig`, etc.) along with
  upstream-op contributions. The interpreter returns the same (deep-copied
  and mutated) dict — no separate `merge_sds` call after.
- `DataFlow._run_df_interpreter` pass-through wrapper in `dataflow.py`:
  matches the new signature and returns the tuple.
- Test helpers in `tests/unit/commands/` (`assert_to_py_same_transform_df`
  in `command_test.py`, `pandas_commands_test.py`, `polars_command_test.py`):
  `tdf, _sd = transform_df(tdf_ops, test_df.copy(), {})`.
- `test_run_df_interpreter` in `autocleaning_pd_test.py`: unpack the tuple.

## to_py interpreter

The codegen interpreter (`buckaroo_to_py`) doesn't run transforms — it
stringifies them. But ops that reference `s('sd')` will trip the env
lookup. Fix: pass `{'df': 5, 'sd': {}}` as the placeholder env
(currently `{'df': 5}`). Cheap; no semantic change.

`transform_to_py` for sd-aware commands receives `5, {}` as its first
two args and ignores them. Authors decide what to emit — typically the
df-only equivalent line if there is one (the generated Python is a
standalone script with no `sd` variable), or `# no codegen — sd-only op`
otherwise. Documented on `Command`'s docstring.

`apply-result!` doesn't exist in the to_py interpreter; ops arriving at
codegen are raw ops, not the wrapped `(set! df (apply-result! ...))`
forms (`buckaroo_to_py` walks `instructions` directly, no wrap_set_df).

## Tests

### Interpreter unit tests — `tests/unit/jlisp/test_sd_channel.py` (new file)

Three focused tests at the smallest reasonable scope:

1. **`test_sdresult_merges_via_apply_result_closure`** — single
   SDResult-returning command, run through `buckaroo_transform` directly
   (not `handle_ops_and_clean`), assert `sd_after[col][key] == value`.

2. **`test_sd_arg_is_read_only_mappingproxy`** — sd-as-arg command does
   `sd[col] = ...` inside its transform; `pytest.raises(TypeError)`
   around the `buckaroo_transform` call.

3. **`test_sd_arg_sees_upstream_sdresult_mutations`** — two ops in one
   pipeline: first returns `SDResult` writing `{a: {seed: 1}}`; second
   takes `s('sd')`, reads `sd['a']['seed']`, asserts it sees `1`, then
   returns `SDResult` writing `{a: {after: 2}}`. After: assert both
   `seed=1` and `after=2` in `sd_after`.

### Integration test — `tests/unit/dataflow/autocleaning_pl_test.py`

One end-to-end test:

4. **`test_three_shapes_compose_through_handle_ops_and_clean`** — pipeline
   `[sdresult_op, sd_arg_op, df_only_op]`. The `sdresult_op` seeds sd; the
   `sd_arg_op` reads + writes (returns `SDResult`); the `df_only_op` does
   a real df transform. After `handle_ops_and_clean`: `cleaning_sd`
   contains both ops' contributions, `cleaned_df` has the df transform
   applied.

Per [[feedback_minimal_tests]]: 4 tests total, one per behavior, no
fallback/edge-case tests.

## Files touched

```
buckaroo/jlisp/configure_utils.py                  # SDResult, apply-result! closure, sd proxy, new signature, deepcopy
buckaroo/dataflow/autocleaning.py                  # _run_df_interpreter signature + wrap_set_df
buckaroo/dataflow/dataflow.py                      # pass-through wrapper signature
buckaroo/customizations/all_transforms.py          # re-export SDResult
buckaroo/customizations/polars_commands.py         # re-export SDResult
buckaroo/customizations/pandas_commands.py         # re-export SDResult
buckaroo/auto_clean/cleaning_commands.py           # re-export SDResult
tests/unit/jlisp/test_sd_channel.py                # 3 new interpreter unit tests
tests/unit/dataflow/autocleaning_pl_test.py        # 1 new integration test
tests/unit/dataflow/autocleaning_pd_test.py        # update test_run_df_interpreter unpack
tests/unit/commands/command_test.py                # update transform_df call
tests/unit/commands/pandas_commands_test.py        # update transform_df call
tests/unit/commands/polars_command_test.py         # update transform_df call
```

## Out of scope (follow-ups, not this PR)

- Migrating polars `Search` (currently SDResult-shaped on smorgasbord)
  to use the new contract.
- Key-rewriting op-contributed sd keys onto buckaroo's internal a/b/c
  names. Was a band-aid in PR #744's follow-up; separate concern.
- Pandas/polars `Search` highlight wiring through to JS.
- Updating any existing Command to take sd. The point of this PR is the
  contract, not consumers.

## Test plan (PR checklist)

- [ ] `pytest tests/unit/jlisp/ tests/unit/dataflow/ tests/unit/commands/`
- [ ] Full unit suite (excluding `contrib/` and `file_cache/` which need
      optional deps): `pytest tests/unit/ --ignore=tests/unit/contrib --ignore=tests/unit/file_cache`
- [ ] CI green

## TDD ordering (per global rule)

1. Commit the 4 new tests as failing (they fail because `SDResult`
   doesn't exist, `_run_df_interpreter`'s signature is wrong, sd isn't
   bound, the proxy isn't enforcing). Push, watch CI fail.
2. Bundle the implementation + signature-adapting call-site updates in
   one commit. Push, watch CI pass.

The signature-update touches to existing tests (`test_run_df_interpreter`,
the `assert_to_py_same_transform_df` helpers) are not new failing
assertions — they're adapting to the new signature. They belong in the
fix commit, not the failing-tests commit.

## Supersession

This PR replaces PR #744. After landing:

- Close #744.
- The smorgasbord branch (`fix/wrap-text-and-pinned-row-height`) and
  downstream PRs that depend on PR #744's contract (#745 polars-search,
  #748 init-sd-augmentation, etc.) need to rebase: their tuple-returning
  Search migrates to `SDResult`, the rest of the wiring stays the same
  because the interpreter already accepts the new return shape.
