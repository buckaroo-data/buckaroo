from typing import Dict, List
import pandas as pd
from buckaroo.dataflow.styling_core import ColumnConfig, DFViewerConfig, NormalColumnConfig, PartialColConfig, StylingAnalysis, merge_sd_overrides, rewrite_override_col_references
from buckaroo.ddd_library import get_basic_df2, get_multiindex_index_df, get_multiindex_index_multiindex_with_names_cols_df, get_multiindex_index_with_names_multiindex_cols_df, get_multiindex_with_names_both, get_multiindex_with_names_index_df, get_multindex_cols_df, get_multindex_with_names_cols_df, get_tuple_cols_df
from buckaroo.df_util import ColIdentifier
from buckaroo.pluggable_analysis_framework.col_analysis import SDType
BASIC_DF = get_basic_df2()

def test_simple_styling() -> None:
    simple_df: pd.DataFrame = pd.DataFrame({
        'foo':[10, 20, 30],
        'bar':['foo', 'bar', 'baz']})

    dfvc: DFViewerConfig = StylingAnalysis.get_dfviewer_config(
    {'a':{'orig_col_name':'foo'}, 'b':{'orig_col_name':'bar'}}, simple_df)

    col_config: List[ColumnConfig] = dfvc['column_config']
    assert len(col_config) == 2
    assert col_config[0]['col_name'] == 'a'
    assert col_config[0]['header_name'] == 'foo'
    assert col_config[1]['col_name'] == 'b'
    assert col_config[1]['header_name'] == 'bar'

def test_multi_index_styling() -> None:

    mic_df: pd.DataFrame = get_multindex_cols_df()
    fake_sd:SDType = {
        "a": {'orig_col_name':('foo','a')},
        "b": {'orig_col_name':('foo','b')},
        "c": {'orig_col_name':('bar','a')},
    }

    dfvc: DFViewerConfig = StylingAnalysis.get_dfviewer_config(fake_sd, mic_df)

    col_config: List[ColumnConfig] = dfvc['column_config']
    assert len(col_config) == 3
    #assert col_config[0]['col_path'] == ('index', '')
    assert col_config[0]['col_path'] == ('foo', 'a')
    assert col_config[1]['col_path'] == ('foo', 'b')

    assert col_config[2]['col_path'] == ('bar', 'a')

def test_tuple_col_styling() -> None:

    mic_df: pd.DataFrame = get_tuple_cols_df()
    fake_sd:SDType = {
        "a": {'orig_col_name':('foo','a')},
        "b": {'orig_col_name':('foo','b')},
        "c": {'orig_col_name':('bar','a')},
    }

    dfvc: DFViewerConfig = StylingAnalysis.get_dfviewer_config(fake_sd, mic_df)

    col_config: List[ColumnConfig] = dfvc['column_config']
    assert len(col_config) == 3
    #assert col_config[0]['col_name'] == "('index', '')"
    print(col_config[0])
    #assert col_config[0]['col_path'] == ('index', '')
    assert col_config[0]['col_path'] == ('foo', 'a')
    assert col_config[1]['col_path'] == ('foo', 'b')
    assert col_config[2]['col_path'] == ('bar', 'a')

    
def test_index_styling_simple():
    assert [{'col_name': 'index', 'header_name':'index', 'displayer_args': {'displayer': 'obj'}}] == \
        StylingAnalysis.get_left_col_configs(get_basic_df2())

def test_index_styling1():
    expected = [
        {'header_name': '', 'col_name': 'index_a', 'displayer_args':
         {'displayer': 'obj'}},
        {'header_name': '', 'col_name': 'index_b',
         'displayer_args': {'displayer': 'obj'}}]

    actual = StylingAnalysis.get_left_col_configs(get_multiindex_index_df())
    assert expected == actual

def test_index_styling2():
    assert [{'col_path':['level_a', 'level_b', 'index'],
            'field':'index', 'displayer_args': {'displayer': 'obj'}}] == StylingAnalysis.get_left_col_configs(get_multindex_with_names_cols_df())
def test_index_styling3():
    assert [{'col_path':['index_name_1'], 'field':'index_a', 'displayer_args': {'displayer': 'obj'}},
    {'col_path':['index_name_2'], 'field':'index_b', 'displayer_args': {'displayer': 'obj'}}] == StylingAnalysis.get_left_col_configs(get_multiindex_with_names_index_df())

def test_index_styling4():

    left_col_configs: List[ColumnConfig] = [
                {
                    "col_path": [
                        "",
                        "",
                    ],
                    "field": "index_a",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "col_path": [
                        "level_a",
                        "level_b",
                    ],
                    "field": "index_b",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                }
            ]
    actual = StylingAnalysis.get_left_col_configs(get_multiindex_index_multiindex_with_names_cols_df())
    assert left_col_configs == actual

def test_index_styling5():
    assert [{'col_path':['', '', 'index_name_1'], 'field':'index_a', 'displayer_args': {'displayer': 'obj'}},
    {'col_path':['', '', 'index_name_2'], 'field':'index_b', 'displayer_args': {'displayer': 'obj'}}] == StylingAnalysis.get_left_col_configs(get_multiindex_index_with_names_multiindex_cols_df())

def test_index_styling6():
    assert [{'col_path':['', '', 'index_name_1'], 'field':'index_a', 'displayer_args': {'displayer': 'obj'}},
    {'col_path':['level_a', 'level_b', 'index_name_2'], 'field':'index_b', 'displayer_args': {'displayer': 'obj'}}] == StylingAnalysis.get_left_col_configs(get_multiindex_with_names_both())
        

def test_get_dfviewer_config_merge_hidden():
    sd: SDType = {'a':
        {'orig_col_name': 'sent_int_col', 'rewritten_col_name': 'a'},
        'b':
        {'orig_col_name': 'sent_str_col', 'rewritten_col_name': 'b'},
        'sent_int_col':
        {'merge_rule': 'hidden'}}

    expected_output: DFViewerConfig = {
        'pinned_rows': [],
        'column_config':  [
            {'col_name': 'b', 'header_name':'sent_str_col', 'displayer_args': {'displayer': 'obj'}},
        ],
        'left_col_configs': [{'col_name': 'index', 'header_name':'index',
                             'displayer_args': {'displayer': 'obj'}}],
        'component_config': {},
        'extra_grid_config': {},
    }

    actual = StylingAnalysis.get_dfviewer_config(sd, BASIC_DF)
    assert expected_output == actual

def test_get_dfviewer_column_config_override():
    """
      This test the case where some analysis puts a 'column_config_override' key into the sddict.

      I'm pretty sure that BuckarooWidget(... column_config_overrides=...)
      goes through a different codepath
      """
    sd: SDType = {
    'a': {'orig_col_name': 'sent_int_col', 'rewritten_col_name': 'a'},
    'b': {'orig_col_name': 'sent_str_col', 'rewritten_col_name': 'b',
          'column_config_override' : {
              'color_map_config': {'color_rule': 'color_from_column', 'val_column': 'Volume_colors'}}},
    'c': {'orig_col_name': 'Volume_colors', 'rewritten_col_name': 'c'},
    }
    
    b_config : NormalColumnConfig = {
    'col_name': 'b', 'header_name':'sent_str_col', 'displayer_args': {'displayer': 'obj'},
             'color_map_config': {'color_rule': 'color_from_column', 'val_column': 'c'}}
    expected_output: DFViewerConfig = {
        'pinned_rows': [],
        'column_config':  [
            {'col_name': 'a', 'header_name':'sent_int_col', 'displayer_args': {'displayer': 'obj'}},
            b_config,
            {'col_name': 'c',
             'displayer_args': {'displayer': 'obj'},
        'header_name': 'Volume_colors'}
        ],
        'left_col_configs': [{'col_name': 'index', 'header_name':'index',
                             'displayer_args': {'displayer': 'obj'}}],
        'component_config': {},
        'extra_grid_config': {},
    }
    bdf = BASIC_DF.copy()
    bdf['Volume_colors'] = 8 # necessary so Volume_ccolors exists as a column and it can be rewritten to c
    actual = StylingAnalysis.get_dfviewer_config(sd, bdf)
    assert expected_output == actual


def test_rewrite_override():
    """
      certain column_config overrides, notably  tooltip and color map will reference original column configs

      They need to point at rewritten col_names

      """

    rewrites: Dict[ColIdentifier, ColIdentifier] =  {
        'Volume_colors': "ccc",
        'foo' : 'ddd'
    }
    color_from_column:PartialColConfig = {
              'color_map_config': {'color_rule': 'color_from_column', 'val_column': 'Volume_colors'}}
    rewritten_color_from_column = {
              'color_map_config': {'color_rule': 'color_from_column', 'val_column': 'ccc'}}
    #color_map_config.val_column
    assert rewrite_override_col_references(rewrites, color_from_column) == rewritten_color_from_column

    color_not_null =  {
        'color_map_config': {'color_rule': 'color_not_null', 'exist_column': 'foo'}}

    rewritten_color_not_null =  {
        'color_map_config': {'color_rule': 'color_not_null', 'exist_column': 'ddd'}}
    assert rewrite_override_col_references(rewrites, color_not_null) == rewritten_color_not_null
    #color_map_config.exist_column

    tooltip_config = {
        'tooltip_config': {'tooltip_type':'simple', 'val_column':'Volume_colors'}}

    rewritten_tooltip_config = {
        'tooltip_config': {'tooltip_type':'simple', 'val_column':'ccc'}}

    assert rewrite_override_col_references(rewrites, tooltip_config) == rewritten_tooltip_config
    no_rewrite_config:PartialColConfig = {
        'displayer_args': {'displayer':'boolean'}}
    assert rewrite_override_col_references(rewrites, no_rewrite_config.copy()) == no_rewrite_config

def test_merge_sd_overrides():
    typed_df = pd.DataFrame({'int_col': [1] * 5})
    
    orig_sd : SDType = {'a': {'foo':10, 'orig_col_name':'int_col', 'rewritten_col_name':'a'}}
    #BECAUSE override_sd int_col only has merge_column_config_overrides in it, nothing else should be merged
    override_sd: SDType = { 'int_col': {
        'column_config_override': {'color_map_config': {'color_rule': 'color_from_column', 'col_name': 'a'}}}}

    merged : SDType = merge_sd_overrides(orig_sd, typed_df, override_sd)

    assert merged['a'] == {'foo':10, 'orig_col_name':'int_col', 'rewritten_col_name':'a', 
        'column_config_override': {'color_map_config': {'color_rule': 'color_from_column', 'col_name': 'a'}}}
    assert len(merged) == 1
    assert 'int_col' not in merged

def test_merge_sd_overrides2():
    """
      make sure extra keys are merged too, back to the rwritten col_name.
      I'm not 100% sure I want to support this.
      """
    typed_df = pd.DataFrame({'int_col': [1] * 5})
    override_sd: SDType = { 'int_col': {
        'extra_key': 9,
        'column_config_override': {'color_map_config': {'color_rule': 'color_from_column', 'col_name': 'a'}}}}

    
    orig_sd : SDType = {'a': {'foo':10, 'orig_col_name':'int_col', 'rewritten_col_name':'a'}}

    merged : SDType = merge_sd_overrides(orig_sd, typed_df, override_sd)

    assert merged['a'] == { 'foo':10,
    'orig_col_name':'int_col', 'rewritten_col_name':'a', 
    'column_config_override': {'color_map_config': {'color_rule': 'color_from_column', 'col_name': 'a'}},
    'extra_key':9}
    assert len(merged) == 1


    
