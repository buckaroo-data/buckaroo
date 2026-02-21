"""Tests for v2 @stat function equivalents for Polars DataFrames.

Mirrors test_pd_stats_v2.py structure for polars-native stat functions.
"""
import math
from datetime import datetime

import numpy as np
import pandas as pd
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline

from buckaroo.customizations.pl_stats_v2 import (
    pl_typing_stats, _type,
    pl_base_summary_stats, pl_numeric_stats,
    computed_default_summary_stats,
    pl_histogram_series, histogram,
    PL_ANALYSIS_V2,
)


# ============================================================================
# Tests: pl_typing_stats
# ============================================================================

class TestPlTypingStats:
    def test_numeric_int(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_numeric'] is True
        assert result['is_integer'] is True
        assert result['is_float'] is False
        assert result['is_bool'] is False
        assert result['dtype'] == str(ser.dtype)

    def test_numeric_float(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [1.0, 2.5, 3.0])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_float'] is True
        assert result['is_numeric'] is True

    def test_string(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c'])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_string'] is True
        assert result['is_numeric'] is False

    def test_bool(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [True, False, True])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_bool'] is True

    def test_datetime(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [datetime(2021, 1, 1), datetime(2021, 1, 2)])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_datetime'] is True

    def test_memory_usage(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['memory_usage'] > 0


# ============================================================================
# Tests: _type (reused from pd_stats_v2, driven by pl_typing_stats)
# ============================================================================

class TestPlTypeComputed:
    def _run(self, ser):
        pipeline = StatPipeline([pl_typing_stats, _type], unit_test=False)
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        return result['_type']

    def test_integer(self):
        assert self._run(pl.Series('test', [1, 2, 3])) == 'integer'

    def test_float(self):
        assert self._run(pl.Series('test', [1.0, 2.0, 3.0])) == 'float'

    def test_string(self):
        assert self._run(pl.Series('test', ['a', 'b', 'c'])) == 'string'

    def test_boolean(self):
        assert self._run(pl.Series('test', [True, False])) == 'boolean'

    def test_datetime(self):
        assert self._run(pl.Series('test', [datetime(2021, 1, 1)])) == 'datetime'


# ============================================================================
# Tests: pl_base_summary_stats
# ============================================================================

class TestPlBaseSummaryStats:
    def test_numeric_basics(self):
        pipeline = StatPipeline([pl_base_summary_stats], unit_test=False)
        ser = pl.Series('test', [1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['length'] == 5
        assert result['null_count'] == 0
        assert result['min'] == 1
        assert result['max'] == 5
        assert 'mean' not in result

    def test_with_nulls(self):
        pipeline = StatPipeline([pl_base_summary_stats], unit_test=False)
        ser = pl.Series('test', [1, None, 3, None, 5])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['null_count'] == 2
        assert result['length'] == 5

    def test_string_column(self):
        pipeline = StatPipeline([pl_base_summary_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert 'mean' not in result
        assert 'std' not in result
        assert math.isnan(result['min'])
        assert math.isnan(result['max'])

    def test_bool_column(self):
        """Bool columns should NOT get numeric min/max."""
        pipeline = StatPipeline([pl_base_summary_stats], unit_test=False)
        ser = pl.Series('test', [True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert 'mean' not in result
        assert math.isnan(result['min'])

    def test_value_counts_present(self):
        pipeline = StatPipeline([pl_base_summary_stats], unit_test=False)
        ser = pl.Series('test', [1, 1, 2, 3])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert isinstance(result['value_counts'], pd.Series)
        assert result['value_counts'].iloc[0] == 2  # '1' is most frequent


# ============================================================================
# Tests: pl_numeric_stats
# ============================================================================

class TestPlNumericStats:
    def test_int_column(self):
        pipeline = StatPipeline([pl_numeric_stats], unit_test=False)
        ser = pl.Series('test', [1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['mean'] == 3.0
        assert result['median'] == 3.0
        assert isinstance(result['std'], float)

    def test_float_column(self):
        pipeline = StatPipeline([pl_numeric_stats], unit_test=False)
        ser = pl.Series('test', [1.0, 2.0, 3.0])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['mean'] == 2.0

    def test_bool_column_excluded(self):
        """Bool columns are excluded by column_filter — keys absent."""
        pipeline = StatPipeline([pl_numeric_stats], unit_test=False)
        ser = pl.Series('test', [True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'mean' not in result
        assert 'std' not in result
        assert 'median' not in result

    def test_string_column_excluded(self):
        """String columns are excluded by column_filter — keys absent."""
        pipeline = StatPipeline([pl_numeric_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'mean' not in result

    def test_all_null_numeric(self):
        """All-null numeric column returns nan, not 0."""
        pipeline = StatPipeline([pl_numeric_stats], unit_test=False)
        ser = pl.Series('test', [None, None, None], dtype=pl.Float64)
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert math.isnan(result['mean'])
        assert math.isnan(result['std'])
        assert math.isnan(result['median'])


# ============================================================================
# Tests: histogram
# ============================================================================

class TestPlHistogram:
    def _make_pipeline(self):
        return StatPipeline(
            [pl_typing_stats, pl_base_summary_stats, pl_numeric_stats,
             computed_default_summary_stats,
             pl_histogram_series, histogram],
            unit_test=False,
        )

    def test_numeric_histogram(self):
        pipeline = self._make_pipeline()
        ser = pl.Series('test', np.random.randn(100).tolist())
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)
        assert len(result['histogram']) > 0

    def test_string_histogram(self):
        pipeline = self._make_pipeline()
        ser = pl.Series('test', ['a', 'b', 'c', 'a', 'b'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)

    def test_bool_histogram(self):
        """Bool columns get categorical histogram."""
        pipeline = self._make_pipeline()
        ser = pl.Series('test', [True, False, True, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)

    def test_all_null_numeric(self):
        """All-null numeric column should still produce histogram."""
        pipeline = self._make_pipeline()
        ser = pl.Series('test', [None, None, None], dtype=pl.Float64)
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result


# ============================================================================
# Full pipeline integration tests
# ============================================================================

class TestPlFullPipeline:
    def test_mixed_df(self):
        """Pipeline handles a polars DataFrame with mixed column types."""
        df = pl.DataFrame({
            'ints': [1, 2, 3, 4, 5],
            'floats': [1.1, 2.2, 3.3, 4.4, 5.5],
            'strs': ['a', 'b', 'c', 'd', 'e'],
            'bools': [True, False, True, False, True],
        })
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)
        assert len(result) == 4

        # Numeric columns have mean; non-numeric don't
        for col_key, col_stats in result.items():
            assert 'length' in col_stats
            assert 'dtype' in col_stats
            assert '_type' in col_stats
            assert 'distinct_count' in col_stats
            assert 'nan_per' in col_stats
            assert 'histogram' in col_stats

        # Build lookup by _type
        by_type = {}
        for col_key, col_stats in result.items():
            by_type[col_stats['_type']] = col_stats

        assert 'mean' in by_type['integer']
        assert 'mean' in by_type['float']
        assert 'mean' not in by_type['string']
        assert 'mean' not in by_type['boolean']

    def test_no_errors_on_simple_df(self):
        """Simple DataFrame should produce zero errors."""
        df = pl.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)
        assert errors == []

    def test_empty_df(self):
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(pl.DataFrame({}))
        assert result == {}
        assert errors == []

    def test_type_classification(self):
        """Verify _type is correct per column type."""
        df = pl.DataFrame({
            'ints': [1, 2, 3],
            'floats': [1.0, 2.0, 3.0],
            'strs': ['a', 'b', 'c'],
            'bools': [True, False, True],
        })
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)

        # Collect _type values
        types = {col_stats['_type'] for col_stats in result.values()}
        assert types == {'integer', 'float', 'string', 'boolean'}
