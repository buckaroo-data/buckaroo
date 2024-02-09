import time
import json
import pandas as pd
import numpy as np
from buckaroo.serialization_utils import df_to_obj
import pydantic

# import typing
# if typing.TYPE_CHECKING:
#     from . import AnyComponent


from typing import Optional, List, Literal, Union, Dict



class HistogramModel(pydantic.BaseModel):
    name: str
    population: float

HT = Optional[List[HistogramModel]]


class ObjDisplayerA(pydantic.BaseModel):
    displayer: Literal["obj"]

class BooleanDisplayerA(pydantic.BaseModel):
    displayer: Literal["boolean"]

class StringDisplayerA(pydantic.BaseModel):
    displayer: Literal["string"]
    #max_length: int

class FloatDisplayerA(pydantic.BaseModel):
    displayer: Literal["float"]

class DatetimeDefaultDisplayerA(pydantic.BaseModel):
    displayer: Literal["datetimeDefault"]

class IntegerDisplayerA(pydantic.BaseModel):
    displayer: Literal["integer"]
    min_digits: int
    max_digits: int

class DatetimeLocaleDisplayerA(pydantic.BaseModel):
    displayer: Literal["datetimeLocaleString"]
    locale: Union[
        *map(lambda x: Literal[x],
             ['en-US', 'en-GB', 'en-CA', 'fr-FR', 'es-ES', 'de-DE', 'ja-JP'])]
    args: str # start with a dictionary, not sure of full typing
    #args: Intl.DateTimeFormatOptions;

#End FormatterArgs

# Begin CellRenderArgs
class HistogramDisplayerA(pydantic.BaseModel):
    displayer: Literal["histogram"]

class LinkifyDisplayerA(pydantic.BaseModel):
    displayer: Literal["linkify"]


# Internally DfViewer distinguishes between FormatterArgs and
# CellRendererArgs because they are sent to different functions, but to
# the python side, that is just an implmentation detail

DisplayerArgs = Union[
    #formatters
    ObjDisplayerA, BooleanDisplayerA, StringDisplayerA, FloatDisplayerA, DatetimeDefaultDisplayerA,
    IntegerDisplayerA, DatetimeLocaleDisplayerA,
    #Cell Renderers
    HistogramDisplayerA, LinkifyDisplayerA]

class ColorMapRules(pydantic.BaseModel):
    color_rule: Literal['color_map']
    map_name: Union[Literal['BLUE_TO_YELLOW'], Literal['DIVERGING_RED_WHITE_BLUE']]
    val_column: Optional[str]

class ColorWhenNotNullRules(pydantic.BaseModel):
    color_rule: Literal['color_not_null']
    conditional_color: Union[str, Literal['red']]
    exist_column: str

class ColorFromColumn(pydantic.BaseModel):
    color_rule: Literal['color_from_column']
    col_name: str

ColorMappingConfig = Union[ColorMapRules, ColorWhenNotNullRules, ColorFromColumn]

class SimpleToolTip(pydantic.BaseModel):
    tooltip_type: Literal['simple']
    val_column: str

class SummarySeriesTooltip(pydantic.BaseModel):
    tooltip_type: Literal['summary_series']

TooltipConfig = Union[SimpleToolTip, SummarySeriesTooltip]


class ColumnConfig(pydantic.BaseModel):
    col_name: str
    displayer_args: DisplayerArgs
    color_map_config: Optional[ColorMappingConfig]
    tooltip_config: Optional[TooltipConfig]

class ColorMapRules(pydantic.BaseModel):
    color_rule: Literal['color_map']
    map_name: Union[Literal['BLUE_TO_YELLOW'], Literal['DIVERGING_RED_WHITE_BLUE']]
    val_column: Optional[str]

class LinkifyDisplayerA(pydantic.BaseModel):
    displayer: Literal["linkify"]


class PinnedRowConfig(pydantic.BaseModel):
    primary_key_val: str
    displayer_args: DisplayerArgs


class DFViewerConfig(pydantic.BaseModel):
    pinned_rows: List[PinnedRowConfig]
    column_config: List[ColumnConfig]

DFData = List[Dict[str, Union[str, int, float, None]]]

class DFWhole(pydantic.BaseModel):
    dfviewer_config: DFViewerConfig
    data: DFData


class DFMeta(pydantic.BaseModel):
    """
    stats as calculated about the underlying dataframe.
    Static, these don't change regardless of modification to the dataframe via styling or cleaning
    """
    total_rows: int
    columns: int
    rows_shown: int

class BuckarooOptions(pydantic.BaseModel):
    """
    Buckaroo is opinionated.  Each of these represent an opinion about an aspect of buckaroo.
    The idea being that different opinions can be swapped through by the frontend
    """
    df_list: List[str]  #defaults to "base_df"
    sampled: List[str]  # sampling strategies
    #maybe add "base_df" as an always present option... but also maybe
    #not. PL_Compare won't really use it
    summary_stats: List[str] 
    auto_clean: List[str]    # which cleaning strategy
    #reorderd_columns: List[str]  #strategy for reordering cloumns
    #styling: List[str]    # which column ordering strategy

class BuckarooState(pydantic.BaseModel):
    """
    Given BuckarooOptions, the current state of the frontend. each str
    will be one of the list from BuckarooOptions
    """
    displayed_df: Union[str, Literal['base_df']]
    sampled: Union[str, False]
    summary_stats: Union[str, False]
    show_commands: bool
    auto_clean: Union[str, False]
    #reorderd_columns: Union[str, False]
    #styling: Union[str, False]

class WidgetOptions(pydantic.BaseModel):


    #How is summary_dict['all']  pulled out from df_dict.  DFViewer gets a dfwhole and a summary_df
    df_dict: Dict[str, DFWhole]
    df_meta: DFMeta
    operations: List[any]    # don't think I have typing yet
    operation_results: any   # don't have typing yet
    commandConfig: any       # casing, fix.  not typing
    buckaroo_state: BuckarooState
    buckaroo_options: BuckarooOptions


"""
auto_clean, reorderd_columns and styling all poke at the same things, and I'm not sure the best way to pull it apart.

The trickiest example is lat/long.

imagine a dataframe with a lat column and a long column.

This should be a 'location' tuple that combines the two columns and is displayed as a map or link to a map...
But editting/combining columns is a whole dataframe operation.  Which currently slots it into auto_clean.

For display only, this makes sense as a post processing step.

For autocleaning, it makes sense as a 'foreign key recognition step'.  for citibike data, start_station name, start_station_id, start_station_latitude, start_station_longitude should be replaced with a categorical linking to a 'station enum'.  They should be displayed as either "start station name", a map, or a link to the map geo coordinates.

For now, I will leave it ambiguous.  I will also consider a post_processing_step that has the same interface as auto_clean (df in, df out).

This same attribute could be manipulated via styling like so.
separate lat/long columns -> display separately
tuple column tagged lat/long in summary stats -> display as link to map
tuple column tagged lat/long in summary stats -> display as inline map
categorical to 3 valued tuple (name, lat/long, id) -> display name
categorical to 3 valued tuple (name, lat/long, id) -> display tuple inline nested
categorical to 3 valued tuple (name, lat/long, id) -> display as link to map
categorical to 3 valued tuple (name, lat/long, id) -> display as map


Given the above data processing should go
raw -> auto_clean (pre-processing) -> summary_stats -> post_processing -> styling -> overrides

I would also like to be able to write partial processing classes that can be combined.  So you could just write the lat/long combination into tuple, without having to rewrite a whole auto cleaning command.  These could be composed by programmers (not end users initially).


"""
    
    

# class DfViewer(pydantic.BaseModel):
#     type: 'DFViewer'
#     df: DFWhole

#     #Ilike the serialization_alias... but luckily I avoid the need
#     #because I don't have any snake cased fields




# def test_column_hints():
#     ColumnStringHint(type="string", histogram=[])
#     ColumnStringHint(type="string", histogram=[{'name':'foo', 'population':3500}])
#     with pytest.raises(ValidationError) as exc_info:
#         errant_histogram_entry = {'name':'foo', 'no_population':3500}
#         ColumnStringHint(type="string", histogram=[errant_histogram_entry])
#     assert exc_info.value.errors(include_url=False) == [
#         {'type': 'missing', 'loc': ('histogram', 0, 'population'),
#          'msg': 'Field required','input': errant_histogram_entry}]
    
#     ColumnBooleanHint(type="boolean", histogram=[])

# def test_column_hint_extra():
#     """verify that we can pass in extra unexpected keys"""
#     ColumnStringHint(type="string", histogram=[], foo=8)

# def test_dfwhole():
#     temp = {'schema': {'fields':[{'name':'foo', 'type':'integer'}],
#                        'primaryKey':['foo'], 'pandas_version':'1.4.0'},
#             'table_hints': {'foo':{'type':'string', 'histogram':[]},
#                             'bar':{'type':'integer', 'min_digits':2, 'max_digits':4, 'histogram':[]},
#                             'baz':{'type':'obj', 'histogram':[]},
#                             },
#             'data': [{'foo': 'hello', 'bar':8},
#                      {'foo': 'world', 'bar':10}]}
#     DFWhole(**temp)

# def test_df_to_obj_pydantic():
#     named_index_df = pd.DataFrame(
#         dict(foo=['one', 'two', 'three'],
#              bar=[1, 2, 3]))

#     serialized_df = df_to_obj(named_index_df)
#     print(json.dumps(serialized_df, indent=4))
#     DFWhole(**serialized_df)

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
