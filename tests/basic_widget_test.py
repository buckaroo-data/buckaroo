import pandas as pd
from IPython.display import display
from buckaroo.buckaroo_widget import BuckarooWidget


def test_basic_instantiation():
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    assert w.dfConfig['totalRows'] == 499

def test_basic_display():
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    display(w)

def test_interpreter():    
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    assert w.operation_results['generated_py_code']  == '#from py widget init'
    w.operations = [[{"symbol":"dropcol"},{"symbol":"df"},"starttime"]]

    tdf = w.operation_results['transformed_df']
    assert w.operation_results['transform_error'] == False
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'starttime' not in field_names


def test_interpreter_errors():
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = BuckarooWidget(df)
    assert w.operation_results['generated_py_code']  == '#from py widget init'
    w.operations = [
        [{"symbol":"dropcol"},{"symbol":"df"},"starttime"],
        [{"symbol":"dropcol"},{"symbol":"df"},"starttime"]]
    assert w.operation_results['transform_error'] == '''"['starttime'] not found in axis"'''


