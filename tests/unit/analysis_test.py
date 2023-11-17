from datetime import datetime as dtdt
import numpy as np
import pandas as pd
from buckaroo.customizations.analysis import TypingStats, DefaultSummaryStats, ColDisplayHints


text_ser = pd.Series(["foo", "bar", "baz"])
datelike_ser = pd.Series([
    "2014-01-01 00:00:06",
    "2014-01-01 00:00:38",
    "2014-01-01 00:03:59"])
datetime_ser = pd.Series([dtdt(2000, 1, 1), dtdt(2001, 1, 1), pd.NaT])
all_nan_ser = pd.Series([np.nan, np.nan])
int_ser = pd.Series([10, 30, -10, 33])
fp_ser = pd.Series([33.2, 83.2, -1.0, 0])

nan_text_ser = pd.Series([np.nan, np.nan, 'y', 'y'])
nan_mixed_type_ser = pd.Series([np.nan, np.nan, 'y', 'y', 8.0])
unhashable_ser = pd.Series([['a'], ['b']])



all_sers = [
    text_ser, datelike_ser, all_nan_ser,
    int_ser, fp_ser, nan_text_ser, nan_mixed_type_ser, unhashable_ser]

def test_text_ser():
    DefaultSummaryStats.summary(nan_text_ser, nan_text_ser, nan_text_ser)
    DefaultSummaryStats.summary(nan_mixed_type_ser, nan_mixed_type_ser, nan_mixed_type_ser)

def test_unhashable():
    result = DefaultSummaryStats.summary(unhashable_ser, pd.Series({}), unhashable_ser)
    #print(result)

    assert     {'length': 2, 'nan_count': 0, 'distinct_count': 2, 'distinct_per': 1.0, 'empty_count': 0, 'empty_per': 0.0, 'unique_per': 1.0, 'nan_per': 0.0, 'mode': ['a'], 'min': np.nan, 'max': np.nan} == result

def test_unhashable3():
    ser = pd.Series([{'a':1, 'b':2}, {'b':10, 'c': 5}])
    DefaultSummaryStats.summary(ser, pd.Series({ }), ser) # 'nan_per'
    
def test_default_summary_stats():
    for ser in all_sers:
        print(DefaultSummaryStats.summary(ser, ser, ser))

def test_datetime_hints():
    result = ColDisplayHints.summary(
        datetime_ser, {'nan_per':0}, datetime_ser)
    assert     {'type': 'datetime',
                'formatter': 'default',
                'is_integer': False,
                'is_numeric': False,
                'histogram': [{'cat_pop': 33.0,
                               'name': pd.Timestamp('2000-01-01 00:00:00')},
                              {'cat_pop': 33.0,
                               'name': pd.Timestamp('2001-01-01 00:00:00')},
                              {'name': 'longtail', 'unique': 67.0}],
                } == result    
