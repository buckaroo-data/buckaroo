import polars as pl
import numpy as np
from polars import functions as F
from polars import datatypes as pdt
from buckaroo.customizations.analysis_utils import int_digits

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
    summary_stats_display = [
        'dtype',
        'length', 'nan_count', 'distinct_count', 'empty_count',
        'empty_per', 'unique_per', 'is_numeric', 
        'mode', 'min', 'max','mean']

    requires_summary = ['length', 'nan_count',
                        'unique_count', 'empty_count', 'distinct_count']
    provides_summary = ['distinct_per', 'empty_per', 'unique_per', 'nan_per']
                        

    @staticmethod
    def computed_summary(summary_dict):
        len_ = summary_dict['length']
        
        return dict(
            distinct_per=summary_dict['distinct_count']/len_,
            empty_per=summary_dict.get('empty_count',0)/len_,
            unique_per=summary_dict['unique_count']/len_,
            nan_per=summary_dict['nan_count']/len_)


class VCAnalysis(PolarsAnalysis):
    provides_summary = ['value_counts']
    select_clauses = [
        pl.all().exclude("counts").value_counts(sort=True)
        .implode().name.map(json_postfix('value_counts')),
        pl.selectors.matches("^counts$")
        .alias("not_counts")
        .value_counts(sort=True)
        .implode()
        .alias("counts").name.map(json_postfix('value_counts'))]
    

class BasicAnalysis(PolarsAnalysis):
    provides_summary = ['length', 'nan_count', 'min', 'max', 'min',
                        'mode', 'mean','unique_count', 'empty_count',
                        'distinct_count']
    select_clauses = [
        F.all().len().name.map(json_postfix('length')),
        F.all().null_count().name.map(json_postfix('nan_count')),
        F.all().min().name.map(json_postfix('min')),
        F.all().max().name.map(json_postfix('max')),
        F.all().mean().name.map(json_postfix('mean')),
        F.col(pl.Utf8).str.count_matches("^$").sum().name.map(json_postfix('empty_count')),
        F.all().approx_n_unique().name.map(json_postfix('distinct_count')),
        (F.all().len() - F.all().is_duplicated().sum()).name.map(json_postfix('unique_count')),
    ]

    @staticmethod
    def computed_summary(summary_dict):
        temp_df = pl.DataFrame({'vc': summary_dict['value_counts'].explode()}).unnest('vc')
        regular_col_vc_df = temp_df.select(pl.all().exclude('counts').alias('key'), pl.col('counts'))
        return dict(mode=regular_col_vc_df[0]['key'][0])


class PlTyping(PolarsAnalysis):
    column_ops = {'dtype':  ("all", lambda col_series: col_series.dtype)}
    provides_summary = ['dtype', '_type', 'is_numeric']


    @staticmethod
    def computed_summary(summary_dict):
        dt = summary_dict['dtype']

        res = {'is_numeric':  False}

        if dt in pdt.INTEGER_DTYPES:
            t = 'integer'
        elif dt in pdt.DATETIME_DTYPES:
            t = 'datetime'
        elif dt in pdt.FLOAT_DTYPES:
            t = 'float'
        elif dt == pdt.Utf8:
            t = 'string'
        elif dt == pdt.Boolean:
            t = 'boolean'
        else:
            t = 'unknown'
        if t in ('integer', 'float'):
            res['is_numeric'] = True
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
    hist_df = raw_hist.select(pl.col("break_point"), pl.selectors.ends_with("count").alias("count"))
    edges = hist_df['break_point'].to_list()
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

    requires_summary = ['min', 'max', 'value_counts', 'length', 'unique_count', 'is_numeric', 'nan_per']
    provides_summary = ['categorical_histogram', 'histogram']

    @staticmethod
    def computed_summary(summary_dict):
        vc = summary_dict['value_counts']
        cd = categorical_dict_from_vc(vc)
        is_numeric = summary_dict['is_numeric']
        nan_per = summary_dict['nan_per']
        if is_numeric and len(vc.explode()) > 5:
            #histogram_args = summary_dict['histogram_args']
            histogram_args = summary_dict['histogram_args']
            min_, max_, nan_per = summary_dict['min'], summary_dict['max'], summary_dict['nan_per']
            temp_histo =  numeric_histogram(histogram_args, min_, max_, nan_per)
            if len(temp_histo) > 5:
                #if we had basically a categorical variable encoded into an integer.. don't return it
                return {'histogram': temp_histo}
        return {'categorical_histogram': cd, 'histogram' : categorical_histogram_from_cd(cd, nan_per)}

class PlColDisplayHints(PolarsAnalysis):
    requires_summary = ['min', 'max', '_type', 'is_numeric']
    provides_summary = [
        'min_digits', 'max_digits', 'type', 'formatter']

    @staticmethod
    def computed_summary(summary_dict):
        base_dict = {'type':summary_dict['_type']}
        if summary_dict['_type'] == 'datetime':
            base_dict['formatter'] = 'default'
        if summary_dict['is_numeric']:
            base_dict.update({
                'min_digits':int_digits(summary_dict['min']),
                'max_digits':int_digits(summary_dict['max']),
                })
        return base_dict

PL_Analysis_Klasses = [VCAnalysis, BasicAnalysis, PlTyping, PlColDisplayHints,
                       HistogramAnalysis,
                       ComputedDefaultSummaryStats]

