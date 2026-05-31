import pandas as pd
import numpy as np
import traceback


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

def output_full_reproduce(errs, summary_df, df_name):
    if len(errs) == 0:
        raise Exception("output_full_reproduce called with 0 len errs")

    try:
        for err_key, (err, _kls) in errs.items():
            col, stat = err_key if isinstance(err_key, tuple) else (err_key, '?')
            print(f"# {col}:{stat} — {err}")
    except Exception:
        #this is tricky stuff that shouldn't error, I want these stack traces to escape being caught
        traceback.print_exc()
