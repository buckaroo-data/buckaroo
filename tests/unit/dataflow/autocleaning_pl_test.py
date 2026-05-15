import polars as pl
from buckaroo.customizations.polars_analysis import (
    VCAnalysis, PLCleaningStats, BasicAnalysis)
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PlDfStats
from buckaroo.pluggable_analysis_framework.col_analysis import (ColAnalysis)
from buckaroo.dataflow.autocleaning import merge_ops, format_ops, AutocleaningConfig
from buckaroo.polars_buckaroo import PolarsAutocleaning
from buckaroo.customizations.polars_commands import (
    Command, PlSafeInt, DropCol, FillNA, GroupBy, NoOp, Search
)
from buckaroo.customizations.styling import DefaultMainStyling
from buckaroo.jlisp.lisp_utils import s


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
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}],
                'add_orig': True}
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
        'a': {'cleaning_ops':SAFE_INT_TOKEN, 'orig_col_name':'a', },
        'b': {'cleaning_ops': [
            {'symbol': 'replace_dirty', 'meta':{'auto_clean': True}},
            {'symbol': 'df'}, '\n', None], 'orig_col_name':'b'}}

    expected_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a'],
        [{'symbol': 'replace_dirty', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'b', '\n', None]]
    assert format_ops(column_meta) == expected_ops


def test_merge_ops():
    existing_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']]

    cleaning_ops = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a']]

    expected_merged = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']]
    print( merge_ops(existing_ops, cleaning_ops))
    print("@"*80)
    assert merge_ops(existing_ops, cleaning_ops) == expected_merged

class ACConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [VCAnalysis, PLCleaningStats, BasicAnalysis, CleaningGenOps]
    command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
    name = "default"

class NoCleaning(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
    name = ""


    
def test_handle_user_ops():

    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': [10, 20, 30]})
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
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]


def desired_test_make_origs():
    # I can't make this work in a sensible way because it is not
    # possible to quickly run comparisons against different dtype
    # columns, and object dtypes are serverely limited
    df_a = pl.DataFrame({'a': [10, 20, 30, 40], 'b': [1, 2, 3, 4]})
    df_b = pl.DataFrame({'a': [10, 20,  0, 40], 'b': [1, 2, 3, 4]})    

    expected = pl.DataFrame([pl.Series("a",      [  10,   20,    0,   40], dtype=pl.Int64),
        pl.Series("a_orig", [None, None,   30, None], dtype=pl.Int64),
        pl.Series("b",      [   1,    2,    3,    4], dtype=pl.Int64),
        pl.Series("b_orig", [None, None, None, None], dtype=pl.Int64)])

    combined = PolarsAutocleaning.make_origs(
        df_a, df_b, {'a':{'add_orig': True}, 'b': {'add_orig': True}})
    assert combined.to_dicts() == expected.to_dicts()

def test_make_origs_different_dtype():
    raw = pl.DataFrame({'a': [30, "40"]}, strict=False)
    cleaned = pl.DataFrame({'a': [30,  40]})
    expected = pl.DataFrame(
        {
            'a': [30, 40],
         'a_orig': [30,  "40"]},
        strict=False)
    combined = PolarsAutocleaning.make_origs(
        raw, cleaned, {'a':{'add_orig': True}})
    assert combined.to_dicts() == expected.to_dicts()

def test_handle_clean_df():
    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result
    expected = pl.DataFrame({
        'a': [30, 40],
        'a_orig': ["30",  "40"]})
    print(f"{cleaning_sd=}")
    assert cleaned_df.to_dicts() == expected.to_dicts()

EXPECTED_GEN_CODE = """def clean(df):
    df = df.with_columns(pl.col('a').cast(pl.Int64, strict=False))
    return df"""

class TaggingCommand(Command):
    """A Command whose transform returns the 2-tuple (df, sd_updates)."""
    command_default = [s('tag'), s('df'), 'col', '']
    command_pattern = [[3, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, col, val):
        return df, {col: {'note': val}}

    @staticmethod
    def transform_to_py(df, col, val):
        return "    # tag"


class TagConf(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [TaggingCommand]
    name = ""


def test_transform_can_return_sd_updates_via_2tuple():
    """A Command's transform may return (df, sd_updates); the interpreter
    accumulates sd_updates and autocleaning merges them into cleaning_sd."""
    ac = PolarsAutocleaning([TagConf])
    df = pl.DataFrame({'a': [1, 2, 3]})
    op = [{'symbol': 'tag'}, s('df'), 'a', 'hello']

    _df, cleaning_sd, _gen, _ops = ac.handle_ops_and_clean(
        df, cleaning_method='', quick_command_args={}, existing_operations=[op])

    assert cleaning_sd.get('a', {}).get('note') == 'hello'


class SearchConf(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [Search]
    name = ""


def test_search_threads_highlight_regex_into_cleaning_sd_under_rename():
    """Search plumbs its search term into cleaning_sd as highlight_regex on
    every polars-String column. The rest of the sd is keyed by buckaroo's
    internal a/b/c names, so autocleaning rewrites the op-supplied keys to
    match — otherwise the entries would sit alongside as orphans without
    a `_type` and trip the styling fallback."""
    ac = PolarsAutocleaning([SearchConf])
    # 'businessname' becomes 'a', 'rating' becomes 'b' under buckaroo renaming.
    df = pl.DataFrame({'businessname': ['pizza', 'sushi'], 'rating': [5, 4]})
    search_op = [{'symbol': 'search'}, s('df'), 'col', 'pizza']

    _cleaned, cleaning_sd, _gen, _ops = ac.handle_ops_and_clean(
        df, cleaning_method='', quick_command_args={}, existing_operations=[search_op])

    # keyed by the *renamed* col, not by 'businessname'
    assert cleaning_sd.get('a', {}).get('highlight_regex') == 'pizza'
    assert 'businessname' not in cleaning_sd
    # non-string column ('b' / 'rating') must not receive the highlight
    assert 'highlight_regex' not in cleaning_sd.get('b', {})


def test_default_main_styling_emits_highlight_regex_into_displayer_args():
    """style_column copies highlight_regex out of col_meta and into the
    string displayer_args, where the JS-side displayer reads it."""
    col_meta = {'_type': 'string', 'highlight_regex': 'pizza', 'orig_col_name': 'a'}
    cc = DefaultMainStyling.style_column('a', col_meta)
    assert cc['displayer_args']['displayer'] == 'string'
    assert cc['displayer_args']['highlight_regex'] == 'pizza'


def test_style_column_handles_col_meta_missing_type():
    """A col_meta lacking `_type` (e.g. a stray sd entry contributed by an
    op when the matching summary-stats entry is keyed differently) should
    fall back to obj rather than KeyError."""
    cc = DefaultMainStyling.style_column('whatever', {'highlight_regex': 'x'})
    assert cc['displayer_args']['displayer'] == 'obj'


def test_style_column_merges_nested_displayer_args_and_ag_grid_specs():
    """init_sd entries use the same nested shape as column_config_overrides
    — {'displayer_args': {...}, 'ag_grid_specs': {...}} — but unlike
    overrides, the merge here is shallow-per-bag (caller wins per-key)
    rather than replace-the-bag. That's the whole point: max_length=2000
    overrides styling's 35, wrapText/width overlay on minWidth, and any
    other styled keys (e.g. highlight_regex) survive."""
    col_meta = {'_type': 'string', 'orig_col_name': 'comments',
                'displayer_args': {'displayer': 'string', 'max_length': 2000},
                'ag_grid_specs': {'wrapText': True, 'width': 400, 'maxWidth': 400}}
    cc = DefaultMainStyling.style_column('a', col_meta)
    assert cc['displayer_args']['max_length'] == 2000
    assert cc['ag_grid_specs']['wrapText'] is True
    assert cc['ag_grid_specs']['width'] == 400
    assert cc['ag_grid_specs']['maxWidth'] == 400
    # styling's computed minWidth is still present unless caller overrode it
    assert 'minWidth' in cc['ag_grid_specs']


def test_init_sd_displayer_args_and_search_highlight_coexist_on_same_column():
    """The whole point of routing per-column augmentations through init_sd
    instead of column_config_overrides: init_sd's nested displayer_args and
    a Search op's flat highlight_regex both land in merged_sd, and both
    make it into the final displayer_args. column_config_overrides would
    have clobbered the highlight by replacing displayer_args wholesale."""
    from buckaroo.dataflow.styling_core import merge_sds
    init_sd = {'a': {'_type': 'string', 'orig_col_name': 'comments',
                     'displayer_args': {'displayer': 'string', 'max_length': 2000},
                     'ag_grid_specs': {'wrapText': True}}}
    search_contribution = {'a': {'highlight_regex': 'pizza'}}
    merged = merge_sds(init_sd, search_contribution)
    cc = DefaultMainStyling.style_column('a', merged['a'])
    assert cc['displayer_args']['max_length'] == 2000
    assert cc['displayer_args']['highlight_regex'] == 'pizza'
    assert cc['ag_grid_specs']['wrapText'] is True


def test_autoclean_codegen():
    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': ["30", "40"]})
    cleaning_result = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    cleaned_df, cleaning_sd, generated_code, merged_operations = cleaning_result

    assert generated_code == EXPECTED_GEN_CODE
