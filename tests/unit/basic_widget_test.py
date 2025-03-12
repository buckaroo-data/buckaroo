import pytest
import pandas as pd
from IPython.display import display
from buckaroo.buckaroo_widget import BuckarooWidget
from buckaroo.pluggable_analysis_framework.analysis_management import PERVERSE_DF
from .fixtures import (word_only_df)
from buckaroo.serialization_utils import (DuplicateColumnsException)


simple_df = pd.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})

from buckaroo.dataflow.dataflow_extras import StylingAnalysis
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis

from buckaroo.customizations.analysis import (TypingStats, ComputedDefaultSummaryStats, DefaultSummaryStats)
from buckaroo.customizations.histogram import (Histogram)
from buckaroo.customizations.styling import DefaultSummaryStatsStyling, DefaultMainStyling
from traitlets import observe
import warnings
class EverythingStyling(StylingAnalysis):
    """
    This styling shows as much detail as possible
    """
    df_display_name = "Everything"
    requires_summary = [ "_type"]

    #Styling analysis handles column iteration for us.
    @classmethod
    def style_column(kls, col:str, column_metadata):
        print("EverythingStyling style_column", col)
        
        try:
            t = column_metadata['_type']
            return {'col_name':col, 'displayer_args': disp }
        except Exception as  e:
            #print(col, e)
            disp = {'displayer': 'foo'}
            raise

            
class KitchenSinkWidget(BuckarooWidget):
    #let's be explicit here and show all of the built in analysis klasses
    analysis_klasses = [
    TypingStats, DefaultSummaryStats,
    Histogram, ComputedDefaultSummaryStats,
    # default buckaroo styling
    DefaultSummaryStatsStyling, DefaultMainStyling,
    EverythingStyling
    ]

def test_styling_instantiation():
    
    """styling routines are called before processed_sd has run, that
    can cause errors because EverythingStyling expects keys in
    column_metadata to be present from "requires_summary". There is a
    special case in the code to not warn about this, make sure we
    don't have problems"""
    
    ksw = KitchenSinkWidget(simple_df)
    #TODO: check that nothing was logged, later
    # I'm not quite sure how to verify the clean user experience I want here



def test_basic_instantiation():
    w = BuckarooWidget(simple_df)
    assert w.df_meta['total_rows'] == 3

def test_perverse_instantiation():
    w = BuckarooWidget(PERVERSE_DF)
    assert w.df_meta['total_rows'] == 10

def test_word_only_instantiation():
    BuckarooWidget(word_only_df)

def test_basic_display():
    df = simple_df
    w = BuckarooWidget(df)
    display(w)

def test_debug_true():
    df = simple_df
    w = BuckarooWidget(df, debug=True)
    display(w)

def test_interpreter():    
    #df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

    w = BuckarooWidget(simple_df)
    # assert w.operation_results['generated_py_code'] == '''def clean(df):
    # df['int_col'] = smart_to_int(df['int_col'])
    # df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    # return df'''
    assert 'str_col' in w.dataflow.cleaned_df.columns
    temp_ops = w.operations.copy()
    temp_ops.append([{"symbol":"dropcol"},{"symbol":"df"},"str_col"])
    w.operations = temp_ops

    tdf = w.dataflow.cleaned_df
    assert 'str_col' not in tdf.columns
    '''
    #assert w.operation_results['transform_error'] is False
    field_names = [ f['col_name'] for f in tdf['dfviewer_config']['column_config'] ]
    assert 'str_col' not in field_names
    assert w.operation_results['generated_py_code'] == """def clean(df):
    df['int_col'] = smart_to_int(df['int_col'])
    df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    df.drop('str_col', axis=1, inplace=True)
    return df"""
    '''

def test_string_column_handling():
    """
    If the front end is passed numeric column names, nothing works, and no error is thrown
    """
    
    df = pd.DataFrame([["a","b","c"]], columns=[10,20,30])
    bw = BuckarooWidget(df)
    # print(bw.df_data_dict['main'])
    # print(bw.df_display_args['main']['df_viewer_config']['column_config'])
    #we want the column to be named the string '10' not the number t10
    assert bw.df_display_args['main']['df_viewer_config']['column_config'][1]['col_name'] == '10'
    assert bw.df_data_dict['main'] == [{'index': 0, '10': 'a', '20': 'b', '30': 'c'}]
    assert bw.df_display_args['main']['df_viewer_config']['column_config'][1]['tooltip_config']['val_column'] == '10'


def test_non_unique_column_names():
    #you end up with columns named [0,1,2, 0,1,2]
    #refactor to instantiating the dataframe without concat

    with pytest.raises(DuplicateColumnsException):
        BuckarooWidget(pd.DataFrame([['a', 'b'], [1,2]], columns = [1,1]))


def test_init_sd():
    """
    I have run into a bug where init_sd causes an error in DefaultMainStyling, it shouldn't blow up
    """
    BuckarooWidget(simple_df, init_sd={'int_col': {'foo':8}})



    
def atest_symbol_meta():    
    """verifies that a symbol with a meta key can be added and
    properly interpretted.  This should probably be a lower level
    parser test

    """

    df = pd.read_csv('./docs/examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    assert w.operation_results['generated_py_code'] == '# instantiation, unused'
    w.operations = [[{"symbol":"dropcol", "meta":{}},{"symbol":"df"},"starttime"]]

    tdf = w.operation_results['transformed_df']
    assert w.operation_results['transform_error'] is False
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'starttime' not in field_names


def xtest_interpreter_errors():
    w = BuckarooWidget(simple_df)
    w.operations = [
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"],
        #dropping the same column will result in an error
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"]]
    assert w.operation_results['transform_error'] == '''"['int_col'] not found in axis"'''


def xtest_displayed_after_interpreter_filter():
    """verify that the displayed number updates when an operation changes the size of cleaned_df  """
    pass
