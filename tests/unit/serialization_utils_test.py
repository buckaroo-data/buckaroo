from datetime import date
import pytest
import pandas as pd
from buckaroo.ddd_library import get_multiindex_with_names_index_df, get_multiindex_cols_df, get_multiindex_index_df
from buckaroo.serialization_utils import (
    is_ser_dt_safe, is_dataframe_datetime_safe, check_and_fix_df, pd_to_obj,
    to_arrow_ipc, DuplicateColumnsException)
import pyarrow.ipc as ipc
from io import BytesIO


def _read_ipc_to_polars(ipc_bytes):
    """Read Arrow IPC bytes into a polars DataFrame."""
    import polars as pl
    reader = ipc.open_stream(BytesIO(ipc_bytes))
    table = reader.read_all()
    return pl.from_arrow(table)



dt_strs = ['2024-06-24 09:32:00-04:00', '2024-06-24 09:33:00-04:00', '2024-06-24 09:34:00-04:00']
dt_series = pd.Series(pd.to_datetime(dt_strs).values)
dt_series_with_tz = pd.Series(pd.to_datetime(dt_strs).tz_convert('UTC').values)

dt_index_series = pd.Series(pd.to_datetime(dt_strs))
dt_index_series_with_tz = pd.Series(pd.to_datetime(dt_strs).tz_convert('UTC'))

dt_index = pd.DatetimeIndex(pd.to_datetime(dt_strs))
dt_index_with_tz = pd.DatetimeIndex(pd.to_datetime(dt_strs).tz_convert('UTC'))

def test_is_col_dt_safe():
    # it works for non dt series
    assert is_ser_dt_safe(pd.Series(dt_strs)) is True
    assert is_ser_dt_safe(pd.Index(dt_strs)) is True
    assert is_ser_dt_safe(pd.RangeIndex(0, 3)) is True
    #no tz
    assert is_ser_dt_safe(dt_series) is True
    assert is_ser_dt_safe(dt_index_series) is False
    assert is_ser_dt_safe(dt_index_series_with_tz) is True
    assert is_ser_dt_safe(dt_series_with_tz) is True
    assert is_ser_dt_safe(dt_index) is False
    assert is_ser_dt_safe(dt_index_with_tz) is True

def test_is_dataframe_datetime_safe():
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_strs})) is True
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_series})) is True
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_index_series})) is False
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_index_series_with_tz})) is True
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_series_with_tz})) is True
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_strs}, index=dt_index)) is False
    assert is_dataframe_datetime_safe(pd.DataFrame({'a':dt_strs}, index=dt_index_with_tz)) is True

def recheck(df):
    fixed_df = check_and_fix_df(df)
    fixed_df.to_json(orient='table')
    return is_dataframe_datetime_safe(fixed_df)

def test_check_and_fix_df():
    
    assert recheck(pd.DataFrame({'a':dt_strs})) is True
    assert recheck(pd.DataFrame({'a':dt_series})) is True
    assert recheck(pd.DataFrame({'a':dt_series_with_tz})) is True
    assert recheck(pd.DataFrame({'a':dt_strs}, index=dt_index)) is True
    assert recheck(pd.DataFrame({'a':dt_strs}, index=dt_index_with_tz)) is True

    with pytest.raises(DuplicateColumnsException):
        check_and_fix_df(pd.DataFrame([['a', 'b'], [1,2]], columns = [1,1]))

def test_check_and_fix_df2():
    dt_strs = ['2024-06-24 09:32:00-04:00', '2024-06-24 09:33:00-04:00', '2024-06-24 09:34:00-04:00']
    dt_vals = pd.to_datetime(dt_strs)
    df = pd.DataFrame(
        {'value': [10, 20, 30], 'datetime_vals':dt_vals, 'datetime_vals_tz':dt_vals.tz_convert('UTC')},
        index=dt_vals)
    recheck(df)

def test_check_and_fix_df3():
    dt_strs = ['2024-06-24 09:32:00-04:00', '2024-06-24 09:33:00-04:00', '2024-06-24 09:34:00-04:00']
    dt_vals = pd.to_datetime(dt_strs)
    df = pd.DataFrame(
        {'value': [10, 20, 30],
         'datetime_vals_tz':dt_vals.tz_convert('UTC')},
        index=dt_vals)
    recheck(df)

def test_check_and_fix_df4():
    dt_strs = ['2024-06-24 09:32:00-04:00', '2024-06-24 09:33:00-04:00', '2024-06-24 09:34:00-04:00']
    dt_vals = pd.to_datetime(dt_strs)
    df = pd.DataFrame({'value': [10, 20, 30],},
        index=dt_vals)
    recheck(df)

def test_check_and_fix_df5():
    df = pd.DataFrame({'value': [10, 20, 30], 'strs': ['a', 'b', 'c']})
    recheck(df)

def test_serialize_multiindex_json():
    df = get_multiindex_cols_df()
    pd_to_obj(df)
    assert isinstance(df.columns, pd.MultiIndex)

def test_serialize_multiindex_cols_parquet():
    df = get_multiindex_cols_df()
    output = to_arrow_ipc(df)
    second_df = _read_ipc_to_polars(output)
    assert set(second_df.columns) ==  set(['index','a','b','c','d','e'])

def test_serialize_multiindex_index_simple():
    
    df = get_multiindex_index_df()
    output = to_arrow_ipc(df)
    second_df = _read_ipc_to_polars(output)
    print("Actual columns:", second_df.columns)
    print("DataFrame contents:")
    print(second_df)
    assert set(second_df.columns) ==  set(['index_a', 'index_b', 'a', 'b'])

    assert list(second_df['index_a']) == ['foo', 'foo', 'bar', 'bar', 'bar', 'baz']
    assert list(second_df['index_b']) == ['a', 'b', 'a', 'b', 'c', 'a']
    assert list(second_df['a']) == [10, 20, 30, 40, 50, 60]
    assert list(second_df['b']) == ['foo', 'bar', 'baz', 'quux', 'boff', None]

def test_serialize_multiindex_index():
    df = get_multiindex_with_names_index_df()
    output = to_arrow_ipc(df)
    second_df = _read_ipc_to_polars(output)
    assert set(second_df.columns) ==  set(['index_a', 'index_b', 'a', 'b'])
    
def test_serialize_naive_json():
    d = date(year=1999, month=10, day=3)
    d2 = date(year=1999, month=10, day=3)
    df = pd.DataFrame({'a': [pd.DataFrame, Exception, lambda x: x+10],
                       'b': [d, d2, None]})

    #just make sure we don't throw an error
    output = to_arrow_ipc(df)
    #and make sure output isn't empty. I don't want to hardcode a
    #response here
    assert len(output) > 20
    
# def test_int_overflow_validation():
#     value=float('nan')
#     class Model(BaseModel):
#         a: int
#     Model(a=3)
#     with pytest.raises(ValidationError) as exc_info:
#         Model(a=value)
#     assert exc_info.value.errors(include_url=False) == [
#         {'type': 'finite_number', 'loc': ('a',), 'msg': 'Input should be a finite number',
#          'input': value
#          }]


