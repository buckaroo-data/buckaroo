"""Tests for v2 @stat function equivalents of v1 ColAnalysis classes.

Tests for: typing_stats, _type, base_summary_stats, numeric_stats,
computed_default_summary_stats, histogram, pd_cleaning_stats,
heuristic_fracs, and full pipeline integration.
"""
import math

import numpy as np
import pandas as pd

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.utils import PERVERSE_DF

from buckaroo.customizations.pd_stats_v2 import (typing_stats, _type, base_summary_stats, numeric_stats, computed_default_summary_stats, histogram_series, histogram, pd_cleaning_stats, heuristic_fracs, orig_col_name, PD_ANALYSIS_V2)


# ============================================================================
# Tests: typing_stats
# ============================================================================

class TestTypingStats:
    def test_numeric_int(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series([1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_numeric'] is True
        assert result['is_integer'] is True
        assert result['is_float'] is False
        assert result['is_bool'] is False
        assert result['dtype'] == str(ser.dtype)

    def test_numeric_float(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series([1.0, 2.5, 3.0])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_float'] is True
        assert result['is_numeric'] is True

    def test_string(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(['a', 'b', 'c'])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_string'] is True
        assert result['is_numeric'] is False

    def test_bool(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series([True, False, True])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_bool'] is True

    def test_datetime(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.to_datetime(['2021-01-01', '2021-01-02']))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['is_datetime'] is True
        assert result['is_timedelta'] is False

    def test_timedelta(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.to_timedelta(['1 days', '2 days', '3 days']))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_timedelta'] is True
        assert result['is_datetime'] is False
        assert result['is_numeric'] is False

    def test_categorical_string(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.Categorical(['a', 'b', 'c']))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_categorical'] is True

    def test_categorical_numeric(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.Categorical([1, 2, 3]))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_categorical'] is True
        assert result['is_numeric'] is False  # categorical is not numeric in pandas

    def test_period(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.period_range('2021-01', periods=3, freq='M'))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_period'] is True
        assert result['is_datetime'] is False

    def test_interval(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series(pd.arrays.IntervalArray.from_breaks([0, 1, 2, 3]))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_interval'] is True

    def test_memory_usage(self):
        pipeline = StatPipeline([typing_stats], unit_test=False)
        ser = pd.Series([1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['memory_usage'] > 0


# ============================================================================
# Tests: _type
# ============================================================================

class TestTypeComputed:
    def _run(self, ser):
        pipeline = StatPipeline([typing_stats, _type], unit_test=False)
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        return result['_type']

    def test_integer(self):
        assert self._run(pd.Series([1, 2, 3])) == 'integer'

    def test_float(self):
        assert self._run(pd.Series([1.0, 2.0, 3.0])) == 'float'

    def test_string(self):
        assert self._run(pd.Series(['a', 'b', 'c'])) == 'string'

    def test_boolean(self):
        assert self._run(pd.Series([True, False])) == 'boolean'

    def test_datetime(self):
        assert self._run(pd.Series(pd.to_datetime(['2021-01-01']))) == 'datetime'

    def test_timedelta(self):
        assert self._run(pd.Series(pd.to_timedelta(['1 days', '2 days']))) == 'duration'

    def test_categorical(self):
        assert self._run(pd.Series(pd.Categorical(['a', 'b', 'c']))) == 'categorical'

    def test_period(self):
        assert self._run(pd.Series(pd.period_range('2021-01', periods=3, freq='M'))) == 'period'

    def test_interval(self):
        assert self._run(pd.Series(pd.arrays.IntervalArray.from_breaks([0, 1, 2]))) == 'interval'


# ============================================================================
# Tests: base_summary_stats
# ============================================================================

class TestBaseSummaryStats:
    def test_numeric_basics(self):
        pipeline = StatPipeline([base_summary_stats], unit_test=False)
        ser = pd.Series([1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['length'] == 5
        assert result['null_count'] == 0
        assert result['min'] == 1
        assert result['max'] == 5
        # mean/std/median are NOT provided by base_summary_stats
        assert 'mean' not in result

    def test_with_nulls(self):
        pipeline = StatPipeline([base_summary_stats], unit_test=False)
        ser = pd.Series([1, None, 3, None, 5])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['null_count'] == 2
        assert result['length'] == 5

    def test_string_column(self):
        pipeline = StatPipeline([base_summary_stats], unit_test=False)
        ser = pd.Series(['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        # mean/std/median are absent (not baked in as 0)
        assert 'mean' not in result
        assert 'std' not in result
        assert math.isnan(result['min'])
        assert math.isnan(result['max'])

    def test_bool_column(self):
        """Bool columns should NOT get numeric min/max."""
        pipeline = StatPipeline([base_summary_stats], unit_test=False)
        ser = pd.Series([True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert 'mean' not in result
        assert math.isnan(result['min'])

    def test_value_counts_present(self):
        pipeline = StatPipeline([base_summary_stats], unit_test=False)
        ser = pd.Series([1, 1, 2, 3])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert isinstance(result['value_counts'], pd.Series)
        assert result['value_counts'].iloc[0] == 2  # '1' is most frequent


# ============================================================================
# Tests: numeric_stats
# ============================================================================

class TestNumericStats:
    def test_int_column(self):
        pipeline = StatPipeline([numeric_stats], unit_test=False)
        ser = pd.Series([1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['mean'] == 3.0
        assert result['median'] == 3.0
        assert isinstance(result['std'], float)

    def test_float_column(self):
        pipeline = StatPipeline([numeric_stats], unit_test=False)
        ser = pd.Series([1.0, 2.0, 3.0])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['mean'] == 2.0
        assert result['std'] == 1.0

    def test_bool_column_excluded(self):
        """Bool columns are excluded by column_filter — keys absent."""
        pipeline = StatPipeline([numeric_stats], unit_test=False)
        ser = pd.Series([True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'mean' not in result
        assert 'std' not in result
        assert 'median' not in result

    def test_string_column_excluded(self):
        """String columns are excluded by column_filter — keys absent."""
        pipeline = StatPipeline([numeric_stats], unit_test=False)
        ser = pd.Series(['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'mean' not in result

    def test_all_null_numeric(self):
        """All-null numeric column returns nan, not 0."""
        pipeline = StatPipeline([numeric_stats], unit_test=False)
        ser = pd.Series([None, None, None], dtype='float64')
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert math.isnan(result['mean'])
        assert math.isnan(result['std'])
        assert math.isnan(result['median'])


# ============================================================================
# Tests: computed_default_summary_stats
# ============================================================================

class TestComputedDefaultSummaryStats:
    def test_basic_computed(self):
        pipeline = StatPipeline([base_summary_stats, computed_default_summary_stats], unit_test=False)
        ser = pd.Series([1, 2, 3, 1, 2])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['distinct_count'] == 3
        assert result['distinct_per'] == 3 / 5
        assert result['nan_per'] == 0
        assert result['non_null_count'] == 5
        assert result['most_freq'] == 1  # most common value

    def test_with_nulls(self):
        pipeline = StatPipeline([base_summary_stats, computed_default_summary_stats], unit_test=False)
        ser = pd.Series([1, None, 2, None, 1])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['nan_per'] == 2 / 5
        assert result['non_null_count'] == 3

    def test_freq_values(self):
        pipeline = StatPipeline([base_summary_stats, computed_default_summary_stats], unit_test=False)
        ser = pd.Series(['a', 'b', 'c', 'd', 'e', 'f'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['most_freq'] is not None
        assert result['5th_freq'] is not None
        # 6th doesn't exist in provides, but all 5 freq slots filled
        assert result['2nd_freq'] is not None


# ============================================================================
# Tests: histogram
# ============================================================================

class TestHistogram:
    def _make_pipeline(self):
        return StatPipeline([typing_stats, base_summary_stats, numeric_stats,
            computed_default_summary_stats,
            histogram_series, histogram], unit_test=False)

    def test_numeric_histogram(self):
        pipeline = self._make_pipeline()
        ser = pd.Series(np.random.randn(100))
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)
        assert len(result['histogram']) > 0

    def test_string_histogram(self):
        pipeline = self._make_pipeline()
        ser = pd.Series(['a', 'b', 'c', 'a', 'b'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)

    def test_bool_histogram(self):
        """Bool columns get categorical histogram."""
        pipeline = self._make_pipeline()
        ser = pd.Series([True, False, True, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result
        assert isinstance(result['histogram'], list)

    def test_all_null_numeric(self):
        """All-null numeric column should still produce histogram."""
        pipeline = self._make_pipeline()
        ser = pd.Series([None, None, None], dtype='float64')
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in result


# ============================================================================
# Tests: pd_cleaning_stats
# ============================================================================

class TestPdCleaningStats:
    def test_numeric_column(self):
        pipeline = StatPipeline([base_summary_stats, pd_cleaning_stats], unit_test=False)
        ser = pd.Series([1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'int_parse' in result
        assert 'int_parse_fail' in result
        assert result['int_parse'] == 1.0  # All values are parseable

    def test_string_column(self):
        pipeline = StatPipeline([base_summary_stats, pd_cleaning_stats], unit_test=False)
        ser = pd.Series(['abc', 'def', '123', '456'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['int_parse'] > 0
        assert result['int_parse_fail'] > 0


# ============================================================================
# Tests: heuristic_fracs
# ============================================================================

class TestHeuristicFracs:
    def test_string_column(self):
        pipeline = StatPipeline([heuristic_fracs], unit_test=False)
        ser = pd.Series(['true', 'false', 'yes', 'no'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['str_bool_frac'] > 0

    def test_numeric_column_returns_zeros(self):
        pipeline = StatPipeline([heuristic_fracs], unit_test=False)
        ser = pd.Series([1, 2, 3])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['str_bool_frac'] == 0
        assert result['regular_int_parse_frac'] == 0

    def test_integer_strings(self):
        pipeline = StatPipeline([heuristic_fracs], unit_test=False)
        ser = pd.Series(['1', '2', '3', '4'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['regular_int_parse_frac'] > 0


# ============================================================================
# Tests: orig_col_name
# ============================================================================

class TestOrigColName:
    def test_provides_name(self):
        pipeline = StatPipeline([orig_col_name], unit_test=False)
        ser = pd.Series([1, 2, 3], name='my_col')
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['orig_col_name'] == 'my_col'


# ============================================================================
# Full pipeline integration tests
# ============================================================================

class TestFullPipeline:
    def test_perverse_df(self):
        """Full v2 pipeline should handle PERVERSE_DF without crashing."""
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(PERVERSE_DF)
        assert len(result) == len(PERVERSE_DF.columns)

        for col_key, col_stats in result.items():
            assert 'length' in col_stats
            assert 'dtype' in col_stats
            assert '_type' in col_stats
            assert 'distinct_count' in col_stats
            assert 'nan_per' in col_stats
            assert 'histogram' in col_stats

    def test_mixed_df(self):
        """Pipeline handles a DataFrame with mixed column types."""
        df = pd.DataFrame({'ints': [1, 2, 3, 4, 5], 'floats': [1.1, 2.2, 3.3, 4.4, 5.5],
            'strs': ['a', 'b', 'c', 'd', 'e'], 'bools': [True, False, True, False, True]})
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)
        assert len(result) == 4

        # Build orig_col_name -> stats lookup (keys are rewritten a,b,c,...)
        by_orig = {
            col_stats['orig_col_name']: col_stats
            for col_stats in result.values()
        }

        # Check type classification
        assert by_orig['ints']['_type'] == 'integer'
        assert by_orig['floats']['_type'] == 'float'
        assert by_orig['strs']['_type'] == 'string'
        assert by_orig['bools']['_type'] == 'boolean'

        # Numeric columns have mean; non-numeric don't
        assert 'mean' in by_orig['ints']
        assert 'mean' in by_orig['floats']
        assert 'mean' not in by_orig['strs']
        assert 'mean' not in by_orig['bools']

    def test_no_errors_on_simple_df(self):
        """Simple DataFrame should produce zero errors."""
        df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)
        assert errors == []

    def test_empty_df(self):
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(pd.DataFrame({}))
        assert result == {}
        assert errors == []

    def test_unit_test_runs(self):
        """StatPipeline.unit_test should not crash."""
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=True)
        passed, errors = pipeline._unit_test_result
        # Some errors may occur on edge cases, but shouldn't crash

