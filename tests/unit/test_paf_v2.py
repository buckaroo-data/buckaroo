"""Comprehensive tests for the Pluggable Analysis Framework v2.

Tests for: stat_func, stat_result, typed_dag, column_filters,
stat_pipeline, v1_adapter, df_stats_v2.
"""
import warnings
from typing import Any, TypedDict

import numpy as np
import pandas as pd
import pytest

from buckaroo.pluggable_analysis_framework.stat_func import (
    StatKey, StatFunc, RawSeries, SampledSeries, RawDataFrame,
    RAW_MARKER_TYPES, MISSING, stat, collect_stat_funcs,
)
from buckaroo.pluggable_analysis_framework.stat_result import (
    Ok, Err, UpstreamError, StatError, resolve_accumulator,
)
from buckaroo.pluggable_analysis_framework.typed_dag import (
    build_typed_dag, build_column_dag, DAGConfigError,
)
from buckaroo.pluggable_analysis_framework.column_filters import (
    is_numeric, is_string, is_temporal, is_boolean, any_of, not_,
)
from buckaroo.pluggable_analysis_framework.stat_pipeline import (
    StatPipeline, _normalize_inputs,
)
from buckaroo.pluggable_analysis_framework.v1_adapter import (
    col_analysis_to_stat_funcs,
)
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.pluggable_analysis_framework.utils import PERVERSE_DF


# ============================================================================
# Test fixtures — v2 stat functions
# ============================================================================

# Note: The function name becomes the stat key in the DAG.
# So `length` provides 'length', `distinct_count` provides 'distinct_count', etc.

@stat()
def length(ser: RawSeries) -> int:
    return len(ser)


@stat()
def null_count(ser: RawSeries) -> int:
    return int(ser.isna().sum())


@stat()
def distinct_count(ser: RawSeries) -> int:
    return len(ser.value_counts())


@stat()
def distinct_per(length: int, distinct_count: int) -> float:
    return distinct_count / length


@stat()
def nan_per(length: int, null_count: int) -> float:
    return null_count / length if length > 0 else 0.0


@stat(column_filter=is_numeric)
def mean_stat(ser: RawSeries) -> float:
    return float(ser.mean())


@stat(default=0.0)
def safe_ratio(length: int, distinct_count: int) -> float:
    return distinct_count / length


class FreqStats(TypedDict):
    most_freq: Any
    freq_count: int


@stat()
def freq_stats(ser: RawSeries) -> FreqStats:
    vc = ser.value_counts()
    if len(vc) > 0:
        return FreqStats(most_freq=vc.index[0], freq_count=int(vc.iloc[0]))
    return FreqStats(most_freq=None, freq_count=0)


# Stat group class
class BasicStats:
    @stat()
    def grp_length(ser: RawSeries) -> int:
        return len(ser)

    @stat()
    def grp_null_count(ser: RawSeries) -> int:
        return int(ser.isna().sum())


# V1 ColAnalysis fixtures
class V1Len(ColAnalysis):
    provides_defaults = {'length': 0}
    provides_series_stats = ['length']

    @staticmethod
    def series_summary(sampled_ser, ser):
        return {'length': len(ser)}


class V1DistinctCount(ColAnalysis):
    provides_defaults = {'distinct_count': 0}
    provides_series_stats = ['distinct_count']

    @staticmethod
    def series_summary(sampled_ser, ser):
        return {'distinct_count': len(ser.value_counts())}


class V1DistinctPer(ColAnalysis):
    provides_defaults = {'distinct_per': 0.0}
    requires_summary = ['length', 'distinct_count']

    @staticmethod
    def computed_summary(summary_dict):
        l = summary_dict['length']
        dc = summary_dict['distinct_count']
        return {'distinct_per': dc / l if l > 0 else 0.0}


class V1Combined(ColAnalysis):
    """V1 class with both series_summary and computed_summary."""
    provides_defaults = {'raw_len': 0, 'doubled_len': 0}
    provides_series_stats = ['raw_len']
    requires_summary = ['raw_len']

    @staticmethod
    def series_summary(sampled_ser, ser):
        return {'raw_len': len(ser)}

    @staticmethod
    def computed_summary(summary_dict):
        return {'doubled_len': summary_dict.get('raw_len', 0) * 2}


# ============================================================================
# Tests: stat_func
# ============================================================================

class TestStatDecorator:
    def test_basic_raw_series(self):
        sf = length._stat_func
        assert sf.name == 'length'
        assert len(sf.requires) == 1
        assert sf.requires[0].name == 'ser'
        assert sf.requires[0].type is RawSeries
        assert sf.needs_raw is True
        assert len(sf.provides) == 1
        assert sf.provides[0].name == 'length'
        assert sf.provides[0].type is int

    def test_computed_stat(self):
        sf = distinct_per._stat_func
        assert sf.name == 'distinct_per'
        assert sf.needs_raw is False
        assert len(sf.requires) == 2
        req_names = {r.name for r in sf.requires}
        assert req_names == {'length', 'distinct_count'}
        assert sf.requires[0].type is int
        assert sf.provides[0].name == 'distinct_per'
        assert sf.provides[0].type is float

    def test_typed_dict_return(self):
        sf = freq_stats._stat_func
        assert sf.name == 'freq_stats'
        assert len(sf.provides) == 2
        prov_names = {p.name for p in sf.provides}
        assert prov_names == {'most_freq', 'freq_count'}

    def test_column_filter(self):
        sf = mean_stat._stat_func
        assert sf.column_filter is is_numeric

    def test_default(self):
        sf = safe_ratio._stat_func
        assert sf.default == 0.0

    def test_no_default(self):
        sf = distinct_per._stat_func
        assert sf.default is MISSING


class TestStatKey:
    def test_frozen(self):
        sk = StatKey('foo', int)
        with pytest.raises(AttributeError):
            sk.name = 'bar'

    def test_equality(self):
        assert StatKey('foo', int) == StatKey('foo', int)
        assert StatKey('foo', int) != StatKey('foo', float)

    def test_repr(self):
        sk = StatKey('length', int)
        assert 'length' in repr(sk)
        assert 'int' in repr(sk)


class TestCollectStatFuncs:
    def test_from_stat_func(self):
        sf = length._stat_func
        assert collect_stat_funcs(sf) == [sf]

    def test_from_decorated_function(self):
        funcs = collect_stat_funcs(length)
        assert len(funcs) == 1
        assert funcs[0].name == 'length'

    def test_from_class(self):
        funcs = collect_stat_funcs(BasicStats)
        assert len(funcs) == 2
        names = {f.name for f in funcs}
        assert names == {'grp_length', 'grp_null_count'}

    def test_from_unknown(self):
        assert collect_stat_funcs(42) == []
        assert collect_stat_funcs("hello") == []


class TestMissingSentinel:
    def test_singleton(self):
        assert MISSING is MISSING

    def test_falsy(self):
        assert not MISSING

    def test_repr(self):
        assert repr(MISSING) == '<MISSING>'


# ============================================================================
# Tests: stat_result
# ============================================================================

class TestOkErr:
    def test_ok(self):
        r = Ok(42)
        assert r.value == 42

    def test_ok_frozen(self):
        r = Ok(42)
        with pytest.raises(AttributeError):
            r.value = 99

    def test_err(self):
        e = Err(
            error=ValueError("bad"),
            stat_func_name="test",
            column_name="col1",
            inputs={'a': 1},
        )
        assert isinstance(e.error, ValueError)
        assert e.stat_func_name == 'test'
        assert e.column_name == 'col1'
        assert e.inputs == {'a': 1}

    def test_upstream_error(self):
        orig = ValueError("original")
        ue = UpstreamError("downstream", "input_x", orig)
        assert "downstream" in str(ue)
        assert "input_x" in str(ue)
        assert ue.original_error is orig


class TestResolveAccumulator:
    def test_all_ok(self):
        acc = {'a': Ok(1), 'b': Ok('hello')}
        plain, errors = resolve_accumulator(acc, 'col1')
        assert plain == {'a': 1, 'b': 'hello'}
        assert errors == []

    def test_with_err(self):
        acc = {
            'a': Ok(1),
            'b': Err(ValueError("bad"), "func", "col1"),
        }
        plain, errors = resolve_accumulator(acc, 'col1')
        assert plain['a'] == 1
        assert plain['b'] is None
        assert len(errors) == 1
        assert errors[0].stat_key == 'b'

    def test_with_key_to_func(self):
        sf = StatFunc(
            name='test', func=lambda: None,
            requires=[], provides=[StatKey('a', int)],
            needs_raw=False,
        )
        acc = {'a': Err(ValueError("bad"), "test", "col1")}
        _, errors = resolve_accumulator(acc, 'col1', {'a': sf})
        assert errors[0].stat_func is sf


class TestStatError:
    def test_reproduce_code_scalar(self):
        sf = StatFunc(
            name='distinct_per', func=distinct_per,
            requires=[StatKey('length', int), StatKey('distinct_count', int)],
            provides=[StatKey('distinct_per', float)],
            needs_raw=False,
        )
        se = StatError(
            column='col1', stat_key='distinct_per',
            error=ZeroDivisionError('division by zero'),
            stat_func=sf,
            inputs={'length': 0, 'distinct_count': 0},
        )
        code = se.reproduce_code()
        assert 'distinct_per' in code
        assert 'ZeroDivisionError' in code
        assert 'length=0' in code

    def test_reproduce_code_series(self):
        sf = StatFunc(
            name='length', func=length,
            requires=[StatKey('ser', RawSeries)],
            provides=[StatKey('length', int)],
            needs_raw=True,
        )
        ser = pd.Series([1, 2, 3])
        se = StatError(
            column='col1', stat_key='length',
            error=TypeError('test'),
            stat_func=sf,
            inputs={'ser': ser},
        )
        code = se.reproduce_code()
        assert 'pd.Series' in code
        assert 'TypeError' in code


# ============================================================================
# Tests: typed_dag
# ============================================================================

class TestBuildTypedDag:
    def test_basic_ordering(self):
        f1 = StatFunc('length', lambda: 10, [], [StatKey('length', int)], False)
        f2 = StatFunc('dc', lambda: 5, [], [StatKey('distinct_count', int)], False)
        f3 = StatFunc(
            'dp', lambda l, d: d / l,
            [StatKey('length', int), StatKey('distinct_count', int)],
            [StatKey('distinct_per', float)],
            False,
        )
        ordered = build_typed_dag([f3, f1, f2])
        names = [f.name for f in ordered]
        assert names.index('length') < names.index('dp')
        assert names.index('dc') < names.index('dp')

    def test_missing_provider(self):
        f1 = StatFunc(
            'dp', lambda: None,
            [StatKey('nonexistent', int)],
            [StatKey('result', float)],
            False,
        )
        with pytest.raises(DAGConfigError, match='nonexistent'):
            build_typed_dag([f1])

    def test_raw_types_not_validated(self):
        """RawSeries requirements should not raise DAGConfigError."""
        f1 = StatFunc(
            'length', lambda ser: len(ser),
            [StatKey('ser', RawSeries)],
            [StatKey('length', int)],
            True,
        )
        ordered = build_typed_dag([f1])
        assert len(ordered) == 1

    def test_cycle_detection(self):
        f1 = StatFunc(
            'a', lambda: None,
            [StatKey('b', int)], [StatKey('a', int)], False,
        )
        f2 = StatFunc(
            'b', lambda: None,
            [StatKey('a', int)], [StatKey('b', int)], False,
        )
        with pytest.raises(DAGConfigError, match='[Cc]ycle'):
            build_typed_dag([f1, f2])

    def test_type_mismatch_warning(self):
        f1 = StatFunc('a', lambda: 1.5, [], [StatKey('x', float)], False)
        f2 = StatFunc(
            'b', lambda: None,
            [StatKey('x', int)], [StatKey('y', int)], False,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            build_typed_dag([f1, f2])
            assert len(w) == 1
            assert 'mismatch' in str(w[0].message).lower()

    def test_empty_input(self):
        assert build_typed_dag([]) == []


class TestBuildColumnDag:
    def test_filters_by_dtype(self):
        f_numeric = StatFunc(
            'mean', lambda: 0.0, [StatKey('ser', RawSeries)],
            [StatKey('mean', float)], True,
            column_filter=is_numeric,
        )
        f_all = StatFunc(
            'length', lambda: 0, [StatKey('ser', RawSeries)],
            [StatKey('length', int)], True,
        )

        # Numeric column — both should be included
        result = build_column_dag([f_numeric, f_all], pd.Series([1]).dtype)
        assert len(result) == 2

        # String column — only f_all should be included
        result = build_column_dag([f_numeric, f_all], pd.Series(['a']).dtype)
        assert len(result) == 1
        assert result[0].name == 'length'

    def test_cascade_removal(self):
        """If a filtered-out func provides a key needed by another, cascade remove."""
        f1 = StatFunc(
            'mean', lambda: 0.0, [StatKey('ser', RawSeries)],
            [StatKey('mean', float)], True,
            column_filter=is_numeric,
        )
        f2 = StatFunc(
            'mean_ratio', lambda: 0.0,
            [StatKey('mean', float)],
            [StatKey('mean_ratio', float)], False,
        )
        f3 = StatFunc(
            'length', lambda: 0, [StatKey('ser', RawSeries)],
            [StatKey('length', int)], True,
        )

        # String column: mean is filtered out, mean_ratio cascades out
        result = build_column_dag([f1, f2, f3], pd.Series(['a']).dtype)
        assert len(result) == 1
        assert result[0].name == 'length'


# ============================================================================
# Tests: column_filters
# ============================================================================

class TestColumnFilters:
    def test_is_numeric_pandas(self):
        assert is_numeric(pd.Series([1]).dtype) is True
        assert is_numeric(pd.Series([1.0]).dtype) is True
        assert is_numeric(pd.Series(['a']).dtype) is False
        assert is_numeric(pd.Series([True]).dtype) is True

    def test_is_numeric_nullable(self):
        assert is_numeric(pd.Series([1], dtype='Int64').dtype) is True
        assert is_numeric(pd.Series([None], dtype='UInt8').dtype) is True

    def test_is_string_pandas(self):
        assert is_string(pd.Series(['a']).dtype) is True
        assert is_string(pd.Series([1]).dtype) is False

    def test_is_temporal_pandas(self):
        assert is_temporal(pd.Series(pd.to_datetime(['2021-01-01'])).dtype) is True
        assert is_temporal(pd.Series([1]).dtype) is False

    def test_is_boolean_pandas(self):
        assert is_boolean(pd.Series([True, False]).dtype) is True
        assert is_boolean(pd.Series([1]).dtype) is False

    def test_any_of(self):
        pred = any_of(is_numeric, is_string)
        assert pred(pd.Series([1]).dtype) is True
        assert pred(pd.Series(['a']).dtype) is True
        assert pred(pd.Series(pd.to_datetime(['2021-01-01'])).dtype) is False

    def test_not_(self):
        pred = not_(is_numeric)
        assert pred(pd.Series([1]).dtype) is False
        assert pred(pd.Series(['a']).dtype) is True


# ============================================================================
# Tests: v1_adapter
# ============================================================================

class TestV1Adapter:
    def test_series_only_class(self):
        funcs = col_analysis_to_stat_funcs(V1Len)
        assert len(funcs) == 1
        sf = funcs[0]
        assert sf.name == 'V1Len__series'
        assert sf.needs_raw is True
        prov_names = {sk.name for sk in sf.provides}
        assert 'length' in prov_names

    def test_computed_only_class(self):
        funcs = col_analysis_to_stat_funcs(V1DistinctPer)
        assert len(funcs) == 1
        sf = funcs[0]
        assert sf.name == 'V1DistinctPer__computed'
        assert sf.needs_raw is False
        req_names = {sk.name for sk in sf.requires}
        assert req_names == {'length', 'distinct_count'}

    def test_combined_class(self):
        """Class with both series_summary and computed_summary."""
        funcs = col_analysis_to_stat_funcs(V1Combined)
        assert len(funcs) == 2
        names = {f.name for f in funcs}
        assert 'V1Combined__series' in names
        assert 'V1Combined__computed' in names

    def test_series_func_executes(self):
        funcs = col_analysis_to_stat_funcs(V1Len)
        sf = funcs[0]
        result = sf.func(ser=pd.Series([1, 2, 3]))
        assert isinstance(result, dict)
        assert result['length'] == 3

    def test_computed_func_executes(self):
        funcs = col_analysis_to_stat_funcs(V1DistinctPer)
        sf = funcs[0]
        result = sf.func(length=10, distinct_count=5)
        assert isinstance(result, dict)
        assert result['distinct_per'] == 0.5


# ============================================================================
# Tests: stat_pipeline
# ============================================================================

class TestNormalizeInputs:
    def test_stat_func_passthrough(self):
        sf = length._stat_func
        result = _normalize_inputs([sf])
        assert result == [sf]

    def test_decorated_function(self):
        result = _normalize_inputs([length])
        assert len(result) == 1
        assert result[0].name == 'length'

    def test_stat_group_class(self):
        result = _normalize_inputs([BasicStats])
        assert len(result) == 2

    def test_v1_col_analysis(self):
        result = _normalize_inputs([V1Len])
        assert len(result) == 1
        assert result[0].name == 'V1Len__series'

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            _normalize_inputs([42])

    def test_mixed_inputs(self):
        result = _normalize_inputs([V1Len, distinct_count, BasicStats])
        assert len(result) >= 3


class TestStatPipeline:
    def test_basic_pipeline(self):
        pipeline = StatPipeline(
            [length, distinct_count, distinct_per],
            unit_test=False,
        )
        assert 'distinct_per' in pipeline.provided_summary_facts_set
        assert 'length' in pipeline.provided_summary_facts_set

    def test_process_column(self):
        pipeline = StatPipeline(
            [length, distinct_count, distinct_per],
            unit_test=False,
        )
        ser = pd.Series([1, 2, 3, 1, 2])
        result, errors = pipeline.process_column(
            column_name='test',
            column_dtype=ser.dtype,
            raw_series=ser,
        )
        assert result['length'] == 5
        assert result['distinct_count'] == 3
        assert result['distinct_per'] == 3 / 5
        assert errors == []

    def test_process_df(self):
        pipeline = StatPipeline(
            [length, null_count, nan_per],
            unit_test=False,
        )
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [None, 2, None]})
        result, errors = pipeline.process_df(df)
        assert len(result) == 2

        for col_key, col_stats in result.items():
            assert 'length' in col_stats
            assert 'null_count' in col_stats
            assert 'nan_per' in col_stats

    def test_error_propagation(self):
        """Errors should propagate downstream via UpstreamError."""
        @stat()
        def always_fails(ser: RawSeries) -> int:
            raise ValueError("intentional failure")

        @stat()
        def depends_on_fail(always_fails: int) -> float:
            return always_fails * 2.0

        pipeline = StatPipeline(
            [always_fails, depends_on_fail],
            unit_test=False,
        )
        ser = pd.Series([1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)

        assert result['always_fails'] is None
        assert result['depends_on_fail'] is None
        assert len(errors) >= 1

    def test_default_fallback(self):
        """@stat(default=...) should produce Ok(default) on error."""
        @stat(default=-1)
        def fails_with_default(ser: RawSeries) -> int:
            raise ValueError("intentional")

        pipeline = StatPipeline([fails_with_default], unit_test=False)
        ser = pd.Series([1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['fails_with_default'] == -1
        assert errors == []

    def test_type_enforcement_at_boundary(self):
        """If a provider declares int but produces str, the consumer gets a TypeError."""
        @stat()
        def bad_length(ser: RawSeries) -> int:
            return "not_an_int"  # lies about its return type

        @stat()
        def needs_int(bad_length: int) -> float:
            return bad_length * 2.0

        pipeline = StatPipeline([bad_length, needs_int], unit_test=False)
        ser = pd.Series([1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)

        # bad_length itself succeeds (it returned a value)
        assert result['bad_length'] == "not_an_int"
        # but needs_int should fail with TypeError because it declared int
        assert result['needs_int'] is None
        assert len(errors) == 1
        assert isinstance(errors[0].error, TypeError)
        assert 'int' in str(errors[0].error)
        assert 'str' in str(errors[0].error)

    def test_column_filter(self):
        """Numeric-only stat should not appear for string columns."""
        pipeline = StatPipeline(
            [length, mean_stat],
            unit_test=False,
        )
        df = pd.DataFrame({'nums': [1, 2, 3], 'strs': ['a', 'b', 'c']})
        result, errors = pipeline.process_df(df)

        for col_key, col_stats in result.items():
            if col_stats.get('orig_col_name') == 'strs':
                assert 'mean_stat' not in col_stats
            elif col_stats.get('orig_col_name') == 'nums':
                assert 'mean_stat' in col_stats

    def test_typed_dict_return(self):
        pipeline = StatPipeline([freq_stats], unit_test=False)
        ser = pd.Series([1, 1, 2, 3])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['most_freq'] == 1
        assert result['freq_count'] == 2

    def test_v1_compat_mixed(self):
        """Mix v1 and v2 in the same pipeline."""
        pipeline = StatPipeline(
            [V1Len, V1DistinctCount, distinct_per],
            unit_test=False,
        )
        ser = pd.Series([1, 2, 3, 1])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 4
        assert result['distinct_count'] == 3
        assert result['distinct_per'] == 3 / 4

    def test_explain(self):
        pipeline = StatPipeline([length, distinct_per, distinct_count], unit_test=False)
        explanation = pipeline.explain('distinct_per')
        assert 'distinct_per' in explanation
        assert 'length' in explanation
        assert 'distinct_count' in explanation

    def test_test_stat(self):
        pipeline = StatPipeline([length, distinct_count, distinct_per], unit_test=False)
        result = pipeline.test_stat('distinct_per', {'length': 10, 'distinct_count': 5})
        assert isinstance(result, Ok)
        assert result.value == 0.5

    def test_test_stat_error(self):
        pipeline = StatPipeline([length, distinct_count, distinct_per], unit_test=False)
        result = pipeline.test_stat('distinct_per', {'length': 0, 'distinct_count': 0})
        assert isinstance(result, Err)

    def test_add_stat(self):
        pipeline = StatPipeline([length, distinct_count], unit_test=False)
        assert 'distinct_per' not in pipeline.provided_summary_facts_set
        passed, errors = pipeline.add_stat(distinct_per)
        assert 'distinct_per' in pipeline.provided_summary_facts_set

    def test_dag_config_error(self):
        """Pipeline should raise DAGConfigError for unsatisfiable deps."""
        with pytest.raises(DAGConfigError):
            StatPipeline([distinct_per], unit_test=False)

    def test_process_perverse_df(self):
        """Pipeline should handle PERVERSE_DF without crashing."""
        pipeline = StatPipeline(
            [length, null_count, distinct_count, nan_per, distinct_per],
            unit_test=False,
        )
        result, errors = pipeline.process_df(PERVERSE_DF)
        assert len(result) == len(PERVERSE_DF.columns)

    def test_empty_df(self):
        pipeline = StatPipeline([length], unit_test=False)
        result, errors = pipeline.process_df(pd.DataFrame({}))
        assert result == {}
        assert errors == []

    def test_unit_test_runs(self):
        pipeline = StatPipeline(
            [length, null_count, nan_per],
            unit_test=True,
        )
        passed, errors = pipeline._unit_test_result
        assert passed is True


class TestStatPipelineV1Compat:
    """Test backward compatibility with v1 ColAnalysis classes."""

    def test_v1_only_pipeline(self):
        pipeline = StatPipeline(
            [V1Len, V1DistinctCount, V1DistinctPer],
            unit_test=False,
        )
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [1, 1, 1]})
        result, errors = pipeline.process_df(df)
        assert len(result) == 2

        for col_key, col_stats in result.items():
            assert 'length' in col_stats
            assert 'distinct_count' in col_stats
            assert 'distinct_per' in col_stats

    def test_v1_process_df_v1_compat(self):
        """process_df_v1_compat should return ErrDict format."""
        pipeline = StatPipeline([V1Len], unit_test=False)
        df = pd.DataFrame({'a': [1, 2, 3]})
        result, errs = pipeline.process_df_v1_compat(df)
        assert isinstance(errs, dict)
        assert len(errs) == 0


# ============================================================================
# Tests: df_stats_v2
# ============================================================================

class TestDfStatsV2:
    def test_basic_usage(self):
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        stats = DfStatsV2(df, [V1Len, V1DistinctCount, V1DistinctPer])
        assert isinstance(stats.sdf, dict)
        assert len(stats.sdf) == 2

    def test_interface_matches_dfstats(self):
        from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
        df = pd.DataFrame({'x': [1, 2, 3]})
        stats = DfStatsV2(df, [V1Len])
        assert hasattr(stats, 'sdf')
        assert hasattr(stats, 'errs')
        assert hasattr(stats, 'df')
        assert hasattr(stats, 'col_order')
        assert hasattr(stats, 'ap')


# ============================================================================
# Integration tests
# ============================================================================

class TestIntegration:
    def test_mix_v1_v2_pipeline(self):
        """The primary integration test from the plan: mix v1 and v2."""
        pipeline = StatPipeline([
            V1Len,             # v1 ColAnalysis (series only)
            V1DistinctCount,   # v1 ColAnalysis (series only)
            distinct_per,      # v2 @stat function
        ], unit_test=False)

        ser = pd.Series([1, 2, 3, 1, 2])
        result, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert result['length'] == 5
        assert result['distinct_count'] == 3
        assert result['distinct_per'] == 3 / 5
        assert errors == []

    def test_full_pipeline_on_perverse_df(self):
        """Run a realistic pipeline on PERVERSE_DF."""
        pipeline = StatPipeline([
            length,
            null_count,
            distinct_count,
            nan_per,
            distinct_per,
        ], unit_test=False)

        result, errors = pipeline.process_df(PERVERSE_DF)
        assert len(result) == len(PERVERSE_DF.columns)

        for col_key, col_stats in result.items():
            assert 'length' in col_stats
            assert 'null_count' in col_stats
            assert 'distinct_count' in col_stats
            assert 'nan_per' in col_stats
            assert 'distinct_per' in col_stats

    def test_error_chain_reproduction(self):
        """Verify error reproduction code is generated."""
        @stat()
        def bad_stat(ser: RawSeries) -> float:
            raise RuntimeError("intentional test error")

        pipeline = StatPipeline([bad_stat], unit_test=False)
        ser = pd.Series([1, 2, 3])
        _, errors = pipeline.process_column('test', ser.dtype, raw_series=ser)
        assert len(errors) == 1
        code = errors[0].reproduce_code()
        assert 'RuntimeError' in code
        assert 'bad_stat' in code

    def test_backward_compat_output(self):
        """V1 and V2 pipelines should produce matching stat values."""
        v1_klasses = [V1Len, V1DistinctCount, V1DistinctPer]
        v2_pipeline = StatPipeline(v1_klasses, unit_test=False)

        df = pd.DataFrame({'a': [1, 2, 3, 1], 'b': ['x', 'y', 'x', 'x']})
        v2_result, v2_errors = v2_pipeline.process_df(df)

        # Verify expected stat values
        for col_key, col_stats in v2_result.items():
            assert col_stats['length'] == 4
            assert isinstance(col_stats['distinct_per'], float)
            assert col_stats['distinct_per'] > 0
