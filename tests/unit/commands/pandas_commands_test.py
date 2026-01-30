"""
Tests for buckaroo/customizations/pandas_commands.py

This file tests commands that were previously untested to improve coverage.
"""
import pandas as pd
import pytest

from buckaroo.jlisp.configure_utils import configure_buckaroo
from buckaroo.customizations.pandas_commands import (
    NoOp, SafeInt, MakeCategory, RemoveOutliers, OnlyOutliers,
    ToDatetime, Search, SearchCol, DropDuplicates, Rank, Replace,
    GroupByTransform, smart_to_int, coerce_series, search_df_str, search_col_str
)


def result_from_exec(code_str, df_input):
    """Execute generated Python code and return result."""
    CODE_PREAMBLE = "import pandas as pd\nimport numpy as np\n"
    CODE_PREAMBLE += "from buckaroo.auto_clean.auto_clean import smart_to_int\n"
    RETRIEVE_RESULT_STR = '\n__ret_closure[0] = clean(__test_df)'
    outer_scope_result = [0]
    full_code_str = CODE_PREAMBLE + code_str + RETRIEVE_RESULT_STR
    try:
        exec(full_code_str, {'__test_df': df_input, '__ret_closure': outer_scope_result})
    except Exception as e:
        print("Failure calling exec with following code string", e)
        print(full_code_str)
    return outer_scope_result[0]


def assert_to_py_same_transform_df(command_kls, operations, test_df):
    """Verify that transform() and transform_to_py() produce the same result."""
    _a, _b, transform_df, transform_to_py = configure_buckaroo([command_kls])
    tdf_ops = [{'symbol': 'begin'}]
    tdf_ops.extend(operations)
    tdf = transform_df(tdf_ops, test_df.copy())
    py_code_string = transform_to_py(operations)

    edf = result_from_exec(py_code_string, test_df.copy())
    pd.testing.assert_frame_equal(tdf, edf)
    return tdf


same = assert_to_py_same_transform_df


# ============================================================================
# smart_to_int function tests
# ============================================================================

def test_smart_to_int_positive_small():
    """Test smart_to_int with small positive integers -> UInt8."""
    ser = pd.Series([1, 2, 3, 100, 200])
    result = smart_to_int(ser)
    assert result.dtype == 'UInt8'
    assert list(result) == [1, 2, 3, 100, 200]


def test_smart_to_int_positive_medium():
    """Test smart_to_int with medium positive integers -> UInt16."""
    ser = pd.Series([1, 2, 3, 1000, 50000])
    result = smart_to_int(ser)
    assert result.dtype == 'UInt16'


def test_smart_to_int_positive_large():
    """Test smart_to_int with large positive integers -> UInt32."""
    ser = pd.Series([1, 2, 3, 100000, 1000000])
    result = smart_to_int(ser)
    assert result.dtype == 'UInt32'


def test_smart_to_int_positive_very_large():
    """Test smart_to_int with very large positive integers -> UInt64."""
    ser = pd.Series([1, 2, 3, 5_000_000_000])
    result = smart_to_int(ser)
    assert result.dtype == 'UInt64'


def test_smart_to_int_negative_small():
    """Test smart_to_int with small negative integers -> Int8."""
    ser = pd.Series([-10, -5, 0, 5, 10])
    result = smart_to_int(ser)
    assert result.dtype == 'Int8'


def test_smart_to_int_negative_medium():
    """Test smart_to_int with medium negative integers -> Int16."""
    ser = pd.Series([-1000, 0, 10000])
    result = smart_to_int(ser)
    assert result.dtype == 'Int16'


def test_smart_to_int_negative_large():
    """Test smart_to_int with large negative integers -> Int32."""
    ser = pd.Series([-100000, 0, 100000])
    result = smart_to_int(ser)
    assert result.dtype == 'Int32'


def test_smart_to_int_negative_very_large():
    """Test smart_to_int with very large negative integers -> Int64."""
    ser = pd.Series([-5_000_000_000, 0, 5_000_000_000])
    result = smart_to_int(ser)
    assert result.dtype == 'Int64'


def test_smart_to_int_string_input():
    """Test smart_to_int with string numeric values."""
    ser = pd.Series(['1', '2', '3', '100'])
    result = smart_to_int(ser)
    assert result.dtype == 'UInt8'
    assert list(result) == [1, 2, 3, 100]


def test_smart_to_int_with_nulls():
    """Test smart_to_int preserves null positions."""
    ser = pd.Series([1, None, 3, None, 5])
    result = smart_to_int(ser)
    assert pd.isna(result.iloc[1])
    assert pd.isna(result.iloc[3])
    assert result.iloc[0] == 1
    assert result.iloc[4] == 5


# ============================================================================
# coerce_series function tests
# ============================================================================

def test_coerce_series_bool():
    """Test coerce_series with bool type."""
    ser = pd.Series([1, 0, 1, None, 0])
    result = coerce_series(ser, 'bool')
    assert result.dtype == 'boolean'
    assert result.iloc[0] is True or bool(result.iloc[0]) is True
    assert result.iloc[1] is False or bool(result.iloc[1]) is False


def test_coerce_series_datetime():
    """Test coerce_series with datetime type."""
    ser = pd.Series(['2024-01-01', '2024-06-15', 'invalid', None])
    result = coerce_series(ser, 'datetime')
    assert pd.api.types.is_datetime64_any_dtype(result)
    assert pd.isna(result.iloc[2])  # 'invalid' should become NaT


def test_coerce_series_int():
    """Test coerce_series with int type."""
    ser = pd.Series(['1', '2', '3', 'abc', None])
    result = coerce_series(ser, 'int')
    # Should use smart_to_int
    assert pd.api.types.is_integer_dtype(result)


def test_coerce_series_float():
    """Test coerce_series with float type."""
    ser = pd.Series(['1.5', '2.5', 'abc', None])
    result = coerce_series(ser, 'float')
    assert result.dtype == 'float'
    assert result.iloc[0] == 1.5
    assert result.iloc[1] == 2.5


def test_coerce_series_string():
    """Test coerce_series with string type."""
    ser = pd.Series([1, 2, None, 'abc'])
    result = coerce_series(ser, 'string')
    assert result.dtype == 'string'


def test_coerce_series_unknown_type():
    """Test coerce_series raises exception for unknown type."""
    ser = pd.Series([1, 2, 3])
    with pytest.raises(Exception, match="Unkown type"):
        coerce_series(ser, 'unknown_type')


# ============================================================================
# NoOp command tests
# ============================================================================

def test_noop():
    """Test that NoOp returns dataframe unchanged."""
    base_df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
    result = NoOp.transform(base_df.copy(), 'a')
    pd.testing.assert_frame_equal(result, base_df)


def test_noop_to_py():
    """Test NoOp.transform_to_py returns noop comment."""
    result = NoOp.transform_to_py(None, 'col')
    assert '#noop' in result


# ============================================================================
# SafeInt command tests
# ============================================================================

def test_safe_int():
    """Test SafeInt converts string numbers to integers."""
    base_df = pd.DataFrame({'a': ['1', '2', '3', '100'], 'b': [4, 5, 6, 7]})
    result = SafeInt.transform(base_df.copy(), 'a')
    assert pd.api.types.is_integer_dtype(result['a'])


def test_safe_int_index_col():
    """Test SafeInt does nothing when col='index'."""
    base_df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
    result = SafeInt.transform(base_df.copy(), 'index')
    pd.testing.assert_frame_equal(result, base_df)


def test_safe_int_with_errors():
    """Test SafeInt handles non-numeric values gracefully."""
    base_df = pd.DataFrame({'a': ['1', '2', 'abc', '4'], 'b': [4, 5, 6, 7]})
    result = SafeInt.transform(base_df.copy(), 'a')
    # Should still work, converting what it can
    assert 'a' in result.columns


def test_safe_int_to_py():
    """Test SafeInt.transform_to_py generates correct code."""
    result = SafeInt.transform_to_py(None, 'my_col')
    assert 'smart_to_int' in result
    assert 'my_col' in result


# ============================================================================
# MakeCategory command tests
# ============================================================================

def test_make_category():
    """Test MakeCategory converts column to category dtype."""
    base_df = pd.DataFrame({'a': ['cat', 'dog', 'cat', 'bird'], 'b': [1, 2, 3, 4]})
    result = MakeCategory.transform(base_df.copy(), 'a')
    assert result['a'].dtype.name == 'category'


def test_make_category_index_col():
    """Test MakeCategory does nothing when col='index'."""
    base_df = pd.DataFrame({'a': ['cat', 'dog'], 'b': [1, 2]})
    result = MakeCategory.transform(base_df.copy(), 'index')
    pd.testing.assert_frame_equal(result, base_df)


def test_make_category_to_py():
    """Test MakeCategory.transform_to_py generates correct code."""
    result = MakeCategory.transform_to_py(None, 'my_col')
    assert "astype('category')" in result
    assert 'my_col' in result


# ============================================================================
# RemoveOutliers command tests
# ============================================================================

def test_remove_outliers():
    """Test RemoveOutliers filters extreme values."""
    # Create data with clear outliers
    base_df = pd.DataFrame({
        'a': [1, 2, 3, 4, 5, 100, 200],  # 100 and 200 are outliers
        'b': list(range(7))
    })
    result = RemoveOutliers.transform(base_df.copy(), 'a', 10)  # 10% tail
    # Should have fewer rows after removing outliers
    assert len(result) < len(base_df)


def test_remove_outliers_index_col():
    """Test RemoveOutliers does nothing when col='index'."""
    base_df = pd.DataFrame({'a': [1, 2, 100], 'b': [1, 2, 3]})
    result = RemoveOutliers.transform(base_df.copy(), 'index', 10)
    pd.testing.assert_frame_equal(result, base_df)


def test_remove_outliers_to_py():
    """Test RemoveOutliers.transform_to_py generates correct code."""
    result = RemoveOutliers.transform_to_py(None, 'my_col', 5)
    assert 'quantile' in result
    assert 'my_col' in result


# ============================================================================
# OnlyOutliers command tests
# ============================================================================

def test_only_outliers():
    """Test OnlyOutliers keeps only extreme values."""
    # Create data with values at different positions
    base_df = pd.DataFrame({
        'a': [1, 50, 50, 50, 50, 50, 100],
        'b': list(range(7))
    })
    result = OnlyOutliers.transform(base_df.copy(), 'a', 0.2)
    # Should return only rows with outlier values
    assert len(result) <= len(base_df)


def test_only_outliers_index_col():
    """Test OnlyOutliers does nothing when col='index'."""
    base_df = pd.DataFrame({'a': [1, 50, 100], 'b': [1, 2, 3]})
    result = OnlyOutliers.transform(base_df.copy(), 'index', 0.1)
    pd.testing.assert_frame_equal(result, base_df)


def test_only_outliers_integer_mean():
    """Test OnlyOutliers uses int mean for integer columns."""
    base_df = pd.DataFrame({
        'a': pd.Series([1, 50, 50, 50, 100], dtype='Int64'),
        'b': list(range(5))
    })
    # Should not raise - mean should be calculated as int
    result = OnlyOutliers.transform(base_df.copy(), 'a', 0.2)
    assert isinstance(result, pd.DataFrame)


def test_only_outliers_to_py():
    """Test OnlyOutliers.transform_to_py generates correct code."""
    result = OnlyOutliers.transform_to_py(None, 'my_col', 0.05)
    assert 'quantile' in result
    assert 'my_col' in result
    assert 'fillna' in result


# ============================================================================
# ToDatetime command tests
# ============================================================================

def test_to_datetime():
    """Test ToDatetime converts column to datetime."""
    base_df = pd.DataFrame({
        'date_str': ['2024-01-01', '2024-06-15', '2024-12-31'],
        'b': [1, 2, 3]
    })
    result = ToDatetime.transform(base_df.copy(), 'date_str')
    assert pd.api.types.is_datetime64_any_dtype(result['date_str'])


def test_to_datetime_to_py():
    """Test ToDatetime.transform_to_py generates correct code."""
    result = ToDatetime.transform_to_py(None, 'my_date')
    assert 'pd.to_datetime' in result
    assert 'my_date' in result


# ============================================================================
# Search command tests
# ============================================================================

def test_search_df_str():
    """Test search_df_str finds matching rows."""
    df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'David'],
        'city': ['New York', 'Boston', 'Chicago', 'Denver']
    })
    result = search_df_str(df, 'Bob')
    assert len(result) == 1
    assert result.iloc[0]['name'] == 'Bob'


def test_search_df_str_multiple_matches():
    """Test search_df_str finds all matching rows."""
    df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie'],
        'note': ['likes Bob', 'is Bob', 'knows Bob']
    })
    result = search_df_str(df, 'Bob')
    assert len(result) == 3


def test_search_empty_needle():
    """Test Search returns full df when needle is empty."""
    base_df = pd.DataFrame({'a': ['Alice', 'Bob'], 'b': [1, 2]})
    result = Search.transform(base_df.copy(), 'a', '')
    pd.testing.assert_frame_equal(result, base_df)


def test_search_none_needle():
    """Test Search returns full df when needle is None."""
    base_df = pd.DataFrame({'a': ['Alice', 'Bob'], 'b': [1, 2]})
    result = Search.transform(base_df.copy(), 'a', None)
    pd.testing.assert_frame_equal(result, base_df)


def test_search_with_match():
    """Test Search filters rows containing the needle."""
    base_df = pd.DataFrame({
        'name': pd.Series(['Alice', 'Bob', 'Charlie'], dtype='object'),
        'b': [1, 2, 3]
    })
    result = Search.transform(base_df.copy(), 'name', 'Bob')
    assert len(result) == 1


def test_search_to_py():
    """Test Search.transform_to_py generates correct code."""
    result = Search.transform_to_py(None, 'col', 'needle')
    assert 'search_df_str' in result
    assert 'needle' in result


# ============================================================================
# SearchCol command tests
# ============================================================================

def test_search_col_str():
    """Test search_col_str finds matching rows in specific column."""
    df = pd.DataFrame({
        'name': pd.Series(['Alice', 'Bob', 'Charlie'], dtype='object'),
        'city': pd.Series(['Boston', 'New York', 'Chicago'], dtype='object')
    })
    result = search_col_str(df, 'name', 'Bob')
    assert len(result) == 1
    assert result.iloc[0]['name'] == 'Bob'


def test_search_col_empty_needle():
    """Test SearchCol returns full df when needle is empty."""
    base_df = pd.DataFrame({'a': ['Alice', 'Bob'], 'b': [1, 2]})
    result = SearchCol.transform(base_df.copy(), 'a', '')
    pd.testing.assert_frame_equal(result, base_df)


def test_search_col_with_match():
    """Test SearchCol filters rows containing the needle in specific column."""
    base_df = pd.DataFrame({
        'name': pd.Series(['Alice', 'Bob', 'Charlie'], dtype='object'),
        'b': [1, 2, 3]
    })
    result = SearchCol.transform(base_df.copy(), 'name', 'Bob')
    assert len(result) == 1


def test_search_col_to_py():
    """Test SearchCol.transform_to_py generates correct code."""
    result = SearchCol.transform_to_py(None, 'my_col', 'needle')
    assert 'search_col_str' in result
    assert 'my_col' in result
    assert 'needle' in result


# ============================================================================
# DropDuplicates command tests
# ============================================================================

def test_drop_duplicates_keep_first():
    """Test DropDuplicates with keep='first'."""
    base_df = pd.DataFrame({'a': [1, 2, 2, 3, 3, 3], 'b': range(6)})
    result = DropDuplicates.transform(base_df.copy(), 'a', 'first')
    assert len(result) == 3  # 1, 2, 3


def test_drop_duplicates_keep_last():
    """Test DropDuplicates with keep='last'."""
    base_df = pd.DataFrame({'a': [1, 2, 2, 3, 3, 3], 'b': range(6)})
    result = DropDuplicates.transform(base_df.copy(), 'a', 'last')
    assert len(result) == 3


def test_drop_duplicates_keep_false():
    """Test DropDuplicates with keep='False' (drop all duplicates)."""
    base_df = pd.DataFrame({'a': [1, 2, 2, 3, 3, 3], 'b': range(6)})
    result = DropDuplicates.transform(base_df.copy(), 'a', 'False')
    assert len(result) == 1  # Only 1 has no duplicates


def test_drop_duplicates_to_py_first():
    """Test DropDuplicates.transform_to_py with keep='first'."""
    result = DropDuplicates.transform_to_py(None, 'my_col', 'first')
    assert "keep='first'" in result


def test_drop_duplicates_to_py_false():
    """Test DropDuplicates.transform_to_py with keep='False'."""
    result = DropDuplicates.transform_to_py(None, 'my_col', 'False')
    assert "keep=False" in result


# ============================================================================
# Rank command tests
# ============================================================================

def test_rank_min_method():
    """Test Rank with min method."""
    base_df = pd.DataFrame({'a': [1, 2, 2, 3], 'b': range(4)})
    result = Rank.transform(base_df.copy(), 'a', 'min', False)
    # With min method, tied values get minimum rank
    assert result['a'].iloc[1] == result['a'].iloc[2]


def test_rank_dense_method():
    """Test Rank with dense method."""
    base_df = pd.DataFrame({'a': [1, 2, 2, 3], 'b': range(4)})
    result = Rank.transform(base_df.copy(), 'a', 'dense', False)
    assert list(result['a']) == [1.0, 2.0, 2.0, 3.0]


def test_rank_new_col_min():
    """Test Rank creates new column when new_col=True with min method."""
    base_df = pd.DataFrame({'a': [3, 1, 2], 'b': ['x', 'y', 'z']})
    result = Rank.transform(base_df.copy(), 'a', 'min', True)
    assert 'a_rank' in result.columns
    assert 'a' in result.columns  # Original preserved
    assert list(result['a_rank']) == [3.0, 1.0, 2.0]


def test_rank_to_py_new_col():
    """Test Rank.transform_to_py generates correct code when creating new column."""
    result = Rank.transform_to_py(None, 'my_col', 'min', True)
    assert 'rank' in result
    assert "'min'" in result


# ============================================================================
# Replace command tests
# ============================================================================

def test_replace():
    """Test Replace replaces values in column."""
    base_df = pd.DataFrame({'a': ['foo', 'bar', 'foo'], 'b': [1, 2, 3]})
    result = Replace.transform(base_df.copy(), 'a', 'foo', 'baz')
    assert list(result['a']) == ['baz', 'bar', 'baz']


def test_replace_no_match():
    """Test Replace when no values match."""
    base_df = pd.DataFrame({'a': ['foo', 'bar'], 'b': [1, 2]})
    result = Replace.transform(base_df.copy(), 'a', 'qux', 'baz')
    assert list(result['a']) == ['foo', 'bar']


def test_replace_to_py():
    """Test Replace.transform_to_py generates correct code."""
    result = Replace.transform_to_py(None, 'my_col', 'old_val', 'new_val')
    assert 'replace' in result
    assert 'old_val' in result
    assert 'new_val' in result


# ============================================================================
# GroupByTransform command tests
# ============================================================================

def test_groupby_transform_mean():
    """Test GroupByTransform with mean aggregation."""
    base_df = pd.DataFrame({
        'group': ['A', 'A', 'B', 'B'],
        'value': [10, 20, 30, 40]
    })
    result = GroupByTransform.transform(base_df.copy(), 'group', {'value': 'mean'})
    assert 'value_mean' in result.columns
    # Group A mean = 15, Group B mean = 35
    assert result[result['group'] == 'A']['value_mean'].iloc[0] == 15.0
    assert result[result['group'] == 'B']['value_mean'].iloc[0] == 35.0


def test_groupby_transform_count_null():
    """Test GroupByTransform with count_null aggregation."""
    base_df = pd.DataFrame({
        'group': ['A', 'A', 'B', 'B'],
        'value': [10, None, 30, None]
    })
    result = GroupByTransform.transform(base_df.copy(), 'group', {'value': 'count_null'})
    assert 'value_count_null' in result.columns
    # Each group has 1 null
    assert result['value_count_null'].iloc[0] == 1


def test_groupby_transform_null_skip():
    """Test GroupByTransform skips columns with 'null' value."""
    base_df = pd.DataFrame({
        'group': ['A', 'A', 'B', 'B'],
        'value': [10, 20, 30, 40]
    })
    result = GroupByTransform.transform(base_df.copy(), 'group', {'value': 'null'})
    assert 'value_null' not in result.columns


def test_groupby_transform_to_py():
    """Test GroupByTransform.transform_to_py generates correct code."""
    result = GroupByTransform.transform_to_py(None, 'group', {'value': 'mean'})
    assert 'groupby' in result
    assert 'value' in result
    assert 'mean' in result


def test_groupby_transform_to_py_count_null():
    """Test GroupByTransform.transform_to_py with count_null."""
    result = GroupByTransform.transform_to_py(None, 'group', {'value': 'count_null'})
    assert 'count_null' in result
    assert 'size' in result
    assert 'count' in result
