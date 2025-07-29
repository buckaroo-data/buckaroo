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
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
        ['foo', 'bar', 'baz', 'quux', 'boff', None],
        [10,20,30,40, 50, 60],
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

def df_with_col_named_index() -> pd.DataFrame:
    return pd.DataFrame({'a':      ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"],
                         'index':  ["7777", "ooooo", "--- -", "33333", "assdf"]})

def get_df_with_named_index() -> pd.DataFrame:
    """
      someone put the effort into naming the index, you'd probably want to display that
    """
    return pd.DataFrame({'a':      ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"]},
                        index=pd.Index([10,20,30,40,50], name='foo'))


"""
Mkae a duplicate column dataframe

  the numeric column dataframe

  a dataframe with a column named index

  a dataframe with a named index

  a dataframe with series composed of names different than the column names
  

  """
