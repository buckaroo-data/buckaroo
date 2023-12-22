import json
import pandas as pd
from pandas.io.json import dumps as pdumps
from typing import Union

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
        if isinstance(v, pd.Series):
            ret_dict[k] = UnquotedString('pd.Series()')
        elif v in replacements:
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



EMPTY_DF_OBJ = {'schema': {'fields': [{'name': 'index', 'type': 'string'}],
  'primaryKey': ['index'],
  'pandas_version': '1.4.0'},
  'data': []}


def dumb_table_sumarize(df):
    """used when table_hints aren't provided.  Trests every column as a string"""
    table_hints = {col:{'is_numeric':False, 'type':'obj', 'histogram':[]}  for col in df}
    table_hints['index'] = {'is_numeric': False, 'type':'obj', 'histogram':[] } 
    return table_hints


#def force_to_pandas(df_pd_or_pl:Union[pd.DataFrame, pl.DataFrame]) -> pd.DataFrame:
def force_to_pandas(df_pd_or_pl) -> pd.DataFrame:
    if isinstance(df_pd_or_pl, pd.DataFrame):
        return df_pd_or_pl

    
    import polars as pl
    #hack for now so everything else flows through

    if isinstance(df_pd_or_pl, pl.DataFrame):
        return df_pd_or_pl.to_pandas()
    else:
        raise Exception("unexpected type for dataframe, got %r" % (type(df_pd_or_pl)))


#def df_to_obj(unknown_df:Union[pd.DataFrame, pl.DataFrame], order = None, table_hints=None):
def df_to_obj(unknown_df:Union[pd.DataFrame], order = None, table_hints=None):
    df = force_to_pandas(unknown_df)
    return pd_to_obj(df, order=order, table_hints=table_hints)

def pd_to_obj(df:pd.DataFrame , order = None, table_hints=None):
    if order is None:
        order = df.columns
    obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))

    if isinstance(df.index,  pd.MultiIndex):
        old_index = df.index
        temp_index = pd.Index(df.index.to_list(), tupleize_cols=False)
        df.index = temp_index
        obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))
        df.index = old_index
    else:
        obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))

    if table_hints is None:
        obj['table_hints'] = json.loads(pdumps(dumb_table_sumarize(df)))
    else:
        obj['table_hints'] = json.loads(pdumps(table_hints))

    index_name = df.index.name or "index"
    fields=[{'name': index_name, 'type':'unused' }]
    for c in order:
        fields.append({'name':str(c), 'type':'unused'})
    obj['schema'] = dict(fields=fields, primaryKey=[index_name], pandas_version='1.4.0')
    return obj



