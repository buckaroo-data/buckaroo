import json
import numpy as np
import pandas as pd
from pandas.io.json import dumps as pdumps

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


EMPTY_DF_OBJ = {'schema': {'fields': [{'name': 'index', 'type': 'string'}],
  'primaryKey': ['index'],
  'pandas_version': '1.4.0'},
 'data': []}


def dumb_table_sumarize(df):
    """used when table_hints aren't provided.  Trests every column as a string"""
    table_hints = {col:{'is_numeric':False, type:'obj'}  for col in df}
    table_hints['index'] = {'is_numeric': False} 
    return table_hints


def df_to_obj(df, order = None, table_hints=None):
    if order is None:
        order = df.columns

    temp_index_name = False
    if not df.index.name is None:
        temp_index_name = df.index.name
        df.index.name = None
    obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))
    if temp_index_name:
        df.index.name = temp_index_name
    
    if table_hints is None:
        obj['table_hints'] = json.loads(pdumps(dumb_table_sumarize(df)))
    else:
        obj['table_hints'] = json.loads(pdumps(table_hints))
    fields=[{'name':'index'}]
    for c in order:
        fields.append({'name':c})
    obj['schema'] = dict(fields=fields)
    return obj
