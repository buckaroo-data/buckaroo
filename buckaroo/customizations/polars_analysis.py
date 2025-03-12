import polars as pl
import numpy as np
import polars.selectors as cs
from polars import functions as F
from polars import datatypes as pdt

from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.polars_utils import NUMERIC_POLARS_DTYPES
from buckaroo.pluggable_analysis_framework.utils import json_postfix
from buckaroo.customizations.histogram import numeric_histogram
from typing import Dict

def get_mode(ser):
    mode_raw = ser.mode()
    if len(mode_raw) == 0:
        return np.nan
    else:
        return mode_raw.values[0]

"""
to best take advantage of the DAG and pluggable_analysis_framework, structure your code as follows
a single ColAnalysis can return multiple facts, but those facts shouldn't be interdepedent
That way individual facts can be overridden via the DAG machinery, and other facts that depend on them will
get the proper value

Overtime codebases will probably trend towards many classes with single facts, but it doesn't have to be that way.  Code what comes naturally to you


"""




class ComputedDefaultSummaryStats(PolarsAnalysis):
    requires_summary = ['length',
                        'unique_count', 'empty_count', 'distinct_count']
    provides_defaults = dict(
        distinct_per=0, empty_per=0, unique_per=0, nan_per=0)



                        

    @staticmethod
    def computed_summary(summary_dict):
        len_ = summary_dict['length']
        return dict(
            distinct_per=summary_dict['distinct_count']/len_,
            empty_per=summary_dict.get('empty_count',0)/len_,
            unique_per=summary_dict['unique_count']/len_,
            nan_per=summary_dict['null_count']/len_)



PROBABLY_STRUCTS = (~cs.numeric() & ~cs.string() & ~cs.temporal() &
                    ~cs.boolean())
NOT_STRUCTS = (~PROBABLY_STRUCTS)

class VCAnalysis(PolarsAnalysis):
    provides_defaults = dict(
        value_counts=pl.Series(
            "",
            [{'a': 'error', 'count': 1}], dtype=pl.Struct({'a': pl.String, 'count': pl.UInt32})))

    select_clauses = [
        NOT_STRUCTS.exclude("count").value_counts(sort=True)
        .implode().name.map(json_postfix('value_counts')),
        (NOT_STRUCTS & pl.selectors.matches("^count$"))
        .alias("not_counts")
        .value_counts(sort=True)
        .implode()
        .alias("count").name.map(json_postfix('value_counts'))]
    

DUMMY_VALUE_COUNTS = pl.Series(
    [{'a': 3, 'count': 1}, {'a': 4, 'count': 1}, {'a': 5, 'count': 1}])


class BasicAnalysis(PolarsAnalysis):


    provides_defaults = {'length':0, 'min':0, 'max':0, 'mode':0,
                         'mean':0, 'unique_count':0, 'empty_count':0, 'distinct_count':0,
                         'most_freq':0, 'median':0,
                         'std':0,
                         'null_count':0, 'non_null_count':0,
                         '2nd_freq':0, '3rd_freq':0, '4th_freq':0, '5th_freq':0}


    requires_summary = ['value_counts']
    select_clauses = [
        F.all().len().name.map(json_postfix('length')),
        F.all().null_count().name.map(json_postfix('null_count')),
        NOT_STRUCTS.min().name.map(json_postfix('min')),
        NOT_STRUCTS.max().name.map(json_postfix('max')),
        NOT_STRUCTS.mean().name.map(json_postfix('mean')),
        NOT_STRUCTS.mode().name.map(json_postfix('most_freq')),
        cs.numeric().median().name.map(json_postfix('median')),
        cs.numeric().std().name.map(json_postfix('std')),
        
        F.col(pl.Utf8).str.count_matches("^$").sum().name.map(json_postfix('empty_count')),
        (NOT_STRUCTS.len() - NOT_STRUCTS.is_duplicated().sum()).name.map(json_postfix('unique_count')),
        (NOT_STRUCTS.len() - NOT_STRUCTS.null_count()).name.map(json_postfix('non_null_count'))
        ]

    @staticmethod
    def computed_summary(summary_dict):
        
        if 'value_counts' in summary_dict:
            temp_df = pl.DataFrame({'vc': summary_dict['value_counts'].explode()}).unnest('vc')
            regular_col_vc_df = temp_df.select(pl.all().exclude('count').alias('key'), pl.col('count'))

            def get_freq(pos):
                if len(regular_col_vc_df) > pos:
                    return regular_col_vc_df[pos]['key'][0]
                return None
            return {'mode': get_freq(0),
                    '2nd_freq': get_freq(1),
                    '3rd_freq': get_freq(2),
                    '4th_freq': get_freq(3),
                    '5th_freq': get_freq(4),
                    'distinct_count':len(temp_df)}
        else:

            return dict(mode=None, value_counts=DUMMY_VALUE_COUNTS, distinct_count=0,
                        mean=0, unique_count=0)


class PlTyping(PolarsAnalysis):
    column_ops = {'dtype':  ("all", lambda col_series: col_series.dtype)}
    provides_defaults = dict(dtype='unknown', _type='unknown', is_numeric=False, is_integer=False)

    @staticmethod
    def computed_summary(summary_dict):
        dt = summary_dict['dtype']
        '''
        ['Array', 'Binary', 'Boolean', 'Categorical', 'DTYPE_TEMPORAL_UNITS', 'DataType', 'DataTypeClass', 'Date', 'Datetime', 'Decimal', 'Duration', 'Enum', 'Field', 'Float32', 'Float64', 'Int16', 'Int32', 'Int64', 'Int8', 'IntegerType', 'List', 'N_INFER_DEFAULT', 'Null', 'Object', 'String', 'Struct', 'TemporalType', 'Time', 'UInt16', 'UInt32', 'UInt64', 'UInt8', 'Unknown', 'Utf8', '__all__', '__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__path__', '__spec__', '_parse', '_utils', 'classes', 'constants', 'constructor', 'convert', 'dtype_to_ffiname', 'dtype_to_py_type', 'group', 'is_polars_dtype', 'maybe_cast', 'numpy_char_code_to_dtype', 'numpy_type_to_constructor', 'numpy_values_and_dtype', 'parse_into_dtype', 'polars_type_to_constructor', 'py_type_to_arrow_type', 'py_type_to_constructor', 'supported_numpy_char_code', 'try_parse_into_dtype', 'unpack_dtypes']
        '''
        res = {'is_numeric':  False, 'is_integer': False}


        if isinstance(dt, pdt.IntegerType):
            t = 'integer'
        elif isinstance(dt, pdt.Datetime) or isinstance(dt, pdt.Date):
            t = 'datetime'
        elif isinstance(dt, pdt.Float32) or isinstance(dt, pdt.Float64):
            t = 'float'
        elif  isinstance(dt, pdt.TemporalType): 
            #feels like a hack
            t = 'temporal'
        elif isinstance(dt, pdt.Utf8):
            t = 'string'
        elif isinstance(dt, pdt.Boolean):
            t = 'boolean'
        else:
            t = 'unknown'
        if t in ('integer', 'float'):
            res['is_numeric'] = True
        if t == 'integer':
            res['is_integer'] = True
        res['_type'] = t
        return res

def normalize_polars_histogram_ser(ser):
    df = pl.DataFrame({'named_col':ser})

    C = pl.col('named_col')
    small_q, large_q = C.quantile(.01).alias('small'), C.quantile(.99).alias('large')
    smallest, largest =  df.select(small_q, large_q).to_numpy()[0]

    meat_df = df.lazy().filter(
        (small_q < C) & (C < large_q)
    ).select(C).collect()['named_col']
    if len(meat_df) == 0:
        return { 'low_tail': smallest, 'high_tail':largest,
                 'meat_histogram': [[],[]], 'normalized_populations': []}
    raw_hist = meat_df.hist(bin_count=10, include_breakpoint=True)
    hist_df = raw_hist.select(pl.col("breakpoint"), pl.selectors.ends_with("count").alias("count"))
    edges = hist_df['breakpoint'].to_list()
    edges[0], edges[-1] = smallest, largest
    counts = hist_df['count'][1:]
    norm_counts = counts/counts.sum()
    return { 'low_tail': smallest, 'high_tail':largest,
             'meat_histogram': (counts.to_list(), edges),
             'normalized_populations': norm_counts.to_list()}


def categorical_dict_from_vc(vc_ser, top_n_positions=7) -> Dict[str, int]:
    temp_df = pl.DataFrame({'vc': vc_ser.explode()}).unnest('vc')
    regular_col_vc_df = temp_df.select(pl.all().exclude('count').alias('key'), pl.col('count'))
    length = regular_col_vc_df['count'].sum()
    normalized_counts = regular_col_vc_df['count'] / length
    nml_df = pl.DataFrame({'key':regular_col_vc_df['key'], 'normalized_count':normalized_counts})

    #filter out small categories
    significant_categories_df = nml_df.filter(pl.col('normalized_count') > .05)
    relevant_length = min(len(significant_categories_df), top_n_positions)
    cat_df = significant_categories_df[:relevant_length]

    #everything that isn't a named category.  relevant_length still applies
    full_long_tail = regular_col_vc_df['count'][relevant_length:].sum()
    unique_count = regular_col_vc_df['count'].eq(1).cum_sum()[-1]

    actual_long_tail = full_long_tail - unique_count

    categorical_histogram = dict(zip(cat_df['key'].to_list(), cat_df['normalized_count'].to_list()))
    categorical_histogram['longtail'] = actual_long_tail/length
    categorical_histogram['unique'] = unique_count/length
    return categorical_histogram


def categorical_histogram_from_cd(cd, nan_per):
    histogram = []
    longtail_obs = {'name': 'longtail'}
    unique_obs = {'name': 'unique'}
    for k,v in cd.items():
        if k == "longtail":
            longtail_obs['longtail'] = np.round((v)*100,0)
            continue
        elif k == "unique":
            unique_obs['unique'] = np.round((v)*100,0)
            continue
        histogram.append({'name':k, 'cat_pop': np.round((v)*100,0) })
    if longtail_obs['longtail'] > 0:
        histogram.append(longtail_obs)
    if unique_obs['unique'] > 0:
        histogram.append(unique_obs)
    nan_observation = {'name':'NA', 'NA':np.round(nan_per*100, 0)}
    if nan_per > 0.0:
        histogram.append(nan_observation)
    return histogram

class HistogramAnalysis(PolarsAnalysis):

    column_ops = {
        'histogram_args': (NUMERIC_POLARS_DTYPES, normalize_polars_histogram_ser)}

    requires_summary = ['min', 'max', 'value_counts', 'length', 'unique_count', 'is_numeric', 'nan_per',
                        'null_count',
                        ]
    provides_defaults = dict(categorical_histogram=[], histogram=[], histogram_bins=[])

    @staticmethod
    def computed_summary(summary_dict):
        if len(summary_dict.keys()) == 0:
            return {}
        
        vc = summary_dict['value_counts']
        cd = categorical_dict_from_vc(vc)
        is_numeric = summary_dict.get('is_numeric', False)
        nan_per = summary_dict['null_count']
        if is_numeric and len(vc.explode()) > 5:
            histogram_args = summary_dict['histogram_args']
            min_, max_, nan_per = summary_dict['min'], summary_dict['max'], summary_dict['nan_per']
            temp_histo =  numeric_histogram(histogram_args, min_, max_, nan_per)
            if len(temp_histo) > 5:
                #if we had basically a categorical variable encoded into an integer.. don't return it
                return {'histogram': temp_histo,
                        'histogram_bins': summary_dict['histogram_args']['meat_histogram'][1]
                        }
        return {'categorical_histogram': cd, 'histogram' : categorical_histogram_from_cd(cd, nan_per),
                'histogram_bins': ['faked']
                }

class PLCleaningStats(PolarsAnalysis):
    requires_summary = ['value_counts', 'length']
    provides_defaults = {'int_parse_fail': 0.0, 'int_parse':0.0}
    
    @staticmethod
    def computed_summary(column_metadata):
        vc_ser, len_ = column_metadata['value_counts'], column_metadata['length']
        vc_df = pl.DataFrame({'vc': vc_ser.explode()}).unnest('vc')
        regular_col_vc_df = vc_df.select(pl.all().exclude('count').alias('key'), pl.col('count'))
        int_parse = pl.col('key').cast(pl.Int64, strict=False).is_null()
        per_df = regular_col_vc_df.select(
            int_parse.replace({True:1, False:0}).mul(pl.col('count')).sum().alias('int_parse_fail'),
            int_parse.replace({True:0, False:1}).mul(pl.col('count')).sum().alias('int_parse')) / len_
        return per_df.to_dicts()[0]


PL_Analysis_Klasses = [VCAnalysis, BasicAnalysis, PlTyping, ComputedDefaultSummaryStats,
                       HistogramAnalysis
                       ]


