from functools import reduce
import pandas as pd
from pandas.io.json import dumps as pdumps
import numpy as np
from buckaroo.pluggable_analysis_framework import ColAnalysis

def probable_datetime(ser):
    s_ser = ser.sample(np.min([len(ser), 500]))
    try:
        dt_ser = pd.to_datetime(s_ser)
        #pd.to_datetime(1_00_000_000_000_000_000) == pd.to_datetime('1973-01-01') 
        if dt_ser.max() < pd.to_datetime('1973-01-01'):
            return False
        return True
        
    except Exception as e:
        return False

def get_mode(ser):
    mode_raw = ser.mode()
    if len(mode_raw) == 0:
        return np.nan
    else:
        return mode_raw.values[0]

"""
to best take advantage of the DAG and pluggable_analysis_framework, structure your code as follows
a single ColAnalysis can return multiple facts, but those facts shouldn't be interdepedent
That way individual facts can be overridden via the DAG machinery, and other facts that depend on them will
get the proper value

Overtime codebases will probably trend towards many classes with single facts, but it doesn't have to be that way.  Code what comes naturally to you


"""

class TypingStats(ColAnalysis):
    provided_summary = [
        'dtype', 'is_numeric', 'is_integer', 'is_datetime',]

    @staticmethod
    def summary(sampled_ser, summary_ser, ser):
        return dict(
            dtype=ser.dtype,
            is_numeric=pd.api.types.is_numeric_dtype(ser),
            is_integer=pd.api.types.is_integer_dtype(ser),
            is_datetime=probable_datetime(ser),
            memory_usage=ser.memory_usage()
            )

class DefaultSummaryStats(ColAnalysis):
    provided_summary = [
        'length', 'min', 'max', 'mean', 'nan_count', 'distinct_count',
        'distinct_per', 'empty_count', 'empty_per', 'unique_per', 'nan_per',
        'mode']

    summary_stats_display = [
        'dtype',
        'length', 'nan_count', 'distinct_count', 'empty_count',
        'empty_per', 'unique_per', 'nan_per', 'is_numeric', 'is_integer',
        'is_datetime', 'mode', 'min', 'max','mean']
    
    @staticmethod
    def summary(sampled_ser, summary_ser, ser):
        l = len(ser)
        val_counts = ser.value_counts()
        distinct_count= len(val_counts)
        nan_count = l - len(ser.dropna())
        unique_count = len(val_counts[val_counts==1])
        empty_count = val_counts.get('', 0)

        is_numeric = pd.api.types.is_numeric_dtype(ser)
        is_object = pd.api.types.is_object_dtype

        base_d = dict(
            length=l,
            nan_count=nan_count,
            distinct_count=distinct_count,
            distinct_per=distinct_count/l,
            empty_count=empty_count,
            empty_per=empty_count/l,
            unique_per=unique_count/l,
            nan_per=nan_count/l,
            mode=get_mode(ser),
            min=(is_numeric and ser.dropna().min() or np.nan),
            max=(is_numeric and ser.dropna().max() or np.nan),
            mean=(is_numeric and ser.dropna().mean() or np.nan))
        if is_numeric:
            base_d['mean'] = ser.mean()
        return base_d


def int_digits(n):
    if n == 0:
        return 1
    if np.sign(n) == -1:
        return int(np.floor(np.log10(np.abs(n)))) + 2
    return int(np.floor(np.log10(n)+1))

def histogram(ser):
    raw_counts, bins = np.histogram(ser, 10)
    scaled_counts = np.round(raw_counts/raw_counts.sum(),2)
    return [scaled_counts, bins]


class ColDisplayHints(ColAnalysis):
    requires_summary = ['min', 'max'] # What summary stats does this analysis provide
    provided_summary = []
    
    provides_hints = [
        'is_numeric', 'is_integer', 'min_digits', 'max_digits', 'histogram']

    @staticmethod
    def col_hints(sampled_ser, summary_ser, ser):
        is_numeric = pd.api.types.is_numeric_dtype(ser.dtype)
        if not is_numeric:
            return dict(is_numeric=False)
        if len(ser) == 0:
            return dict(is_numeric=False)
        return dict(
            is_numeric=True,
            is_integer=pd.api.types.is_integer_dtype(ser),
            min_digits=int_digits(summary_ser.loc['min']),
            max_digits=int_digits(summary_ser.loc['max']),
            histogram=histogram(ser))
