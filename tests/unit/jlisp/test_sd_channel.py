"""Interpreter-level tests for the sd channel.

Three transform shapes share one mutable sd dict:
  - df-only            : transform returns df; sd untouched
  - SDResult-return    : transform returns SDResult(df, sd_updates);
                         interpreter merges sd_updates into the live sd
  - sd-as-arg          : command_default lists s('sd'); transform receives
                         a read-only MappingProxyType view of the current
                         sd state (post all upstream ops' mutations)

To write sd, a command returns SDResult — sd-as-arg is read-only.
A command can do both: take s('sd') as arg AND return SDResult, which
gives the read-then-write pattern.
"""

import pytest
import polars as pl

from buckaroo.jlisp.lisp_utils import s
from buckaroo.jlisp.configure_utils import configure_buckaroo, SDResult


class _CommandBase:
    """Bare base — not the customizations Command, just enough for configure_buckaroo."""
    pass


def _build_transform(*command_klasses):
    """Helper: build a buckaroo_transform callable from a set of Commands.
    Returns (transform_fn, ops_factory) where transform_fn is the lisp
    runner and the caller supplies operations manually."""
    _defaults, _patterns, buckaroo_transform, _to_py = configure_buckaroo(command_klasses)
    return buckaroo_transform


class SDResultCommand(_CommandBase):
    """Returns SDResult; interpreter must merge its sd_updates into sd."""
    command_default = [s('sdresult_op'), s('df'), 'col', '']
    command_pattern = [[3, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, col, val):
        return SDResult(df, {col: {'note': val}})

    @staticmethod
    def transform_to_py(df, col, val):
        return "    # sdresult_op"


def test_sdresult_merges_via_apply_result_closure():
    """A Command returning SDResult(df, sd_updates) has its sd_updates
    merged into the running sd dict via apply-result! (per-call closure
    over the mutable dict)."""
    buckaroo_transform = _build_transform(SDResultCommand)
    df = pl.DataFrame({'a': [1, 2, 3]})
    # Build the wrapped form by hand mirroring autocleaning's _run_df_interpreter:
    # (begin (set! df (apply-result! sd <op>)) df)
    op = [{'symbol': 'sdresult_op'}, s('df'), 'a', 'hello']
    instructions = [
        s('begin'),
        [s('set!'), s('df'), [s('apply-result!'), s('sd'), op]],
        s('df'),
    ]
    _ret_df, sd_after = buckaroo_transform(instructions, df, {})
    assert sd_after.get('a', {}).get('note') == 'hello'


class ReadOnlyAttemptCommand(_CommandBase):
    """Takes sd as arg and TRIES to mutate it top-level. The interpreter
    binds sd as MappingProxyType, so this raises TypeError."""
    command_default = [s('mutate_attempt'), s('df'), s('sd'), 'col', '']
    command_pattern = [[4, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, sd, col, val):
        sd[col] = {'note': val}  # top-level mutation — must raise
        return df

    @staticmethod
    def transform_to_py(df, sd, col, val):
        return "    # mutate_attempt"


def test_sd_arg_is_read_only_mappingproxy():
    """sd is bound in the lisp env as a MappingProxyType view. Commands
    that take s('sd') get the proxy; top-level mutation raises TypeError.
    Writes must go through SDResult."""
    buckaroo_transform = _build_transform(ReadOnlyAttemptCommand)
    df = pl.DataFrame({'a': [1, 2, 3]})
    op = [{'symbol': 'mutate_attempt'}, s('df'), s('sd'), 'a', 'hello']
    instructions = [
        s('begin'),
        [s('set!'), s('df'), [s('apply-result!'), s('sd'), op]],
        s('df'),
    ]
    with pytest.raises(TypeError):
        buckaroo_transform(instructions, df, {})


class SeedSDCommand(_CommandBase):
    """Writes via SDResult to seed sd for the next op."""
    command_default = [s('seed'), s('df'), 'col', 0]
    command_pattern = [[3, 'tag', 'type', 'integer']]

    @staticmethod
    def transform(df, col, val):
        return SDResult(df, {col: {'seed': val}})

    @staticmethod
    def transform_to_py(df, col, val):
        return "    # seed"


class ReadAndAssertSDCommand(_CommandBase):
    """Takes sd as arg, asserts it can see an upstream SDResult's contribution,
    then returns SDResult writing more sd_updates. Read-then-write pattern."""
    command_default = [s('read_assert'), s('df'), s('sd'), 'col', 0]
    command_pattern = [[4, 'tag', 'type', 'integer']]

    @staticmethod
    def transform(df, sd, col, expected_seed):
        actual_seed = sd.get(col, {}).get('seed')
        assert actual_seed == expected_seed, (
            f"sd-as-arg did not see upstream SDResult merge: "
            f"expected seed={expected_seed!r}, got {actual_seed!r}")
        return SDResult(df, {col: {'after': 2}})

    @staticmethod
    def transform_to_py(df, sd, col, expected_seed):
        return "    # read_assert"


def test_sd_arg_sees_upstream_sdresult_mutations():
    """A downstream sd-as-arg command reads the live (merged) sd; mutations
    from an earlier SDResult op are visible. Confirms the three shapes
    share one sd via env binding + apply-result! closure."""
    buckaroo_transform = _build_transform(SeedSDCommand, ReadAndAssertSDCommand)
    df = pl.DataFrame({'a': [1, 2, 3]})
    seed_op = [{'symbol': 'seed'}, s('df'), 'a', 1]
    read_op = [{'symbol': 'read_assert'}, s('df'), s('sd'), 'a', 1]
    instructions = [
        s('begin'),
        [s('set!'), s('df'), [s('apply-result!'), s('sd'), seed_op]],
        [s('set!'), s('df'), [s('apply-result!'), s('sd'), read_op]],
        s('df'),
    ]
    _ret_df, sd_after = buckaroo_transform(instructions, df, {})
    assert sd_after['a']['seed'] == 1
    assert sd_after['a']['after'] == 2
