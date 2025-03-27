import warnings

import pandas as pd
import numpy as np


from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis


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
        from packaging.version import Version
    except Exception:
        #this package isn't available in jupyterlite
        
        # but in jupyterlite envs, we have a recent version of pandas
        # without this problem
        mode_raw = ser.mode()
        if len(mode_raw) == 0:
            return np.nan
        return mode_raw.values[0]
        
    try:
        mode_raw = ser.mode()
        if len(mode_raw) == 0:
            return np.nan
        else:
            if Version(pd.__version__) < Version("2.0.7"):
                # add check to verify  that mode isn't np.datetime64, change it to a pd.timestamp.
                # this leads to segfaults for pandas < 2.07 on serialization
                retval = mode_raw.values[0]
                if isinstance(retval, np.datetime64):
                    return pd.Timestamp(retval)
                return retval
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
            is_datetime=pd.api.types.is_datetime64_any_dtype(ser),
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
        'length':0, 'min':0, 'max':0, 'mean':0, 'null_count':0,
        'value_counts':0, 'mode':0, "std":0, "median":0}
    @staticmethod
    def series_summary(sampled_ser, ser):
        l = len(ser)
        value_counts = ser.value_counts()
        is_numeric = pd.api.types.is_numeric_dtype(ser)
        is_bool = pd.api.types.is_bool_dtype(ser)

        base_d = dict(
            length=l,
            null_count=ser.isna().sum(),
            value_counts=value_counts,
            mode=get_mode(ser),
            min=np.nan,
            max=np.nan)
        if is_numeric and not is_bool:
            base_d.update({
                'std': ser.std(),
                'mean': ser.mean(),
                'median': ser.median(),
                'min': ser.dropna().min(),
                'max': ser.dropna().max()})
        return base_d

class ComputedDefaultSummaryStats(ColAnalysis):


    requires_summary = ['length', 'value_counts', 'null_count']

    provides_defaults = {
        'non_null_count':0,
        'most_freq':0, '2nd_freq':0, '3rd_freq':0, '4th_freq':0, '5th_freq':0,
        
        'distinct_per':0, 'empty_per':0, 'unique_per':0, 'nan_per':0,
        'unique_count':0, 'empty_count':0, 'distinct_count':0,
    }


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

        try:
            empty_count = value_counts.get('', 0)
        except:
            empty_count = 0
        distinct_count=len(value_counts)
        unique_count = len(value_counts[value_counts==1])

        def vc_nth(pos):
            if pos >= len(value_counts):
                return None
            else:
                return value_counts.index[pos]

        return {
            'non_null_count':l - summary_dict['null_count'],
            'null_count': summary_dict['null_count'],
            'most_freq':vc_nth(0),
            '2nd_freq':vc_nth(1),
            '3rd_freq':vc_nth(2),
            '4th_freq':vc_nth(3),
            '5th_freq':vc_nth(4),
            'unique_count':unique_count,
            'empty_count':empty_count,
            'distinct_count':distinct_count,
            'distinct_per':distinct_count/l,
            'empty_per':empty_count/l,
            'unique_per':unique_count/l,
            'nan_per':summary_dict['null_count']/l
        }

class PdCleaningStats(ColAnalysis):
    provides_defaults = {'int_parse_fail': 0.0, 'int_parse':0.0}
    requires_summary = ['value_counts', 'length']


    @staticmethod
    def computed_summary(summary_dict):
        vc = summary_dict['value_counts']
        coerced_ser = pd.to_numeric(vc.index.values, errors='coerce', downcast='integer', dtype_backend='pyarrow')
        #return 0 for all floats
        nan_sum = (pd.Series(coerced_ser).isna() * 1 * vc.values).sum()
        l = summary_dict['length']
        return dict(
            int_parse_fail = nan_sum / l,
            int_parse = ((l - nan_sum )/l))


# class PLCleaningStats(PolarsAnalysis):
#     requires_summary = ['value_counts', 'length']
#     provides_defaults = {'int_parse_fail': 0.0, 'int_parse':0.0}
    
#     @staticmethod
#     def computed_summary(column_metadata):
#         vc_ser, len_ = column_metadata['value_counts'], column_metadata['length']
#         vc_df = pl.DataFrame({'vc': vc_ser.explode()}).unnest('vc')
#         regular_col_vc_df = vc_df.select(pl.all().exclude('count').alias('key'), pl.col('count'))
#         pd.to_numeric(vc_b.index, errors='coerce')
#         int_parse = pl.col('key').cast(pl.Int64, strict=False).is_null()
#         per_df = regular_col_vc_df.select(
#             int_parse.replace({True:1, False:0}).mul(pl.col('count')).sum().alias('int_parse_fail'),
#             int_parse.replace({True:0, False:1}).mul(pl.col('count')).sum().alias('int_parse')) / len_
#         return per_df.to_dicts()[0]
