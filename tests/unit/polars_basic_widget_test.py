import os
import polars as pl
from polars import functions as F
import numpy as np
from typing import Any, TypedDict
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.pluggable_analysis_framework.stat_func import stat, RawSeries

from buckaroo.polars_buckaroo import PolarsBuckarooWidget, PolarsBuckarooInfiniteWidget, to_parquet
from buckaroo.dataflow.dataflow import StylingAnalysis
from buckaroo.styling_helpers import inherit_
from buckaroo.serialization_utils import resolve_summary_stats_payload as _resolve_all_stats
from buckaroo.jlisp.lisp_utils import (s, sQ)

def test_basic_instantiation():
    PolarsBuckarooWidget(
        pl.DataFrame({'a':[1,2,3]}))


EXPECTED_DF_VIEWER_CONFIG = {
    'pinned_rows': [],
    'column_config': [
        {'col_name':'a', 'header_name': 'normal_int_series', 'displayer_args': {'displayer': 'obj'}}],
    'left_col_configs': [{'col_name': 'index', 'header_name': 'index',
                         'displayer_args': {'displayer': 'obj'}}],
    'component_config': {},
    'extra_grid_config': {},
}
                             
SelectOnlyResult = TypedDict('SelectOnlyResult', {'null_count': int, 'mean': Any, 'quin99': Any})


@stat()
def select_only(ser: RawSeries) -> SelectOnlyResult:
    """A small custom @stat analysis (replaces the v1 select_clauses SelectOnlyAnalysis)."""
    return {'null_count': int(ser.null_count()), 'mean': ser.mean(), 'quin99': ser.quantile(0.99)}



# Pin the stats SelectOnlyAnalysis produces so they survive the #880 wire
# projection (which trims all_stats to the displayed/pinned keys).
SELECT_ONLY_PINNED = [inherit_('null_count'), inherit_('mean'), inherit_('quin99')]


class SelectOnlyStyling(StylingAnalysis):
    pinned_rows = SELECT_ONLY_PINNED

test_df = pl.DataFrame({'normal_int_series' : pl.Series([1,2,3,4])})


def test_polars_all_stats():
    """
    the all_stats verify that PolarsBuckarooWidget produces the
    same summary_stats shape tatha pandas does.

    Since polars doesn't have an index concept, some things are a little different, but the summary_stats display essentiall depends on the index being present and displayed

    """

    expected = {
        'a':  {'mean': 2.5, 'null_count':  0, 'quin99':  4.0, 'rewritten_col_name':'a',
            'orig_col_name':'normal_int_series'}}
    class SimplePolarsBuckaroo(PolarsBuckarooWidget):
        analysis_klasses= [select_only, SelectOnlyStyling]

    spbw = SimplePolarsBuckaroo(test_df)
    assert spbw.dataflow.merged_sd == expected

    resolved_stats = _resolve_all_stats(spbw.df_data_dict['all_stats'])
    # #880: the wire payload is projected to the displayed (pinned) stats.
    # orig_col_name / rewritten_col_name stay on merged_sd (asserted above)
    # but aren't pinned, so they no longer ship to the frontend.
    by_index = {row['index']: row['a'] for row in resolved_stats}
    assert by_index == {'null_count': 0.0, 'mean': 2.5, 'quin99': 4.0}
    assert spbw.df_display_args['main']['df_viewer_config'] == dict(
        EXPECTED_DF_VIEWER_CONFIG, pinned_rows=SELECT_ONLY_PINNED)

def test_polars_boolean():
    bool_df = pl.DataFrame({'bools':[True, True, False, False, True, None]})
    bw = PolarsBuckarooWidget(bool_df)
    assert bw.dataflow.merged_sd is not None

def test_polars_infinite():
    bool_df = pl.DataFrame({'bools':[True, True, False, False, True, None]})
    pbw = PolarsBuckarooInfiniteWidget(bool_df)
    pbw._handle_payload_args({'start':0, 'end':3})

def Xtest_polars_index_col():
    df = pl.DataFrame({'bools':[True, True, False, False, True, None],
                       'index':[   0,    1,     2,     3,    4,    5]})
    pbw2= PolarsBuckarooWidget(df)
    assert pbw2 is not None


def test_pandas_all_stats():
    """

    just make sure this doesn't fail"""
    from buckaroo.buckaroo_widget import BuckarooWidget

    import pandas as pd

    pd_test_df = pd.DataFrame({
        'normal_int_series' : pl.Series([1,2,3,4]),
        #'empty_na_ser' : pl.Series([pl.Null] * 4, dtype="Int64"),
        #'float_nan_ser' : pl.Series([3.5, np.nan, 4.8, 2.2])
    })

    
    SimpleResult = TypedDict('SimpleResult', {'null_count': int, 'mean': Any, 'quin99': Any})

    @stat()
    def simple_analysis(ser: RawSeries) -> SimpleResult:
        return {'null_count': 0, 'mean': 2.5, 'quin99': 4.0}

    class SimpleBuckaroo(BuckarooWidget):
        analysis_klasses= [simple_analysis, StylingAnalysis]

    sbw = SimpleBuckaroo(pd_test_df)
    assert sbw.dataflow.merged_sd == {
        'a' :  {'mean': 2.5, 'null_count':  0, 'quin99':  4.0, 'rewritten_col_name':'a',
            'orig_col_name':'normal_int_series'}}
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
            F.all().value_counts().implode().list.gather(pl.arange(0, 10), null_on_oob=True).explode().struct.rename_fields(['val',
                'unused_count']).struct.field('val').prefix('val_'),
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
typed_df = typed_df.with_columns(timestamp=pl.col('timestamp').str.to_datetime(time_zone="UTC") )
column_config_overrides={'float_col': {'color_map_config': {
    'color_rule': 'color_not_null',
    'conditional_color': 'red', 'exist_column': 'errored_float'}}}
    
def test_polars_to_pandas():
    bw = PolarsBuckarooWidget(typed_df)
    bw.add_analysis(ShowErrorsPostProcessing)
    
    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['post_processing'] = 'show_errors'
    bw.buckaroo_state = temp_buckaroo_state



def test_polars_search():
    """
    Makes sure that search actually works

    """
    df = pl.DataFrame(
        {'a':[10,20,30,40], 'b': ['a', 'aa', 'ab', 'bb']})

    bw = PolarsBuckarooWidget(df)
    assert bw.buckaroo_state['cleaning_method'] == ''
    assert bw.dataflow.cleaning_method == ''
    # class VCBuckarooWidget(BuckarooWidget):
    #     #analysis_klasses = base_a_klasses
    #     autoclean_conf = tuple([NoCleaningConf]) 

    # vcb = VCBuckarooWidget(typed_df, debug=False)
    assert len(bw.dataflow.processed_df) == 4
    
    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['quick_command_args'] = {'search': ['a']}
    bw.buckaroo_state = temp_buckaroo_state

    #probably something in autocleaning config should be responsible for generating these commands
    assert bw.dataflow.merged_operations == [
        [sQ('search'), s('df'), "col", "a"]]

    assert len(bw.dataflow.processed_df) == 3

    temp_buckaroo_state = bw.buckaroo_state.copy()
    temp_buckaroo_state['quick_command_args'] = {'search': ['aa']}
    bw.buckaroo_state = temp_buckaroo_state

    #probably something in autocleaning config should be responsible for generating these commands
    assert bw.dataflow.merged_operations == [
        [sQ('search'), s('df'), "col", "aa"]]

    assert len(bw.dataflow.processed_df) == 1

    """
    add an additional test that accounts for arbitrary, configurable status bar command args

    dataflow should just be responsible for parsing back the frontend datastructure.

    There should be another part where the frontend presents a command structure to the status bar.
    

    """

def get_named_col_pldf():
    return pl.DataFrame({'foo':[1,2,3],
        'bar':["asdf","iiu", "asd999"],
        'baz':[True, False, True]})
                  

def test_serialize_regular_df():
    #this is a bit of a hack, but to_parquet expects the index to alread have an index column.  This is necessary for proper slicing in the infinite widget
    df = get_named_col_pldf().with_row_index()
    output = to_parquet(df)
    #second_df = pd.read_parquet(output)
    import polars as pl
    second_df = pl.read_parquet(output)
    assert set(second_df.columns) ==  set(['index','a','b','c'])

def test_citibike_df():
    from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget
    print(os.getcwd())
    citibike_df = pl.read_parquet("./docs/example-notebooks/citibike-trips-2016-04.parq")
    PolarsBuckarooInfiniteWidget(citibike_df, debug=True)

def test_citibike_minimal_failure():
    import polars as pl
    from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget
    df = pl.read_parquet("./docs/example-notebooks/citibike-trips-2016-04.parq")
    PolarsBuckarooInfiniteWidget(df)
