import numpy as np
import pandas as pd

def d_update(d1, d2):
    ret_dict = d1.copy()
    ret_dict.update(d2)
    return ret_dict

def pick(dct, keys):
    new_dict = {}
    for k in keys:
        new_dict[k] = dct[k]
    return new_dict


def val_replace(dct, replacements):
    ret_dict = {}
    for k, v in dct.items():
        if v in replacements:
            ret_dict[k] = replacements[v]
        else:
            ret_dict[k] = v
    return ret_dict

class UnquotedString(str):
    pass

def dict_repr(dct):
    ret_str = "{"
    for k, v in dct.items():
        ret_str += "'%s': " % k
        if type(v) == UnquotedString:
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

