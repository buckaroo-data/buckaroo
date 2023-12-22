from unittest import TestCase

import polars as pl
import numpy as np
from polars import functions as F
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PlTyping, BasicAnalysis, HistogramAnalysis,
    ComputedDefaultSummaryStats)

from buckaroo.pluggable_analysis_framework.utils import (json_postfix, replace_in_dict)

from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    full_produce_summary_df,
    produce_series_df, PolarsAnalysis, extract_table_hint)

test_df = pl.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        #'empty_na_ser' : pl.Series([pl.Null] * 4, dtype="Int64"),
        'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])
    })

word_only_df = pl.DataFrame({'letters': 'h o r s e'.split(' ')})

df = pl.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

empty_df = pl.DataFrame({})
#empty_df_with_columns = pl.DataFrame({}, columns=[0])



class SelectOnlyAnalysis(PolarsAnalysis):

    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
        F.all().quantile(.99).name.map(json_postfix('quin99'))]


def test_produce_series_df():
    """just make sure this doesn't fail"""
    
    sdf, errs = produce_series_df(
        test_df, [SelectOnlyAnalysis], 'test_df', debug=True)
    expected = {
        'float_nan_ser':      {'mean': None, 'null_count':  0, 'quin99': None},
        'normal_int_series':  {'mean': 2.5,  'null_count':  0, 'quin99':  4.0}}
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected

class MaxAnalysis(PolarsAnalysis):
    select_clauses = [F.all().max().name.map(json_postfix('max'))]

def test_produce_series_combine_df():
    """just make sure this doesn't fail"""
    
    sdf, errs = produce_series_df(
        test_df, [SelectOnlyAnalysis, MaxAnalysis], 'test_df', debug=True)
    expected = {
        'float_nan_ser':      {'mean': None, 'null_count':  0, 'quin99': None, 'max': 4.8},
        'normal_int_series':  {'mean': 2.5,  'null_count':  0, 'quin99':  4.0, 'max': 4.0},
        }
    dsdf = replace_in_dict(sdf, [(np.nan, None)])
    assert dsdf == expected

def test_produce_series_column_ops():
    mixed_df = pl.DataFrame(
        {'string_col': ["foo", "bar", "baz"] + [""]*2,
         'int_col':[1,2,3,30, 100],
         'float_col':[1.1, 1.1, 3, 3, 5]})

    summary_df, _unused = produce_series_df(mixed_df, [HistogramAnalysis])
    assert summary_df["string_col"] == {}

    assert summary_df["int_col"]["histogram_args"]["meat_histogram"] == (
        [2,  0,  0,  0,  0,  0,  0,  0,  0,  1],
        [1.0,  4.0,  7.0,  10.0,  13.0,  16.0,  19.0,  22.0,  25.0,  28.0,  100.0],)
    

HA_CLASSES = [VCAnalysis, PlTyping, BasicAnalysis,  ComputedDefaultSummaryStats,  HistogramAnalysis]
def test_histogram_analysis():
    cats = [chr(x) for x in range(97, 102)] * 2 
    cats += [chr(x) for x in range(103,113)]
    cats += ['foo']*30 + ['bar'] * 50

    df = pl.DataFrame({'categories': cats, 'numerical_categories': [3]*30 + [7] * 70})
    summary_df, _unused, errs = full_produce_summary_df(df, HA_CLASSES, debug=True)
    assert summary_df["categories"]["categorical_histogram"] == {'bar': 0.5, 'foo': 0.3, 'longtail': 0.1, 'unique': 0.1}
    assert summary_df["numerical_categories"]["categorical_histogram"] == {3:.3, 7:.7, 'longtail': 0.0, 'unique': 0.0}
    
def test_numeric_histograms():
    #np.random.standard_normal(50)
    #note the negative numbers
    float_arr = np.array(
        [  0.15866514,  1.17068755, -0.33565104,  0.65639612, -1.82228383,
          -0.31636192,  1.15528901,  0.51853447, -2.46400234, -0.43549045,
           0.00352285,  0.81172013, -0.72803939, -1.00862492, -0.22710132,
          -0.3175636 ,  0.75857194, -1.78286566, -1.34886293,  0.13987727,
           0.38449789, -1.40855498,  1.87998263,  0.67376218,  0.35140324,
           0.57988045, -0.88552517, -1.89412544, -0.93349705, -0.79151579,
          -1.43998107,  0.44633053,  0.46607586, -0.28883213, -0.16766607,
           1.49832905,  0.56894383,  0.66272376,  0.89071271, -2.03593151,
          -0.52559652, -1.87226564, -0.55629666, -0.56985112,  0.06456509,
          -0.44142502, -2.09803033,  0.51801718, -1.56189092, -1.17083831])
    #make them all positive numbers
    float_arr2 = float_arr + 2.46400234

    #np.round(np.random.standard_normal(50) * 100).astype('int16')
    int_arr = np.array(
        [-272,  107,  -85,    5,   -6,   19,   38, -102,  -84,   79,  106,
         59, -132,   81, -122,  -62,  -34,   80,   14,   19,  -20, -155,
          1,   -9,   82,   37,  114,   76,  -90,   -2,   63,  169, -239,
         -225,   71,   55,  174,   30,  -69,   99,   62, -116,   51,  -45,
         57,   64,    8,  -20, -130,  -83])
    int_arr2 = int_arr + 272
    df = pl.DataFrame({
        'float_col': float_arr,
        'float_col2': float_arr2,
        'int_col': int_arr,
        'int_col2': int_arr2
    })
                      
    summary_df, _unused, errs = full_produce_summary_df(df, HA_CLASSES, debug=True)
    print(summary_df['int_col']['histogram'])

    expected_float_histogram = [
        {'name': '-2.46400234 - -2.46400234', 'tail': 1},
        {'name': '-2--3', 'population': 0.0},  {'name': '-3--3', 'population': 0.0},
        {'name': '-3--2', 'population': 4.0},  {'name': '-2--1', 'population': 17.0},
        {'name': '-1--0', 'population': 19.0}, {'name': '-0-0',  'population': 25.0},
        {'name': '0-1',   'population': 29.0}, {'name': '1-2',   'population': 6.0},
        {'name': '2-2',   'population': 0.0},  {'name': '2-2',   'population': 0.0},
        {'name': '1.87998263 - 1.87998263', 'tail': 1}]
    assert summary_df['float_col']['histogram'] == expected_float_histogram

    expected_int_histogram = [
        {'name': '-272 - -272.0', 'tail': 1},
        {'name': '-272--199', 'population': 4.0},  {'name': '-199--158', 'population': 0.0},
        {'name': '-158--117', 'population': 8.0},  {'name': '-117--76',  'population': 12.0},
        {'name': '-76--35',   'population': 6.0},  {'name': '-35-6',     'population': 17.0},
        {'name': '6-47',      'population': 15.0}, {'name': '47-88',     'population': 27.0},
        {'name': '88-129',    'population': 8.0},  {'name': '129-174',   'population': 2.0},
        {'name': '174.0 - 174', 'tail': 1}]
    assert summary_df['int_col']['histogram'] == expected_int_histogram



def test_extract_table_hint():

    summary_dict = {'a': {'null_count': 0,
                          'mean': 35.0,
                          'max': 100,
                          'min': 2,
                          'is_numeric': True,
                          '_type': 'integer',
                          'type': 'integer'}
                    }


    expected =  {
        'a': {
            'type':'integer',
            'is_numeric': True,
            'is_integer': None,
            'min_digits':None,
            'max_digits':None,
            'formatter':None,
            'histogram': []}}
    TestCase().assertDictEqual(expected, extract_table_hint(summary_dict, ['a']))
