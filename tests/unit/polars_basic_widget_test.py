import polars as pl
from polars import functions as F
import numpy as np
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_produce_series_df)
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis)
from buckaroo.pluggable_analysis_framework.utils import (json_postfix)
from buckaroo.polars_buckaroo import PolarsBuckarooWidget
from buckaroo.dataflow.dataflow import StylingAnalysis

def test_basic_instantiation():
    PolarsBuckarooWidget(
        pl.DataFrame({'a':[1,2,3]}))


EXPECTED_DF_VIEWER_CONFIG = {
    'pinned_rows': [],
    'column_config': [
        {'col_name': 'index', 'displayer_args': {'displayer': 'obj'}},
        {'col_name': 'normal_int_series', 'displayer_args': {'displayer': 'obj'}}],
    'component_config': {},
    'extra_grid_config': {},
}
                             
class SelectOnlyAnalysis(PolarsAnalysis):

    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
        F.all().quantile(.99).name.map(json_postfix('quin99'))]

test_df = pl.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
})



def test_polars_all_stats():
    """
    FIXME temporarily disabled to test other build stuff
    the all_stats verify that PolarsBuckarooWidget produces the
    same summary_stats shape tatha pandas does.

    Since polars doesn't have an index concept, some things are a little different, but the summary_stats display essentiall depends on the index being present and displayed

    """
    
    sdf, errs = polars_produce_series_df(
        test_df, [SelectOnlyAnalysis], 'test_df', debug=True)
    expected = {
        'normal_int_series':  {'mean': 2.5,  'null_count':  0, 'quin99':  4.0}}
    #dsdf = replace_in_dict(sdf, [(np.nan, None)])
    class SimplePolarsBuckaroo(PolarsBuckarooWidget):
        analysis_klasses= [SelectOnlyAnalysis, StylingAnalysis]

    spbw = SimplePolarsBuckaroo(test_df)
    assert spbw.merged_sd == expected

    assert spbw.df_data_dict['all_stats'] == [
        {'index': 'null_count', 'normal_int_series': 0.0},
        {'index': 'mean', 'normal_int_series': 2.5},
        {'index': 'quin99', 'normal_int_series': 4.0}]
    assert spbw.df_display_args['main']['df_viewer_config'] == EXPECTED_DF_VIEWER_CONFIG



def test_pandas_all_stats():
    """

    just make sure this doesn't fail"""
    from buckaroo.buckaroo_widget import BuckarooWidget
    from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (ColAnalysis)
    import pandas as pd

    pd_test_df = pd.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        #'empty_na_ser' : pl.Series([pl.Null] * 4, dtype="Int64"),
        #'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])
    })

    
    class SimpleAnalysis(ColAnalysis):
        provides_defaults = {}
        requires_raw = True
        provides_series_stats = ["distinct_count"]

        @staticmethod
        def series_summary(sampled_ser, raw_ser):
            return dict(
                null_count=0,
                mean=2.5,
                quin99=4.0)

    class SimpleBuckaroo(BuckarooWidget):
        analysis_klasses= [SimpleAnalysis, StylingAnalysis]

    sbw = SimpleBuckaroo(pd_test_df)
    assert sbw.merged_sd == {
        'index': {'mean': 2.5, 'null_count': 0, 'quin99': 4.0},
        'normal_int_series':  {'mean': 2.5,  'null_count':  0, 'quin99':  4.0}}
    assert sbw.df_display_args['main']['df_viewer_config'] == EXPECTED_DF_VIEWER_CONFIG



def test_object_dtype1():
    """
    originally I thought that these errors with objects in polars were caused by just doing something dumb with polars...
    But the first two lines run fine, something happens inside of PolarsBuckarooWidget

    I think the problme is related to type coercion or serialization
    """
    ser = pl.Series([{'a':5}])
    df = pl.DataFrame({'b': ser})
    PolarsBuckarooWidget(df)

def Xtest_object_dtype2():

    ser = pl.Series([{'a':5}], dtype=pl.Object)
    df = pl.DataFrame({'b': ser})
    PolarsBuckarooWidget(df)


    # I eventually wanted to test non regular object like this
    # ser = pl.Series([
    #         {'level_1': {'a':10}}, None], dtype=pl.Object)
    # df = pl.DataFrame({'nested_dicts2': ser})

def test_weird():
# RAW = {
#     'names': ['all_NA', 'half_NA','longtail', 'longtail_unique'],
#     'histo': [
#         [{'name': 'NA', 'NA': 100.0}],
#         [{'name': 1, 'cat_pop': 46.0}, {'name': 'NA', 'NA': 54.0}],
#         [{'name': 'long_30', 'cat_pop': 0.0}, {'name': 'long_15', 'cat_pop': 0.0},
#          {'name': 'long_29', 'cat_pop': 0.0}, {'name': 'long_184', 'cat_pop': 0.0},
#          {'name': 'long_101', 'cat_pop': 0.0}, {'name': 'long_48', 'cat_pop': 0.0},
#          {'name': 'long_123', 'cat_pop': 0.0}, {'name': 'longtail', 'longtail': 77.0},
#          {'name': 'NA', 'NA': 20.0}],
#     [
#          {'name': 'long_120', 'cat_pop': 0.0}, {'name': 'long_41', 'cat_pop': 0.0},
#          {'name': 'long_0', 'cat_pop': 0.0}, {'name': 'long_32', 'cat_pop': 0.0},
#          {'name': 'long_44', 'cat_pop': 0.0}, {'name': 'long_113', 'cat_pop': 0.0},
#          {'name': 'long_22', 'cat_pop': 0.0},
#          {'name': 'longtail', 'unique': 50.0, 'longtail': 47.0}]]}

# pl_histo = pl.DataFrame(RAW)
# pl_histo

#     RAW = ​ {
#      'all_NA':           [{'name': 'NA', 'NA': 100.0}],
#      'half_NA':          [{'name': 1, 'cat_pop': 46.0}, {'name': 'NA', 'NA': 54.0}],
#      'longtail':         [{'name': 'long_30', 'cat_pop': 0.0}, {'name': 'long_15', 'cat_pop': 0.0},
#                           {'name': 'long_29', 'cat_pop': 0.0}, {'name': 'long_184', 'cat_pop': 0.0},
#                           {'name': 'long_101', 'cat_pop': 0.0}, {'name': 'long_48', 'cat_pop': 0.0},
#                           {'name': 'long_123', 'cat_pop': 0.0}, {'name': 'longtail', 'longtail': 77.0},
#                           {'name': 'NA', 'NA': 20.0}],
#      'longtail_unique': [
#          {'name': 'long_120', 'cat_pop': 0.0}, {'name': 'long_41', 'cat_pop': 0.0},
#          {'name': 'long_0', 'cat_pop': 0.0}, {'name': 'long_32', 'cat_pop': 0.0},
#          {'name': 'long_44', 'cat_pop': 0.0}, {'name': 'long_113', 'cat_pop': 0.0},
#          {'name': 'long_22', 'cat_pop': 0.0},
#          {'name': 'longtail', 'unique': 50.0, 'longtail': 47.0}]}

    RAW = {'names': ['all_NA', 'half_NA'],
        'histo': [
            [{'name': 'NA', 'NA': 100.0}],
            [{'name': 1, 'cat_pop': 46.0}, {'name': 'NA', 'NA': 54.0}]]}
    pl_histo = pl.DataFrame(RAW, strict=False)
        
    PolarsBuckarooWidget(pl_histo)

class ValueCountPostProcessing(PolarsAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        result_df = df.select(
            F.all().value_counts().implode().list.gather(pl.arange(0, 10), null_on_oob=True).explode().struct.rename_fields(['val', 'unused_count']).struct.field('val').prefix('val_'),
            F.all().value_counts().implode().list.gather(pl.arange(0, 10), null_on_oob=True).explode().struct.field('count').prefix('count_'))
        return [result_df, {}]
    post_processing_method = "value_counts"
    

class TransposeProcessing(ColAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        return [df.transpose(), {}]
    post_processing_method = "transpose"

class ShowErrorsPostProcessing(PolarsAnalysis):
    provides_defaults = {}
    @classmethod
    def post_process_df(kls, df):
        print("^"*80)
        print(type(df))
        df.select
        result_df = df.select(
            F.all(),
            pl.col('float_col').lt(5).replace(True, "foo").replace(False, None).alias('errored_float'))
        return [result_df, {}]

    post_processing_method = "show_errors"

ROWS = 5
typed_df = pl.DataFrame(
    {'int_col':np.random.randint(1,50, ROWS), 'float_col': np.random.randint(1,30, ROWS)/.7,
     'timestamp':["2020-01-01 01:00Z", "2020-01-01 02:00Z",
                  "2020-02-28 02:00Z", "2020-03-15 02:00Z", None],
     "str_col": ["foobar", "Realllllly long string", "", None, "normal"]})
typed_df = typed_df.with_columns(timestamp=pl.col('timestamp').str.to_datetime() )
column_config_overrides={'float_col': {'color_map_config': {
    'color_rule': 'color_not_null',
    'conditional_color': 'red', 'exist_column': 'errored_float'}}}
    
def test_polars_to_pandas():
    bw = PolarsBuckarooWidget(typed_df)
    bw.add_analysis(ShowErrorsPostProcessing)
    
    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'show_errors'
    bw.buckaroo_state = temp_buckaroo_state

    
'''
FIXME:test a large dataframe that forces sampling
'''
