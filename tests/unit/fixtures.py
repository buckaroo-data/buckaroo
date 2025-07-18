import numpy as np
import pandas as pd
from buckaroo.pluggable_analysis_framework.col_analysis import (ColAnalysis)

test_df = pd.DataFrame({
        'normal_int_series' : pd.Series([1,2,3,4]),
        'empty_na_ser' : pd.Series([], dtype="Int64"),
        'float_nan_ser' : pd.Series([3.5, np.nan, 4.8])
    })

test_multi_index_df = pd.DataFrame({
    'normal_int_series' : pd.Series([1,2,3,4]),
    'empty_na_ser' : pd.Series([], dtype="Int64"),
    'float_nan_ser' : pd.Series([3.5, np.nan, 4.8])})

test_multi_index_df.columns = pd.MultiIndex.from_tuples(
[('foo', 'normal_int_series'), ('foo', 'empty_na_ser'), ('bar', 'float_nan_ser')])

word_only_df = pd.DataFrame({'letters': 'h o r s e'.split(' ')})

df = pd.read_csv('./docs/example-notebooks/data/2014-01-citibike-tripdata.csv')

empty_df = pd.DataFrame({})
empty_df_with_columns = pd.DataFrame({}, columns=[0])



class DistinctCount(ColAnalysis):
    provides_defaults = {'distinct_count':0}
    requires_raw = True
    provides_series_stats = ["distinct_count"]

    @staticmethod
    def series_summary(sampled_ser, raw_ser):
        val_counts = raw_ser.value_counts()
        distinct_count= len(val_counts)
        return {'distinct_count': distinct_count}

class Len(ColAnalysis):
    provides_defaults = {'len':0}
    provides_series_stats = ["len"]
    requires_raw = True

    @staticmethod
    def series_summary(sampled_ser, ser):
        return {'len': len(ser)}

class DCLen(ColAnalysis):
    provides_defaults = {'len':0, 'distinct_count':0}
    provides_series_stats = ["len", "distinct_count"]
    requires_raw = True

    @staticmethod
    def series_summary(sampled_ser, raw_ser):
        val_counts = raw_ser.value_counts()
        distinct_count= len(val_counts)
        return {'distinct_count': distinct_count}


class DistinctPer(ColAnalysis):
    provides_defaults = {'distinct_per':0}
    requires_summary = ["len", "distinct_count"]
    
    @staticmethod
    def computed_summary(summary_dict):
        print("summary_dict", summary_dict)
        return {'distinct_per': summary_dict['distinct_count'] / summary_dict['len']}

class DependsNoProvides(ColAnalysis):
    provides_defaults = {}
    requires_summary = ["len"]
