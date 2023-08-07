import numpy as np
import pandas as pd
from buckaroo.pluggable_analysis_framework import (ColAnalysis)

test_df = pd.DataFrame({
        'normal_int_series' : pd.Series([1,2,3,4]),
        'empty_na_ser' : pd.Series([], dtype="Int64"),
        'float_nan_ser' : pd.Series([3.5, np.nan, 4.8])
    })

df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')


class DistinctCount(ColAnalysis):
    requires_raw = True
    provided_summary = ["distinct_count"]
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        val_counts = raw_ser.value_counts()
        distinct_count= len(val_counts)
        return {'distinct_count': distinct_count}

class Len(ColAnalysis):
    provided_summary = ["len"]
    requires_raw = True
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        return {'len': len(raw_ser)}


class DistinctPer(ColAnalysis):
    provided_summary = ["distinct_per"]
    requires_summary = ["len", "distinct_count"]
    
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        return {'distinct_per': summary_ser.loc['distinct_count'] / summary_ser.loc['len']}

class DistinctCount(ColAnalysis):
    requires_raw = True
    provided_summary = ["distinct_count"]
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        val_counts = raw_ser.value_counts()
        distinct_count= len(val_counts)
        return {'distinct_count': distinct_count}

class Len(ColAnalysis):
    provided_summary = ["len"]
    requires_raw = True
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        return {'len': len(raw_ser)}

class DCLen(ColAnalysis):
    provided_summary = ["len", "distinct_count"]
    requires_raw = True
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        val_counts = raw_ser.value_counts()
        distinct_count= len(val_counts)
        return {'len':len(raw_ser), 'distinct_count':distinct_count}

class DistinctPer(ColAnalysis):
    provided_summary = ["distinct_per"]
    requires_summary = ["len", "distinct_count"]
    
    @staticmethod
    def summary(sampled_ser, summary_ser, raw_ser):
        return {'distinct_per': summary_ser.loc['distinct_count'] / summary_ser.loc['len']}

class DependsNoProvides(ColAnalysis):
    requires_summary = ["len"]
