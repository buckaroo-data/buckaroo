import polars as pl
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PLCleaningStats, BasicAnalysis)
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PlDfStats
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.dataflow.autocleaning import merge_ops, format_ops, AutocleaningConfig
from buckaroo.polars_buckaroo import PolarsAutocleaning
from buckaroo.customizations.polars_commands import (
    PlSafeInt, DropCol, FillNA, GroupBy, NoOp
)


dirty_df = pl.DataFrame(
    {'a':[10,  20,  30,   40,  10, 20.3,   5, None, None, None],
     'b':["3", "4", "a", "5", "5",  "b", "b", None, None, None]},
    strict=False)


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


def test_cleaning_stats():
    dfs = PlDfStats(dirty_df, [VCAnalysis, PLCleaningStats, BasicAnalysis])

    # "3", "4", "5", "5"   4 out of 10
    assert dfs.sdf['b']['int_parse'] == 0.4
    assert dfs.sdf['b']['int_parse_fail'] == 0.6


SAFE_INT_TOKEN = [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]
def test_ops_gen():

    dfs = PlDfStats(dirty_df, [make_default_analysis(int_parse=.4, int_parse_fail=.6),
                               CleaningGenOps], debug=True)
    assert dfs.sdf['b']['cleaning_ops'] == SAFE_INT_TOKEN
    dfs = PlDfStats(dirty_df, [make_default_analysis(int_parse=.2, int_parse_fail=.8),
                               CleaningGenOps])
    assert dfs.sdf['b']['cleaning_ops'] == []



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
    autocleaning_analysis_klasses = [VCAnalysis, PLCleaningStats, BasicAnalysis, CleaningGenOps]
    command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
    name="default"


    
def test_handle_user_ops():

    ac = PolarsAutocleaning([ACConf])
    df = pl.DataFrame({'a': [10, 20, 30]})
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


def desired_test_make_origs():
    # I can't make this work in a sensible way because it is not
    # possible to quickly run comparisons against different dtype
    # columns, and object dtypes are serverely limited
    df_a = pl.DataFrame({'a': [10, 20, 30, 40], 'b': [1, 2, 3, 4]})
    df_b = pl.DataFrame({'a': [10, 20,  0, 40], 'b': [1, 2, 3, 4]})    

    expected = pl.DataFrame(
        [pl.Series("a",      [  10,   20,    0,   40], dtype=pl.Int64),
         pl.Series("a_orig", [None, None,   30, None], dtype=pl.Int64),
         pl.Series("b",      [   1,    2,    3,    4], dtype=pl.Int64),
         pl.Series("b_orig", [None, None, None, None], dtype=pl.Int64)],
    )

    assert PolarsAutocleaning.make_origs(df_a, df_b).to_dicts() == expected.to_dicts()

def test_make_origs_different_dtype():
    raw = pl.DataFrame({'a': [30, "40"]}, strict=False)
    cleaned = pl.DataFrame({'a': [30,  40]})
    expected = pl.DataFrame(
        {
            'a': [30, 40],
            'a_orig': [30,  "40"]},
        strict=False)
    assert PolarsAutocleaning.make_origs(raw, cleaned).to_dicts() == expected.to_dicts()

def test_handle_clean_df():
    ac = PolarsAutocleaning([ACConf])
    df = pl.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(df, cleaning_method='default', existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    expected = pl.DataFrame({
        'a': [30, 40],
        'a_orig': ["30",  "40"]})
    assert cleaned_df.to_dicts() == expected.to_dicts()

EXPECTED_GEN_CODE = """def clean(df):
    df = df.with_columns(pl.col('a').cast(pl.Int64, strict=False))
    return df"""

def test_autoclean_codegen():
    ac = PolarsAutocleaning([ACConf])
    df = pl.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(df, cleaning_method='default', existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE
