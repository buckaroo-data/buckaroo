from typing import Dict, List
import pandas as pd
from buckaroo.dataflow.styling_core import ColumnConfig, DFViewerConfig, NormalColumnConfig, PartialColConfig, StylingAnalysis, merge_sd_overrides, rewrite_override_col_references
from buckaroo.customizations.styling import (
    _formatted_char_count,
    estimate_min_width_px,
    _HISTOGRAM_MIN_PX,
    _MIN_COL_PX,
)
from buckaroo.ddd_library import get_basic_df2, get_multiindex_index_df, get_multiindex_index_multiindex_with_names_cols_df, get_multiindex_index_with_names_multiindex_cols_df, get_multiindex_with_names_both, get_multiindex_with_names_index_df, get_multiindex_cols_df, get_multiindex_with_names_cols_df, get_tuple_cols_df
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

    mic_df: pd.DataFrame = get_multiindex_cols_df()
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
            'field':'index', 'displayer_args': {'displayer': 'obj'}}] == StylingAnalysis.get_left_col_configs(get_multiindex_with_names_cols_df())
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


# ── Tests for estimate_min_width_px and _formatted_char_count ────────────────


class TestFormattedCharCount:
    def test_float_small_values(self):
        # max=9, min=0 → 1 int digit, 0 commas, 3 frac digits, decimal, no sign
        disp = {'displayer': 'float', 'max_fraction_digits': 3}
        meta = {'max': 9, 'min': 0}
        assert _formatted_char_count(disp, meta) == 1 + 0 + 1 + 3 + 0  # 5

    def test_float_large_values(self):
        # max=5_700_000_000 → 10 int digits, 3 commas, 2 frac digits, decimal
        disp = {'displayer': 'float', 'max_fraction_digits': 2}
        meta = {'max': 5_700_000_000, 'min': 0}
        assert _formatted_char_count(disp, meta) == 10 + 3 + 1 + 2 + 0  # 16

    def test_float_negative(self):
        # min=-100 → sign char added
        disp = {'displayer': 'float', 'max_fraction_digits': 2}
        meta = {'max': 50, 'min': -100}
        # max_abs = 100 → 3 int digits, 0 commas, decimal, 2 frac, 1 sign
        assert _formatted_char_count(disp, meta) == 3 + 0 + 1 + 2 + 1  # 7

    def test_float_zero_frac(self):
        # max_fraction_digits=0 → no decimal point
        disp = {'displayer': 'float', 'max_fraction_digits': 0}
        meta = {'max': 999, 'min': 0}
        assert _formatted_char_count(disp, meta) == 3 + 0 + 0 + 0 + 0  # 3

    def test_float_nan_guard(self):
        # NaN max → int_digits defaults to 1
        disp = {'displayer': 'float', 'max_fraction_digits': 2}
        meta = {'max': float('nan'), 'min': 0}
        assert _formatted_char_count(disp, meta) == 1 + 0 + 1 + 2 + 0  # 4

    def test_float_none_metadata(self):
        # None values in metadata → treated as 0
        disp = {'displayer': 'float', 'max_fraction_digits': 3}
        meta = {'max': None, 'min': None}
        assert _formatted_char_count(disp, meta) == 1 + 0 + 1 + 3 + 0  # 5

    def test_integer(self):
        disp = {'displayer': 'integer', 'max_digits': 7}
        # 7 digits + 2 commas = 9
        assert _formatted_char_count(disp, {}) == 7 + 2  # 9

    def test_integer_default(self):
        # no max_digits → default 4
        disp = {'displayer': 'integer'}
        assert _formatted_char_count(disp, {}) == 4 + 1  # 5

    def test_compact_number(self):
        disp = {'displayer': 'compact_number'}
        assert _formatted_char_count(disp, {}) == 5

    def test_string(self):
        disp = {'displayer': 'string', 'max_length': 35}
        # capped at 20
        assert _formatted_char_count(disp, {}) == 20

    def test_string_short(self):
        disp = {'displayer': 'string', 'max_length': 10}
        assert _formatted_char_count(disp, {}) == 10

    def test_datetime(self):
        disp = {'displayer': 'datetimeLocaleString'}
        assert _formatted_char_count(disp, {}) == 18

    def test_datetime_default(self):
        disp = {'displayer': 'datetimeDefault'}
        assert _formatted_char_count(disp, {}) == 18

    def test_obj_fallback(self):
        disp = {'displayer': 'obj'}
        assert _formatted_char_count(disp, {}) == 8

    def test_unknown_displayer(self):
        disp = {'displayer': 'something_new'}
        assert _formatted_char_count(disp, {}) == 8


class TestEstimateMinWidthPx:
    def test_data_wider_than_header(self):
        # float with large values, short header "a"
        disp = {'displayer': 'float', 'max_fraction_digits': 3}
        meta = {'max': 999_999, 'min': 0}
        # data: 6 int + 1 comma + 1 decimal + 3 frac = 11 chars → 11*7 + 16 = 93
        # header "a": 1*8 + 14 + 16 = 38
        result = estimate_min_width_px(disp, 'a', meta)
        assert result == 93

    def test_header_wider_than_data(self):
        # short data, long header
        disp = {'displayer': 'integer', 'max_digits': 2}
        meta = {}
        # data: 2 digits + 0 commas = 2 chars → 2*7 + 16 = 30
        # header "customer_lifetime_value": 23 chars → 23*8 + 14 + 16 = 214
        result = estimate_min_width_px(disp, 'customer_lifetime_value', meta)
        assert result == 214

    def test_histogram_enforces_minimum(self):
        # tiny data + short header → would be small, but histogram enforces 100px
        disp = {'displayer': 'integer', 'max_digits': 1}
        meta = {}
        # data: 1*7 + 16 = 23; header "x": 1*8 + 14 + 16 = 38; max = 38
        # but histogram: max(38, 100) = 100
        result = estimate_min_width_px(disp, 'x', meta, has_histogram=True)
        assert result == _HISTOGRAM_MIN_PX

    def test_histogram_doesnt_shrink(self):
        # wide column should not be shrunk by histogram
        disp = {'displayer': 'float', 'max_fraction_digits': 3}
        meta = {'max': 999_999_999, 'min': -999_999_999}
        result_with = estimate_min_width_px(disp, 'a', meta, has_histogram=True)
        result_without = estimate_min_width_px(disp, 'a', meta, has_histogram=False)
        assert result_with >= result_without

    def test_minimum_floor(self):
        # even with nothing, should return _MIN_COL_PX
        disp = {'displayer': 'obj'}
        meta = {}
        result = estimate_min_width_px(disp, '', meta)
        assert result >= _MIN_COL_PX

    def test_none_header(self):
        # None header should not crash
        disp = {'displayer': 'obj'}
        meta = {}
        result = estimate_min_width_px(disp, None, meta)
        assert result >= _MIN_COL_PX

    def test_compact_number_narrow(self):
        # compact_number is always ~5 chars regardless of data magnitude
        disp = {'displayer': 'compact_number'}
        meta = {'max': 5_700_000_000, 'min': 0}
        result = estimate_min_width_px(disp, 'a', meta)
        # data: 5*7 + 16 = 51; header "a": 1*8 + 14 + 16 = 38 → 51
        assert result == 51

    def test_float_vs_compact_savings(self):
        # compact_number should produce a narrower column than float for large values
        meta = {'max': 5_700_000_000, 'min': 0}
        float_disp = {'displayer': 'float', 'max_fraction_digits': 2}
        compact_disp = {'displayer': 'compact_number'}
        float_w = estimate_min_width_px(float_disp, 'a', meta)
        compact_w = estimate_min_width_px(compact_disp, 'a', meta)
        assert compact_w < float_w

