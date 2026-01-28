from io import BytesIO
import json
import pandas as pd
from typing import Dict, Any, List, Tuple
from pandas._libs.tslibs import timezones
from pandas.core.dtypes.dtypes import DatetimeTZDtype
from fastparquet import json as fp_json
import logging

from buckaroo.df_util import old_col_new_col, to_chars
logger = logging.getLogger()

#realy pd.Series
def is_ser_dt_safe(ser:Any) -> bool:
    if isinstance(ser.dtype, DatetimeTZDtype):
        dt = ser.dtype
        if timezones.is_utc(dt.tz):
            return True
        elif hasattr(dt.tz, 'zone'):
            return True
        return False
    return True

def is_dataframe_datetime_safe(df:pd.DataFrame) -> bool:
    for col in df.columns:
        if not is_ser_dt_safe(df[col]):
            return False
    if not is_ser_dt_safe(df.index):
        return False
    return True

def fix_df_dates(df:pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if not is_ser_dt_safe(df[col]):
            df[col] = pd.to_datetime(df[col], utc=True)
    if not is_ser_dt_safe(df.index):
        df.index = df.index.tz_convert('UTC')
    return df

class DuplicateColumnsException(Exception):
    pass


def check_and_fix_df(df:pd.DataFrame) -> pd.DataFrame:
    if not df.columns.is_unique:
        print("Your dataframe has duplicate columns. Buckaroo requires distinct column names")
        raise DuplicateColumnsException("Your dataframe has duplicate columns. Buckaroo requires distinct column names")
    if not is_dataframe_datetime_safe(df):
        print("your dataframe has a column or index with a datetime series without atimezone.  Setting a default UTC timezone to proceed with display. https://github.com/paddymul/buckaroo/issues/277")
        return fix_df_dates(df)
    return df



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
        if isinstance(v, UnquotedString):
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



    
def pd_to_obj(df:pd.DataFrame) -> Dict[str, Any]:
    df2 = prepare_df_for_serialization(df)
    try:
        # Use index=False to avoid pandas 3.0 ValueError when column named 'index'
        # overlaps with the DataFrame's index name (which defaults to None/'index')
        obj = json.loads(df2.to_json(orient='table', indent=2, default_handler=str, index=False))
        return obj['data']
    finally:
        pass


class MyJsonImpl(fp_json.BaseImpl):
    def __init__(self):
        pass
        #for some reason the following line causes errors, so I have to reimport ujson_dumps
        # from pandas._libs.json import ujson_dumps
        # self.dumps = ujson_dumps

    def dumps(self, data):
        from pandas._libs.json import ujson_dumps
        return ujson_dumps(data, default_handler=str).encode("utf-8")

    def loads(self, s):
        return self.api.loads(s)

def get_multiindex_to_cols_sers(index) -> List[Tuple[str, Any]]: #pd.Series[Any]
    if not isinstance(index, pd.MultiIndex):
        return []
    objs: List[Tuple[str, Any]] = [] #pd.Series[Any] = []
    for i in range(index.nlevels):
        col_name = "index_" + to_chars(i)
        ser = pd.Series(index.get_level_values(i), index=pd.RangeIndex(len(index)))
        objs.append((col_name, ser))
    return objs


def prepare_df_for_serialization(df:pd.DataFrame) -> pd.DataFrame:
    # I don't like this copy.  modify to keep the same data with different names
    df2 = df.copy()
    attempted_columns = [new_col for _, new_col in old_col_new_col(df)]
    df2.columns = attempted_columns
    if isinstance(df2.index, pd.MultiIndex):
        new_idx = pd.RangeIndex(len(df2))
        for index_col_name, index_series in get_multiindex_to_cols_sers(df2.index):
            df2[index_col_name] = index_series.values
        df2.index = new_idx
    else:
        # Add both 'index' and 'level_0' columns to maintain backwards compatibility
        # 'level_0' matches what pandas' to_json(orient='table') would add for the index
        df2['index'] = df2.index
        df2['level_0'] = df2.index
    return df2

def to_parquet(df):
    data: BytesIO = BytesIO()

    # data.close doesn't work in pyodide, so we make close a no-op
    orig_close = data.close
    data.close = lambda: None
    # I don't like this copy.  modify to keep the same data with different names
    df2 = prepare_df_for_serialization(df)
    obj_columns = df2.select_dtypes([pd.CategoricalDtype(), 'object']).columns.to_list()
    encodings = {k:'json' for k in obj_columns}

    orig_get_cached_codec = fp_json._get_cached_codec
    def fake_get_cached_codec():
        return MyJsonImpl()

    fp_json._get_cached_codec = fake_get_cached_codec
    try:
        df2.to_parquet(data, engine='fastparquet', object_encoding=encodings)
    except Exception as e:
        logger.error("error serializing to parquet %r", e)
        raise
    finally:
        data.close = orig_close
        fp_json._get_cached_codec = orig_get_cached_codec

    data.seek(0)
    return data.read()

