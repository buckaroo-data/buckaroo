"""Tests for ibis-based analysis classes.

All tests use ibis.memtable(pd.DataFrame(...)) — no xorq or remote backend
required. Tests are skipped if ibis is not installed.
"""
import pandas as pd
import pytest

ibis = pytest.importorskip("ibis")

from buckaroo.pluggable_analysis_framework.ibis_analysis import (  # noqa: E402
    IbisAnalysisPipeline,
)
from buckaroo.customizations.ibis_stats_v2 import (  # noqa: E402
    IbisTypingStats,
    IbisBaseSummaryStats,
    IbisNumericStats,
    IbisComputedSummaryStats,
    IBIS_ANALYSIS,
)


# ============================================================
# Helpers
# ============================================================

def _make_table():
    """Mixed-type test table."""
    return ibis.memtable(pd.DataFrame({
        'ints': [1, 2, 3, 4, 5],
        'floats': [1.1, 2.2, 3.3, 4.4, 5.5],
        'strs': ['a', 'b', 'c', 'd', 'e'],
        'bools': [True, False, True, False, True],
    }))


def _make_table_with_nulls():
    """Table with null values."""
    return ibis.memtable(pd.DataFrame({
        'vals': [1.0, None, 3.0, None, 5.0],
        'strs': ['a', None, 'c', None, 'e'],
    }))


# ============================================================
# TestIbisTypingStats
# ============================================================

class TestIbisTypingStats:
    def test_int_column(self):
        pipeline = IbisAnalysisPipeline([IbisTypingStats])
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert stats['ints']['is_numeric'] is True
        assert stats['ints']['is_integer'] is True
        assert stats['ints']['is_float'] is False
        assert stats['ints']['_type'] == 'integer'

    def test_float_column(self):
        pipeline = IbisAnalysisPipeline([IbisTypingStats])
        table = _make_table()
        stats = pipeline.execute(table, ['floats'])
        assert stats['floats']['is_numeric'] is True
        assert stats['floats']['is_float'] is True
        assert stats['floats']['_type'] == 'float'

    def test_string_column(self):
        pipeline = IbisAnalysisPipeline([IbisTypingStats])
        table = _make_table()
        stats = pipeline.execute(table, ['strs'])
        assert stats['strs']['is_string'] is True
        assert stats['strs']['is_numeric'] is False
        assert stats['strs']['_type'] == 'string'

    def test_bool_column(self):
        pipeline = IbisAnalysisPipeline([IbisTypingStats])
        table = _make_table()
        stats = pipeline.execute(table, ['bools'])
        assert stats['bools']['is_bool'] is True
        assert stats['bools']['_type'] == 'boolean'

    def test_datetime_column(self):
        table = ibis.memtable(pd.DataFrame({
            'ts': pd.to_datetime(['2021-01-01', '2021-01-02', '2021-01-03']),
        }))
        pipeline = IbisAnalysisPipeline([IbisTypingStats])
        stats = pipeline.execute(table, ['ts'])
        assert stats['ts']['is_datetime'] is True
        assert stats['ts']['_type'] == 'datetime'


# ============================================================
# TestIbisBaseSummaryStats
# ============================================================

class TestIbisBaseSummaryStats:
    def test_numeric_column(self):
        pipeline = IbisAnalysisPipeline([IbisBaseSummaryStats])
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert stats['ints']['length'] == 5
        assert stats['ints']['null_count'] == 0
        assert stats['ints']['min'] == 1.0
        assert stats['ints']['max'] == 5.0
        assert stats['ints']['distinct_count'] == 5

    def test_string_column_no_min_max(self):
        pipeline = IbisAnalysisPipeline([IbisBaseSummaryStats])
        table = _make_table()
        stats = pipeline.execute(table, ['strs'])
        assert stats['strs']['length'] == 5
        assert stats['strs']['null_count'] == 0
        assert stats['strs']['distinct_count'] == 5
        # min/max not present for strings (expression returns None)
        assert 'min' not in stats['strs']
        assert 'max' not in stats['strs']

    def test_with_nulls(self):
        pipeline = IbisAnalysisPipeline([IbisBaseSummaryStats])
        table = _make_table_with_nulls()
        stats = pipeline.execute(table, ['vals'])
        assert stats['vals']['null_count'] == 2
        assert stats['vals']['length'] == 5

    def test_bool_column_no_min_max(self):
        """Bool columns: ibis boolean.is_numeric() is False, so no min/max."""
        pipeline = IbisAnalysisPipeline([IbisBaseSummaryStats])
        table = _make_table()
        stats = pipeline.execute(table, ['bools'])
        assert stats['bools']['length'] == 5
        # ibis boolean.is_numeric() returns False
        assert 'min' not in stats['bools']
        assert 'max' not in stats['bools']


# ============================================================
# TestIbisNumericStats
# ============================================================

class TestIbisNumericStats:
    def test_int_column(self):
        pipeline = IbisAnalysisPipeline([IbisNumericStats])
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert 'mean' in stats['ints']
        assert abs(stats['ints']['mean'] - 3.0) < 0.01

    def test_float_column(self):
        pipeline = IbisAnalysisPipeline([IbisNumericStats])
        table = _make_table()
        stats = pipeline.execute(table, ['floats'])
        assert 'mean' in stats['floats']
        assert 'std' in stats['floats']
        assert 'median' in stats['floats']

    def test_string_column_excluded(self):
        pipeline = IbisAnalysisPipeline([IbisNumericStats])
        table = _make_table()
        stats = pipeline.execute(table, ['strs'])
        assert 'mean' not in stats['strs']
        assert 'std' not in stats['strs']
        assert 'median' not in stats['strs']

    def test_bool_column_excluded(self):
        pipeline = IbisAnalysisPipeline([IbisNumericStats])
        table = _make_table()
        stats = pipeline.execute(table, ['bools'])
        assert 'mean' not in stats['bools']
        assert 'std' not in stats['bools']


# ============================================================
# TestIbisComputedSummaryStats
# ============================================================

class TestIbisComputedSummaryStats:
    def test_derived_stats(self):
        pipeline = IbisAnalysisPipeline([
            IbisBaseSummaryStats,
            IbisComputedSummaryStats,
        ])
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert stats['ints']['non_null_count'] == 5
        assert stats['ints']['nan_per'] == 0.0
        assert stats['ints']['distinct_per'] == 1.0

    def test_with_nulls(self):
        pipeline = IbisAnalysisPipeline([
            IbisBaseSummaryStats,
            IbisComputedSummaryStats,
        ])
        table = _make_table_with_nulls()
        stats = pipeline.execute(table, ['vals'])
        assert stats['vals']['nan_per'] == 2 / 5
        assert stats['vals']['non_null_count'] == 3


# ============================================================
# TestIbisFullPipeline
# ============================================================

class TestIbisFullPipeline:
    def test_mixed_type_df(self):
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats = pipeline.execute(table, table.columns)

        # All columns have base stats
        for col in table.columns:
            assert 'length' in stats[col]
            assert 'null_count' in stats[col]
            assert '_type' in stats[col]
            assert 'distinct_count' in stats[col]

        # Numeric columns have mean
        assert 'mean' in stats['ints']
        assert 'mean' in stats['floats']

        # Non-numeric don't
        assert 'mean' not in stats['strs']
        assert 'mean' not in stats['bools']

        # Type classification
        assert stats['ints']['_type'] == 'integer'
        assert stats['floats']['_type'] == 'float'
        assert stats['strs']['_type'] == 'string'
        assert stats['bools']['_type'] == 'boolean'

    def test_with_nulls(self):
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table_with_nulls()
        stats = pipeline.execute(table, table.columns)

        assert stats['vals']['nan_per'] == 2 / 5
        assert stats['strs']['nan_per'] == 2 / 5

    def test_process_df_interface(self):
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats, errors = pipeline.process_df(table)
        assert errors == {}
        assert len(stats) == 4

    def test_single_column(self):
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert len(stats) == 1
        assert 'ints' in stats

    def test_computed_stats_present(self):
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats = pipeline.execute(table, ['ints'])
        assert 'non_null_count' in stats['ints']
        assert 'nan_per' in stats['ints']
        assert 'distinct_per' in stats['ints']


# ============================================================
# TestIbisAnalysisPipelineWithoutXorq
# ============================================================

class TestIbisAnalysisPipelineWithoutXorq:
    def test_pipeline_works_without_xorq(self):
        """IbisAnalysisPipeline should work if ibis is installed but xorq is not."""
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats, errors = pipeline.process_df(table)
        assert errors == {}
        assert len(stats) == 4

    def test_pipeline_with_empty_table(self):
        table = ibis.memtable(pd.DataFrame({'a': pd.Series([], dtype='int64')}))
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        stats = pipeline.execute(table, ['a'])
        assert stats['a']['length'] == 0

    def test_pipeline_default_columns(self):
        """process_df with no columns arg defaults to all columns."""
        pipeline = IbisAnalysisPipeline(IBIS_ANALYSIS)
        table = _make_table()
        stats, errors = pipeline.process_df(table)
        assert set(stats.keys()) == set(table.columns)
