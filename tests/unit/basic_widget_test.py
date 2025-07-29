import pytest
import pandas as pd
from IPython.display import display
from buckaroo.buckaroo_widget import BuckarooWidget
from buckaroo.ddd_library import get_multiindex_cols_df
from buckaroo.pluggable_analysis_framework.analysis_management import PERVERSE_DF
from .fixtures import (word_only_df)
from buckaroo.serialization_utils import (DuplicateColumnsException)
from buckaroo.dataflow.styling_core import StylingAnalysis

from buckaroo.customizations.analysis import (TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)
from buckaroo.customizations.histogram import (Histogram)
from buckaroo.customizations.styling import DefaultSummaryStatsStyling, DefaultMainStyling
from buckaroo.jlisp.lisp_utils import (s, sQ)
from buckaroo.customizations.pd_autoclean_conf import (NoCleaningConf)
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.buckaroo_widget import AutocleaningBuckaroo


simple_df = pd.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})
class EverythingStyling(StylingAnalysis):
    """
    This styling shows as much detail as possible
    """
    df_display_name = "Everything"
    requires_summary = [ "_type"]

    #Styling analysis handles column iteration for us.
    @classmethod
    def style_column(kls, col:str, column_metadata):
        print("EverythingStyling style_column", col)
        try:
            t = column_metadata['_type']
            assert t is not None
            disp = {'displayer': 'foo'}        
            return {'col_name':col, 'displayer_args': disp }
        except:
            raise

            
class KitchenSinkWidget(BuckarooWidget):
    #let's be explicit here and show all of the built in analysis klasses
    analysis_klasses = [
    TypingStats, DefaultSummaryStats,
    Histogram, ComputedDefaultSummaryStats,
    # default buckaroo styling
    DefaultSummaryStatsStyling, DefaultMainStyling,
    EverythingStyling
    ]

def test_styling_instantiation():
    
    """styling routines are called before processed_sd has run, that
    can cause errors because EverythingStyling expects keys in
    column_metadata to be present from "requires_summary". There is a
    special case in the code to not warn about this, make sure we
    don't have problems"""
    
    ksw = KitchenSinkWidget(simple_df)
    #TODO: check that nothing was logged, later
    # I'm not quite sure how to verify the clean user experience I want here
    assert ksw is not None


def test_basic_instantiation():
    w = BuckarooWidget(simple_df)
    assert w.df_meta['total_rows'] == 3

def test_perverse_instantiation():
    w = BuckarooWidget(PERVERSE_DF)
    assert w.df_meta['total_rows'] == 10

def test_word_only_instantiation():
    BuckarooWidget(word_only_df)

def test_basic_display():
    df = simple_df
    w = BuckarooWidget(df)
    display(w)

def test_debug_true():
    df = simple_df
    w = BuckarooWidget(df, debug=True)
    display(w)

def test_interpreter():    
    #df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

    w = BuckarooWidget(simple_df)
    # assert w.operation_results['generated_py_code'] == '''def clean(df):
    # df['int_col'] = smart_to_int(df['int_col'])
    # df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    # return df'''
    assert 'str_col' in w.dataflow.cleaned_df.columns
    temp_ops = w.operations.copy()
    temp_ops.append([{"symbol":"dropcol"},{"symbol":"df"},"str_col"])

    w.operations = temp_ops

    tdf = w.dataflow.cleaned_df
    assert 'str_col' not in tdf.columns
    '''
    #assert w.operation_results['transform_error'] is False
    field_names = [ f['col_name'] for f in tdf['dfviewer_config']['column_config'] ]
    assert 'str_col' not in field_names
    assert w.operation_results['generated_py_code'] == """def clean(df):
    df['int_col'] = smart_to_int(df['int_col'])
    df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    df.drop('str_col', axis=1, inplace=True)
    return df"""
    '''

def test_string_column_handling():
    """
    If the front end is passed numeric column names, nothing works, and no error is thrown
    """
    
    df = pd.DataFrame([["foo","bar","baz"]], columns=[10,20,30])
    bw = BuckarooWidget(df)
    #we want the  column have col_name 'a' and the header_name to be 10
    bw.df_display_args['main']['df_viewer_config']['column_config'][0]
    ten_col = bw.df_display_args['main']['df_viewer_config']['column_config'][0]
    assert ten_col['col_name'] == 'a'  # this is the field that ag-grid will read from
    assert ten_col['header_name'] == '10'  # this should be a string
    
    assert bw.df_data_dict['main'] == [{'index': 0, 'a': 'foo', 'b': 'bar', 'c': 'baz', 'level_0':0}]
    assert ten_col['tooltip_config'] == {'tooltip_type': 'simple', 'val_column': 'a'}



def test_non_unique_column_names():
    #you end up with columns named [0,1,2, 0,1,2]
    #refactor to instantiating the dataframe without concat

    with pytest.raises(DuplicateColumnsException):
        BuckarooWidget(pd.DataFrame([['a', 'b'], [1,2]], columns = [1,1]))


def test_init_sd():
    """
    I have run into a bug where init_sd causes an error in DefaultMainStyling, it shouldn't blow up
    """
    BuckarooWidget(simple_df, init_sd={'int_col': {'foo':8}})



def test_buckaroo_options_populate():
    """
    test that buckaroo_options are populated properly given AC Confs
    """

    df = pd.DataFrame({'a': ["30", "40"], 'b': ['aa', 'bb']})
    class AC2(AutocleaningConfig):
        name="AC2"
    class ACBuckaroo(BuckarooWidget):
        autoclean_conf = tuple([AC2, NoCleaningConf])
    
    bw = ACBuckaroo(df)
    assert bw.buckaroo_options["cleaning_method"] == ["AC2", ""]


def test_quick_commands_run():
    """
    test that quick_commands work with autocleaning disabled
    """

    df = pd.DataFrame({'a': ["30", "40"], 'b': ['aa', 'bb']})
    bw = BuckarooWidget(df)
    bw.buckaroo_state = {'cleaning_method': '',
                         'post_processing': '',
                         'sampled': False,
                         'show_commands': False,
                         'df_display': 'main',
                         'search_string': '',
                         'quick_command_args': {'search': ['aa']}}

    expected = pd.DataFrame({
        'a': ["30"],
        'b': ['aa']})
    assert bw.dataflow.quick_command_args == {'search': ['aa']}
    assert bw.dataflow.merged_operations == [[sQ('search'), s('df'), "col", "aa"]]
    assert bw.dataflow.processed_df.to_dict() == expected.to_dict()
    assert bw.dataflow.processed_df.to_dict() == expected.to_dict()


    # FIXME
    # I need unmerging logic to make this work
    # dataflow.merged_operations is the combination of quick_args (and possibly cleaning_ops) + operations that are executed.  Resetting bw.operations after this is merged would result in a loop
    # the ops from cleaning and quick_args are tagged so that they can be treated differently, changing cleaning or quick_args shouldn't affect manually editted operations
    #assert bw.operations == [[sQ('search'), s('df'), "col", "aa"]]


def test_multi_index_cols() -> None:
    df = get_multiindex_cols_df()
    bw = BuckarooWidget(df)
    col_config = bw.df_display_args['main']['df_viewer_config']['column_config']

    assert col_config[0]['col_path'] == ('foo', 'a')
    assert col_config[1]['col_path'] == ('foo', 'b')
    
def atest_symbol_meta():    
    """verifies that a symbol with a meta key can be added and
    properly interpretted.  This should probably be a lower level
    parser test

    """

    df = pd.read_csv('./docs/examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    assert w.operation_results['generated_py_code'] == '# instantiation, unused'
    w.operations = [[{"symbol":"dropcol", "meta":{}},{"symbol":"df"},"starttime"]]

    tdf = w.operation_results['transformed_df']
    assert w.operation_results['transform_error'] is False
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'starttime' not in field_names


def xtest_interpreter_errors():
    w = BuckarooWidget(simple_df)
    w.operations = [
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"],
        #dropping the same column will result in an error
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"]]
    assert w.operation_results['transform_error'] == '''"['int_col'] not found in axis"'''


def xtest_displayed_after_interpreter_filter():
    """verify that the displayed number updates when an operation changes the size of cleaned_df  """
    pass


def test_auto_clean_preserve_error():
    dirty_df = pd.DataFrame(
        {
        "a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
        "b": ["3", "4", "a", "5", "5", "b9", None, " 9", "9-", 11, "867-5309", "-9", None, ],
        "us_dates": ["", "07/10/1982", "07/15/1982", "7/10/1982", "17/10/1982", "03/04/1982",
            "03/02/2002", "12/09/1968", "03/04/1982", "", "06/22/2024","07/4/1776", "07/20/1969",
        ],
        "mostly_bool": [
            True, "True", "Yes", "On", "false", False, "1", "Off","0",
            " 0", "No",1, None,]})

    bw = AutocleaningBuckaroo(dirty_df)
    bw.buckaroo_state = {
        "cleaning_method": "aggressive", #aggressive, that's the change that throws the error
        "post_processing": "",
        "sampled": False,
        "show_commands": "1",
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}}
    assert len(bw.operations) == 3
    bw.operations = [
        [{ "symbol": "us_date",
        "meta": { "clean_strategy": "AggresiveCleaningGenOps",
                  "clean_col": "us_dates", "auto_clean": True }},
      {"symbol": "df" }, "us_dates" ],
  [{"symbol": "str_bool", "meta": { "clean_strategy": "AggresiveCleaningGenOps",
                                    "clean_col": "mostly_bool",
                                    "auto_clean": True}},
    {"symbol": "df"},"mostly_bool"],
  [{"symbol": "strip_int_parse",
      "meta": {
        "clean_strategy": "AggresiveCleaningGenOps",
        "clean_col": "b"
      }
    },
    { "symbol": "df" }, "b" ]]
    
    bw.buckaroo_state = {
        "cleaning_method": "conservative", #aggressive, that's the change that throws the error
        "post_processing": "",
        "sampled": False,
        "show_commands": "1",
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}}
    
def test_get_story_config():
    df = get_multiindex_cols_df()
    bw = BuckarooWidget(df)
    bw.get_story_config(test_name="basic_widget_test")
    #fix this when there is more debugging done
    #assert bw.get_story_config(test_name="basic_widget_test") == ""
