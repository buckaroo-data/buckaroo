import pandas as pd
from dcef.dcef_widget import DCEFWidget


def test_basic_instantiation():
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = DCEFWidget(df)
    assert w.dfConfig['totalRows'] == 499

def test_interpreter():    
    df = pd.read_csv('./examples/data/2014-01-citibike-tripdata.csv')
    w = DCEFWidget(df)
    assert w.operation_results['generated_py_code']  == '#from py widget init'
    w.operations = [[{"symbol":"dropcol"},{"symbol":"df"},"starttime"]]

    tdf = w.operation_results['transformed_df']
    field_names = [ f['name'] for f in tdf['schema']['fields'] ]
    assert 'starttime' not in field_names
