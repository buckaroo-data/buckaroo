import pandas as pd
from IPython.display import display
from buckaroo.buckaroo_widget import BuckarooWidget


simple_df = pd.DataFrame({'int_col':[1, 2, 3], 'str_col':['a', 'b', 'c']})

def test_basic_instantiation():
    df = simple_df
    w = BuckarooWidget(df)
    assert w.dfConfig['totalRows'] == 3

def test_basic_display():
    df = simple_df
    w = BuckarooWidget(df)
    display(w)

def test_interpreter():    
    #df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')

    w = BuckarooWidget(simple_df)
    assert w.operation_results['generated_py_code'] == '''def clean(df):
    df['int_col'] = smart_int(df['int_col'])
    df['str_col'] = df['str_col'].fillna(value='').astype('string').replace('', None)
    return df'''

    temp_ops = w.operations.copy()
    temp_ops.append([{"symbol":"dropcol"},{"symbol":"df"},"str_col"])
    w.operations = temp_ops

    tdf = w.operation_results['transformed_df']
    assert w.operation_results['transform_error'] == False
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'str_col' not in field_names
    assert w.operation_results['generated_py_code'] == """def clean(df):
    df['int_col'] = smart_int(df['int_col'])
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
    assert w.operation_results['transform_error'] == False
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'starttime' not in field_names


def test_interpreter_errors():
    w = BuckarooWidget(simple_df)
    w.operations = [
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"],
        #dropping the same column will result in an error
        [{"symbol":"dropcol"},{"symbol":"df"},"int_col"]]
    assert w.operation_results['transform_error'] == '''"['int_col'] not found in axis"'''

def test_analysis_pipeline():
    """  uses built in analysis_management unit tests on the Buckaroo Widget as configured"""
    w = BuckarooWidget(simple_df)
    assert w.stats.ap.unit_test() == True

def test_autotype_false():
    """  uses built in analysis_management unit tests on the Buckaroo Widget as configured"""
    w = BuckarooWidget(simple_df, autoType=False)
    assert w.stats.ap.unit_test() == True
    
def test_post_processing():
    def my_func(df):
        return df['int_col'].sum()
    
    bw = BuckarooWidget(simple_df, postProcessingF=my_func)
    assert bw.processed_result == 6

    bw2 = BuckarooWidget(simple_df, autoType=False, postProcessingF=my_func)
    assert bw2.processed_result == 6
    

