from typing import Any, TypedDict
import polars as pl
from buckaroo.dataflow.autocleaning import (
    merge_ops, format_ops, AutocleaningConfig, PandasAutocleaning, _rekey_op_sd_to_internal)
from buckaroo.customizations.polars_commands import (Command, Search, SDResult, PlSafeInt, DropCol, FillNA, GroupBy, NoOp)
from buckaroo.customizations.styling import DefaultMainStyling
from buckaroo.customizations.pl_stats_v2 import PL_AUTOCLEAN_DEFAULT_V2, pl_cleaning_stats
from buckaroo.polars_buckaroo import PolarsAutocleaning
from buckaroo.pluggable_analysis_framework.df_stats_v2 import PlDfStatsV2
from buckaroo.pluggable_analysis_framework.stat_func import stat
from buckaroo.jlisp.lisp_utils import s


SAFE_INT_TOKEN = [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]

dirty_df = pl.DataFrame(
    {'a':[10,  20,  30,   40,  10, 20.3,   5, None, None, None],
     'b':["3", "4", "a", "5", "5",  "b", "b", None, None, None]},
    strict=False)


_AddOrigResult = TypedDict('_AddOrigResult', {'cleaning_ops': Any, 'add_orig': Any})


@stat()
def _pl_add_orig_cleaning(int_parse: float, int_parse_fail: float) -> _AddOrigResult:
    """Polars cleaning op generator that flags add_orig (keeps <col>_orig)."""
    if int_parse > 0.3:
        return {'cleaning_ops': SAFE_INT_TOKEN, 'add_orig': True}
    return {'cleaning_ops': [], 'add_orig': False}


_PL_AC_CLEANING = [pl_cleaning_stats, _pl_add_orig_cleaning]


class ACConf(AutocleaningConfig):
    autocleaning_analysis_klasses = _PL_AC_CLEANING
    command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
    name = "default"


class NoCleaning(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [PlSafeInt, DropCol, FillNA, GroupBy, NoOp]
    name = ""


def test_cleaning_stats():
    # "3", "4", "5", "5"  -> 4 of 10 parse as int
    s = PlDfStatsV2(dirty_df, PL_AUTOCLEAN_DEFAULT_V2)
    assert s.sdf['b']['int_parse'] == 0.4
    assert s.sdf['b']['int_parse_fail'] == 0.6


def test_ops_gen():
    s = PlDfStatsV2(dirty_df, PL_AUTOCLEAN_DEFAULT_V2)
    assert s.sdf['b']['cleaning_ops'] == SAFE_INT_TOKEN
    no_ints = PlDfStatsV2(pl.DataFrame({'x': ['aa', 'bb', 'cc']}), PL_AUTOCLEAN_DEFAULT_V2)
    assert no_ints.sdf['a']['cleaning_ops'] == []


def test_handle_user_ops():
    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': [10, 20, 30]})
    _cleaned, _sd, _gen, merged_operations = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    assert merged_operations == [[{'symbol': 'safe_int', 'meta': {'auto_clean': True}}, {'symbol': 'df'}, 'a']]

    user_ops = [[{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]
    _cleaned, _sd, _gen, merged_operations3 = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=user_ops)
    assert merged_operations3 == [
        [{'symbol': 'safe_int', 'meta': {'auto_clean': True}}, {'symbol': 'df'}, 'a'],
        [{'symbol': 'noop'}, {'symbol': 'df'}, 'b']]


def test_handle_clean_df():
    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': ["30", "40"]})
    cleaned_df, _sd, _gen, _ops = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    expected = pl.DataFrame({'a': [30, 40], 'a_orig': ["30", "40"]})
    assert cleaned_df.to_dicts() == expected.to_dicts()


EXPECTED_GEN_CODE = """def clean(df):
    df = df.with_columns(pl.col('a').cast(pl.Int64, strict=False))
    return df"""


def test_autoclean_codegen():
    ac = PolarsAutocleaning([ACConf, NoCleaning])
    df = pl.DataFrame({'a': ["30", "40"]})
    _cleaned, _sd, generated_code, _ops = ac.handle_ops_and_clean(
        df, cleaning_method='default', quick_command_args={}, existing_operations=[])
    assert generated_code == EXPECTED_GEN_CODE


def test_make_origs_different_dtype():
    raw = pl.DataFrame({'a': [30, "40"]}, strict=False)
    cleaned = pl.DataFrame({'a': [30, 40]})
    expected = pl.DataFrame({'a': [30, 40], 'a_orig': [30, "40"]}, strict=False)
    combined = PolarsAutocleaning.make_origs(raw, cleaned, {'a': {'add_orig': True}})
    assert combined.to_dicts() == expected.to_dicts()


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
    assert merge_ops(existing_ops, cleaning_ops) == expected_merged


class TaggingCommand(Command):
    """A Command whose transform returns SDResult(df, sd_updates)."""
    command_default = [s('tag'), s('df'), 'col', '']
    command_pattern = [[3, 'tag', 'type', 'string']]

    @staticmethod
    def transform(df, col, val):
        return SDResult(df, {col: {'note': val}})

    @staticmethod
    def transform_to_py(df, col, val):
        return "    # tag"


class TagConf(AutocleaningConfig):
    autocleaning_analysis_klasses = []
    command_klasses = [TaggingCommand]
    name = ""


def test_sdresult_lands_in_cleaning_sd_through_handle_ops_and_clean():
    ac = PandasAutocleaning([TagConf])
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
    ac = PandasAutocleaning([SearchConf])
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


def test_rekey_preserves_analysis_entries_when_orig_names_collide_with_letters():
    """Regression for codex review on #758. If an orig col name happens
    to equal an internal letter (e.g. df cols ['b', 'foo'] → internal
    a='b', b='foo'), the rekey must not merge the analysis entry for
    internal 'b' into 'a' just because rewrites['b']=='a'. Analysis
    entries (marked by `rewritten_col_name`) pass through untouched;
    only op-contributed (orig-keyed) entries get rekeyed."""
    cleaned_df = pl.DataFrame({'b': [1], 'foo': [2]})
    cleaning_sd = {
        'a': {'rewritten_col_name': 'a', 'orig_col_name': 'b', '_type': 'integer'},
        'b': {'rewritten_col_name': 'b', 'orig_col_name': 'foo', '_type': 'integer'},
        # op-contributed entry keyed by orig name 'foo'
        'foo': {'highlight_regex': 'x'}}
    out = _rekey_op_sd_to_internal(cleaning_sd, cleaned_df)
    # analysis entries untouched, in place
    assert out['a']['orig_col_name'] == 'b'
    assert out['a']['_type'] == 'integer'
    assert out['b']['orig_col_name'] == 'foo'
    assert out['b']['_type'] == 'integer'
    # op-contributed entry rekeyed onto the matching internal letter
    assert out['b']['highlight_regex'] == 'x'
    # no stray orig-keyed entry left behind
    assert 'foo' not in out


def test_style_column_handles_col_meta_missing_type():
    """A col_meta lacking `_type` (e.g. a stray sd entry contributed by an
    op when no cleaning_method ran so no analysis entry exists for the
    column) should fall back to obj rather than KeyError."""
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


def test_style_column_delete_keys_drops_tooltip():
    """init_sd's delete_keys lets a user drop top-level keys that style_column
    adds by default. The motivating case: a string column where the user
    doesn't want a tooltip permanently attached to the cell."""
    col_meta = {'_type': 'string', 'orig_col_name': 'comments',
        'delete_keys': ['tooltip_config']}
    cc = DefaultMainStyling.style_column('a', col_meta)
    assert 'tooltip_config' not in cc
    # Other styled keys unaffected
    assert cc['displayer_args']['displayer'] == 'string'
    assert 'minWidth' in cc['ag_grid_specs']
