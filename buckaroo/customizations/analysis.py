import pandas as pd
import numpy as np
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
import warnings

def probable_datetime(ser):
    #turning off warnings in this single function is a bit of a hack.
    #Understandable since this is explicitly abusing pd.to_datetime
    #which throws warnings.

    warnings.filterwarnings('ignore')
    s_ser = ser.sample(np.min([len(ser), 500]))
    try:
        dt_ser = pd.to_datetime(s_ser)
        #pd.to_datetime(1_00_000_000_000_000_000) == pd.to_datetime('1973-01-01') 
        warnings.filterwarnings('default')
        if dt_ser.max() < pd.to_datetime('1973-01-01'):
            return False
        return True
        
    except Exception:
        warnings.filterwarnings('default')
        return False

def get_mode(ser):
    try:
        mode_raw = ser.mode()
        if len(mode_raw) == 0:
            return np.nan
        else:
            return mode_raw.values[0]
    except Exception:
        return np.nan


"""
to best take advantage of the DAG and pluggable_analysis_framework, structure your code as follows
a single ColAnalysis can return multiple facts, but those facts shouldn't be interdepedent
That way individual facts can be overridden via the DAG machinery, and other facts that depend on them will
get the proper value

Overtime codebases will probably trend towards many classes with single facts, but it doesn't have to be that way.  Code what comes naturally to you


"""

class TypingStats(ColAnalysis):

    provides_defaults = {
        'dtype':'asdf', 'is_numeric':False, 'is_integer':False,
        'is_datetime':False, 'is_bool':False, 'is_float':False, '_type':'asdf'}

    @staticmethod
    def series_summary(sampled_ser, ser):
        return dict(
            dtype=str(ser.dtype),
            is_numeric=pd.api.types.is_numeric_dtype(ser),
            is_integer=pd.api.types.is_integer_dtype(ser),
            is_datetime=probable_datetime(ser),
            is_bool=pd.api.types.is_bool_dtype(ser),
            is_float=pd.api.types.is_float_dtype(ser),
            is_string=pd.api.types.is_string_dtype(ser),
            memory_usage=ser.memory_usage())

    @staticmethod
    def computed_summary(summary_dict):
        _type = "obj"
        if summary_dict['is_bool']:
            _type = "boolean"
        elif summary_dict['is_numeric']:
            if summary_dict['is_float']:
                _type = "float"
            else:
                _type = "integer"
        #elif pd.api.types.is_datetime64_any_dtype(ser):
        elif summary_dict['is_datetime']:
            _type = 'datetime'
        elif summary_dict['is_string']:
            _type = "string"
        return dict(_type=_type)

class DefaultSummaryStats(ColAnalysis):
    provides_defaults = {
        'length':0, 'min':0, 'max':0, 'mean':0, 'nan_count':0,
        'value_counts':0, 'mode':0}
    @staticmethod
    def series_summary(sampled_ser, ser):
        l = len(ser)
        value_counts = ser.value_counts()
        nan_count = l - len(ser.dropna())
        is_numeric = pd.api.types.is_numeric_dtype(ser)
        is_bool = pd.api.types.is_bool_dtype(ser)

        base_d = dict(
            length=l,
            nan_count=nan_count,
            value_counts=value_counts,
            mode=get_mode(ser),
            min=np.nan,
            max=np.nan)
        if is_numeric and not is_bool:
            base_d.update({
                'mean': ser.mean(),
                'min': ser.dropna().min(),
                'max': ser.dropna().max()})
        return base_d

class ComputedDefaultSummaryStats(ColAnalysis):


    requires_summary = ['length', 'nan_count',
                        'value_counts']

    provides_defaults = {
        'distinct_per':0, 'empty_per':0, 'unique_per':0, 'nan_per':0,
        'unique_count':0, 'empty_count':0, 'distinct_count':0}


    @staticmethod
    def computed_summary(summary_dict):
        l = summary_dict['length']
        value_counts = summary_dict['value_counts']
        try:
            empty_count = value_counts.get('', 0)
        except:
            empty_count = 0
        distinct_count=len(value_counts)
        unique_count = len(value_counts[value_counts==1])

        return dict(
            unique_count=unique_count,
            empty_count=empty_count,
            distinct_count=distinct_count,
            distinct_per=distinct_count/l,
            empty_per=empty_count/l,
            unique_per=unique_count/l,
            nan_per=summary_dict['nan_count']/l)

