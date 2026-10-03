"""Tests for PolarsStatPipeline: the PlColumn batch phase and the max_rows gate.

Mirrors the XorqStatPipeline tests in tests/unit/test_xorq_stats_v2.py for
the polars twin (#999).
"""
from typing import Any

import pandas as pd
import polars as pl
import pytest

from buckaroo.pluggable_analysis_framework.stat_func import stat, PlColumn, RawSeries
from buckaroo.pluggable_analysis_framework.stat_result import NOT_COMPUTED
from buckaroo.pluggable_analysis_framework.column_filters import is_numeric_not_bool
from buckaroo.pluggable_analysis_framework.typed_dag import build_column_dag
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.polars_stat_pipeline import PolarsStatPipeline


# ============================================================================
# Fixtures — a small DAG with one batch stat per phase
# ============================================================================

BATCH_CALLS = []


@stat()
def null_count(col: PlColumn) -> int:
    BATCH_CALLS.append(col.name)
    return col.expr.null_count()


@stat()
def length(col: PlColumn) -> int:
    return col.expr.len()


@stat()
def distinct_count(col: PlColumn) -> int:
    return col.expr.n_unique()


@stat(column_filter=is_numeric_not_bool)
def col_sum(col: PlColumn) -> Any:
    return col.expr.sum()


@stat()
def non_null_count(length: int, null_count: int) -> int:
    return length - null_count


@stat(max_rows=100)
def value_counts(ser: RawSeries) -> pd.Series:
    vc = ser.drop_nulls().value_counts(sort=True)
    return pd.Series(vc['count'].to_list(), index=vc[ser.name].to_list())


@stat()
def most_freq(value_counts: pd.Series) -> Any:
    return value_counts.index[0] if len(value_counts) else None


ALL_STATS = [null_count, length, col_sum, non_null_count, value_counts, most_freq]


def _frame(n_rows):
    return pl.DataFrame({'ints': list(range(n_rows)), 'strs': ['x'] * n_rows, 'bools': [True] * n_rows})


# ============================================================================
# @stat(max_rows=...) and build_column_dag
# ============================================================================

class TestMaxRows:
    def test_decorator_stores_max_rows(self):
        assert value_counts._stat_func.max_rows == 100
        assert null_count._stat_func.max_rows is None

    def test_build_column_dag_gates_on_row_count(self):
        stat_funcs = [f._stat_func for f in ALL_STATS]
        names = lambda funcs: {sf.name for sf in funcs}  # noqa: E731
        assert {'value_counts', 'most_freq'} <= names(build_column_dag(stat_funcs, pl.Int64))
        assert {'value_counts', 'most_freq'} <= names(build_column_dag(stat_funcs, pl.Int64, row_count=100))
        gated = names(build_column_dag(stat_funcs, pl.Int64, row_count=101))
        # The gated stat and its dependent drop; everything else stays.
        assert 'value_counts' not in gated
        assert 'most_freq' not in gated
        assert {'null_count', 'length', 'col_sum', 'non_null_count'} <= gated


# ============================================================================
# PolarsStatPipeline — batch phase
# ============================================================================

class TestPolarsBatchPhase:
    def test_batch_stat_called_once_per_column_and_lands_in_sd(self):
        BATCH_CALLS.clear()
        df = pl.DataFrame({'ints': [1, None, 3], 'strs': ['a', 'b', None], 'bools': [True, True, True]})
        pipeline = PolarsStatPipeline([null_count, length, non_null_count], unit_test=False)
        sd, errors = pipeline.process_df(df)
        assert errors == []
        assert sorted(BATCH_CALLS) == ['bools', 'ints', 'strs']
        assert sd['a']['null_count'] == 1
        assert sd['b']['null_count'] == 1
        assert sd['c']['null_count'] == 0
        assert sd['a']['length'] == 3
        assert sd['a']['non_null_count'] == 2
        assert sd['a']['orig_col_name'] == 'ints'

    def test_batch_stat_respects_column_filter(self):
        df = pl.DataFrame({'ints': [1, 2, 3], 'strs': ['a', 'b', 'c'], 'bools': [True, False, True]})
        pipeline = PolarsStatPipeline([col_sum], unit_test=False)
        sd, errors = pipeline.process_df(df)
        assert errors == []
        assert sd['a']['col_sum'] == 6
        assert 'col_sum' not in sd['b']
        assert 'col_sum' not in sd['c']

    def test_lazyframe_input(self):
        df = pl.DataFrame({'ints': [1, None, 3], 'strs': ['a', 'b', None]})
        pipeline = PolarsStatPipeline([null_count, length, non_null_count], unit_test=False)
        eager, _ = pipeline.process_df(df)
        lazy, errors = pipeline.process_df(df.lazy())
        assert errors == []
        assert lazy == eager

    def test_skip_columns_get_no_batch_stats(self):
        BATCH_CALLS.clear()
        df = pl.DataFrame({'ints': [1, 2], 'strs': ['a', 'b']})
        pipeline = PolarsStatPipeline([null_count], unit_test=False)
        sd, errors = pipeline.process_df(df, skip_columns={'strs'})
        assert errors == []
        assert BATCH_CALLS == ['ints']
        assert sd['b'] == {'orig_col_name': 'strs', 'rewritten_col_name': 'b'}

    def test_process_column_runs_the_batch_for_one_series(self):
        pipeline = PolarsStatPipeline([null_count, length, non_null_count], unit_test=False)
        ser = pl.Series('x', [1, None, None])
        result, errors = pipeline.process_column('x', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['null_count'] == 2
        assert result['non_null_count'] == 1

    def test_plain_stat_pipeline_reports_plcolumn_stats_as_errors(self):
        """A PlColumn stat only runs in PolarsStatPipeline's batch phase; the
        base pipeline reports that instead of a confusing missing-key error."""
        pipeline = StatPipeline([null_count], unit_test=False)
        ser = pl.Series('x', [1, None])
        result, errors = pipeline.process_column('x', ser.dtype, raw_series=ser)
        assert result['null_count'] is None
        assert len(errors) == 1
        assert 'PolarsStatPipeline' in str(errors[0].error)

    @pytest.mark.parametrize('weird_name', ['^a$', '*', '^.*$'])
    def test_regex_like_column_names_do_not_corrupt_other_columns(self, weird_name):
        """pl.col('^a$') is a regex selector that can expand to any number of
        outputs; the batch select must address columns literally."""
        df = pl.DataFrame({weird_name: [1, 2, 2], 'b': [1, 2, 3]})
        pipeline = PolarsStatPipeline([null_count, length, distinct_count, non_null_count], unit_test=False)
        sd, errors = pipeline.process_df(df)
        assert errors == []
        assert sd['a']['orig_col_name'] == weird_name
        assert (sd['a']['length'], sd['a']['null_count'], sd['a']['distinct_count']) == (3, 0, 2)
        assert (sd['b']['length'], sd['b']['null_count'], sd['b']['distinct_count']) == (3, 0, 3)

    def test_one_failing_expression_keeps_the_columns_other_batch_stats(self):
        """distinct_count can't run on pl.Object; length and null_count on the
        same column still can."""
        df = pl.DataFrame({'o': pl.Series([object(), object(), None], dtype=pl.Object), 'b': [1, 2, 3]})
        pipeline = PolarsStatPipeline([null_count, length, distinct_count], unit_test=False)
        sd, errors = pipeline.process_df(df)
        assert sd['a']['length'] == 3
        assert sd['a']['null_count'] == 1
        assert sd['a']['distinct_count'] is None
        assert [e.stat_key for e in errors] == ['distinct_count']
        assert (sd['b']['length'], sd['b']['null_count'], sd['b']['distinct_count']) == (3, 0, 3)


# ============================================================================
# PolarsStatPipeline — max_rows gate
# ============================================================================

class TestPolarsMaxRowsGate:
    def test_gated_on_101_rows(self):
        pipeline = PolarsStatPipeline(ALL_STATS, unit_test=False)
        sd, errors = pipeline.process_df(_frame(101))
        assert errors == []
        for col in sd.values():
            assert col['value_counts'] is NOT_COMPUTED
            assert col['most_freq'] is NOT_COMPUTED
            assert col['length'] == 101
            assert col['non_null_count'] == 101
        assert pipeline.gated_keys == ['most_freq', 'value_counts']

    def test_runs_on_100_rows(self):
        pipeline = PolarsStatPipeline(ALL_STATS, unit_test=False)
        sd, errors = pipeline.process_df(_frame(100))
        assert errors == []
        assert pipeline.gated_keys == []
        assert sd['b']['most_freq'] == 'x'
        assert sd['b']['value_counts'].to_dict() == {'x': 100}

    def test_gated_keys_reset_between_runs(self):
        pipeline = PolarsStatPipeline(ALL_STATS, unit_test=False)
        pipeline.process_df(_frame(101))
        assert pipeline.gated_keys == ['most_freq', 'value_counts']
        pipeline.process_df(_frame(5))
        assert pipeline.gated_keys == []

    def test_not_computed_sentinel_is_falsy_and_prints(self):
        assert not NOT_COMPUTED
        assert str(NOT_COMPUTED) == 'not computed'
