from functools import lru_cache
import json
import sys
import pandas as pd
import numpy as np
from pandas.util import hash_pandas_object

BASE_COL_HINT = {
    'type':'string',
    'is_numeric': False,
    'is_integer': None,
    'min_digits':None,
    'max_digits':None,
    'formatter':None,
    'histogram': []}

FAST_SUMMARY_WHEN_GREATER = 1_000_000

PERVERSE_DF = pd.DataFrame({
    'all_nan': [np.nan] * 10,
    'all_false': [False] * 10,
    'all_True': [True] * 10,
    'mixed_bool': np.concatenate([[True]*5, [False]*5]),
    'mixed_float': np.concatenate([[0.5, np.nan, None], [6]*7]),
    'float': [0.5]*10,
    'int': [8] *10,
    'negative': [-1]*10,
    'UInt32': pd.Series([5]*10, dtype='UInt32'),
    'UInt8None':pd.Series([None] * 10, dtype='UInt8')
    })


class NonExistentSummaryRowException(Exception):
    pass

def get_df_name(df, level=0):
    """ looks up the call stack until it finds the variable with this name"""
    if level == 0:
        _globals = globals()
    elif level < 60:
        try:
            call_frame = sys._getframe(level)
            _globals = call_frame.f_globals
        except ValueError:
            return None #we went to far up the stacktrace to a non-existent frame
    else:
        return None

    name_possibs = [x for x in _globals.keys() if _globals[x] is df]
    if name_possibs:
        return name_possibs[0]
    else:
        #+2 because the function is recursive, and we need to skip over this frame
        return get_df_name(df, level + 2)


def safe_isnan(v):
    try:
        return np.isnan(v)
    except Exception:
        return False

def replace_in_dict(input_dict, replace_tuples):
    ret_dict = {}
    for k,v in input_dict.items():
        if isinstance(v, dict):
            ret_dict[k] = replace_in_dict(v, replace_tuples)
        elif safe_isnan(v):
            ret_dict[k] = None
        else:
            for old, new in replace_tuples:
                if v is old:
                    ret_dict[k] = new
                    break
                elif v == old:
                    ret_dict[k] = new
                    break
            ret_dict[k] = v
    return ret_dict


def json_postfix(postfix):
    return lambda nm: json.dumps([nm, postfix])
    

def filter_analysis(klasses, attr):
    ret_klses = {}
    for k in klasses:
        attr_val = getattr(k, attr, None)
        if attr_val is not None:
            ret_klses[attr_val] = k
    return ret_klses

def hash_series(ser):
    return int(hash_pandas_object(ser).sum())

class SeriesWrapper:
    def __init__(self, series):
        self.series = series
        if not getattr(series, '_hash', False):
            #saving the _hash as an attribute of the series means we don't have to run this hash and sum frequently.  I do worry about 
            series._hash = hash_series(series)
        self._hash = series._hash

    def __eq__(self, other):
        return isinstance(other, SeriesWrapper) and self._hash == other._hash

    def __hash__(self):
        return self._hash
def cache_series_func(f, max_size=256):
    _cache = {}

    def unwrapped_hashable_func(ser):
        #we need to take the series out of the wrapper call the original function
        ret_val = f(ser.series)
        ser.series = None # we don't need to keep a reference to the series around
        # this behaviour should be explicitly checked by
        # tests/unit/pluggable_analysis_framework_test.py::TestCacheSeriesFunc::test_memoize_gc 

        
        return ret_val
    cached_func= lru_cache(max_size)(unwrapped_hashable_func)

    def ret_func(ser):
        if isinstance(ser, SeriesWrapper):
            return cached_func(ser)
        elif isinstance(ser, pd.Series):
            cser = SeriesWrapper(ser)
            return cached_func(cser)
        else:
            raise Exception(f"Unknown type of {type(ser)}")
    return ret_func
