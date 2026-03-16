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
        names=['index_name_1', 'index_name_2']
    )
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
        names=['index_name_1', 'index_name_2']
    )
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
        names=['index_name_1', 'index_name_2']
    )
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


"""
Mkae a duplicate column dataframe

  the numeric column dataframe

  a dataframe with a column named index

  a dataframe with a named index

  a dataframe with series composed of names different than the column names
  

  """
