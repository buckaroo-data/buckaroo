import time
import json
import pytest
from pydantic import ValidationError
import pandas as pd
import numpy as np
from buckaroo.serialization_utils import df_to_obj
import pydantic

# import typing
# if typing.TYPE_CHECKING:
#     from . import AnyComponent


from typing import Optional, List, Literal, Union, Dict



Formatter = Union[Literal["histogram"], Literal["float"], Literal["string"]]


class HistogramFormatterConfig(pydantic.BaseModel):
    formatter = Literal["histogram"]
    #histograms aren't formatters they are renderers, but that's a frontend problem

class IntegerFormatterConfig(pydantic.BaseModel):
    formatter: Literal["integer"]
    min_digits:int
    max_digits:int

FormatterConfig = Union[HistogramFormatterConfig, IntegerFormatterConfig]

class PinnedRowConfig(pydantic.BaseModel):
    primary_key_val : str #value of primary key for this row
    displayer_args: FormatterConfig

class ColumnConfig(pydantic.BaseModel):
    col_name : str #value of primary key for this row
    displayer_args: FormatterConfig

class DFViewerConfig(pydantic.BaseModel):
    pinned_rows: List[PinnedRowConfig]
    column_config: List[ColumnConfig]

    #//extra_config: Dict[str, Any] #height, width

class DfViewer(pydantic.BaseModel):
    df:pd.DataFrame
    summary_stats_df: pd.DataFrame
    dfviewer_config: DFViewerConfig


"""
DFViewer is responsible for picking through summary_stats_df and ordering rows in the order of pinned_rows

Otherwise, there would be two specification of the order of summary_stats_rows
----

When actually displaying summary_stats, the df argument will be empty.  Only summary_stats_df will be populated
and every displayed row must have a pinned_row config





"""

class HistogramModel(pydantic.BaseModel):
    name: str
    population: float

HT = Optional[List[HistogramModel]]



class ColumnStringHint(pydantic.BaseModel):
    type: Literal["string"]
    histogram: HT

class ColumnObjHint(pydantic.BaseModel):
    type: Literal["obj"]
    histogram: HT


class ColumnBooleanHint(pydantic.BaseModel):
    type: Literal["boolean"]
    histogram: HT

class ColumnIntegerHint(pydantic.BaseModel):
    type: Literal["integer"]
    min_digits:int
    max_digits:int
    histogram: HT

class DFColumn(pydantic.BaseModel):
    name: str
    type: str #should be a union

ColumnHint = Union[ColumnStringHint, ColumnObjHint, ColumnBooleanHint, ColumnIntegerHint]

class DFSchema(pydantic.BaseModel):
    fields: List[DFColumn]
    primaryKey: list[str]  #; //['index']
    pandas_version: str #; //'1.4.0',


DFData = List[Dict[str, Union[str, int, float, None]]]



class DFWhole(pydantic.BaseModel):
    schema__ :DFSchema = pydantic.Field(alias='schema')
    table_hints: Dict[str, ColumnHint]
    data: DFData

# class DfViewer(pydantic.BaseModel):
#     type: 'DFViewer'
#     df: DFWhole

#     #Ilike the serialization_alias... but luckily I avoid the need
#     #because I don't have any snake cased fields


def test_column_hints():
    ColumnStringHint(type="string", histogram=[])
    ColumnStringHint(type="string", histogram=[{'name':'foo', 'population':3500}])
    with pytest.raises(ValidationError) as exc_info:
        errant_histogram_entry = {'name':'foo', 'no_population':3500}
        ColumnStringHint(type="string", histogram=[errant_histogram_entry])
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'missing', 'loc': ('histogram', 0, 'population'),
         'msg': 'Field required','input': errant_histogram_entry}]
    
    ColumnBooleanHint(type="boolean", histogram=[])

def test_column_hint_extra():
    """verify that we can pass in extra unexpected keys"""
    ColumnStringHint(type="string", histogram=[], foo=8)

def test_dfwhole():
    temp = {'schema': {'fields':[{'name':'foo', 'type':'integer'}],
                       'primaryKey':['foo'], 'pandas_version':'1.4.0'},
            'table_hints': {'foo':{'type':'string', 'histogram':[]},
                            'bar':{'type':'integer', 'min_digits':2, 'max_digits':4, 'histogram':[]},
                            'baz':{'type':'obj', 'histogram':[]},
                            },
            'data': [{'foo': 'hello', 'bar':8},
                     {'foo': 'world', 'bar':10}]}
    DFWhole(**temp)

def test_df_to_obj_pydantic():
    named_index_df = pd.DataFrame(
        dict(foo=['one', 'two', 'three'],
             bar=[1, 2, 3]))

    serialized_df = df_to_obj(named_index_df)
    print(json.dumps(serialized_df, indent=4))
    DFWhole(**serialized_df)

def bimodal(mean_1, mean_2, N, sigma=5):
    X1 = np.random.normal(mean_1, sigma, int(N/2))
    X2 = np.random.normal(mean_2, sigma, int(N/2))
    X = np.concatenate([X1, X2])
    return X

def rand_cat(named_p, na_per, N):
    choices, p = [], []
    named_total_per = sum(named_p.values()) + na_per
    total_len = int(np.floor(named_total_per * N))
    if named_total_per > 0:
        for k, v in named_p.items():
            choices.append(k)
            p.append(v/named_total_per)
        choices.append(pd.NA)
        p.append(na_per/named_total_per)    
        return [np.random.choice(choices, p=p) for k in range(total_len)]
    return []

def random_categorical(named_p, unique_per, na_per, longtail_per, N):
    choice_arr = rand_cat(named_p, na_per, N)
    discrete_choice_len = len(choice_arr)

    longtail_count = int(np.floor(longtail_per * N))//2
    extra_arr = []
    for i in range(longtail_count):
        extra_arr.append("long_%d" % i)
        extra_arr.append("long_%d" % i)

    unique_len = N - (len(extra_arr) + discrete_choice_len)
    for i in range(unique_len):
        extra_arr.append("unique_%d" % i)
    all_arr = np.concatenate([choice_arr, extra_arr])
    np.random.shuffle(all_arr)
    try:
        return pd.Series(all_arr, dtype='UInt64')
    except Exception: # this is test fixture code
        return pd.Series(all_arr, dtype=pd.StringDtype())        


def _test_df_to_obj_timing():
    N = 100_000
    df = pd.DataFrame({
        'normal': np.random.normal(25, .3, N),
        'exponential' :  np.random.exponential(1.0, N) * 10 ,
        'increasing':[i for i in range(N)],
        'one': [1]*N,
        'dominant_categories':     random_categorical({'foo': .6, 'bar': .25, 'baz':.15}, unique_per=0, na_per=0, longtail_per=0, N=N),
        'all_unique_cat': random_categorical({}, unique_per=1, na_per=0, longtail_per=0, N=N),
        'all_NA' :          pd.Series([pd.NA] * N, dtype='UInt8'),
        'half_NA' :         random_categorical({1: .55}, unique_per=0,   na_per=.45, longtail_per=.0, N=N),
        'longtail' :        random_categorical({},      unique_per=0,   na_per=.2, longtail_per=.8, N=N),
        'longtail_unique' : random_categorical({},      unique_per=0.5, na_per=.0, longtail_per=.5, N=N)})
    

    start_serialize = time.time()
    serialized_df = df_to_obj(df)
    end_serialize = time.time()
    DFWhole(**serialized_df)
    end_pydantic = time.time()
    
    json.dumps(serialized_df)
    end_json_time = time.time()

    serialize_time = end_serialize - start_serialize
    pydantic_time = end_pydantic - end_serialize
    json_time = end_json_time - end_pydantic

    print("serialize_time ", serialize_time)
    print("pydantic_time  ", pydantic_time)
    print("json_time      ", json_time)

    #pydantic time was about  1/5th of serialization time
    #json.dumps time was around 2/5ths of serialization time

    #the following line triggers an error which will force printing
    #1/0
