from buckaroo.dataflow.dataflow import StylingAnalysis
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.polars_buckaroo import PolarsBuckarooWidget
import polars as pl 
import numpy as np

simple_df = pl.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})
BASIC_DF_JSON_DATA = [{'index':0, 'a':10, 'b':'foo'},
                        {'index':1, 'a':20, 'b':'bar'},
                        {'index':2, 'a':20, 'b':'baz'}]

BASIC_DF = pl.DataFrame({'a': [10, 20, 20], 'b':['foo', 'bar', 'baz']})


DFVIEWER_CONFIG_DEFAULT = {
                   'pinned_rows': [],
                   'column_config':  [
                       {'col_name':'index', 'displayer_args': {'displayer': 'obj'}},
                       {'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
                       {'col_name':'b', 'displayer_args': {'displayer': 'obj'}}]}


class BasicStyling(StylingAnalysis):
    provides_defaults = {}
    df_display_name = "basic"
    

def test_widget_instatiation():
    dfc = PolarsBuckarooWidget(BASIC_DF)
    #the BasicStyling is simple and predictable, it writes to 'basic' which nothing else should
    dfc.add_analysis(BasicStyling)

    assert dfc.widget_args_tuple[1] is BASIC_DF
    assert dfc.df_data_dict['main'] == BASIC_DF_JSON_DATA

    actual_column_config = dfc.df_display_args['basic']['df_viewer_config']['column_config']
    expected_column_config = DFVIEWER_CONFIG_DEFAULT['column_config']

    #this test is brittle because styling is rapidly changing in development
    assert actual_column_config == expected_column_config 

def test_custom_dataflow():
    """Tests that a styling method can be added BuckarooWidget and
    that it properly modifies column_config. This Styling analysis
    should be identical between polars and pandas

    """
    class IntStyling(StylingAnalysis):
        @staticmethod
        def style_column(col, sd):
            return {'col_name':col, 'displayer_args': {'displayer': 'int'}}

        df_display_name = "int_styles"
        data_key = "main"
        summary_stats_key= '555555555'


    class TwoStyleDFC(PolarsBuckarooWidget):
        analysis_klasses = [StylingAnalysis, IntStyling]
        #analysis_klasses = [IntStyling]
        
    cdfc = TwoStyleDFC(BASIC_DF)
    assert cdfc.widget_args_tuple[1] is BASIC_DF
    assert cdfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT
    DFVIEWER_CONFIG_INT = {
                   'pinned_rows': [],
                   'column_config':  [
                       {'col_name':'index', 'displayer_args': {'displayer': 'obj'}},
                       {'col_name':'a', 'displayer_args': {'displayer': 'int'}},
                       {'col_name':'b', 'displayer_args': {'displayer': 'int'}}]}
    
    assert cdfc.df_display_args['int_styles']['df_viewer_config'] == DFVIEWER_CONFIG_INT


SENTINEL_DF = pl.DataFrame({'sent_int_col':[11, 22, 33], 'sent_str_col':['ka', 'b', 'c']})


class PostProcessingAnalysis(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "post1"

    @classmethod
    def post_process_df(kls, cleaned_df):
        return [SENTINEL_DF, {'sent_int_col': {'sentinel_prop':5}}]


def test_custom_post_processing():
    """This test demonstrates that a post processing method can be
    added to BuckarooWidget through an analysis class. It further
    checks that BuckarooWidget responds to changes in buckaroo_state
    that activate the actual post_processing function

    """
    class PostDCFC(PolarsBuckarooWidget):
        analysis_klasses = [PostProcessingAnalysis, StylingAnalysis]

    p_dfc = PostDCFC(BASIC_DF)

    assert p_dfc.buckaroo_options['post_processing'] == ['', 'post1']
    assert p_dfc.buckaroo_state['post_processing'] == ''

    temp_buckaroo_state = p_dfc.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'post1'
    p_dfc.buckaroo_state = temp_buckaroo_state

    assert p_dfc.processed_df is SENTINEL_DF


class TransposeProcessing(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        return [df.transpose(), {}]
    post_processing_method = "transpose"


def test_transpose_error():
    ROWS = 5
    typed_df = pl.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})

    base_a_klasses = PolarsBuckarooWidget.analysis_klasses.copy()
    base_a_klasses.extend([TransposeProcessing])

    class VCBuckarooWidget(PolarsBuckarooWidget):
        analysis_klasses = base_a_klasses

    vcb = VCBuckarooWidget(typed_df, debug=False)
    assert type(vcb.processed_df) == pl.DataFrame
    assert vcb.processed_df.to_numpy().tolist() ==[
        [1, 0.5, 'foobar'],
        [1, 0.5, 'foobar'],
        [1, 0.5, 'foobar'],
        [1, 0.5, 'foobar'],
        [1, 0.5, 'foobar']]

    temp_buckaroo_state = vcb.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'transpose'
    vcb.buckaroo_state = temp_buckaroo_state
    assert type(vcb.processed_df) == pl.DataFrame
    #note that Polars doesn'transpose to objects, but to strings instead
    assert vcb.processed_df.to_numpy().tolist() == [
        ['1', '1', '1', '1', '1'],
        ['0.5', '0.5', '0.5', '0.5', '0.5'],
        ['foobar', 'foobar', 'foobar', 'foobar', 'foobar']]


class AlwaysErrorPostProcessing(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        1/0
    post_processing_method = "always_error"

def test_always_error_post_processing():
    ROWS = 5
    typed_df = pl.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})
    bw = PolarsBuckarooWidget(typed_df, debug=False)

    bw.add_analysis(AlwaysErrorPostProcessing)

    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'always_error'
    bw.buckaroo_state = temp_buckaroo_state
    
    print(bw.processed_df.to_numpy().tolist())
    assert bw.processed_df.to_numpy().tolist() ==  [['division by zero']]

ROWS = 5
typed_df = pl.DataFrame(
    {'int_col': [1] * ROWS,
     'float_col': [.5] * ROWS,
     "str_col": ["foobar"]* ROWS})

EXPECTED_OVERRIDE = {'color_map_config': {'color_rule': 'color_from_column', 'col_name': 'Volume_colors'}}
class ColumnConfigOverride(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        return [df, {
            'int_col':{
	        'column_config_override': EXPECTED_OVERRIDE}}]
    post_processing_method = "override"

def test_column_config_override():

    bw = PolarsBuckarooWidget(typed_df, debug=False)

    bw.add_analysis(ColumnConfigOverride)

    assert 'column_config_override' not in bw.merged_sd['int_col']
    cc_initial = bw.df_display_args['main']['df_viewer_config']['column_config']
    int_cc_initial = cc_initial[1]
    assert int_cc_initial['col_name'] == 'int_col' #make sure we found the right row
    assert 'color_map_config' not in int_cc_initial
    
    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'override'
    bw.buckaroo_state = temp_buckaroo_state
    
    assert bw.merged_sd['int_col']['column_config_override'] == EXPECTED_OVERRIDE
    cc_after = bw.df_display_args['main']['df_viewer_config']['column_config']
    int_cc_after = cc_after[1]
    assert int_cc_after['col_name'] == 'int_col' #make sure we found the right row
    assert int_cc_after['color_map_config'] == EXPECTED_OVERRIDE['color_map_config']

def test_sample():
    big_df = pl.DataFrame({'a': np.arange(30_000)})
    bw = PolarsBuckarooWidget(big_df)
    assert len(bw.processed_df) == len(big_df)
    assert len(bw.df_data_dict['main']) == 10_000
