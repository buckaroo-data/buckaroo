"""
THe dastardly dataframe dataset.

The weirdest dataframes that cause trouble frquently

"""

import pandas as pd
import numpy as np

def get_basic_df():
    return pd.DataFrame({'a':[10,20,30]})

#from testing
def get_basic_df2() -> pd.DataFrame:
    return pd.DataFrame({'foo_col': [10, 20, 20], 'bar_col':['foo', 'bar', 'baz']})

def get_basic_df_with_named_index():
    basic_index_with_df = pd.DataFrame({'foo':[10,20, 30]})
    basic_index_with_df.index.name = "named_index"
    return basic_index_with_df

def get_multiindex_cols_df(rows=15) -> pd.DataFrame:
    cols = pd.MultiIndex.from_tuples(
        [('foo', 'a'), ('foo', 'b'),  ('bar', 'a'), ('bar', 'b'), ('bar', 'c')])
    return pd.DataFrame(
        [["asdf","foo_b", "bar_a", "bar_b", "bar_c"]] * rows,
        columns=cols)

def get_multiindex_with_names_cols_df(rows=15) -> pd.DataFrame:
    cols = pd.MultiIndex.from_tuples(
        [('foo', 'a'), ('foo', 'b'),  ('bar', 'a'), ('bar', 'b'), ('bar', 'c')],
        names=['level_a', 'level_b'])
    return pd.DataFrame(
        [["asdf","foo_b", "bar_a", "bar_b", "bar_c"]] * rows,
        columns=cols)

def get_tuple_cols_df(rows=15) -> pd.DataFrame:
    multi_col_df = get_multiindex_cols_df(rows)
    multi_col_df.columns = multi_col_df.columns.to_flat_index()
    return multi_col_df


def get_multiindex_index_df() -> pd.DataFrame:
    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a'), ('foo', 'b'),
        ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
        ('baz', 'a')])
    return pd.DataFrame({
        'foo_col':[10,20,30,40, 50, 60],
        'bar_col':['foo', 'bar', 'baz', 'quux', 'boff', None]},
        index=row_index)

def get_multiindex3_index_df() -> pd.DataFrame:
    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a', 3), ('foo', 'b', 2),
        ('bar', 'a', 1), ('bar', 'b', 3), ('bar', 'c', 5),
        ('baz', 'a', 6)])
    return pd.DataFrame({
        'foo_col':[10,20,30,40, 50, 60],
        'bar_col':['foo', 'bar', 'baz', 'quux', 'boff', None]},
        index=row_index)

def get_multiindex_with_names_index_df() -> pd.DataFrame:
    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a'), ('foo', 'b'),
        ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
        ('baz', 'a')],
        names=['index_name_1', 'index_name_2'])
    return pd.DataFrame({
        'foo_col':[10,20,30,40, 50, 60],
        'bar_col':['foo', 'bar', 'baz', 'quux', 'boff', None]},
        index=row_index)

def get_multiindex_index_multiindex_with_names_cols_df() -> pd.DataFrame:
    cols = pd.MultiIndex.from_tuples(
        [('foo', 'a'), ('foo', 'b'),  ('bar', 'a'), ('bar', 'b'), ('bar', 'c'), ('baz', 'a')],
        names=['level_a', 'level_b'])

    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a'), ('foo', 'b'),
        ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
        ('baz', 'a')])

    return pd.DataFrame([
        [   10,    20,    30,     40,     50,    60],
        ['foo', 'bar', 'baz', 'quux', 'boff',  None],
        [   10,    20,    30,     40,     50,    60],
        ['foo', 'bar', 'baz', 'quux', 'boff',  None],
        [   10,    20,    30,     40,     50,    60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None]],
        columns=cols,
        index=row_index)

def get_multiindex_index_with_names_multiindex_cols_df() -> pd.DataFrame:
    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a'), ('foo', 'b'),
        ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
        ('baz', 'a')],
        names=['index_name_1', 'index_name_2'])
    cols = pd.MultiIndex.from_tuples(
        [('foo', 'a'), ('foo', 'b'),  ('bar', 'a'), ('bar', 'b'), ('bar', 'c'), ('baz', 'a')])

    return pd.DataFrame([
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None]],
        columns=cols,
        index=row_index)

def get_multiindex_with_names_both() -> pd.DataFrame:
    row_index = pd.MultiIndex.from_tuples([
        ('foo', 'a'), ('foo', 'b'),
        ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
        ('baz', 'a')],
        names=['index_name_1', 'index_name_2'])
    cols = pd.MultiIndex.from_tuples(
        [('foo', 'a'), ('foo', 'b'),  ('bar', 'a'), ('bar', 'b'), ('bar', 'c'), ('baz', 'a')],
        names=['level_a', 'level_b'])


    return pd.DataFrame([
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None]],
        columns=cols,
        index=row_index)


def _sales_df() -> pd.DataFrame:
    return pd.DataFrame({
        'region':  ['east', 'east', 'west', 'west', 'east', 'west', 'east', 'west'],
        'year':    [2023, 2024, 2023, 2024, 2023, 2024, 2024, 2023],
        'quarter': [1, 1, 2, 2, 3, 3, 4, 4],
        'revenue': [10.5, 12.0, 8.25, 9.0, 11.0, 7.5, 13.25, 6.0],
        'units':   [100, 120, 80, 90, 110, 75, 130, 60]})

def get_multiindex_int_cols_df() -> pd.DataFrame:
    """pivot_table with a values list: columns ('revenue', 2023), ('revenue', 2024), ...

    The values level is unnamed and the 'year' level holds ints."""
    return _sales_df().pivot_table(index='region', columns='year', values=['revenue', 'units'], aggfunc='sum')

def get_multiindex_int_levels_df() -> pd.DataFrame:
    """unstack onto two int levels: columns (2023, 1), (2023, 3), ... named ['year', 'quarter']

    Year/quarter pairs a region never had come out NaN."""
    return _sales_df().groupby(['region', 'year', 'quarter'])['revenue'].sum().unstack(['year', 'quarter'])

def get_multiindex_int_names_df() -> pd.DataFrame:
    """Pivot of a headerless CSV. Its columns are labelled 0, 1, 2, ..., so the column
    levels are named 1 and 2 and the index is named 0, on top of int level values."""
    headerless = _sales_df()[['region', 'year', 'quarter', 'revenue']]
    headerless.columns = range(4)
    return headerless.pivot_table(index=0, columns=[1, 2], values=3, aggfunc='sum')

def get_multiindex_partly_named_index_df() -> pd.DataFrame:
    """pd.concat of a dict of frames. The dict keys become an unnamed outer index level
    above the named 'region' level. The columns axis is named 'year' and holds ints."""
    by_year = _sales_df().pivot_table(index='region', columns='year', values='revenue', aggfunc='sum')
    return pd.concat({'actual': by_year, 'budget': by_year * 1.1})


def df_with_infinity() -> pd.DataFrame:
    return pd.DataFrame({'a': [np.nan, np.inf, np.inf * -1]})

def df_with_really_big_number() -> pd.DataFrame:
    return pd.DataFrame({"col1": [9999999999999999999, 1]})

def df_with_col_named_index() -> pd.DataFrame:
    return pd.DataFrame({'a':      ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"],
                         'index':  ["7777", "ooooo", "--- -", "33333", "assdf"]})

def get_df_with_named_index() -> pd.DataFrame:
    """
      someone put the effort into naming the index, you'd probably want to display that
    """
    return pd.DataFrame({'a':      ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"]},
        index=pd.Index([10,20,30,40,50], name='foo'))


def df_with_weird_types() -> pd.DataFrame:
    """DataFrame with unusual dtypes that historically broke rendering.

    Exercises: categorical, timedelta, period, interval.
    """
    return pd.DataFrame({
        'categorical': pd.Categorical(['red', 'green', 'blue', 'red', 'green']),
        'timedelta': pd.to_timedelta(['1 days 02:03:04', '0 days 00:00:01',
                                       '365 days', '0 days 00:00:00.001',
                                       '0 days 00:00:00.000100']),
        'period': pd.Series(pd.period_range('2021-01', periods=5, freq='M')),
        'interval': pd.Series(pd.arrays.IntervalArray.from_breaks([0, 1, 2, 3, 4, 5])),
        'int_col': [10, 20, 30, 40, 50],
    })


def pl_df_with_weird_types():
    """Polars DataFrame with unusual dtypes that historically broke rendering.

    Exercises: Duration (issue #622), Time, Categorical, Decimal, Binary.
    Must be displayed with PolarsBuckarooWidget, not the default pandas widget.
    """
    import datetime as dt
    import polars as pl
    return pl.DataFrame({
        'duration': pl.Series([100_000, 3_723_000_000, 86_400_000_000,
                               500, 60_000_000], dtype=pl.Duration('us')),
        'time': [dt.time(14, 30), dt.time(9, 15, 30),
                 dt.time(0, 0, 1), dt.time(23, 59, 59), dt.time(12, 0)],
        'categorical': pl.Series(['red', 'green', 'blue', 'red', 'green']).cast(pl.Categorical),
        'decimal': pl.Series(['100.50', '200.75', '0.01',
                              '99999.99', '3.14']).cast(pl.Decimal(10, 2)),
        'binary': [b'hello', b'world', b'\x00\x01\x02', b'test', b'\xff\xfe'],
        'int_col': [10, 20, 30, 40, 50],
    })


def pl_df_with_weird_types_as_pandas():
    """Polars weird types converted to pandas for use with pandas-based widgets."""
    return pl_df_with_weird_types().to_pandas()


# String cells whose *text* is valid JSON. The JS decoder (parseParquetRow in
# resolveDFData.ts) JSON-parses every string cell, which is correct for the
# pandas/fastparquet path (object cells arrive JSON-encoded) but corrupts the
# native-parquet backends (polars/xorq/lazy), where "null" -> null, "123" ->
# 123, '{"a": 1}' -> object. These frames pin that hazard down for both paths.
_JSON_LIKE_STRINGS = {'norm': ['alpha', 'beta', 'gamma'], 'jnull': ['null', 'value', 'still text'],
    'jbool': ['true', 'false', 'maybe'], 'jint': ['123', '45', '0'], 'jobj': ['{"a": 1}', '{"b": 2}', '{}'],
    'jarr': ['[1, 2]', '[3]', '[]']}


def df_with_json_like_strings() -> pd.DataFrame:
    """Every cell is a string whose text happens to be valid JSON.

    Exercises the cell-encoding seam: a faithful viewer must keep ``"null"``,
    ``"123"`` and ``'{"a": 1}'`` as strings, never coercing them to
    null/number/object. The pandas path JSON-encodes these on the wire, so
    they round-trip; the native-parquet siblings below do not.
    """
    return pd.DataFrame(_JSON_LIKE_STRINGS)


def pl_df_with_json_like_strings():
    """Polars sibling of :func:`df_with_json_like_strings`.

    Polars writes native parquet UTF8 (no JSON encoding), so this is the frame
    that surfaces the ``decodeDFData`` string-coercion bug on the infinite
    path. Must be displayed with PolarsBuckarooWidget.
    """
    import polars as pl
    return pl.DataFrame(_JSON_LIKE_STRINGS)


# Edge values for the summary stats and their per-cell cache, which must give
# every value back with its own type: extremes, specials, empty and all-null
# columns, nested and timezone-aware types.

def df_with_int_extremes() -> pd.DataFrame:
    """Each integer dtype at its limits: int64's min and max, uint64's max (past int64's), int8's range."""
    return pd.DataFrame({
        'int64': pd.Series([-2**63, 2**63 - 1, 0], dtype='int64'),
        'uint64': pd.Series([2**64 - 1, 2**63, 0], dtype='uint64'),
        'int8': pd.Series([-128, 127, 0], dtype='int8')})


def pl_df_with_float_specials():
    """NaN, both infinities, negative zero, the smallest subnormal and the largest float beside a null,
    a column that is all NaN, and float32.

    Polars, because it keeps NaN apart from null: pandas -> arrow turns NaN into null.
    """
    import polars as pl
    return pl.DataFrame({
        'specials': pl.Series([float('nan'), float('inf'), float('-inf'), -0.0, 5e-324,
                               1.7976931348623157e308, None, 1.0], dtype=pl.Float64),
        'all_nan': pl.Series([float('nan')] * 8, dtype=pl.Float64),
        'float32': pl.Series([1.1, 2.2, 3.3, float('nan'), 4.4, 5.5, 6.6, 7.7], dtype=pl.Float32)})


def pl_df_all_null():
    """Typed columns holding no values at all, beside a column of polars' Null type."""
    import polars as pl
    n = 4
    return pl.DataFrame({
        'null': pl.Series([None] * n, dtype=pl.Null),
        'int': pl.Series([None] * n, dtype=pl.Int64),
        'float': pl.Series([None] * n, dtype=pl.Float64),
        'str': pl.Series([None] * n, dtype=pl.String),
        'bool': pl.Series([None] * n, dtype=pl.Boolean),
        'datetime': pl.Series([None] * n, dtype=pl.Datetime('us')),
        'list': pl.Series([None] * n, dtype=pl.List(pl.Int64))})


def pl_df_empty():
    """Columns of several types and zero rows."""
    import polars as pl
    return pl.DataFrame(schema={'int': pl.Int64, 'float': pl.Float64, 'str': pl.String,
        'datetime': pl.Datetime('us')})


def pl_df_with_unicode_strings():
    """Strings that get mangled in transit: emoji, a combining accent, right-to-left and CJK text, an
    embedded NUL, empty and whitespace-only strings, and one 10,000 characters long."""
    import polars as pl
    return pl.DataFrame({
        'unicode': ['😀', 'é', 'שלום', '中文', '', '  ', '\t\n', None],
        'nul': ['a\x00b', '\x00', 'x', 'y', 'z', 'w', 'v', 'u'],
        'long': ['x' * 10_000, 'y', 'z', 'w', 'v', 'u', 't', 's']})


def pl_df_with_temporal_edges():
    """Datetimes with nanoseconds that matter, in a named timezone, and outside pandas' nanosecond
    range (years 1, 3000 and 9999), beside the calendar's first and last dates, negative durations
    and times with nanoseconds."""
    import datetime as dt
    import polars as pl
    far = [dt.datetime(1, 1, 1), dt.datetime(9999, 12, 31, 23, 59, 59), dt.datetime(3000, 1, 1), None]
    return pl.DataFrame({
        'ns': pl.Series([1, 10**18 + 123, -1, None], dtype=pl.Int64).cast(pl.Datetime('ns')),
        'new_york': pl.Series([dt.datetime(2020, 1, 1, 12), dt.datetime(2020, 11, 1, 1, 30),
                               dt.datetime(2020, 7, 1, 12), None]).dt.replace_time_zone('America/New_York', ambiguous='latest'),
        'far': pl.Series(far, dtype=pl.Datetime('us')),
        'far_kolkata': pl.Series(far, dtype=pl.Datetime('us')).dt.replace_time_zone('Asia/Kolkata'),
        'date': [dt.date(1, 1, 1), dt.date(9999, 12, 31), dt.date(2000, 2, 29), None],
        'duration': pl.Series([-1, 0, 10**15, None], dtype=pl.Int64).cast(pl.Duration('us')),
        'time': pl.Series([1, 86_399_999_999_999, 0, None], dtype=pl.Int64).cast(pl.Time)})


def df_with_fixed_offset_timestamps() -> pd.DataFrame:
    """Timestamps in fixed-offset timezones (+05:30, -08:00), which arrow names by offset rather
    than by place."""
    import datetime as dt
    times = pd.Series(pd.to_datetime(['2020-01-01 12:00', '2020-07-01 12:00', '2020-01-02 00:00']))
    return pd.DataFrame({
        'plus_0530': times.dt.tz_localize(dt.timezone(dt.timedelta(hours=5, minutes=30))),
        'minus_0800': times.dt.tz_localize(dt.timezone(dt.timedelta(hours=-8)))})


def df_with_far_future_fixed_offset_timestamps() -> pd.DataFrame:
    """Fixed-offset timestamps past 2262, where pandas' nanosecond range ends. They arrive as
    microsecond pd.Timestamps, and through arrow as datetime.datetime with a pytz.FixedOffset."""
    import datetime as dt
    times = pd.Series([dt.datetime(3000, 1, 1, 12), dt.datetime(9999, 12, 31), dt.datetime(2020, 1, 1)],
        dtype='datetime64[us]')
    return pd.DataFrame({'plus_0530': times.dt.tz_localize(dt.timezone(dt.timedelta(hours=5, minutes=30)))})


def pl_df_with_nested_types():
    """List, fixed-size array and struct columns holding empty lists, nulls inside lists, structs
    whose fields are null, and lists of structs."""
    import polars as pl
    return pl.DataFrame({
        'list_int': pl.Series([[1, 2], [], None, [3, None]], dtype=pl.List(pl.Int64)),
        'list_str': pl.Series([['a'], ['b', 'c'], [], None], dtype=pl.List(pl.String)),
        'array': pl.Series([[1, 2], [3, 4], None, [5, 6]], dtype=pl.Array(pl.Int64, 2)),
        'struct': pl.Series([{'a': 1, 'b': 'x'}, {'a': None, 'b': None}, None, {'a': 2, 'b': 'y'}]),
        'list_of_struct': pl.Series([[{'a': 1}], [], None, [{'a': None}]])})


def df_with_nullable_dtypes() -> pd.DataFrame:
    """pandas' nullable extension dtypes, whose missing cells are pd.NA rather than NaN or None."""
    return pd.DataFrame({
        'Int64': pd.array([1, None, 3], dtype='Int64'),
        'Float64': pd.array([1.5, None, 3.5], dtype='Float64'),
        'boolean': pd.array([True, None, False], dtype='boolean'),
        'string': pd.array(['a', None, 'c'], dtype='string')})


def df_with_arrow_dtypes() -> pd.DataFrame:
    """pandas columns backed by pyarrow types numpy has no equivalent of: a map, time32, date64 and
    a large string."""
    import pyarrow as pa

    def arrow(values, typ):
        return pd.Series(pd.arrays.ArrowExtensionArray(pa.array(values, typ)))
    return pd.DataFrame({
        'map': arrow([[('k', 1)], [], [('j', 2), ('k', 3)]], pa.map_(pa.string(), pa.int64())),
        'time32': arrow([0, 1, 86_399], pa.time32('s')),
        'date64': arrow([0, 86_400_000, 2 * 86_400_000], pa.date64()),
        'large_string': arrow(['a', 'b', 'c'], pa.large_string())})


"""
Mkae a duplicate column dataframe

  the numeric column dataframe

  a dataframe with a column named index

  a dataframe with a named index

  a dataframe with series composed of names different than the column names
  

  """
