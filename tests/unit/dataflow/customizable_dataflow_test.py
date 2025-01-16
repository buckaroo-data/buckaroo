import numpy as np
import pandas as pd
import pytest
from ..fixtures import (DistinctCount)
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.dataflow.dataflow import CustomizableDataflow, StylingAnalysis
from buckaroo.buckaroo_widget import BuckarooWidget
from buckaroo.customizations.pd_autoclean_conf import (NoCleaningConf)         
from buckaroo.jlisp.lisp_utils import (s, qc_sym)

EMPTY_DF_JSON = {
            'dfviewer_config': {
                'pinned_rows': [],
                'column_config': []},
            'data': []}

BASIC_DF = pd.DataFrame({'a': [10, 20, 20], 'b':['foo', 'bar', 'baz']})
BASIC_DF_JSON_DATA = [{'index':0, 'a':10, 'b':'foo'},
                        {'index':1, 'a':20, 'b':'bar'},
                        {'index':2, 'a':20, 'b':'baz'}]
DFVIEWER_CONFIG_DEFAULT = {
                   'pinned_rows': [],
                   'column_config':  [
                       {'col_name':'index', 'displayer_args': {'displayer': 'obj'}},
                       {'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
                       {'col_name':'b', 'displayer_args': {'displayer': 'obj'}}],
                    'component_config': {},
                    'extra_grid_config': {},
}
DFVIEWER_CONFIG_WITHOUT_B = {
    'pinned_rows': [],
    'column_config':  [
        {'col_name':'index', 'displayer_args': {'displayer': 'obj'}},
        ## note that col_name:'b' isn't present because of the merge rule
        {'col_name':'a', 'displayer_args': {'displayer': 'obj'}},
    ],
    'component_config': {},
    'extra_grid_config': {},
}


def test_widget_instatiation():
    dfc = CustomizableDataflow(BASIC_DF)
    assert dfc.widget_args_tuple[1] is BASIC_DF
    assert dfc.df_data_dict['main'] == BASIC_DF_JSON_DATA
    assert dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT

def test_custom_dataflow():
    """
    verifies that that both StylingAnalysis are called and that we get a
    df_display key of 'int_styles' and 'main'
    """
    class IntStyling(StylingAnalysis):
        provides_defaults = {}
        @staticmethod
        def style_column(col, sd):
            return {'col_name':col, 'displayer_args': {'displayer': 'int'}}

        df_display_name = "int_styles"
        data_key = "main"
        summary_stats_key= '555555555'


    class TwoStyleDFC(CustomizableDataflow):
        analysis_klasses = [StylingAnalysis, IntStyling]
        #analysis_klasses = [IntStyling]
        
    cdfc = TwoStyleDFC(BASIC_DF)
    assert cdfc.widget_args_tuple[1] is BASIC_DF
    assert cdfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT
    DFVIEWER_CONFIG_INT = {
                   'pinned_rows': [],
                   'column_config':  [
                       {'col_name':'index', 'displayer_args': {'displayer': 'int'}},
                       {'col_name':'a', 'displayer_args': {'displayer': 'int'}},
                       {'col_name':'b', 'displayer_args': {'displayer': 'int'}}],
                    'component_config': {},
                    'extra_grid_config': {},
    }
    
    assert cdfc.df_display_args['int_styles']['df_viewer_config'] == DFVIEWER_CONFIG_INT

def test_hide_column_config_overrides():
    """
    verifies that column_config_overrides works properly and column b doesn't end up in column_config
    """
    cdfc = CustomizableDataflow(BASIC_DF)
    assert cdfc.widget_args_tuple[1] is BASIC_DF
    assert cdfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT

    cdfc2 = CustomizableDataflow(BASIC_DF,
                      column_config_overrides={'b': {'merge_rule': 'hidden'}}
                      )

    assert cdfc2.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_WITHOUT_B


def test_custom_summary_stats():
    class DCDFC(CustomizableDataflow):
        analysis_klasses = [DistinctCount, StylingAnalysis]

    dc_dfc = DCDFC(BASIC_DF)

    summary_sd = dc_dfc.widget_args_tuple[2]
    print(summary_sd)
    print("^"*80)
    assert summary_sd == {'index': {'distinct_count': 3}, 
                          'a': {'distinct_count':2}, 'b': {'distinct_count':3}}
    assert list(summary_sd.keys()) == ['index', 'a', 'b']

def test_init_sd():
    class DCDFC(CustomizableDataflow):
        analysis_klasses = [DistinctCount, StylingAnalysis]

    dc_dfc = DCDFC(BASIC_DF, init_sd={'a':{'foo':8}})

    summary_sd = dc_dfc.widget_args_tuple[2]
    print(summary_sd)
    print("^"*80)
    assert dc_dfc.merged_sd == {
        'index': {'distinct_count': 3}, 
        'a': {'distinct_count':2, 'foo':8}, 'b': {'distinct_count':3}}

class AlwaysFailStyling(StylingAnalysis):
    requires_summary = []

    @classmethod
    def style_column(kls, col, column_metadata):
        1/0


def test_always_fail_styling():
    """ styling should default to obj displayer if an error is thrown
    """
    class DCDFC(CustomizableDataflow):
        analysis_klasses = [AlwaysFailStyling]
        pass

    dc_dfc = DCDFC(BASIC_DF) #, init_sd={'a':{'foo':8}})

    summary_sd = dc_dfc.widget_args_tuple[2]
    print(summary_sd)
    print("^"*80)



SENTINEL_DF = pd.DataFrame({'sent_int_col':[11, 22, 33], 'sent_str_col':['ka', 'b', 'c']})


class PostProcessingAnalysis(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "post1"

    @classmethod
    def post_process_df(kls, cleaned_df):
        return [SENTINEL_DF, {'sent_int_col': {'sentinel_prop':5}}]


def test_custom_post_processing():
    class PostDCFC(CustomizableDataflow):
        analysis_klasses = [PostProcessingAnalysis, StylingAnalysis]

    p_dfc = PostDCFC(BASIC_DF)

    assert p_dfc.buckaroo_options['post_processing'] == ['', 'post1']
    assert p_dfc.post_processing_method == ''
    p_dfc.post_processing_method = 'post1'

    assert p_dfc.processed_df is SENTINEL_DF


class HidePostProcessingAnalysis(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "hide_post"

    @classmethod
    def post_process_df(kls, cleaned_df):
        return [SENTINEL_DF, {'sent_int_col': {'merge_rule': 'hidden'}}]

SENTINEL_CONFIG_WITHOUT_INT = {
    'pinned_rows': [],
    'column_config':  [
        {'col_name':'index', 'displayer_args': {'displayer': 'obj'}},
        {'col_name':'sent_str_col', 'displayer_args': {'displayer': 'obj'}},
    ],
    'component_config': {},
    'extra_grid_config': {},
}


def test_hide_column_config_post_processing():
    """
    verifies that a PostProcessing function can hide columns 
    """
    class PostDCFC(CustomizableDataflow):
        analysis_klasses = [HidePostProcessingAnalysis, StylingAnalysis]

    p_dfc = PostDCFC(BASIC_DF)
    assert p_dfc.post_processing_method == ''
    assert p_dfc.processed_df is BASIC_DF
    assert p_dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT
    assert p_dfc.cleaned_sd == {}
    p_dfc.post_processing_method = 'hide_post'
    assert p_dfc.processed_df is SENTINEL_DF
    assert p_dfc.df_display_args['main']['df_viewer_config'] == SENTINEL_CONFIG_WITHOUT_INT
    """ Make sure we can switch post_processing back to unset and everything works """
    p_dfc.post_processing_method = ''
    assert p_dfc.processed_df is BASIC_DF
    assert p_dfc.cleaned_sd == {}
    assert p_dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT


class HidePostProcessingAnalysis2(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "hide_post"

    @classmethod
    def post_process_df(kls, cleaned_df):
        return [cleaned_df, {'b': {'merge_rule': 'hidden'}}]


def test_hide_column_config_post_processing2():
    """
    This only works because we add an unknown column c, then remove it.
    returning cleaned_df and dropping 'b' doesn't work
    """
    class PostDCFC(CustomizableDataflow):
        analysis_klasses = [HidePostProcessingAnalysis2, StylingAnalysis]

    p_dfc = PostDCFC(BASIC_DF)
    assert p_dfc.post_processing_method == ''
    assert p_dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT
    p_dfc.post_processing_method = 'hide_post'
    assert p_dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_WITHOUT_B


class AlwaysFailAnalysis(ColAnalysis):
    provides_defaults = {}

    @staticmethod
    def computed_summary(foo):
        1/0
def test_error_analysis():
    class ErrorCustomDataflow(CustomizableDataflow):
        analysis_klasses = [AlwaysFailAnalysis]

    ErrorCustomDataflow(BASIC_DF)
    #basically asserting that it doesn't throw an error
    with pytest.raises(Exception):
        ErrorCustomDataflow(BASIC_DF, debug=True)

class AlwaysFailPostProcessingAnalysis(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "always_fail"

    @classmethod
    def post_process_df(kls, cleaned_df):
        1/0


def test_error_post_processing():
    class ErrorCFC(CustomizableDataflow):
        analysis_klasses = [AlwaysFailPostProcessingAnalysis, StylingAnalysis]

    e_dfc = ErrorCFC(BASIC_DF)

    assert e_dfc.buckaroo_options['post_processing'] == ['', 'always_fail']
    e_dfc.post_processing_method = 'always_fail'
    assert e_dfc.processed_df.values == [["division by zero"]]

def test_column_config_override_widget():
    ROWS = 200
    typed_df = pd.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})
    bw2 = BuckarooWidget(
        typed_df, 
        column_config_overrides={
            'float_col':
            {'displayer_args': { 'displayer': 'integer', 'min_digits': 3, 'max_digits': 5 }}})
    float_col_config = bw2.df_display_args['main']['df_viewer_config']['column_config'][2]
    assert float_col_config == {'col_name': 'float_col', 'displayer_args': { 'displayer': 'integer', 'min_digits': 3, 'max_digits': 5 }}
    


def test_pinned_rows_override_widget():
    ROWS = 200
    typed_df = pd.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})
    HIST_ROW = {'primary_key_val': 'histogram', 'displayer_args': { 'displayer': 'histogram' }}
    bw2 = BuckarooWidget(typed_df, pinned_rows=[HIST_ROW])
    pinned_rows = bw2.df_display_args['main']['df_viewer_config']['pinned_rows']
    assert pinned_rows[0] == HIST_ROW

def test_stock_flow():
    ROWS = 5
    typed_df = pd.DataFrame({'int_col': [1] * ROWS})
    bw = BuckarooWidget(typed_df)
    #cleaning should be off by default. no columns should be changed
    #and the values shouldn't be changed
    assert bw.processed_df.columns.tolist() == typed_df.columns.tolist()
    assert bw.processed_df.values.tolist() == typed_df.values.tolist()
    

class TransposeProcessing(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        print("post_process_df TransposeProcessing")
        return [df.T, {}]
    post_processing_method = "transpose"


def test_transpose_error():
    """Swaps in a different post processing method at runtime to show the
    values are changed.

    """
    ROWS = 5
    typed_df = pd.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})

    base_a_klasses = BuckarooWidget.analysis_klasses.copy()
    base_a_klasses.extend([TransposeProcessing])

    class VCBuckarooWidget(BuckarooWidget):
        analysis_klasses = base_a_klasses

    vcb = VCBuckarooWidget(typed_df, debug=False)
    temp_buckaroo_state = vcb.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'transpose'
    vcb.buckaroo_state = temp_buckaroo_state
    assert vcb.processed_df.values.tolist() == [
        [1, 1, 1, 1, 1],
        [0.5, 0.5, 0.5, 0.5, 0.5],
        ['foobar', 'foobar', 'foobar', 'foobar', 'foobar']]


def test_bstate_commands():
    """
    Makes sure that when bstate is editted, the correct commands get added

    """
    ROWS = 5
    typed_df = pd.DataFrame(
        {'int_col': [1] * ROWS,
         'float_col': [.5] * ROWS,
         "str_col": ["foobar"]* ROWS})

    base_a_klasses = BuckarooWidget.analysis_klasses.copy()
    base_a_klasses.extend([TransposeProcessing])

    bw = BuckarooWidget(typed_df)
    assert bw.buckaroo_state['cleaning_method'] == 'NoCleaning'
    assert bw.cleaning_method == 'NoCleaning'
    class VCBuckarooWidget(BuckarooWidget):
        #analysis_klasses = base_a_klasses
        autoclean_conf = tuple([NoCleaningConf]) 

    vcb = VCBuckarooWidget(typed_df, debug=False)
    temp_buckaroo_state = vcb.buckaroo_state.copy()
    temp_buckaroo_state['quick_command_args'] = {'search': ['needle']}
    vcb.buckaroo_state = temp_buckaroo_state

    #probably something in autocleaning config should be responsible for generating these commands
    assert vcb.merged_operations == [
        [qc_sym('search'), s('df'), "col", "needle"]]


    """
    add an additional test that accounts for arbitrary, configurable status bar command args

    dataflow should just be responsible for parsing back the frontend datastructure.

    There should be another part where the frontend presents a command structure to the status bar.
    

    """

    
def test_sample():
    big_df = pd.DataFrame({'a': np.arange(105_000)})
    bw = CustomizableDataflow(big_df)
    assert len(bw.processed_df) == 100_000
    print(list(bw.df_data_dict.keys()))
    assert len(bw.df_data_dict['main']) == 5_000


