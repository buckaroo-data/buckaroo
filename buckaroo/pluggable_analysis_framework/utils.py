import json
import sys
import pandas as pd
import numpy as np


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
