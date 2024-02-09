import json
import pandas as pd
from typing import Union, Any


EMPTY_DF_WHOLE = {
    'pinned_rows':[],
    'column_config': [],
    'data': []
}

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

#def generate_column_config(df:pd.DataFrame, summary_dict) -> List[ColumnConfig]:
def generate_column_config(df:pd.DataFrame, summary_dict):
    ret_conf = []
    index_name = df.index.name or "index"
    ret_conf.append({'col_name':index_name, 'displayer_args' : { 'displayer':'obj'}})
    for col in df.columns:
        ret_conf.append({'col_name': col, 'displayer_args' : { 'displayer':'obj'} })
    return ret_conf
        

#def df_to_obj(unknown_df:Union[pd.DataFrame, Any], summary_dict:Any) -> DFWhole:
def df_to_obj(unknown_df:Union[pd.DataFrame, Any], summary_dict:Any):
    df = force_to_pandas(unknown_df)
    data = pd_to_obj(df)
    #dfviewer_config:DFViewerConfig = {
    dfviewer_config = {
        'pinned_rows'   : [],
        'column_config' : generate_column_config(df, summary_dict)
    }
    return {'data':data, 'dfviewer_config': dfviewer_config}


def pd_to_obj(df:pd.DataFrame):
    obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))

    if isinstance(df.index, pd.MultiIndex):
        old_index = df.index
        temp_index = pd.Index(df.index.to_list(), tupleize_cols=False)
        df.index = temp_index
        obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))
        df.index = old_index
    else:
        obj = json.loads(df.to_json(orient='table', indent=2, default_handler=str))
    return obj['data']



