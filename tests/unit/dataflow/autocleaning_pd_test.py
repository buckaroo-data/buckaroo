import pandas as pd
import numpy as np
from buckaroo import BuckarooWidget
from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.dataflow.autocleaning import merge_ops, format_ops, AutocleaningConfig
from buckaroo.dataflow.autocleaning import PandasAutocleaning, generate_quick_ops
from buckaroo.jlisp.lisp_utils import (s, qc_sym)
from buckaroo.customizations.pandas_commands import (
    Command,
    SafeInt, DropCol, FillNA, GroupBy, NoOp, Search, OnlyOutliers
)
from buckaroo.customizations.pd_autoclean_conf import (NoCleaningConf)


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


def xtest_cleaning_stats():
    dfs = DfStats(dirty_df, [DefaultSummaryStats])

    # "3", "4", "5", "5"   4 out of 10
    assert dfs.sdf['b']['int_parse'] == 0.4
    assert dfs.sdf['b']['int_parse_fail'] == 0.6


SAFE_INT_TOKEN = [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]


def test_format_ops():
    column_meta = {
        'a': {'cleaning_ops':SAFE_INT_TOKEN },
        'b': {'cleaning_ops': [
            {'symbol': 'replace_dirty', 'meta':{'auto_clean': True}},
            {'symbol': 'df'}, '\n', None]}}

    expected_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a'],
        [{'symbol': 'replace_dirty', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'b', '\n', None]]
    assert format_ops(column_meta) == expected_ops


def test_merge_ops():
    existing_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']
    ]

    cleaning_ops = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a']]

    expected_merged = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']
    ]
    print( merge_ops(existing_ops, cleaning_ops))
    print("@"*80)
    assert merge_ops(existing_ops, cleaning_ops) == expected_merged

class ACConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt, Search]
    quick_command_klasses = [Search]
    name="default"


def test_handle_user_ops():

    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': [10, 20, 30]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    assert merged_operations == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    existing_ops = [
        [{'symbol': 'old_safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]
    cleaning_result2 = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=existing_ops)
    cleaned_df, cleaning_sd, generated_code, merged_operations2 = cleaning_result2
    assert merged_operations2 == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    user_ops = [
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]
    cleaning_result3 = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=user_ops)
    cleaned_df, cleaning_sd, generated_code, merged_operations3 = cleaning_result3
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
        raw, cleaned, {'a':{'add_orig': True}})
    assert combined.to_dict() == expected.to_dict()

def Xtest_make_origs_preserve():
    """
    I keep seeing nan's pop up.  We should be using the better Pandas nullable types
    """
    raw = pd.DataFrame({'a': [30, "40", "not_used"]})
    cleaned = pd.DataFrame({'a': [30, 40]})
    expected = pd.DataFrame(
        {
            'a': pd.Series([30, 40, None], dtype='Int64'),
            'a_orig': [30,  "40", "not_used"]})
    combined = PandasAutocleaning.make_origs(
        raw, cleaned, {'a':{'add_orig': True, 'preserve_orig_index':True}})
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

    
def test_quick_commands_run():
    """
    test that quick_commands work with autocleaning disabled
    """
    ac = PandasAutocleaning([ACConf, NoCleaningConf])
    df = pd.DataFrame({'a': ["30", "40"], 'b': ['aa', 'bb']})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method="NoCleaning", quick_command_args={'search':['aa']}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    expected = pd.DataFrame({
        'a': ["30"],
        'b': ['aa']})

    assert merged_operations == [[qc_sym('search'), s('df'), "col", "aa"]]
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
    assert search_only_produced_commands == [[qc_sym('search'), s('df'), "col", "asdf"]]

    #note only_outliers needs quick_command to substitute into the col place, not the last arg
    oo_produced_commands = generate_quick_ops(quick_commands, {"only_outliers": ["col_B"]})
    assert oo_produced_commands == [[qc_sym('only_outliers'), s('df'), "col_B", .01]]

    both_produced_commands = generate_quick_ops(
        quick_commands, {"search": ["asdf"], "only_outliers": ["col_B"]})
    assert both_produced_commands == [
        [qc_sym('search'), s('df'), "col", "asdf"],
        [qc_sym('only_outliers'), s('df'), "col_B", .01]
    ]


    #note the order of produced commands depends on the order of command_list passed into generate_quick_ops
    both_produced_commands_reversed = generate_quick_ops(
        quick_commands[::-1], {"search": ["asdf"], "only_outliers": ["col_B"]})
    assert both_produced_commands_reversed == [
        [qc_sym('only_outliers'), s('df'), "col_B", .01],
        [qc_sym('search'), s('df'), "col", "asdf"]]


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
    assert two_arg_search_produced_commands == [[qc_sym('search_two'), s('df'), "col", "FFFasdf", 9]]
    


    



