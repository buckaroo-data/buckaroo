from io import BytesIO
import base64
import json
import pandas as pd
from typing import Dict, Any, List, Tuple
from pandas._libs.tslibs import timezones
from pandas.core.dtypes.dtypes import DatetimeTZDtype
try:
    from fastparquet import json as fp_json
    HAS_FASTPARQUET = True
except ImportError:
    fp_json = None
    HAS_FASTPARQUET = False
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
    'data': []}

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



    
def _coerce_for_json(df: pd.DataFrame) -> pd.DataFrame:
    """Convert columns with types that pd.to_json can't handle."""
    for col in df.columns:
        dtype = df[col].dtype
        if isinstance(dtype, (pd.PeriodDtype, pd.IntervalDtype)):
            df[col] = df[col].astype(str)
        elif pd.api.types.is_timedelta64_dtype(dtype):
            df[col] = df[col].astype(str)
        elif dtype == object:  # noqa: E721 — np.dtype('O') != builtin object via `is`
            # Check if any values are raw bytes (e.g. from pl.Binary)
            sample = df[col].dropna().head(1)
            if len(sample) > 0 and isinstance(sample.iloc[0], bytes):
                df[col] = df[col].apply(lambda x: x.hex() if isinstance(x, bytes) else x)
    return df


def pd_to_obj(df:pd.DataFrame) -> Dict[str, Any]:
    df2 = prepare_df_for_serialization(df)
    df2 = _coerce_for_json(df2)
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


if HAS_FASTPARQUET:
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
    if not HAS_FASTPARQUET:
        raise ImportError(
            "fastparquet is required for parquet serialization but is not installed. "
            "Install it with: pip install fastparquet")

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

    # Convert dtypes that fastparquet can't handle to string/object
    for col in df2.columns:
        dtype = df2[col].dtype
        if isinstance(dtype, (pd.PeriodDtype, pd.IntervalDtype)):
            df2[col] = df2[col].astype(str)
        elif pd.api.types.is_timedelta64_dtype(dtype):
            df2[col] = df2[col].astype(str)
        elif dtype == object:  # noqa: E721 — np.dtype('O') != builtin object via `is`
            sample = df2[col].dropna().head(1)
            if len(sample) > 0 and isinstance(sample.iloc[0], bytes):
                df2[col] = df2[col].apply(lambda x: x.hex() if isinstance(x, bytes) else x)

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


def resolve_summary_stats_payload(payload: Any) -> List[Dict[str, Any]]:
    """Decode a summary stats payload back to row-form ``DFData``.

    Mirror of the JS ``resolveDFDataAsync`` for summary stats: returns the
    list of ``{'index': stat_name, <col>: value, ...}`` rows that the grid
    consumes. Handles all three on-wire shapes:

    * Plain list (already resolved) — returned as-is.
    * Tagged parquet-b64 with ``layout='wide'`` — pivoted from wide format.
    * Tagged parquet-b64 with row layout (legacy fallback) — decoded and
      cell-by-cell JSON-parsed like the original ``parseParquetRow``.

    Useful for Python-side test assertions that want to inspect exactly
    what the JS side will render.
    """
    import pyarrow.parquet as pq

    if isinstance(payload, list):
        return payload
    if not (isinstance(payload, dict) and payload.get('format') == 'parquet_b64'):
        return payload  # unknown shape — caller decides

    raw = base64.b64decode(payload['data'])
    table = pq.read_table(BytesIO(raw))
    rows = table.to_pylist()

    if payload.get('layout') == 'wide':
        if not rows:
            return []
        return _pivot_wide_sd_row(rows[0])

    # Row layout: every non-index cell is a JSON string.
    parsed = []
    for row in rows:
        out = {}
        for k, v in row.items():
            if k in ('index', 'level_0'):
                out[k] = v
            elif isinstance(v, str):
                try:
                    out[k] = json.loads(v)
                except (json.JSONDecodeError, ValueError):
                    out[k] = v
            else:
                out[k] = v
        parsed.append(out)
    return parsed


def _pivot_wide_sd_row(wide_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pivot a single wide-layout SD row into row-form ``DFData``.

    Inverse of ``sd_to_parquet_b64``'s encoding step. Native parquet scalars
    pass through; JSON-encoded strings (the only string form the encoder
    emits) are parsed back to their original Python value.
    """
    stat_cols: Dict[str, Dict[str, Any]] = {}
    all_cols: List[str] = []
    seen = set()

    for key, raw_val in wide_row.items():
        sep = key.find('__')
        if sep == -1:
            continue
        col = key[:sep]
        stat = key[sep + 2:]
        if col not in seen:
            seen.add(col)
            all_cols.append(col)
        stat_cols.setdefault(stat, {})

        if isinstance(raw_val, str):
            try:
                val = json.loads(raw_val)
            except (json.JSONDecodeError, ValueError):
                val = raw_val
        else:
            val = raw_val
        stat_cols[stat][col] = val

    rows = []
    for stat, cols in stat_cols.items():
        row_out: Dict[str, Any] = {'index': stat, 'level_0': stat}
        for col in all_cols:
            row_out[col] = cols.get(col)
        rows.append(row_out)
    return rows


def _stat_value_to_pa_array(val):
    """Encode a single SD stat value as a one-element typed pyarrow array.

    Scalars (int / float / bool) ride native parquet types — no JSON round-trip.
    Strings, lists, dicts go through JSON so the JS side can unambiguously
    JSON.parse every string cell back to its original type.

    NaN floats become parquet nulls; None becomes a null string cell.
    """
    import numpy as np
    import pyarrow as pa

    # bool BEFORE int — np.bool_ and Python bool both pass isinstance(_, int).
    if isinstance(val, (bool, np.bool_)):
        return pa.array([bool(val)], type=pa.bool_())
    if isinstance(val, (int, np.integer)):
        iv = int(val)
        # uint64 stats (e.g. a column max on an unsigned dtype) routinely exceed
        # int64 max. Promote to uint64, then to a JSON-encoded string for
        # bignums that don't fit either — pyarrow would otherwise raise here,
        # before sd_to_parquet_b64 reaches its JSON fallback.
        if -(2**63) <= iv <= 2**63 - 1:
            return pa.array([iv], type=pa.int64())
        if 0 <= iv <= 2**64 - 1:
            return pa.array([iv], type=pa.uint64())
        return pa.array([_json_encode_cell(iv)], type=pa.string())
    if isinstance(val, (float, np.floating)):
        v = float(val)
        # NaN sentinel -> parquet null so the JS side sees null, not "NaN".
        return pa.array([None if v != v else v], type=pa.float64())
    if val is None:
        return pa.array([None], type=pa.string())
    # str / list / dict / anything else: JSON-encoded string.
    return pa.array([_json_encode_cell(val)], type=pa.string())


def sd_to_parquet_b64(sd: Dict[str, Any]) -> Dict[str, str]:
    """Convert a summary stats dict to a tagged parquet-b64 payload.

    Wide-column layout: one parquet column per ``{short_col}__{stat_name}``
    pair (e.g. ``a__mean``, ``a__histogram``), with a single row. Scalars
    (numbers, bools) ride native parquet types — the JSON round-trip that
    used to apply to every cell now only applies to strings and to
    list/dict values (histograms, value_counts).

    Returns ``{'format': 'parquet_b64', 'layout': 'wide', 'data': '<base64>'}``.
    Falls back to the JSON/row payload if parquet serialization fails — the
    absence of ``layout: 'wide'`` is how the JS side picks the row decoder.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    col_mapping = [(orig, to_chars(i)) for i, orig in enumerate(sd.keys())]
    names: List[str] = []
    arrays: List[Any] = []

    for orig_col, short_col in col_mapping:
        stats = sd[orig_col]
        if not isinstance(stats, dict):
            continue
        for stat_name, val in stats.items():
            names.append(f"{short_col}__{stat_name}")
            arrays.append(_stat_value_to_pa_array(val))

    try:
        table = pa.table(dict(zip(names, arrays)))
        buf = BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('ascii')
        return {'format': 'parquet_b64', 'layout': 'wide', 'data': b64}
    except Exception as e:
        logger.warning("Failed to serialize summary stats as parquet, falling back to JSON: %r", e)
        return pd_to_obj(pd.DataFrame(sd))

