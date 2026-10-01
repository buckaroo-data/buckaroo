import sys
import numpy as np
import pandas as pd
import pytest
from buckaroo.dataflow.dataflow import DataFlow
from buckaroo.df_util import to_chars
from buckaroo.dataflow import dataflow as dft
from buckaroo.dataflow.autocleaning import SENTINEL_DF_1, SENTINEL_DF_2

simple_df = pd.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})


def test_dataflow_operating_df():
    d_flow = DataFlow(simple_df)
    d_flow.raw_df = simple_df

    pd.testing.assert_frame_equal(d_flow.sampled_df, simple_df)
    d_flow.sample_method = "first"
    assert len(d_flow.sampled_df) == 1
    d_flow.sample_method = "default"
    pd.testing.assert_frame_equal(d_flow.sampled_df, simple_df)

    
def Xtest_dataflow_cleaned():
    d_flow = DataFlow(simple_df)
    print("d_flow.cleaned_df")
    print(d_flow.cleaned_df)
    print("simple_df")
    print(simple_df)
    pd.testing.assert_frame_equal(d_flow.cleaned_df, simple_df)

    d_flow.operations = ["one"]
    pd.testing.assert_frame_equal(d_flow.cleaned_df, SENTINEL_DF_1)
    d_flow.cleaning_method = "one op"
    pd.testing.assert_frame_equal(d_flow.cleaned_df, SENTINEL_DF_2)

def Xtest_dataflow_processed():

    d_flow = DataFlow(simple_df)
    pd.testing.assert_frame_equal(d_flow.sampled_df, simple_df)
    #processed is currently a no-op, so I'm skipping actual tests for now

def Xtest_summary_sd():
    d_flow = DataFlow(simple_df)
    assert d_flow.summary_sd == {'index': {}, 'int_col': {}, 'str_col': {}}
    d_flow.analysis_klasses = "foo"
    d_flow.cleaning_method = "one op"
    assert d_flow.summary_sd == {'some-col': {'foo':8}}

def Xtest_merged_sd():
    d_flow = DataFlow(simple_df)
    assert d_flow.merged_sd == {'index': {}, 'int_col': {}, 'str_col': {}}
    d_flow.analysis_klasses = "foo"
    d_flow.cleaning_method = "one op"
    assert d_flow.summary_sd == {'some-col': {'foo':8}}
    assert d_flow.merged_sd == {'some-col': {'foo':8}}


def Xtest_column_config():
    basic_df = pd.DataFrame({'a': [10, 20, 30], 'b':['foo', 'bar', 'baz']})
    d_flow = DataFlow(basic_df)
    _unused, df, merged_sd = d_flow.widget_args_tuple

    #dfviewer_config = d_flow.df_display_args['main']
    assert merged_sd == {'index' : {}, 'a': {}, 'b': {}}
    
def test_merge_sds():
    """
    verifies that summary_dicts are merged together properly
    """
    sd_base = {
        'Volume' : {
            'a':10,
	    'column_config_override': {
                'color_map_config' : {'color_rule': 'color_from_column',
	                              'col_name': 'Volume_colors'}}},
        'Volume_colors' : {
            'a': 30,
	    'column_config_override': { 'displayer': 'hidden'}},
        'only_in_base': {'f':77}}

    sd_second = {
        'Volume' : {
            'a': 999,
            'b': "foo",
	    'column_config_override': {
                'tooltip_config': {'tooltip_type' : 'summary_series'}}},
        'Volume_colors' : {
            'd':111,
	    'column_config_override': { 'displayer': 'string'}},
        'completely_new_column': {'k':90}}

    expected = {
        'Volume' : {
            'a': 999,
            'b': "foo",
	    'column_config_override': {
                'color_map_config' : {'color_rule': 'color_from_column',
	                              'col_name': 'Volume_colors'},
                #note that column_config_override is merged, not just overwritten
                'tooltip_config': {'tooltip_type' : 'summary_series'}}},
        'Volume_colors' : {
            'a': 30,
            'd': 111,
            #sd_second has a different value for 'displayer then sd_base
	    'column_config_override': { 'displayer': 'string'}},
        #only in base, needs to be present
        'only_in_base': {'f':77},
        #only found in second should show up here
        'completely_new_column': {'k':90}}

    result = dft.merge_sds(sd_base, sd_second)
    
    assert result == expected
    

def test_merge_column_config():
    overrides = {
        'bar' : {'displayer_args':  {'displayer': 'int'}},
        'foo' : {'color_map_config' : {'color_rule': 'color_from_column',
	                               'col_name': 'Volume_colors'}}}

    computed_column_config =     [
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'bar', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}}]
    temp_df=pd.DataFrame({'foo':[], 'bar':[], 'volume_colors':[]})
    merged = dft.merge_column_config(computed_column_config, temp_df, overrides)

    expected = [
            {'header_name':'foo', 'col_name': 'a', 'displayer_args': {'displayer': 'obj'},
             'color_map_config' : {'color_rule': 'color_from_column',
	                               'col_name': 'Volume_colors'}},
            {'header_name':'bar', 'col_name': 'b', 'displayer_args': {'displayer': 'int'}}]
    assert expected == merged
        

def test_merge_column_config_hide():
    overrides = {
        'bar' : {'merge_rule':'hidden'}}
    computed_column_config =     [
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'bar', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}}]
    temp_df=pd.DataFrame({'foo':[], 'bar':[], 'volume_colors':[]})
    merged = dft.merge_column_config(
        computed_column_config, temp_df, overrides)

    expected = [
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}}]

    assert expected == merged


def test_merge_column_config_follows_df_order():
    """Display order is the df's column order, not the order the sd layers named the columns in (#988)"""
    computed_column_config = [
            {'header_name':'s1', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'s2', 'col_name':'d', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'n1', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'n2', 'col_name':'c', 'displayer_args': {'displayer': 'obj'}}]
    temp_df=pd.DataFrame({'n1':[], 's1':[], 'n2':[], 's2':[]})
    merged = dft.merge_column_config(computed_column_config, temp_df, {})
    assert [c['col_name'] for c in merged] == ['a', 'b', 'c', 'd']


def test_merge_column_config_follows_df_order_multiindex():
    """multi-index column configs carry the rewritten name in field, not col_name"""
    mi_df = pd.DataFrame([[1, 2, 3]], columns=pd.MultiIndex.from_tuples([('foo', 'a'), ('foo', 'b'), ('bar', 'a')]))
    computed_column_config = [
            {'col_path':('bar', 'a'), 'field':'c', 'displayer_args': {'displayer': 'obj'}},
            {'col_path':('foo', 'a'), 'field':'a', 'displayer_args': {'displayer': 'obj'}},
            {'col_path':('foo', 'b'), 'field':'b', 'displayer_args': {'displayer': 'obj'}}]
    merged = dft.merge_column_config(computed_column_config, mi_df, {})
    assert [c['field'] for c in merged] == ['a', 'b', 'c']


def test_merge_column_config_unknown_cols_last():
    """A config whose col_name isn't one of the df's columns goes after the df's columns"""
    computed_column_config = [
            {'header_name':'stale', 'col_name':'z', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'bar', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}}]
    temp_df=pd.DataFrame({'foo':[], 'bar':[]})
    merged = dft.merge_column_config(computed_column_config, temp_df, {})
    assert [c['col_name'] for c in merged] == ['a', 'b', 'z']


ORDERING_KEYS = {'absolute_order', 'prefer_order', 'order_group'}
FIVE_COLS = ['foo', 'bar', 'baz', 'boof', 'bop']


def ordered_configs(cols, overrides):
    """the column configs merge_column_config produces for a df with columns `cols`"""
    temp_df = pd.DataFrame({c: [] for c in cols})
    computed_column_config = [{'header_name': c, 'col_name': to_chars(i), 'displayer_args': {'displayer': 'obj'}}
        for i, c in enumerate(cols)]
    return dft.merge_column_config(computed_column_config, temp_df, overrides)


def ordered_headers(cols, overrides):
    return [cc['header_name'] for cc in ordered_configs(cols, overrides)]


def test_absolute_order():
    """the column is taken out of its place and put at that 0-based position (#990)"""
    assert ordered_headers(FIVE_COLS, {'baz': {'absolute_order': 0}}) == ['baz', 'foo', 'bar', 'boof', 'bop']
    assert ordered_headers(FIVE_COLS, {'foo': {'absolute_order': 3}}) == ['bar', 'baz', 'boof', 'foo', 'bop']
    # absolutes go in ascending index order, so each lands at its own index
    assert ordered_headers(FIVE_COLS, {'bop': {'absolute_order': 2}, 'baz': {'absolute_order': 0}}) == \
        ['baz', 'foo', 'bop', 'bar', 'boof']
    # positions computed with numpy are fine
    assert ordered_headers(FIVE_COLS, {'baz': {'absolute_order': np.int64(0)}}) == ['baz', 'foo', 'bar', 'boof', 'bop']


def test_absolute_order_past_the_end():
    assert ordered_headers(FIVE_COLS, {'foo': {'absolute_order': 99}}) == ['bar', 'baz', 'boof', 'bop', 'foo']


def test_prefer_order():
    assert ordered_headers(FIVE_COLS, {'boof': {'prefer_order': 'first'}, 'bar': {'prefer_order': 'last'}}) == \
        ['boof', 'foo', 'baz', 'bop', 'bar']


def test_order_group():
    """numbered groups come first in group order, ungrouped columns after all of them"""
    assert ordered_headers(['name', 'id', 'ts', 'val'], {'id': {'order_group': 0}, 'ts': {'order_group': 1}}) == \
        ['id', 'ts', 'name', 'val']
    # gaps between group numbers are fine
    assert ordered_headers(['name', 'id', 'ts', 'val'], {'id': {'order_group': 5}, 'ts': {'order_group': 20}}) == \
        ['id', 'ts', 'name', 'val']


def test_prefer_order_is_within_the_group():
    """a 'first' column with no group goes to the front of the ungrouped columns, not ahead of group 0"""
    assert ordered_headers(['name', 'id', 'ts', 'note'],
        {'id': {'order_group': 0}, 'note': {'prefer_order': 'first'}}) == ['id', 'note', 'name', 'ts']


def test_absolute_order_beats_groups():
    assert ordered_headers(['name', 'id', 'ts'], {'id': {'order_group': 0}, 'ts': {'absolute_order': 0}}) == \
        ['ts', 'id', 'name']


def test_hidden_columns_take_no_position():
    assert ordered_headers(['a1', 'b1', 'c1', 'd1'], {'b1': {'merge_rule': 'hidden'}, 'd1': {'absolute_order': 1}}) == \
        ['a1', 'd1', 'c1']


def test_none_unsets_an_ordering_key():
    """a later layer clears an earlier layer's value with None"""
    temp_df = pd.DataFrame({'foo': [], 'bar': []})
    computed_column_config = [
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'bar', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}, 'absolute_order': 0}]
    merged = dft.merge_column_config(computed_column_config, temp_df, {'bar': {'absolute_order': None}})
    assert merged == [
            {'header_name':'foo', 'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
            {'header_name':'bar', 'col_name':'b', 'displayer_args': {'displayer': 'obj'}}]


def test_ordering_keys_are_stripped():
    """the ordering pass consumes the keys, the frontend never sees them"""
    merged = ordered_configs(FIVE_COLS, {'baz': {'absolute_order': 0, 'prefer_order': 'last', 'order_group': 2},
        'foo': {'absolute_order': None}})
    assert [cc for cc in merged if ORDERING_KEYS & set(cc)] == []


def test_duplicate_absolute_order_raises():
    with pytest.raises(ValueError, match='absolute_order') as exc_info:
        ordered_headers(FIVE_COLS, {'baz': {'absolute_order': 0}, 'bop': {'absolute_order': 0}})
    assert "'baz'" in str(exc_info.value) and "'bop'" in str(exc_info.value)


@pytest.mark.parametrize("key, val", [
    ('absolute_order', -1), ('absolute_order', True), ('absolute_order', 1.0), ('absolute_order', '1'),
    ('order_group', -1), ('order_group', False), ('order_group', 0.5),
    ('prefer_order', 'frist'), ('prefer_order', 0)])
def test_bad_ordering_values_raise(key, val):
    with pytest.raises(ValueError, match=key) as exc_info:
        ordered_headers(FIVE_COLS, {'baz': {key: val}})
    assert "'baz'" in str(exc_info.value)



class ExpectedFail(Exception):
    pass


    
def tb_depth(tb, depth=1):
    """
    returns the depth of a traceback
    """
    if tb.tb_next is None:
        return depth
    else:
        return tb_depth(tb.tb_next, depth+1)

def exc_depth(exc):
    """
    returns the depth of an exception
    """
    return tb_depth(exc.__traceback__)



def test_exc_depth():
    def level_3():
        1/0
    def level_2():
        level_3()
    def level_1():
        level_2()
    try:
        level_1()
    except Exception:
        l1_exc = sys.exc_info()[1]
    assert tb_depth(l1_exc.__traceback__) == 4

    try:
        level_2()
    except Exception:
        l2_exc = sys.exc_info()[1]
    assert tb_depth(l2_exc.__traceback__) == 3


class SampleFailDataFlow(DataFlow):
    def _compute_sampled_df(self, raw_df, sample_method):
        raise ExpectedFail("_compute_sampled_df")
    
def Xtest_error_handling():
    """

    when something fails in DataFlow, we get stack traces of traitlets.change
    there should be shorter stacktraces, the errors should be written to "data_flow_errors"

    I get 300 line stacktraces, aint nobody got time for that
    https://pymotw.com/3/traceback/
    """
    try:
        SampleFailDataFlow(simple_df)
    except Exception:
        sf_exc = sys.exc_info()[1] #eption()
    print(exc_depth(sf_exc))

    assert exc_depth(sf_exc) < 7
