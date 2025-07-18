import pandas as pd

from buckaroo.jlisp.lisp_utils import s
from .command_test import assert_to_py_same_transform_df

from buckaroo.customizations.pandas_cleaning_commands import (
    StrBool)


same = assert_to_py_same_transform_df
dirty_df = pd.DataFrame(
    {
        "untouched_a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
        "mostly_ints": [
            "3",
            "4",
            "a",
            "5",
            "5",
            "b9",
            None,
            " 9",
            "9-",
            11,
            "867-5309",
            "-9",
            None,
        ],
        "us_dates": [
            "",
            "07/10/1982",
            "07/15/1982",
            "7/10/1982",
            "17/10/1982",
            "03/04/1982",
            "03/02/2002",
            "12/09/1968",
            "03/04/1982",
            "",
            "06/22/2024",
            "07/4/1776",
            "07/20/1969",
        ],
        "mostly_bool": [
            True,
            "True",
            "Yes",
            "On",
            "false",
            False,
            "1",
            "Off",
            "0",
            " 0",
            "No",
            1,
            None,
        ],
    }
)

expected_df = pd.DataFrame({
    'untouched_a': dirty_df['untouched_a'],
    'mostly_ints': pd.Series(
[
  3,
  4,
  None,
  5,
  5,
  9,
  None,
  9,
  9,
  11,
  8675309,
  -9,
  None,
]
, dtype='Int64'),
    'mostly_ints_orig': dirty_df['mostly_ints'],
    'us_dates' : pd.Series([
        "NaT",
        "1982-07-10 00:00:00",
        "1982-07-15 00:00:00",
        "1982-07-10 00:00:00",
        "NaT",
        "1982-03-04 00:00:00",
        "2002-03-02 00:00:00",
        "1968-12-09 00:00:00",
        "1982-03-04 00:00:00",
        "NaT",
        "2024-06-22 00:00:00",
        "1776-07-04 00:00:00",
        "1969-07-20 00:00:00"
    ], dtype='datetime64[ns]'),
    'us_dates_orig': dirty_df['us_dates'],
    'mostly_bool': pd.Series([
        True,
        True, 
        True, 
        True,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
        True,
        None
    ], dtype='boolean'),
    'mostly_bool_orig':dirty_df['mostly_bool']
})

def test_str_bool():
    base_df = pd.DataFrame({'mostly_bool': dirty_df['mostly_bool']})
    
    output_df = same(StrBool, [[s('str_bool'), s('df'), "mostly_bool"]], base_df)
    assert isinstance(output_df['mostly_bool'].dtype , pd.core.arrays.boolean.BooleanDtype)
    assert output_df['mostly_bool'].to_list() == expected_df['mostly_bool'].to_list()



def test_full_autoclean():
    from buckaroo.buckaroo_widget import AutocleaningBuckaroo
    abw = AutocleaningBuckaroo(dirty_df)
    abw.buckaroo_state = {
        "cleaning_method": "aggressive",
        "post_processing": "",
        "sampled": False,
        "show_commands": False,
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}
    }

    result =  abw.dataflow.processed_df

    assert result.columns.to_list() == expected_df.columns.to_list()
    pd.testing.assert_frame_equal( abw.dataflow.processed_df, expected_df)
    
# def test_to_float():
#     base_df = pd.DataFrame({
#         'mixed_floats':['3', '4', '7.1', 'asdf', np.nan], 'b': [pd.NA] * 5})
    
#     output_df = same(to_float, [[s('to_float'), s('df'), "mixed_floats"]], base_df)
#     pd.testing.assert_series_equal(
#         output_df['mixed_floats'],
#         pd.Series([3, 4, 7.1, np.nan, np.nan], dtype='float64', name='mixed_floats'))

# def _test_to_string():
#     """
#     skipping for now.  works on my machine against pandas 2.1.1 fails in CI against pandas 1.3.5
#     """
#     base_df = pd.DataFrame({
#         'mixed_strings':['a', 'b', pd.NA], 'b': [pd.NA] * 3})
    
#     output_df = same(to_string, [[s('to_string'), s('df'), "mixed_strings"]], base_df)
#     pd.testing.assert_series_equal(
#         output_df['mixed_strings'],
#         pd.Series(['a', 'b', pd.NA], dtype='string', name='mixed_strings'))

