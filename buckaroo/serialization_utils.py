from io import BytesIO
import base64
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
    # Add level_0 for JSON serialization to maintain backwards compatibility
    # This is only needed for JSON, not for Parquet serialization
    if not isinstance(df.index, pd.MultiIndex):
        df2['level_0'] = df2['index']
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
        df2['index'] = df2.index
    return df2

def to_parquet(df):
    data: BytesIO = BytesIO()

    # data.close doesn't work in pyodide, so we make close a no-op
    orig_close = data.close
    data.close = lambda: None
    # I don't like this copy.  modify to keep the same data with different names
    df2 = prepare_df_for_serialization(df)

    # Convert PyArrow-backed string columns to object dtype for fastparquet compatibility
    # pandas 3.0+ uses PyArrow strings by default, which fastparquet can't handle directly
    for col in df2.columns:
        if pd.api.types.is_string_dtype(df2[col].dtype) and not pd.api.types.is_object_dtype(df2[col].dtype):
            df2[col] = df2[col].astype('object')

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


def to_parquet_b64(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a base64-encoded parquet string.

    Note: to_parquet already calls prepare_df_for_serialization internally,
    so the caller should pass a raw DataFrame (not pre-prepared).
    """
    raw_bytes = to_parquet(df)
    return base64.b64encode(raw_bytes).decode('ascii')


def _make_json_safe(val):
    """Recursively convert non-JSON-serializable types (datetime keys, etc.) to strings."""
    if isinstance(val, dict):
        return {str(k): _make_json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_make_json_safe(v) for v in val]
    return val


def _json_encode_cell(val):
    """JSON-encode a single cell value for parquet transport."""
    return json.dumps(_make_json_safe(val), default=str)


def sd_to_parquet_b64(sd: Dict[str, Any]) -> Dict[str, str]:
    """Convert a summary stats dict to a tagged parquet-b64 payload.

    Summary stats DataFrames have mixed-type columns (strings, numbers, lists)
    which fastparquet can't handle directly. We JSON-encode every cell value
    first so each column becomes a pure string column, then use pyarrow for
    parquet serialization. The JS side decodes parquet then JSON.parse's each cell.

    Returns {'format': 'parquet_b64', 'data': '<base64 string>'}
    Falls back to JSON if parquet serialization fails.
    """
    # JSON-encode every value so parquet sees only string columns
    json_sd: Dict[str, Any] = {}
    for col, stats in sd.items():
        if isinstance(stats, dict):
            json_sd[col] = {k: _json_encode_cell(v) for k, v in stats.items()}
        else:
            json_sd[col] = stats

    df = pd.DataFrame(json_sd)
    df2 = prepare_df_for_serialization(df)
    # Add level_0 for backwards compatibility with JSON path (pd_to_obj adds it)
    if not isinstance(df.index, pd.MultiIndex):
        df2['level_0'] = df2['index']

    try:
        data = BytesIO()
        df2.to_parquet(data, engine='pyarrow')
        data.seek(0)
        raw_bytes = data.read()
        b64 = base64.b64encode(raw_bytes).decode('ascii')
        return {'format': 'parquet_b64', 'data': b64}
    except Exception as e:
        logger.warning("Failed to serialize summary stats as parquet, falling back to JSON: %r", e)
        return pd_to_obj(pd.DataFrame(sd))

