import traceback
import pandas as pd
import numpy as np
from buckaroo import BuckarooWidget
from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)
from buckaroo.pluggable_analysis_framework.col_analysis import (ColAnalysis)
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.dataflow.autocleaning import PandasAutocleaning, generate_quick_ops
from buckaroo.jlisp.lisp_utils import (s, sA, sQ)
from buckaroo.customizations.pandas_commands import (
    Command,
    SafeInt, DropCol, FillNA, GroupBy, NoOp, Search, OnlyOutliers
)
from buckaroo.customizations.pd_autoclean_conf import (NoCleaningConf)
from buckaroo.dataflow.pandas_dataflow import PandasCustomizableDataflow

dirty_df = pd.DataFrame(
    {'a':[10,  20,  30,   40,  10, 20.3,   5, None, None, None],
     'b':["3", "4", "a", "5", "5",  "b", "b", None, None, None]})



def make_default_analysis(**kwargs):
    class DefaultAnalysis(ColAnalysis):
        requires_summary = []
        provides_defaults = kwargs
    return DefaultAnalysis

class CleaningGenOps(ColAnalysis):
    requires_summary = ['int_parse_fail', 'int_parse']
    provides_defaults = {'cleaning_ops': []}

    int_parse_threshhold = .3
    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['int_parse'] > kls.int_parse_threshhold:
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}],
                    'add_orig': True}
        else:
            return {'cleaning_ops': []}




class ACConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name="default"


def test_handle_user_ops():
    """
      autocleaning should only replace the autocleaning ops,  but the existing user ops should stay.
      
      """

    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': [10, 20, 30]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    _cleaned_df, _cleaning_sd, _generated_code, merged_operations = cleaning_result
    assert merged_operations == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    existing_ops = [
        [{'symbol': 'old_safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]
    cleaning_result2 = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=existing_ops)
    _cleaned_df, _cleaning_sd, _generated_code, merged_operations2 = cleaning_result2
    assert merged_operations2 == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    user_ops = [
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]
    cleaning_result3 = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=user_ops)
    _cleaned_df, _cleaning_sd, _generated_code, merged_operations3 = cleaning_result3
    assert merged_operations3 == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a'],
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']
    ]


def test_make_origs_different_dtype():
    raw = pd.DataFrame({'a': [30, "40"]})
    cleaned = pd.DataFrame({'a': [30,  40]})
    expected = pd.DataFrame(
        {
            'a': [30, 40],
            'a_orig': [30,  "40"]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {'a':{'add_orig': True, 'orig_col_name': 'a'}})
    assert combined.to_dict() == expected.to_dict()

def test_make_origs_preserve():
    """
    I keep seeing nan's pop up.  We should be using the better Pandas nullable types
    """
    raw = pd.DataFrame({'a': [30, "40", "not_used"]})
    cleaned = pd.DataFrame({'a': pd.Series([30, 40, None], dtype='Int64')})
    expected = pd.DataFrame(
        {
            'a': pd.Series([30, 40, None], dtype='Int64'),
            'a_orig': [30,  "40", "not_used"]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {'a':{'add_orig': True, 'preserve_orig_index':True, 'orig_col_name':'a'}})
    assert combined.to_dict() == expected.to_dict()

def test_make_origs_non_alphabetpreserve():
    """
    I keep seeing nan's pop up.  We should be using the better Pandas nullable types
    """
    raw = pd.DataFrame({'a_modified': [30, "40", "not_used"]})
    cleaned = pd.DataFrame({'a_modified': pd.Series([30, 40, None], dtype='Int64')})
    expected = pd.DataFrame(
        {
            'a_modified': pd.Series([30, 40, None], dtype='Int64'),
            'a_modified_orig': [30,  "40", "not_used"]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {'a_modified':{'add_orig': True, 'preserve_orig_index':True, 'orig_col_name':'a_modified'}})
    assert combined.to_dict() == expected.to_dict()

def Xtest_make_origs_filtered_new():
    """
    When the operations remove rows.  those should be removed fromm origs too.  Filter ops are generally explicit
    """
    raw = pd.DataFrame({'a': [30, "40", "not_used"]})
    cleaned = pd.DataFrame({'a': [30, 40]})
    expected = pd.DataFrame(
        {
            'a': [30, 40],
            'a_orig': [30,  "40"]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {'a':{'add_orig': True, 'preserve_orig_index':True}})
    assert combined.to_dict() == expected.to_dict()

def test_make_origs_disable():
    """
    Verify that make_origs doesn't run by default
    """
    raw = pd.DataFrame({'a': [30, "40", "not_used"]})
    cleaned = pd.DataFrame({'a': [30, 40]})
    expected = pd.DataFrame({'a': [30, 40]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {})
    assert combined.to_dict() == expected.to_dict()

def test_handle_clean_df():
    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    expected = pd.DataFrame({
        'a': [30, 40],
        'a_orig': ["30",  "40"]})
    assert cleaned_df.to_dict() == expected.to_dict()

class ThrowError(Command):
    command_default = [s('throw_error'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        1/0
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = df['%s'].apply(pd.to_numeric, errors='coerce')" % (col, col)


def error_func():
    3/0
    
class ThrowNestedError(Command):
    command_default = [s('throw_nested_error'), s('df'), "col"]
    command_pattern = []

    @staticmethod 
    def transform(df, col):
        """ This is  used for testing traceback filtering """
        error_func()
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df['%s'] = df['%s'].apply(pd.to_numeric, errors='coerce')" % (col, col)

class ACErrorConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search, ThrowError, ThrowNestedError]
    quick_command_klasses = [Search]
    name=""

def test_run_df_interpreter():
    """ this is testing a semi private method

    I want to test error handling, so we can tag it on operations that cause errors
    """
    ac = PandasAutocleaning([ACErrorConf])
    df = pd.DataFrame({'a': ["30", "40"]})

    output_df = ac._run_df_interpreter(
        df,
        [
            [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']])
    expected = pd.DataFrame({'a': [30, 40]})
    assert output_df.to_dict() == expected.to_dict()


def find_error_op(df, operations, interpreter_func):

    L = len(operations)
    low, high  = 0, L-1
    first_run = True

    res = None
    i = high

    formatted_exception = None
    while first_run or (high-low) > 1:
        test_ops = operations[:(i+1)]
        try:
            res = interpreter_func(df, test_ops)
            if first_run:
                return [res, -1, None]
            low = i
        except Exception as e:

            high = i
            formatted_exception = traceback.format_exception(e)

        first_run = False
        i = low + (high - low)//2

    if high == 1:
        try:
            res = interpreter_func(df, [operations[0]])
            return [res, 1, None]
        except Exception as e:
            formatted_exception = traceback.format_exception(e)
            return [df, 0, formatted_exception]
    return [res, high, formatted_exception]

def Xtest_find_error_ops_traceback():
    """ I only want to show users errors from their stuff
    """
    ac = PandasAutocleaning([ACErrorConf])
    df = pd.DataFrame({'a': ["30", "40"]})

    def run_func(df_a, ops):
        return ac._run_df_interpreter(df_a, ops)

    #ERROR = [{'symbol': 'throw_error'}, {'symbol': 'df'}, 'a']
    NESTED_ERROR = [{'symbol': 'throw_nested_error'}, {'symbol': 'df'}, 'a']
    #output_df, error_op, formatted_exception = find_error_op(df, [ERROR], run_func)
    output_df, error_op, formatted_exception = find_error_op(df, [NESTED_ERROR], run_func)

    # Figure out a way to filter the traceback to just user written
    # code, not the internals of the jlisp interpreter
    # Currently punting

    #assert formatted_exception == []

#This is disabled because this code isn't used yet, and there is an incompatability between python 3.9 and 3.10 and greater with format_exception
def Xtest_find_error_ops():
    
    """ this is testing a semi private method

    I want to test error handling, so we can tag it on operations that cause errors
    """
    ac = PandasAutocleaning([ACErrorConf])
    df = pd.DataFrame({'a': ["30", "40"]})

    def run_func(df_a, ops):
        return ac._run_df_interpreter(df_a, ops)

    NOOP = [{'symbol': 'noop'}, {'symbol': 'df'}, 'a']
    ERROR = [{'symbol': 'throw_error'}, {'symbol': 'df'}, 'a']


    # This is probably paranoid and overkill, but off by one errors
    # are very easy with binary search. Errors can also occur with
    # odd/even lists
    
    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, NOOP], run_func)
    assert error_op == -1

    output_df, error_op, formatted_exception = find_error_op(df, [ERROR], run_func)
    assert error_op == 0

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, ERROR], run_func)
    assert error_op == 1

    output_df, error_op, formatted_exception = find_error_op(df, [ERROR, NOOP], run_func)
    assert error_op == 0
    ######################################
    output_df, error_op, formatted_exception = find_error_op(df, [ERROR, NOOP, NOOP], run_func)
    assert error_op == 0

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, ERROR, NOOP], run_func)
    assert error_op == 1

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, NOOP, ERROR], run_func)
    assert error_op == 2
    ############################
    output_df, error_op, formatted_exception = find_error_op(df, [ERROR, NOOP, NOOP, NOOP], run_func)
    assert error_op == 0

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, ERROR, NOOP, NOOP], run_func)
    assert error_op == 1

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, NOOP, ERROR, NOOP], run_func)
    assert error_op == 2

    output_df, error_op, formatted_exception = find_error_op(df, [NOOP, NOOP, NOOP, ERROR], run_func)
    assert error_op == 3


def test_quick_commands_run():
    """
    test that quick_commands work with autocleaning disabled
    """
    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"], 'b': ['aa', 'bb']})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method="", quick_command_args={'search':['aa']}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    expected = pd.DataFrame({
        'a': ["30"],
        'b': ['aa']})

    assert merged_operations == [[sQ('search'), s('df'), "col", "aa"]]
    assert cleaned_df.to_dict() == expected.to_dict()


def Xtest_origs_quick_commands():
    """
    Test that quick_commands work with autocleaning add_origs.  this needs a better make_origs
    or a cleaning method that doesn't call make_origs
    """
    
    ac = PandasAutocleaning([ACConf])
    df = pd.DataFrame({'a': ["30", "40"], 'b': ['aa', 'bb']})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={'search':['aa']}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    expected = pd.DataFrame({
        'a': [30.0, np.nan],
        'a_orig': ["30", "40"],
        'b': ['aa', None],
        'b_orig': ['aa', 'bb']})
    print("merged_operations", merged_operations)
    print("cleaned_df", cleaned_df.to_dict())
        
    assert cleaned_df.to_dict() == expected.to_dict()

EXPECTED_GEN_CODE = """def clean(df):
    df['a'] = smart_to_int(df['a'])
    return df"""

def test_autoclean_codegen():
    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE

class NoOp2(Command):
    #used for testing command stuff
    command_default = [s('noop2'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    #noop2"

class SentinelCleaningGenOps(ColAnalysis):
    """
    This class just calls no-op on each column
    """
    requires_summary = []
    provides_defaults = {'cleaning_ops': []}


    @classmethod
    def computed_summary(kls, column_metadata):
        ops = [sA('noop', clean_col=column_metadata['orig_col_name']), s('df')]
        return {'cleaning_ops': ops}

class SentinelConfig(AutocleaningConfig):
    """
    add a check between rules_op_names to all of the included command classes
    """
    autocleaning_analysis_klasses = [SentinelCleaningGenOps]
    command_klasses = [
        DropCol, FillNA, GroupBy, NoOp, Search, NoOp2]
    
    quick_command_klasses = [Search]
    name="sentinel1"



class SentinelCleaningGenOps2(ColAnalysis):
    """
    This class just generated noop2 for 'b_col'
    """
    requires_summary = []
    provides_defaults = {'cleaning_ops': []}


    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['orig_col_name'] == 'c':
            ops = [
                sA('noop2', clean_col='c'),
                {'symbol': 'df'}]
            print("ops", ops)
            return {'cleaning_ops': ops}
        return {}

class SentinelConfig2(AutocleaningConfig):
    """
    add a check between rules_op_names to all of the included command classes
    """
    autocleaning_analysis_klasses = [SentinelCleaningGenOps2]
    command_klasses = [
        DropCol, FillNA, GroupBy, NoOp, Search, NoOp2]
    
    quick_command_klasses = [Search]
    name="sentinel2"

def test_autoclean_merge_ops():
    """Make sure that remvoing {'auto_clean':True} from an operation
    as preserve does, retains taht operation when switching between
    auto_cleaning methods

    """
    class SentinelBuckaroo(BuckarooWidget):
        autocleaning_klass = PandasAutocleaning
        autoclean_conf = tuple([SentinelConfig, SentinelConfig2, NoCleaningConf])

    dirty_df = pd.DataFrame(
            {'a':[10,  20,  30,   40,  10, 20.3,   5, None, None, None],
             'b':["3", "4", "a", "5", "5",  "b", "b", None, None, None],
             'c':["3", "4", "a", "5", "5",  "b", "b", None, None, None],
             })

    bw = SentinelBuckaroo(dirty_df)
    assert bw.operations == []

    bw.buckaroo_state = {
        "cleaning_method": "sentinel1",
        "post_processing": "",
        "sampled": False,
        "show_commands": "on",
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}
    }

    assert bw.dataflow.cleaning_method == 'sentinel1'
    assert bw.operations ==  [
        [sA('noop', clean_col='a'), s('df'), 'a'],
        [sA('noop', clean_col='b'), s('df'), 'b'],
        [sA('noop', clean_col='c'), s('df'), 'c']]
        

    # come up with a convience method for updating a single prop of buckaroo_state
    bw.buckaroo_state = {
        "cleaning_method": "sentinel2",
        "post_processing": "",
        "sampled": False,
        "show_commands": "on",
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}
    }
    assert bw.operations ==  [
        [sA('noop2', clean_col='c') , s('df'), 'c']]

    bw.operations = [
        [s('noop2', clean_col='c') , s('df'), 'c']]

    assert bw.operations == [
        [s('noop2', clean_col='c') , s('df'), 'c']]


def test_autoclean_dataflow():
    """
    verify that different autocleaning confs are actually called
    """
    class SentinelDataflow(PandasCustomizableDataflow):
        autocleaning_klass = PandasAutocleaning
        autoclean_conf = tuple([SentinelConfig, NoCleaningConf])

    sdf = SentinelDataflow(dirty_df)
    sdf.cleaning_method = ''

    assert sdf.operations == []
    sdf.cleaning_method = "sentinel1"
    assert len(sdf.operations) > 0

def test_autoclean_full_widget():
    """
    verify that different autocleaning confs are actually called
    """
    class SentinelBuckaroo(BuckarooWidget):
        autocleaning_klass = PandasAutocleaning
        autoclean_conf = tuple([SentinelConfig, NoCleaningConf])

    bw = SentinelBuckaroo(dirty_df)
    assert bw.operations == []

    bw.buckaroo_state = {
        "cleaning_method": "sentinel1",
        "post_processing": "",
        "sampled": False,
        "show_commands": "on",
        "df_display": "main",
        "search_string": "",
        "quick_command_args": {}
    }

    assert bw.dataflow.cleaning_method == 'sentinel1'
    # make sure the widget oprations were updated
    assert len(bw.operations) > 0


def test_drop_col():
    """make sure we can that make_origs doesn't throw an error when
    drop_col is called. It might depend on columns existing

    """
    df = pd.DataFrame({
        'a':[10,20,20, 10, 10, None],
        'b':['20',10,None,'5',10, 'asdf']})
    bw = BuckarooWidget(df)
    bw.operations = [[{'symbol': 'dropcol'}, {'symbol': 'df'}, 'a']]


def test_stacked_filters():
    """make sure that filters apply combinatorially not just last one first

    fixing this requires replacing the progn with some type of
    threading macro. or making every operation in place. and adding a
    copy() at the beginning

    """

def test_quick_commands():
    """ simulate the data structure sent from the frontend to autocleaning that should generate
    filtering commands

    Verify that no commands are added for blank strings or null (the frontend is fairly dumb)
    """

    quick_commands = [Search, OnlyOutliers]

    #start with empty
    empty_produced_commands = generate_quick_ops(quick_commands, {"search": [""], "only_outliers": [""]})
    assert empty_produced_commands == []

    empty_produced_commands2 = generate_quick_ops(quick_commands, {"search": [None], "only_outliers": [""]})
    assert empty_produced_commands2 == []

    #verify that both quick_args aren't necessary
    empty_produced_commands3 = generate_quick_ops(quick_commands, {"search": [None]})
    assert empty_produced_commands3 == []

    #assertRaises generate_quick_ops(quick_commands, {"non_matching_command": ""})
    #assertRaises generate_quick_ops(quick_commands, {"non_matching_command": "", "search":""})



    search_only_produced_commands = generate_quick_ops(quick_commands, {"search": ["asdf"]})
    assert search_only_produced_commands == [[sQ('search'), s('df'), "col", "asdf"]]

    #note only_outliers needs quick_command to substitute into the col place, not the last arg
    oo_produced_commands = generate_quick_ops(quick_commands, {"only_outliers": ["col_B"]})
    assert oo_produced_commands == [[sQ('only_outliers'), s('df'), "col_B", .01]]

    both_produced_commands = generate_quick_ops(
        quick_commands, {"search": ["asdf"], "only_outliers": ["col_B"]})
    assert both_produced_commands == [
        [sQ('search'), s('df'), "col", "asdf"],
        [sQ('only_outliers'), s('df'), "col_B", .01]
    ]


    #note the order of produced commands depends on the order of command_list passed into generate_quick_ops
    both_produced_commands_reversed = generate_quick_ops(
        quick_commands[::-1], {"search": ["asdf"], "only_outliers": ["col_B"]})
    assert both_produced_commands_reversed == [
        [sQ('only_outliers'), s('df'), "col_B", .01],
        [sQ('search'), s('df'), "col", "asdf"]]


class TwoArgSearch(Command):
    command_default = [s('search_two'), s('df'), "col", "", 888]
    command_pattern = [[3, 'term', 'type', 'string'],
                       [4, 'term', 'type', 'int']]
    quick_args_pattern = [[3, 'term', 'type', 'string'],
                  [4, 'term', 'type', 'int']]


def test_two_arg_quick_command():
    """
    verify that generate_quick_ops works for a command that has two quick_args
    """
    

    two_arg_search_produced_commands = generate_quick_ops([TwoArgSearch], {"search_two": ["FFFasdf", 9]})
    assert two_arg_search_produced_commands == [[sQ('search_two'), s('df'), "col", "FFFasdf", 9]]
    


    



