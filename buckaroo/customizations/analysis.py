import warnings

import pandas as pd
import numpy as np



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


def _has_unhashable_values(ser):
    """True if ser is object dtype and its first non-null value is unhashable.

    Used to skip value_counts/mode on list/dict/set columns where pandas
    falls back to an O(n^2) pairwise compare and the result is meaningless
    anyway (each row is effectively a unique container). #843
    """
    if ser.dtype != object:
        return False
    for v in ser:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except (TypeError, ValueError):
            pass
        try:
            hash(v)
        except TypeError:
            return True
        return False
    return False


def get_mode(ser):
    try:
        from packaging.version import Version
    except Exception:
        #this package isn't available in jupyterlite
        
        # but in jupyterlite envs, we have a recent version of pandas
        # without this problem
        if not pd.api.types.is_numeric_dtype(ser):
            return np.nan
        mode_raw = ser.mode()
        if len(mode_raw) == 0:
            return np.nan
        return mode_raw.values[0]

    try:
        if not pd.api.types.is_numeric_dtype(ser):
            return np.nan
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

