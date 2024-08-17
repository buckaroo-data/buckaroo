import pandas as pd
import numpy as np
import sys
import traceback
from buckaroo.serialization_utils import pick


class UnquotedString(str):
    pass

def val_replace(dct, replacements):
    ret_dict = {}
    for k, v in dct.items():
        if isinstance(v, pd.Series):
            ret_dict[k] = UnquotedString('pd.Series()')
        #hack, but trying to get away from conditional imports
        elif repr(v.__class__) == "<class 'polars.series.series.Series'>":
            ret_dict[k] = UnquotedString('pl.Series()')
        elif v in replacements:
            ret_dict[k] = replacements[v]
        else:
            ret_dict[k] = v
    return ret_dict


def dict_repr(dct):
    ret_str = "{"
    for k, v in dct.items():
        ret_str += "'%s': " % k
        if isinstance(v, UnquotedString):
            ret_str += "%s, " % v
        else:
            ret_str += "%r, " % v
    ret_str += "}"    
    return ret_str


def pd_py_serialize(dct):
    """
    This is used to output an exact string that is valid python code.
    """
    cleaned_dct = val_replace(dct,
                       {pd.NA: UnquotedString("pd.NA"),
                        np.nan: UnquotedString("np.nan")})
    return dict_repr(cleaned_dct)

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

def safe_summary_df(base_summary_df, index_list):
    #there are instances where not all indexes of the summary_df will
    #be available, because there was no valid data to produce those
    #indexes. This fixes them and explicitly. Empty rows will have NaN
    return pd.DataFrame(base_summary_df, index_list)

def reproduce_summary(ser_name_qualifier, kls, summary_df, err, operating_df_name):
    #print("ser_name_qualifier", ser_name_qualifier)
    #ser_name, method_name = ser_name_qualifier.split(':')
    ser_name, method_name = ser_name_qualifier
    ssdf = safe_summary_df(summary_df, kls.requires_summary)
    summary_ser = ssdf[ser_name]
    minimal_summary_dict = pick(summary_ser, kls.requires_summary)
    sum_ser_repr = "pd.Series(%s)" % pd_py_serialize(minimal_summary_dict)

    f = "{kls}.summary({df_name}['{ser_name}'], {summary_ser_repr}, {df_name}['{ser_name}']) # {err_msg}"
    print(f.format(
        kls=kls.cname(), df_name=operating_df_name, ser_name=ser_name,
        summary_ser_repr=sum_ser_repr, err_msg=err))

def output_reproduce_preamble():
    print("#Reproduction code")
    print("#" + "-" * 80)
    print("from buckaroo.pluggable_analysis_framework.analysis_management import PERVERSE_DF")

def output_full_reproduce(errs, summary_df, df_name):
    if len(errs) == 0:
        raise Exception("output_full_reproduce called with 0 len errs")

    try:
        for ser_name, err_kls in errs.items():
            err, kls = err_kls
            reproduce_summary(ser_name, kls, summary_df, err, df_name)
    except Exception:
        #this is tricky stuff that shouldn't error, I want these stack traces to escape being caught
        traceback.print_exc()
