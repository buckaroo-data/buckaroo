import pandas as pd
from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)
from buckaroo.pluggable_analysis_framework.analysis_management import DfStats
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.dataflow.autocleaning import merge_ops, format_ops, AutocleaningConfig
from buckaroo.dataflow.autocleaning import PandasAutocleaning
from buckaroo.customizations.pandas_commands import (
    SafeInt, DropCol, FillNA, GroupBy, NoOp
)


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
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]}
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
    command_klasses = [DropCol, FillNA, GroupBy, NoOp, SafeInt]
    name="default"


def test_handle_user_ops():

    ac = PandasAutocleaning([ACConf])
    df = pd.DataFrame({'a': [10, 20, 30]})
    cleaning_result = ac.handle_ops_and_clean(df, cleaning_method='default', existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    assert merged_operations == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    existing_ops = [
        [{'symbol': 'old_safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]
    cleaning_result2 = ac.handle_ops_and_clean(
        df, cleaning_method='default', existing_operations=existing_ops)
    cleaned_df, cleaning_sd, generated_code, merged_operations2 = cleaning_result2
    assert merged_operations2 == [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    user_ops = [
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]
    cleaning_result3 = ac.handle_ops_and_clean(
        df, cleaning_method='default', existing_operations=user_ops)
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
    assert PandasAutocleaning.make_origs(raw, cleaned).to_dict() == expected.to_dict()

def test_handle_clean_df():
    ac = PandasAutocleaning([ACConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(df, cleaning_method='default', existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    expected = pd.DataFrame({
        'a': [30, 40],
        'a_orig': ["30",  "40"]})
    assert cleaned_df.to_dict() == expected.to_dict()

EXPECTED_GEN_CODE = """def clean(df):
    df['a'] = smart_to_int(df['a'])
    return df"""

def test_autoclean_codegen():
    ac = PandasAutocleaning([ACConf])
    df = pd.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(df, cleaning_method='default', existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE
