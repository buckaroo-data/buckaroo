import numpy as np
import pandas as pd
import pytest
from ..fixtures import (DistinctCount)
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
from buckaroo.dataflow import CustomizableDataflow, StylingAnalysis
from buckaroo.buckaroo_widget import BuckarooWidget
         

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
                       {'col_name':'b', 'displayer_args': {'displayer': 'obj'}}]}

def test_widget_instatiation():
    dfc = CustomizableDataflow(BASIC_DF)
    assert dfc.widget_args_tuple[1] is BASIC_DF
    assert dfc.df_data_dict['main'] == BASIC_DF_JSON_DATA
    assert dfc.df_display_args['main']['df_viewer_config'] == DFVIEWER_CONFIG_DEFAULT

def test_custom_dataflow():

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
                       {'col_name':'b', 'displayer_args': {'displayer': 'int'}}]}
    
    assert cdfc.df_display_args['int_styles']['df_viewer_config'] == DFVIEWER_CONFIG_INT



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

    

class TransposeProcessing(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        return [df.T, {}]
    post_processing_method = "transpose"


def test_transpose_error():
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
def test_sample():
    big_df = pd.DataFrame({'a': np.arange(105_000)})
    bw = CustomizableDataflow(big_df)
    assert len(bw.processed_df) == 100_000
    print(list(bw.df_data_dict.keys()))
    assert len(bw.df_data_dict['main']) == 10_000
