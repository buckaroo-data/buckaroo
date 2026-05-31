"""End-to-end integration test for the sd channel through handle_ops_and_clean.

Covers all three transform shapes composing in one pipeline:
  - SDResult-return  : writes sd_updates merged into the live sd
  - sd-as-arg        : read-only MappingProxyType view; combine with SDResult
                       for the read-then-write pattern
  - df-only (legacy) : returns just a df; sd untouched

Interpreter-level proofs (apply-result! closure, proxy enforcement, ordering)
live in tests/unit/jlisp/test_sd_channel.py — this test exercises the full
PandasAutocleaning.handle_ops_and_clean pipeline.
"""

import polars as pl

from buckaroo.dataflow.autocleaning import AutocleaningConfig, PandasAutocleaning
from buckaroo.customizations.polars_commands import Command, SDResult
from buckaroo.jlisp.lisp_utils import s


class SDResultSeed(Command):
    """SDResult-return shape: writes sd_updates alongside the new df."""
    command_default = [s('sd_seed'), s('df'), 'col', '']
    command_pattern = [[3, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, col, val):
        return SDResult(df, {col: {'seed': val}})

    @staticmethod
    def transform_to_py(df, col, val):
        return "    # sd_seed"


class SDArgReadWrite(Command):
    """sd-as-arg + SDResult: reads the live sd, then writes via SDResult.
    Demonstrates the read-then-write pattern."""
    command_default = [s('sd_rw'), s('df'), s('sd'), 'col', '']
    command_pattern = [[4, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, sd, col, val):
        prior_seed = sd.get(col, {}).get('seed')
        return SDResult(df, {col: {'after': val, 'saw_seed': prior_seed}})

    @staticmethod
    def transform_to_py(df, sd, col, val):
        return "    # sd_rw"


class DfOnlyAddOne(Command):
    """df-only legacy shape: returns just a df; sd untouched."""
    command_default = [s('add_one'), s('df'), 'col']
    command_pattern = [None]

    @staticmethod
    def transform(df, col):
        return df.with_columns((pl.col(col) + 1).alias(col))

    @staticmethod
    def transform_to_py(df, col):
        return f"    df = df.with_columns((pl.col('{col}') + 1).alias('{col}'))"


class ThreeShapesConf(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [SDResultSeed, SDArgReadWrite, DfOnlyAddOne]
    name = ""


def test_three_shapes_compose_through_handle_ops_and_clean():
    """SDResult, sd-as-arg, and df-only commands compose in one pipeline.
    SDResult seeds sd; sd-as-arg reads the seed and writes again via
    SDResult; df-only mutates df without touching sd."""
    ac = PandasAutocleaning([ThreeShapesConf])
    df = pl.DataFrame({'a': [10, 20, 30]})
    ops = [[{'symbol': 'sd_seed'}, s('df'), 'a', 'hello'], [{'symbol': 'sd_rw'}, s('df'), s('sd'), 'a', 'world'],
        [{'symbol': 'add_one'}, s('df'), 'a']]
    cleaned_df, cleaning_sd, _gen, _ops = ac.handle_ops_and_clean(
        df, cleaning_method='', quick_command_args={}, existing_operations=ops)

    assert cleaned_df['a'].to_list() == [11, 21, 31]
    assert cleaning_sd['a']['seed'] == 'hello'
    assert cleaning_sd['a']['saw_seed'] == 'hello'
    assert cleaning_sd['a']['after'] == 'world'
