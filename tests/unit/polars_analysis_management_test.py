import unittest
import polars as pl
import numpy as np
from polars import functions as F
import polars.selectors as cs
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PlTyping, BasicAnalysis, HistogramAnalysis,
    ComputedDefaultSummaryStats)

from buckaroo.pluggable_analysis_framework.utils import (json_postfix, replace_in_dict)
from buckaroo.pluggable_analysis_framework.polars_utils import NUMERIC_POLARS_DTYPES
import json

from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_select_expressions,
    polars_series_stats_from_select_result)
from tests.unit.test_utils import assert_dict_eq


def _summary(df, klasses, run_computed_summary=True):
    """Run PolarsAnalysis select_clauses + column_ops (and optionally
    computed_summary) via the column-executor path that replaced the v1
    PolarsAnalysisPipeline / polars_produce_series_df."""
    exprs = polars_select_expressions(klasses)
    result_df = df.lazy().select(exprs).collect() if exprs else pl.DataFrame()
    return polars_series_stats_from_select_result(
        result_df, df, klasses, run_computed_summary=run_computed_summary)

test_df = pl.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])})

word_only_df = pl.DataFrame({'letters': 'h o r s e'.split(' ')})

df = pl.read_csv('./docs/example-notebooks/data/2014-01-citibike-tripdata.csv')

empty_df = pl.DataFrame({})
#empty_df_with_columns = pl.DataFrame({}, columns=[0])



class SelectOnlyAnalysis(PolarsAnalysis):
    provides_defaults = {'null_count':3}
    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
        F.all().quantile(.99).name.map(json_postfix('quin99'))]

class RequiresNullCount(PolarsAnalysis):
    requires_summary = ['null_count']
    provides_defaults = {'null_count2':-1}

    @staticmethod
    def computed_summary(summary_dict):
        return {'null_count2': summary_dict['null_count']}


class MixedAnalysis(PolarsAnalysis):
    provides_defaults = dict(
        empty_count=0, sum=0)



test_df = pl.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])})
    
def test_simple_mixed_pipeline():
    """ show that a simple polars pipeline where one analysis depends on the other succesfully computes"""

    sdf, errs = _summary(test_df, [SelectOnlyAnalysis, RequiresNullCount])
    expected = {
    'b': {'mean': None,  'null_count':  0, 'null_count2':0, 'quin99': None,
          'orig_col_name':'float_nan_ser', 'rewritten_col_name':'b'},
    'a' :{'mean': 2.5,  'null_count':  0, 'null_count2':0, 'quin99':  4.0,
          'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'}}
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected

def test_non_full_analysis():
    class MixedAnalysis(PolarsAnalysis):
        provides_defaults = dict(
            empty_count=0, sum=0)

        select_clauses = [
            F.col(pl.Utf8).str.count_matches("^$").sum().name.map(json_postfix('empty_count')),
            cs.numeric().sum().name.map(json_postfix('sum'))]

    df = pl.DataFrame({'foo_col': [10, 20], 'bar_col': ['', 'bar']})

    sdf, errs = _summary(df, [MixedAnalysis])
    assert sdf == {'a': dict(empty_count=0, sum=30, orig_col_name='foo_col', rewritten_col_name='a'),
                   'b': dict(empty_count=1, sum=0, orig_col_name='bar_col', rewritten_col_name='b')}

def test_produce_series_df():
    """just make sure this doesn't fail"""

    sdf, errs = _summary(test_df, [SelectOnlyAnalysis], run_computed_summary=False)
    expected = {
    'b': {'mean': None, 'null_count':  0, 'quin99': None, 'orig_col_name':'float_nan_ser', 'rewritten_col_name':'b'},
    'a' :{'mean': 2.5,  'null_count':  0, 'quin99':  4.0, 'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'}
}
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected

class MaxAnalysis(PolarsAnalysis):
    provides_defaults = {}
    select_clauses = [F.all().max().name.map(json_postfix('max'))]

def test_produce_series_combine_df():
    """just make sure this doesn't fail"""

    sdf, errs = _summary(
        test_df, [SelectOnlyAnalysis, MaxAnalysis], run_computed_summary=False)
    expected = {
        
    'b': {'mean': None, 'null_count':  0, 'quin99': None,
          'orig_col_name':'float_nan_ser', 'rewritten_col_name':'b', 'max': 4.8},
    'a' :{'mean': 2.5,  'null_count':  0, 'quin99':  4.0,
          'orig_col_name':'normal_int_series', 'rewritten_col_name':'a', 'max':4.0}
        }
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected



HA_CLASSES = [VCAnalysis, PlTyping, BasicAnalysis, ComputedDefaultSummaryStats, HistogramAnalysis]


def test_numeric_histograms():
    """Test that numeric columns with many distinct values get numeric histograms"""
    # Create a numeric column with many distinct values (> 5)
    numeric_data = np.random.randn(100)  # 100 random values, all distinct
    df = pl.DataFrame({'numeric_col': numeric_data})

    summary_df, errs = _summary(df, HA_CLASSES)

    # Check that we got a numeric histogram (not categorical)
    histogram = summary_df.get('a', {}).get('histogram', [])
    assert len(histogram) > 0, "Should have a histogram"
    
    # Numeric histograms have 'population' or 'tail' keys, not 'cat_pop'
    has_numeric_keys = any('population' in item or 'tail' in item for item in histogram)
    has_categorical_keys = any('cat_pop' in item for item in histogram)
    
    assert has_numeric_keys, f"Expected numeric histogram with 'population' or 'tail' keys, got: {histogram}"
    assert not has_categorical_keys, f"Should not have categorical keys, got: {histogram}"
    
    # Check that histogram_bins is present and not the fake value
    histogram_bins = summary_df.get('a', {}).get('histogram_bins', [])
    assert histogram_bins != ['faked'], "Should have real histogram_bins, not fake"


class PLLen(PolarsAnalysis):


    provides_defaults = {'len':0}

    select_clauses = [
        F.all().len().name.map(json_postfix('len'))]

    
class TestDfStats(unittest.TestCase):
    def test_dfstats_sometimes_present(self):
        """many ColAnalysis objects are written such that they only
        provide stats for certain dtypes. This used to cause
        instantiation failures. This test verifies that there are no
        stack traces. The alternative would be to have ColAnalyis
        objects always return every key, even if NA. That's a less
        natural style to write analyis code.

        Possible future improvement is to run through PERVERSE_DF and
        verify that each ColAnalyis provides its specified value as
        non NA at least once

        """
        #dfs = DfStats(word_only_df, [SometimesProvides])

        #triggers a getter?
        #PlDfStats(word_only_df, [SometimesProvides]).sdf
        pass



    def test_dfstats_return(self):
        """
          test the actual retuns values from dfstats
          """
        sdf, errs = _summary(test_df, [PLLen])

        assert_dict_eq({
            'a': {'len': 4,
                  'orig_col_name':'normal_int_series', 'rewritten_col_name':'a'},
            'b': {'len': 4,
                  'orig_col_name':'float_nan_ser', 'rewritten_col_name':'b'}},
            sdf)


    # def test_dfstats_Missing_Analysis(self):
    #     # this is missing "len" and should throw an exception
    #     with pytest.raises(NotProvidedException):
    #         dfs = DfStats(test_df, [DistinctCount, DistinctPer], 'test_df', debug=True)


class HistogramAnalysisWithColumnOps(PolarsAnalysis):
    """Test analysis that uses column_ops to compute histogram_args."""
    provides_defaults = {'histogram_args': None, 'histogram': []}
    select_clauses = [F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean'))]
    column_ops = {
        'histogram_args': (
            NUMERIC_POLARS_DTYPES,
            lambda ser: {'computed': True, 'sum': float(ser.sum()), 'mean': float(ser.mean())})}


class SimpleColumnOpsAnalysis(PolarsAnalysis):
    """Simple analysis with column_ops for testing."""
    provides_defaults = {'custom_metric': None}
    select_clauses = [F.all().len().name.map(json_postfix('length'))]
    column_ops = {
        'custom_metric': (
            NUMERIC_POLARS_DTYPES,
            lambda ser: {'sum': float(ser.sum()), 'count': len(ser)})}


def test_polars_series_stats_from_select_result_skips_column_ops_with_empty_schema():
    """
    Test that polars_series_stats_from_select_result skips column_ops
    when original_df_for_schema is empty (backward compatibility behavior).
    """
    df = pl.DataFrame({'numeric_col': [1.0, 2.0, 3.0, 4.0, 5.0], 'string_col': ['a', 'b', 'c', 'd', 'e']})
    
    # Create select result (simulating what PAFColumnExecutor would produce)
    select_result = df.lazy().select(F.col('numeric_col').null_count().alias(json.dumps(['numeric_col', 'null_count'])),
        F.col('numeric_col').mean().alias(json.dumps(['numeric_col', 'mean'])),
        F.col('string_col').len().alias(json.dumps(['string_col', 'length']))).collect()
    
    # Empty schema DataFrame (backward compatibility usage)
    empty_schema = pl.DataFrame({c: [] for c in df.columns})
    
    series_stats, errs = polars_series_stats_from_select_result(
        select_result, empty_schema, [HistogramAnalysisWithColumnOps], debug=False)
    
    # Find the numeric column in results
    numeric_col_key = None
    for key, value in series_stats.items():
        if isinstance(value, dict) and value.get('orig_col_name') == 'numeric_col':
            numeric_col_key = key
            break
    
    assert numeric_col_key is not None, "numeric_col should be in series_stats"
    stats = series_stats[numeric_col_key]
    
    # With empty schema, column_ops are skipped (backward compatibility)
    assert 'histogram_args' not in stats or stats.get('histogram_args') is None, (
        f"With empty schema, histogram_args should be skipped. Available keys: {list(stats.keys())}"
    )


def test_polars_series_stats_from_select_result_executes_column_ops_with_data():
    """
    Test that polars_series_stats_from_select_result executes column_ops
    when actual data DataFrame is provided.
    """
    df = pl.DataFrame({'numeric_col': [1.0, 2.0, 3.0, 4.0, 5.0], 'string_col': ['a', 'b', 'c', 'd', 'e']})
    
    # Create select result
    select_result = df.lazy().select(F.col('numeric_col').null_count().alias(json.dumps(['numeric_col', 'null_count'])),
        F.col('numeric_col').mean().alias(json.dumps(['numeric_col', 'mean'])),
        F.col('string_col').len().alias(json.dumps(['string_col', 'length']))).collect()
    
    # Pass actual data DataFrame
    series_stats, errs = polars_series_stats_from_select_result(
        select_result, df, [HistogramAnalysisWithColumnOps], debug=False)
    
    # Find the numeric column in results
    numeric_col_key = None
    for key, value in series_stats.items():
        if isinstance(value, dict) and value.get('orig_col_name') == 'numeric_col':
            numeric_col_key = key
            break
    
    assert numeric_col_key is not None, "numeric_col should be in series_stats"
    stats = series_stats[numeric_col_key]
    
    # With actual data, histogram_args should be computed
    assert 'histogram_args' in stats, (
        f"With actual data, histogram_args should be present. Available keys: {list(stats.keys())}"
    )
    histogram_args = stats['histogram_args']
    assert histogram_args is not None, "histogram_args should not be None"
    assert histogram_args.get('computed') is True, "histogram_args should have computed=True"
    assert 'sum' in histogram_args, "histogram_args should have sum"
    assert histogram_args['sum'] == 15.0, f"Expected sum=15.0, got {histogram_args['sum']}"


def test_polars_series_stats_from_select_result_column_ops_with_simple_analysis():
    """
    Test column_ops execution with a simpler analysis to verify the general pattern.
    """
    df = pl.DataFrame({'numeric_col': [10.0, 20.0, 30.0], 'string_col': ['a', 'b', 'c']})
    
    select_result = df.lazy().select(F.col('numeric_col').len().alias(json.dumps(['numeric_col', 'length']))).collect()
    
    # Pass actual data
    series_stats, errs = polars_series_stats_from_select_result(
        select_result, df, [SimpleColumnOpsAnalysis], debug=False)
    
    numeric_col_key = None
    for key, value in series_stats.items():
        if isinstance(value, dict) and value.get('orig_col_name') == 'numeric_col':
            numeric_col_key = key
            break
    
    assert numeric_col_key is not None
    stats = series_stats[numeric_col_key]
    
    # With actual data, custom_metric should be computed
    assert 'custom_metric' in stats, (
        f"With actual data, custom_metric should be present. Available keys: {list(stats.keys())}"
    )
    custom_metric = stats['custom_metric']
    assert custom_metric is not None
    assert custom_metric['sum'] == 60.0, f"Expected sum=60.0, got {custom_metric['sum']}"
    assert custom_metric['count'] == 3, f"Expected count=3, got {custom_metric['count']}"


def test_polars_series_stats_from_select_result_handles_empty_dataframe():
    """
    Test that the function still works when original_df_for_schema is empty
    (backward compatibility - should not break existing code).
    """
    df = pl.DataFrame({'numeric_col': [1.0, 2.0, 3.0]})
    
    select_result = df.lazy().select(F.col('numeric_col').mean().alias(json.dumps(['numeric_col', 'mean']))).collect()
    
    empty_schema = pl.DataFrame({c: [] for c in df.columns})
    
    # Should not crash even with empty schema
    series_stats, errs = polars_series_stats_from_select_result(
        select_result, empty_schema, [SimpleColumnOpsAnalysis], debug=False)
    
    # Should still produce basic stats from select_result
    assert len(series_stats) > 0, "Should produce some stats even with empty schema"
    
    # column_ops won't run with empty schema, but that's expected (backward compatibility)
