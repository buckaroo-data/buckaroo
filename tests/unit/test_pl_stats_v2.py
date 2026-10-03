"""Tests for v2 @stat function equivalents for Polars DataFrames.

Mirrors test_pd_stats_v2.py structure for polars-native stat functions.
"""
import math
import datetime as dt
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline

from buckaroo.customizations.pl_stats_v2 import (pl_typing_stats, _type, pl_scalar_stats, pl_distinct_stats, pl_value_counts_stats, pl_numeric_stats, pl_computed_summary_stats, pl_freq_stats, pl_histogram_series, histogram, PL_ANALYSIS_V2)
from buckaroo.customizations.styling import DefaultMainStyling


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
        assert result['is_timedelta'] is False

    def test_duration(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [timedelta(seconds=1), timedelta(seconds=2)])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_timedelta'] is True
        assert result['is_datetime'] is False
        assert result['is_numeric'] is False

    def test_duration_from_schema(self):
        """Duration created via pl.Duration schema (as in issue #622)."""
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        df = pl.DataFrame({"d": [100, 200, 125, 500]}, schema={"d": pl.Duration()})
        ser = df["d"]
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_timedelta'] is True
        assert result['is_datetime'] is False

    def test_categorical(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c']).cast(pl.Categorical)
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_categorical'] is True
        assert result['is_string'] is False
        assert result['is_numeric'] is False

    def test_enum(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c']).cast(pl.Enum(['a', 'b', 'c']))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_categorical'] is True

    def test_time(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [dt.time(14, 30), dt.time(9, 15)])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_time'] is True
        assert result['is_datetime'] is False

    def test_decimal(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', ['100.50', '200.75']).cast(pl.Decimal(10, 2))
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_decimal'] is True
        assert result['is_numeric'] is False  # excluded from numeric to avoid "integer" misclass

    def test_binary(self):
        pipeline = StatPipeline([pl_typing_stats], unit_test=False)
        ser = pl.Series('test', [b'hello', b'world'])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['is_binary'] is True

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

    def test_duration(self):
        ser = pl.Series('test', [timedelta(seconds=1), timedelta(seconds=2)])
        assert self._run(ser) == 'duration'

    def test_duration_from_schema(self):
        """Duration created via pl.Duration schema (as in issue #622)."""
        df = pl.DataFrame({"d": [100, 200, 125, 500]}, schema={"d": pl.Duration()})
        assert self._run(df["d"]) == 'duration'

    def test_categorical(self):
        assert self._run(pl.Series('test', ['a', 'b', 'c']).cast(pl.Categorical)) == 'categorical'

    def test_time(self):
        assert self._run(pl.Series('test', [dt.time(14, 30), dt.time(9, 15)])) == 'time'

    def test_decimal(self):
        assert self._run(pl.Series('test', ['100.50']).cast(pl.Decimal(10, 2))) == 'decimal'

    def test_binary(self):
        assert self._run(pl.Series('test', [b'hello', b'world'])) == 'binary'


# ============================================================================
# Tests: pl_scalar_stats / pl_value_counts_stats
# ============================================================================

class TestPlBaseSummaryStats:
    def test_numeric_basics(self):
        pipeline = StatPipeline([pl_scalar_stats, pl_value_counts_stats], unit_test=False)
        ser = pl.Series('test', [1, 2, 3, 4, 5])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert errors == []
        assert result['length'] == 5
        assert result['null_count'] == 0
        assert result['min'] == 1
        assert result['max'] == 5
        assert 'mean' not in result

    def test_with_nulls(self):
        pipeline = StatPipeline([pl_scalar_stats, pl_value_counts_stats], unit_test=False)
        ser = pl.Series('test', [1, None, 3, None, 5])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['null_count'] == 2
        assert result['length'] == 5

    def test_string_column(self):
        pipeline = StatPipeline([pl_scalar_stats, pl_value_counts_stats], unit_test=False)
        ser = pl.Series('test', ['a', 'b', 'c'])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert 'mean' not in result
        assert 'std' not in result
        assert math.isnan(result['min'])
        assert math.isnan(result['max'])

    def test_bool_column(self):
        """Bool columns should NOT get numeric min/max."""
        pipeline = StatPipeline([pl_scalar_stats, pl_value_counts_stats], unit_test=False)
        ser = pl.Series('test', [True, False, True])
        result, _ = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 3
        assert 'mean' not in result
        assert math.isnan(result['min'])

    def test_value_counts_present(self):
        pipeline = StatPipeline([pl_scalar_stats, pl_value_counts_stats], unit_test=False)
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
        return StatPipeline([pl_typing_stats, pl_scalar_stats, pl_distinct_stats, pl_value_counts_stats,
            pl_numeric_stats, pl_computed_summary_stats, pl_freq_stats, pl_histogram_series, histogram],
            unit_test=False)

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

    def test_bigint_histogram_series(self):
        """Integers near 2^53: np.histogram either raises ValueError (newer
        numpy, where float64 linspace produces colliding bin edges) or returns
        near-degenerate bins (e.g. numpy 2.0.2). pl_histogram_series must not
        raise either way — on the raising versions the guard returns empty
        histogram_args so the categorical fallback renders."""
        ser = pl.Series('big_id', [9007199254740993 + i for i in range(20)])
        result = pl_histogram_series(ser)
        assert isinstance(result['histogram_args'], dict)
        assert isinstance(result['histogram_bins'], list)


# ============================================================================
# Full pipeline integration tests
# ============================================================================

class TestPlFullPipeline:
    def test_mixed_df(self):
        """Pipeline handles a polars DataFrame with mixed column types."""
        df = pl.DataFrame({'ints': [1, 2, 3, 4, 5], 'floats': [1.1, 2.2, 3.3, 4.4, 5.5],
            'strs': ['a', 'b', 'c', 'd', 'e'], 'bools': [True, False, True, False, True]})
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
        df = pl.DataFrame({'ints': [1, 2, 3], 'floats': [1.0, 2.0, 3.0], 'strs': ['a', 'b', 'c'],
            'bools': [True, False, True]})
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)

        # Collect _type values
        types = {col_stats['_type'] for col_stats in result.values()}
        assert types == {'integer', 'float', 'string', 'boolean'}

    def test_duration_column_in_full_pipeline(self):
        """Duration columns should be classified as 'duration', not 'datetime' (issue #622)."""
        df = pl.DataFrame({'duration': [100, 200, 125, 500], 'ints': [1, 2, 3, 4]},
            schema={'duration': pl.Duration(), 'ints': pl.Int64})
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, errors = pipeline.process_df(df)

        types = {col_stats['_type'] for col_stats in result.values()}
        assert 'duration' in types
        assert 'integer' in types

    def test_duration_column_styled_with_duration_displayer(self):
        """Duration columns should use 'duration' displayer, not 'datetimeLocaleString' (issue #622)."""
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        df = pl.DataFrame({"d": [100, 200, 125, 500]}, schema={"d": pl.Duration()})
        result, _ = pipeline.process_df(df)
        col_stats = list(result.values())[0]
        style = DefaultMainStyling.style_column('a', col_stats)
        assert style['displayer_args']['displayer'] == 'duration'

    def test_all_polars_types_classified(self):
        """All common polars types should get a specific _type, not 'obj'."""
        df = pl.DataFrame({'int_col': [1, 2, 3], 'float_col': [1.0, 2.0, 3.0], 'str_col': ['a', 'b', 'c'],
            'bool_col': [True, False, True],
            'dt_col': [datetime(2021, 1, 1), datetime(2021, 1, 2), datetime(2021, 1, 3)],
            'dur_col': pl.Series([100, 200, 300], dtype=pl.Duration()),
            'time_col': [dt.time(14, 30), dt.time(9, 15), dt.time(12, 0)],
            'cat_col': pl.Series(['x', 'y', 'z']).cast(pl.Categorical),
            'dec_col': pl.Series(['1.50', '2.75', '3.00']).cast(pl.Decimal(10, 2)), 'bin_col': [b'aa', b'bb', b'cc']})
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
        result, _ = pipeline.process_df(df)

        types = {col_stats['_type'] for col_stats in result.values()}
        # None should be 'obj'
        assert 'obj' not in types
        assert types == {'integer', 'float', 'string', 'boolean', 'datetime', 'duration', 'time', 'categorical',
            'decimal', 'binary'}

    def test_styling_for_new_types(self):
        """Verify correct displayer for each new type."""
        pipeline = StatPipeline(PL_ANALYSIS_V2, unit_test=False)

        test_cases = [
            (pl.Series('t', [dt.time(14, 30)]), 'string'),
            (pl.Series('c', ['a', 'b']).cast(pl.Categorical), 'string'),
            (pl.Series('d', ['1.50']).cast(pl.Decimal(10, 2)), 'float'),
            (pl.Series('b', [b'hello']), 'obj'),
        ]
        for ser, expected_displayer in test_cases:
            df = pl.DataFrame({ser.name: ser})
            result, _ = pipeline.process_df(df)
            col_stats = list(result.values())[0]
            style = DefaultMainStyling.style_column('a', col_stats)
            actual = style['displayer_args']['displayer']
            assert actual == expected_displayer, (
                f"{ser.dtype}: expected {expected_displayer!r}, got {actual!r}"
            )


# ============================================================================
# Tests: PlDfStatsV2 pre-pass (#999)
# ============================================================================

def _prepass_fixture_df():
    # mode has no ties in any column, so the per-series and pre-pass paths
    # can be compared key by key.
    return pl.DataFrame({
        'ints': [1, 2, 2, None, 5, 5, 5, 8],
        'floats': [1.5, 2.5, None, 4.5, 4.5, 6.0, 7.0, 8.0],
        'strs': ['a', 'b', '', 'a', None, 'a', 'c', ''],
        'bools': [True, False, True, True, None, False, True, True]})


class TestPlDfStatsV2Prepass:
    def test_large_frame_is_not_sampled(self):
        """A 60k x 20 frame exceeds FAST_SUMMARY_WHEN_GREATER (1M cells).
        Today it is cut to a 50,000-row sample, so length reads 50000 and
        distinct_count of a unique-id column caps at 50000."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        n = 60_000
        df = pl.DataFrame({f'c{i}': np.arange(n) + i for i in range(20)})
        stats = PlDfStatsV2(df, PL_ANALYSIS_V2)
        assert stats.errs == {}
        for col_stats in stats.sdf.values():
            assert col_stats['length'] == n
            assert col_stats['null_count'] == 0
            assert col_stats['distinct_count'] == n
            assert col_stats['distinct_per'] == 1.0

    def test_scalar_stats_come_from_the_prepass(self, monkeypatch):
        """null_count/min/max are computed once for the whole frame in the
        pre-pass select, never per pl.Series."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        calls = {'null_count': 0, 'min': 0, 'max': 0}

        def counting(name):
            orig = getattr(pl.Series, name)

            def wrapped(self, *args, **kwargs):
                calls[name] += 1
                return orig(self, *args, **kwargs)
            return wrapped

        for name in calls:
            monkeypatch.setattr(pl.Series, name, counting(name))

        stats = PlDfStatsV2(_prepass_fixture_df(), PL_ANALYSIS_V2)
        assert stats.errs == {}
        assert calls == {'null_count': 0, 'min': 0, 'max': 0}
        assert stats.sdf['a']['null_count'] == 1
        assert stats.sdf['a']['min'] == 1
        assert stats.sdf['a']['max'] == 8
        assert stats.sdf['b']['min'] == 1.5
        assert math.isnan(stats.sdf['c']['min'])

    def test_small_fixture_matches_todays_values(self):
        """Values captured from PlDfStatsV2 on main at 992fdb3 for this fixture."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        stats = PlDfStatsV2(_prepass_fixture_df(), PL_ANALYSIS_V2)
        assert stats.errs == {}
        sdf = stats.sdf
        expected = {
            'a': {'_type': 'integer', 'length': 8, 'null_count': 1, 'min': 1, 'max': 8, 'mean': 4.0,
                'std': pytest.approx(2.449489742783178), 'median': 5.0, 'distinct_count': 4, 'empty_count': 0,
                'unique_count': 2, 'most_freq': 5, 'mode': 5, 'nan_per': 0.125, 'distinct_per': 0.5,
                'non_null_count': 7, 'histogram_bins': [2.0, 2.3, 2.6, 2.9, 3.2, 3.5, 3.8, 4.1, 4.4,
                    pytest.approx(4.7), 5.0]},
            'b': {'_type': 'float', 'length': 8, 'null_count': 1, 'min': 1.5, 'max': 8.0,
                'mean': pytest.approx(4.857142857142857), 'std': pytest.approx(2.340126166724879), 'median': 4.5,
                'distinct_count': 6, 'empty_count': 0, 'unique_count': 5, 'most_freq': 4.5, 'mode': 4.5,
                'nan_per': 0.125, 'distinct_per': 0.75, 'non_null_count': 7},
            'c': {'_type': 'string', 'length': 8, 'null_count': 1, 'distinct_count': 4, 'empty_count': 2,
                'empty_per': 0.25, 'unique_count': 2, 'most_freq': 'a', 'mode': 'a', 'nan_per': 0.125,
                'distinct_per': 0.5, 'non_null_count': 7, 'histogram_bins': []},
            'd': {'_type': 'boolean', 'length': 8, 'null_count': 1, 'distinct_count': 2, 'empty_count': 0,
                'unique_count': 0, 'most_freq': True, 'mode': True, 'nan_per': 0.125, 'distinct_per': 0.25,
                'non_null_count': 7, 'histogram_bins': []},
        }
        for col, exp in expected.items():
            for key, val in exp.items():
                assert sdf[col][key] == val, (col, key, sdf[col][key])
        for col in ('c', 'd'):
            assert math.isnan(sdf[col]['min']) and math.isnan(sdf[col]['max'])
            assert 'mean' not in sdf[col] and 'std' not in sdf[col] and 'median' not in sdf[col]
        assert sdf['a']['value_counts'].to_dict() == {1: 1, 2: 2, 5: 3, 8: 1}
        assert sdf['c']['value_counts'].to_dict() == {'': 2, 'a': 3, 'b': 1, 'c': 1}
        assert sdf['a']['histogram'][0] == {'cat_pop': 38.0, 'name': '5'}
        assert sdf['b']['histogram'][1] == {'name': '2.5–2.95', 'population': 20.0}

    def test_temporal_min_max(self):
        """The pre-pass gives temporal columns a real min/max (today: nan)."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        df = pl.DataFrame({'dates': [datetime(2020, 1, d) for d in (3, 1, 7, 1)] + [None]})
        stats = PlDfStatsV2(df, PL_ANALYSIS_V2)
        assert stats.errs == {}
        assert stats.sdf['a']['min'] == datetime(2020, 1, 1)
        assert stats.sdf['a']['max'] == datetime(2020, 1, 7)
        assert stats.sdf['a']['mode'] == datetime(2020, 1, 1)
        assert stats.sdf['a']['null_count'] == 1

    def test_prepass_matches_per_series_path(self):
        """Running PL_ANALYSIS_V2 per series with no pre-pass gives the same
        values, key by key, as PlDfStatsV2 with the pre-pass."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        df = _prepass_fixture_df().with_columns(
            pl.Series('dates', [datetime(2020, 1, d) for d in (3, 1, 7, 1, 2, 2, 2, 5)]))
        per_series, errors = StatPipeline(PL_ANALYSIS_V2, unit_test=False).process_df(df)
        assert errors == []
        with_prepass = PlDfStatsV2(df, PL_ANALYSIS_V2).sdf
        assert set(per_series) == set(with_prepass)
        for col in per_series:
            assert set(per_series[col]) == set(with_prepass[col]), col
            for key, val in per_series[col].items():
                got = with_prepass[col][key]
                if key == 'value_counts':
                    assert val.to_dict() == got.to_dict(), (col, key)
                elif key == 'histogram_args':
                    assert bool(val) == bool(got), (col, key)
                elif isinstance(val, float) and math.isnan(val):
                    assert math.isnan(got), (col, key)
                else:
                    assert val == got, (col, key, val, got)

    def test_value_counts_gated_above_max_rows(self, monkeypatch):
        """Above max_rows, value_counts and everything that needs it (mode,
        most_freq, histogram, ...) are reported as not computed; the
        pre-pass stats still come through."""
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
        from buckaroo.customizations import pl_stats_v2
        monkeypatch.setattr(pl_stats_v2.pl_value_counts_stats._stat_func, 'max_rows', 100)
        df = pl.DataFrame({'ids': list(range(101)), 'strs': [str(i % 7) for i in range(101)]})
        stats = PlDfStatsV2(df, PL_ANALYSIS_V2)
        assert stats.errs == {}
        for col in ('a', 'b'):
            col_stats = stats.sdf[col]
            assert col_stats['length'] == 101
            assert col_stats['null_count'] == 0
            assert col_stats['nan_per'] == 0.0
            for key in ('value_counts', 'mode', 'most_freq', 'histogram', 'unique_count'):
                assert col_stats[key] is None, (col, key)
            assert 'value_counts' in stats.skipped_stats[col]
            assert 'histogram' in stats.skipped_stats[col]
        assert stats.sdf['a']['distinct_count'] == 101
        assert stats.sdf['a']['min'] == 0 and stats.sdf['a']['max'] == 100
        assert stats.sdf['b']['distinct_count'] == 7

        small = PlDfStatsV2(df.head(100), PL_ANALYSIS_V2)
        assert small.skipped_stats == {}
        assert small.sdf['b']['most_freq'] == '0'
        assert isinstance(small.sdf['a']['histogram'], list)
