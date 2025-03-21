from datetime import datetime as dtdt
import numpy as np
import pandas as pd
from buckaroo.customizations.analysis import DefaultSummaryStats
from buckaroo.customizations.histogram import Histogram
from buckaroo.pluggable_analysis_framework.analysis_management import PERVERSE_DF

def without(dct, *keys):
    cleaned_result = dct.copy()
    for k in keys:
        cleaned_result = {i:cleaned_result[i] for i in cleaned_result if i!= k }
    return cleaned_result

text_ser = pd.Series(["foo", "bar", "baz"])
datelike_ser = pd.Series([
    "2014-01-01 00:00:06",
    "2014-01-01 00:00:38",
    "2014-01-01 00:03:59"

])
datetime_ser = pd.Series([dtdt(2000, 1, 1), dtdt(2001, 1, 1), pd.NaT])
all_nan_ser = pd.Series([np.nan, np.nan])
int_ser = pd.Series([10, 30, -10, 33])
fp_ser = pd.Series([33.2, 83.2, -1.0, 0])

nan_text_ser = pd.Series([np.nan, np.nan, 'y', 'y'])
nan_mixed_type_ser = pd.Series([np.nan, np.nan, 'y', 'y', 8.0])
unhashable_ser = pd.Series([['a'], ['b']])

fifty_int_ser = pd.Series([
    5, 1, 6, 8, 3, 5, 9, 2, 4, 2, 4, 4, 9, 3, 5, 1, 4, 2, 2, 9, 2, 5,
    3, 8, 3, 9, 4, 2, 5, 6, 2, 3, 8, 1, 1, 4, 5, 9, 6, 5, 6, 7, 6, 1,
    7, 5, 8, 7, 3, 1])


all_sers = [
    text_ser, datelike_ser, all_nan_ser,
    int_ser, fp_ser, nan_text_ser, nan_mixed_type_ser, unhashable_ser]

def test_text_ser():
    DefaultSummaryStats.series_summary(nan_text_ser,  nan_text_ser)
    DefaultSummaryStats.series_summary(nan_mixed_type_ser, nan_mixed_type_ser)

def test_unhashable():
    result = DefaultSummaryStats.series_summary(unhashable_ser, unhashable_ser)
    #print(result)
    cleaned_result = {i:result[i] for i in result if i!='value_counts'}
    assert     {'length': 2, 'null_count': 0, 
                'mode': ['a'], 'min': np.nan, 'max': np.nan} == cleaned_result

def test_unhashable3():
    ser = pd.Series([{'a':1, 'b':2}, {'b':10, 'c': 5}])
    DefaultSummaryStats.series_summary(ser, ser) # 'nan_per'
    
def test_default_summary_stats():
    for ser in all_sers:
        print(DefaultSummaryStats.series_summary(ser, ser))

def test_datetime_histogram():
    series_result = Histogram.series_summary(
        datetime_ser, datetime_ser)
    assert series_result == {'histogram_args':{}}

    summary_result = Histogram.computed_summary(
        dict(histogram_args={},
             length=3, 
             value_counts=pd.Series(
                 [1,1],
                 index=pd.DatetimeIndex([                   
                     dtdt(2000, 1, 1),
                     dtdt(2001, 1, 1)])),

             min=dtdt(2000, 1, 1),
             max=dtdt(2001, 1, 1),
             is_numeric=False,
             nan_per=.33
             ))

    assert     {
                'histogram': [{'cat_pop': np.float64(33.0),
                               'name': pd.Timestamp('2000-01-01 00:00:00')},
                              {'cat_pop': np.float64(33.0),
                               'name': pd.Timestamp('2001-01-01 00:00:00')},
                              {'name': 'unique', 'unique': np.float64(67.0)},
                              {'NA': np.float64(33.0), 'name': 'NA'}
                              ],
                } == summary_result

def test_numeric_histogram():
    assert {'a':[1,2,3]} == {'a':[1,2,3]}
    series_result = Histogram.series_summary(
        fifty_int_ser, fifty_int_ser)

    actual_histogram_args = series_result['histogram_args']

    rest_ha = without(actual_histogram_args, 'meat_histogram', 'normalized_populations')
    assert rest_ha ==  {'high_tail': 9.0, 'low_tail': 1.0}

    
    expected_meat_histogram = [[7, 6, 0, 6, 0, 8, 5, 0, 3, 4],
                               [2. , 2.6, 3.2, 3.8, 4.4, 5. , 5.6, 6.2, 6.8, 7.3999999999999995, 8. ]]
    meat_histogram = [x.tolist() for x in actual_histogram_args['meat_histogram']]
    assert meat_histogram == expected_meat_histogram
    Histogram.computed_summary(
        {'histogram_args': actual_histogram_args,
         'value_counts': fifty_int_ser.value_counts(),
         'length':50,
         'min': 1,
         'max': 9,
         'is_numeric':True,
         'nan_per':0})

def test_perverse_on_histogram():

    series_result = Histogram.series_summary(
        PERVERSE_DF['all_false'], PERVERSE_DF['all_false'])
    assert series_result == {'histogram_args':{}}
    Histogram.computed_summary(
        dict(histogram_args={},
             length=10, 
             value_counts=pd.Series(
                 [10],
                 index=[False]),
             min=False,
             max=False,
             is_numeric=True,
             nan_per=0
             ))

def test_perverse_on_histogram2():

    series_result = Histogram.series_summary(
        PERVERSE_DF['UInt8None'], PERVERSE_DF['UInt8None'])
    assert series_result == {'histogram_args':{}}
    Histogram.computed_summary(
        dict(histogram_args={},
             length=10, 
             value_counts=pd.Series(
                 [10],
                 index=[False]),
             min=False,
             max=False,
             is_numeric=True,
             nan_per=0
             ))



def test_weird_grouper():
    """fails on

  File "/Users/paddy/buckaroo/buckaroo/customizations/analysis.py", line 86, in series_summary
    value_counts = ser.value_counts()
                   ^^^^^^^^^^^^^^^^^^
  File "/Users/paddy/anaconda3/envs/buckaroo-dev-5/lib/python3.11/site-packages/pandas/core/frame.py", line 7264, in value_counts
    counts = self.groupby(subset, dropna=dropna, observed=False).grouper.size()
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/paddy/anaconda3/envs/buckaroo-dev-5/lib/python3.11/site-packages/pandas/core/frame.py", line 8869, in groupby
    return DataFrameGroupBy(
           ^^^^^^^^^^^^^^^^^
  File "/Users/paddy/anaconda3/envs/buckaroo-dev-5/lib/python3.11/site-packages/pandas/core/groupby/groupby.py", line 1278, in __init__
    grouper, exclusions, obj = get_grouper(
    # """
    # df = pd.DataFrame({'a':np.random.randint(1,50,200), 'b': np.random.randint(1,30,200)})
    # a_ser = df['a'].value_counts()
    # b_ser = df['b'].value_counts()
    # a_df = pd.DataFrame({
    #     'a': a_ser.index.values, 'a_counts': a_ser.values})
    # b_df = pd.DataFrame({    'b': b_ser.index.values, 'a_counts': b_ser.values})
    # merged_df = pd.concat([a_df, b_df], axis=1)

    #ahh "a_counts" is repeated, hmmm
    
