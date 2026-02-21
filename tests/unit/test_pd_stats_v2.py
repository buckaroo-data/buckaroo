"""Tests for v2 @stat function equivalents of v1 ColAnalysis classes.

Tests for: typing_stats, _type, default_summary_stats,
computed_default_summary_stats, histogram, pd_cleaning_stats,
heuristic_fracs, and full pipeline integration.
"""
import numpy as np
import pandas as pd

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.pluggable_analysis_framework.utils import PERVERSE_DF

from buckaroo.customizations.pd_stats_v2 import (
    typing_stats, _type,
    default_summary_stats, computed_default_summary_stats,
    histogram_series, histogram,
    pd_cleaning_stats, heuristic_fracs,
    orig_col_name,
    PD_ANALYSIS_V2,
)


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


# ============================================================================
# Tests: default_summary_stats
# ============================================================================

class TestDefaultSummaryStats:
    def test_numeric_basics(self):
        pipeline = StatPipeline([default_summary_stats], unit_test=False)
        ser = pd.Series([1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['length'] == 5
        assert result['null_count'] == 0
        assert result['mean'] == 3.0
        assert result['min'] == 1
        assert result['max'] == 5

    def test_with_nulls(self):
        pipeline = StatPipeline([default_summary_stats], unit_test=False)
        ser = pd.Series([1, None, 3, None, 5])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['null_count'] == 2
        assert result['length'] == 5

    def test_string_column(self):
        pipeline = StatPipeline([default_summary_stats], unit_test=False)
        ser = pd.Series(['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert result['mean'] == 0  # Default for non-numeric
        assert result['std'] == 0

    def test_bool_column(self):
        """Bool columns should NOT get numeric stats."""
        pipeline = StatPipeline([default_summary_stats], unit_test=False)
        ser = pd.Series([True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert result['mean'] == 0  # Bools treated as non-numeric for stats

    def test_value_counts_present(self):
        pipeline = StatPipeline([default_summary_stats], unit_test=False)
        ser = pd.Series([1, 1, 2, 3])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert isinstance(result['value_counts'], pd.Series)
        assert result['value_counts'].iloc[0] == 2  # '1' is most frequent


# ============================================================================
# Tests: computed_default_summary_stats
# ============================================================================

class TestComputedDefaultSummaryStats:
    def test_basic_computed(self):
        pipeline = StatPipeline(
            [default_summary_stats, computed_default_summary_stats],
            unit_test=False,
        )
        ser = pd.Series([1, 2, 3, 1, 2])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['distinct_count'] == 3
        assert result['distinct_per'] == 3 / 5
        assert result['nan_per'] == 0
        assert result['non_null_count'] == 5
        assert result['most_freq'] == 1  # most common value

    def test_with_nulls(self):
        pipeline = StatPipeline(
            [default_summary_stats, computed_default_summary_stats],
            unit_test=False,
        )
        ser = pd.Series([1, None, 2, None, 1])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['nan_per'] == 2 / 5
        assert result['non_null_count'] == 3

    def test_freq_values(self):
        pipeline = StatPipeline(
            [default_summary_stats, computed_default_summary_stats],
            unit_test=False,
        )
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
        return StatPipeline(
            [typing_stats, default_summary_stats,
             computed_default_summary_stats,
             histogram_series, histogram],
            unit_test=False,
        )

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
        pipeline = StatPipeline(
            [default_summary_stats, pd_cleaning_stats],
            unit_test=False,
        )
        ser = pd.Series([1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'int_parse' in result
        assert 'int_parse_fail' in result
        assert result['int_parse'] == 1.0  # All values are parseable

    def test_string_column(self):
        pipeline = StatPipeline(
            [default_summary_stats, pd_cleaning_stats],
            unit_test=False,
        )
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
        df = pd.DataFrame({
            'ints': [1, 2, 3, 4, 5],
            'floats': [1.1, 2.2, 3.3, 4.4, 5.5],
            'strs': ['a', 'b', 'c', 'd', 'e'],
            'bools': [True, False, True, False, True],
        })
        pipeline = StatPipeline(PD_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)
        assert len(result) == 4

        # Check type classification
        type_map = {
            col_stats['orig_col_name']: col_stats['_type']
            for col_stats in result.values()
        }
        assert type_map['ints'] == 'integer'
        assert type_map['floats'] == 'float'
        assert type_map['strs'] == 'string'
        assert type_map['bools'] == 'boolean'

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


# ============================================================================
# Backward compatibility tests
# ============================================================================

class TestBackwardCompat:
    """Verify v2 functions produce the same stat keys as v1 classes."""

    def test_typing_stats_keys(self):
        """v2 typing_stats + _type produce all keys from v1 TypingStats."""
        from buckaroo.customizations.analysis import TypingStats

        v1_keys = set(TypingStats.provides_defaults.keys())
        v2_pipeline = StatPipeline([typing_stats, _type], unit_test=False)

        ser = pd.Series([1, 2, 3])
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)

        # v2 should have all v1 keys
        for key in v1_keys:
            assert key in v2_result, f"Missing key: {key}"

        # v2 also provides extras: is_string, memory_usage
        assert 'is_string' in v2_result
        assert 'memory_usage' in v2_result

    def test_summary_stats_keys(self):
        """v2 default_summary_stats produces all keys from v1 DefaultSummaryStats."""
        from buckaroo.customizations.analysis import DefaultSummaryStats

        v1_keys = set(DefaultSummaryStats.provides_defaults.keys())
        v2_pipeline = StatPipeline([default_summary_stats], unit_test=False)

        ser = pd.Series([1, 2, 3, 4, 5])
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)

        for key in v1_keys:
            assert key in v2_result, f"Missing key: {key}"

    def test_computed_summary_keys(self):
        """v2 computed_default_summary_stats produces all keys from v1."""
        from buckaroo.customizations.analysis import ComputedDefaultSummaryStats

        v1_keys = set(ComputedDefaultSummaryStats.provides_defaults.keys())
        v2_pipeline = StatPipeline(
            [default_summary_stats, computed_default_summary_stats],
            unit_test=False,
        )

        ser = pd.Series([1, 2, 3, 1, 2])
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)

        for key in v1_keys:
            assert key in v2_result, f"Missing key: {key}"

    def test_histogram_keys(self):
        """v2 histogram functions produce the histogram key."""
        v2_pipeline = StatPipeline(
            [typing_stats, default_summary_stats,
             computed_default_summary_stats,
             histogram_series, histogram],
            unit_test=False,
        )

        ser = pd.Series([1, 2, 3, 4, 5])
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert 'histogram' in v2_result
        assert 'histogram_args' in v2_result

    def test_typing_values_match_v1(self):
        """v2 typing_stats produces same values as v1 TypingStats."""
        from buckaroo.customizations.analysis import TypingStats

        # Run v1 through adapter
        v1_pipeline = StatPipeline([TypingStats], unit_test=False)
        v2_pipeline = StatPipeline([typing_stats, _type], unit_test=False)

        test_series = [
            pd.Series([1, 2, 3], name='ints'),
            pd.Series([1.0, 2.0], name='floats'),
            pd.Series(['a', 'b'], name='strs'),
            pd.Series([True, False], name='bools'),
        ]

        for ser in test_series:
            v1_result, _ = v1_pipeline.process_column(
                'test', ser.dtype, raw_series=ser)
            v2_result, _ = v2_pipeline.process_column(
                'test', ser.dtype, raw_series=ser)

            for key in ['dtype', 'is_numeric', 'is_integer', 'is_bool',
                        'is_float', 'is_datetime']:
                assert v1_result.get(key) == v2_result.get(key), \
                    f"Mismatch on {key} for {ser.name}: " \
                    f"v1={v1_result.get(key)} v2={v2_result.get(key)}"

    def test_summary_values_match_v1(self):
        """v2 default_summary_stats produces same values as v1."""
        from buckaroo.customizations.analysis import DefaultSummaryStats

        v1_pipeline = StatPipeline([DefaultSummaryStats], unit_test=False)
        v2_pipeline = StatPipeline([default_summary_stats], unit_test=False)

        ser = pd.Series([1, 2, 3, 4, 5])
        v1_result, _ = v1_pipeline.process_column('test', ser.dtype, raw_series=ser)
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)

        for key in ['length', 'null_count', 'min', 'max']:
            assert v1_result[key] == v2_result[key], \
                f"Mismatch on {key}: v1={v1_result[key]} v2={v2_result[key]}"

    def test_heuristic_fracs_keys(self):
        """v2 heuristic_fracs produces all keys from v1 HeuristicFracs."""
        from buckaroo.customizations.pd_fracs import HeuristicFracs

        v1_keys = set(HeuristicFracs.provides_defaults.keys())
        v2_pipeline = StatPipeline([heuristic_fracs], unit_test=False)

        ser = pd.Series(['true', 'false', '123'])
        v2_result, _ = v2_pipeline.process_column('test', ser.dtype, raw_series=ser)

        for key in v1_keys:
            assert key in v2_result, f"Missing key: {key}"
