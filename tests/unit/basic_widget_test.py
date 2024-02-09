import pandas as pd
from IPython.display import display
from buckaroo.buckaroo_widget import BuckarooWidget
from buckaroo.pluggable_analysis_framework.analysis_management import PERVERSE_DF
from .fixtures import (word_only_df)

simple_df = pd.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})



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

def xtest_interpreter():    
    #df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

    w = BuckarooWidget(simple_df, auto_clean=True)
    assert w.operation_results['generated_py_code'] == '''def clean(df):
    df['int_col'] = smart_to_int(df['int_col'])
    df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    return df'''

    temp_ops = w.operations.copy()
    temp_ops.append([{"symbol":"dropcol"},{"symbol":"df"},"str_col"])
    w.operations = temp_ops

    tdf = w.operation_results['transformed_df']
    assert w.operation_results['transform_error'] is False
    field_names = [ f['col_name'] for f in tdf['dfviewer_config']['column_config'] ]
    assert 'str_col' not in field_names
    assert w.operation_results['generated_py_code'] == """def clean(df):
    df['int_col'] = smart_to_int(df['int_col'])
    df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    df.drop('str_col', axis=1, inplace=True)
    return df"""

def atest_symbol_meta():    
    """verifies that a symbol with a meta key can be added and
    properly interpretted.  This should probably be a lower level
    parser test

    """

    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
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

