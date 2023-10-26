from functools import reduce
import pandas as pd
from pandas.io.json import dumps as pdumps
import numpy as np
from buckaroo.pluggable_analysis_framework import ColAnalysis
import warnings

def probable_datetime(ser):
    #turning off warnings in this single function is a bit of a hack.
    #Understandable since this is explicitly abusing pd.to_datetime
    #which throws warnings.

    warnings.filterwarnings('ignore')
    s_ser = ser.sample(np.min([len(ser), 500]))
    try:
        dt_ser = pd.to_datetime(s_ser)
        #pd.to_datetime(1_00_000_000_000_000_000) == pd.to_datetime('1973-01-01') 
        warnings.filterwarnings('default')
        if dt_ser.max() < pd.to_datetime('1973-01-01'):
            return False
        return True
        
    except Exception as e:
        warnings.filterwarnings('default')
        return False

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

class TypingStats(ColAnalysis):
    provides_summary = [
        'dtype', 'is_numeric', 'is_integer', 'is_datetime',]

    @staticmethod
    def summary(sampled_ser, summary_ser, ser):
        return dict(
            dtype=ser.dtype,
            is_numeric=pd.api.types.is_numeric_dtype(ser),
            is_integer=pd.api.types.is_integer_dtype(ser),
            is_datetime=probable_datetime(ser),
            memory_usage=ser.memory_usage()
            )

class DefaultSummaryStats(ColAnalysis):
    provides_summary = [
        'length', 'min', 'max', 'mean', 'nan_count', 'distinct_count',
        'distinct_per', 'empty_count', 'empty_per', 'unique_per', 'nan_per',
        'mode']

    summary_stats_display = [
        'dtype',
        'length', 'nan_count', 'distinct_count', 'empty_count',
        'empty_per', 'unique_per', 'nan_per', 'is_numeric', 'is_integer',
        'is_datetime', 'mode', 'min', 'max','mean']
    
    @staticmethod
    def summary(sampled_ser, summary_ser, ser):
        l = len(ser)
        val_counts = ser.value_counts()
        distinct_count= len(val_counts)
        nan_count = l - len(ser.dropna())
        unique_count = len(val_counts[val_counts==1])
        empty_count = val_counts.get('', 0)

        is_numeric = pd.api.types.is_numeric_dtype(ser)
        is_object = pd.api.types.is_object_dtype
        is_bool = pd.api.types.is_bool_dtype(ser)

        base_d = dict(
            length=l,
            nan_count=nan_count,
            distinct_count=distinct_count,
            distinct_per=distinct_count/l,
            empty_count=empty_count,
            empty_per=empty_count/l,
            unique_per=unique_count/l,
            nan_per=nan_count/l,
            mode=get_mode(ser),
            min=np.nan,
            max=np.nan)
        if is_numeric and not is_bool:
            base_d.update({
                'mean': ser.mean(),
                'min': ser.dropna().min(),
                'max': ser.dropna().max()})
        return base_d

def int_digits(n):
    if pd.isna(n):
        return 1
    if np.isnan(n):
        return 1
    if n == 0:
        return 1
    if np.sign(n) == -1:
        return int(np.floor(np.log10(np.abs(n)))) + 2
    return int(np.floor(np.log10(n)+1))



def numeric_histogram_labels(endpoints):
    left = endpoints[0]
    labels = []
    for edge in endpoints[1:]:
        labels.append("{:.0f}-{:.0f}".format(left, edge))
        left = edge
    return labels
#histogram_labels(endpoints)

def numeric_histogram(arr, nan_per):
    ret_histo = []
    nan_observation = {'name':'NA', 'NA':np.round(nan_per*100, 0)}
    if nan_per == 1.0:
        return [nan_observation]
    
    vals = arr.dropna()
    low_tail, high_tail = np.quantile(vals, 0.01), np.quantile(vals, 0.99)
    low_pass = arr>low_tail 
    high_pass = arr < high_tail
    meat = vals[low_pass & high_pass]
    populations, endpoints =np.histogram(meat, 10)
    
    labels = numeric_histogram_labels(endpoints)
    normalized_pop = populations / populations.sum()
    low_label = "%r - %r" % (vals.min(), low_tail)
    high_label = "%r - %r" % (high_tail, vals.max())
    ret_histo.append({'name': low_label, 'tail':1})
    for label, pop in zip(labels, normalized_pop):
        ret_histo.append({'name': label, 'population':np.round(pop * 100, 0)})
    high_label = "%r - %r" % (high_tail, vals.max())
    ret_histo.append({'name': high_label, 'tail':1})
    if nan_per > 0.0:
        ret_histo.append(nan_observation)
    return ret_histo


def histo_format(v, l):
    scaled = v/l
    

def categorical_dict(ser, val_counts, top_n_positions=7):
    l = len(ser)
    top = min(len(val_counts), top_n_positions)


    top_vals = val_counts.iloc[:top]
    #top_percentage = top_vals.sum() / l
    #if len(val_counts) > 5 and top_percentage < .05:
        
    rest_vals = val_counts.iloc[top:]
    histogram = top_vals.to_dict()


    full_long_tail = rest_vals.sum()
    unique_count = sum(val_counts == 1)
    long_tail = full_long_tail - unique_count
    if unique_count > 0:
        histogram['unique'] = np.round( (unique_count/l)* 100, 0)
    if long_tail > 0:
        histogram['longtail'] = np.round((long_tail/l) * 100,0)
    return histogram    

def categorical_histogram(ser, val_counts, nan_per, top_n_positions=7):
    nan_observation = {'name':'NA', 'NA':np.round(nan_per*100, 0)}
    cd = categorical_dict(ser, val_counts, top_n_positions)
    
    l = len(ser)
    histogram = []
    longtail_obs = {'name': 'longtail'}
    for k,v in cd.items():
        if k in ["longtail", "unique"]:
            longtail_obs[k] = v
            continue
        histogram.append({'name':k, 'cat_pop': np.round((v/l)*100,0) })
    if len(longtail_obs) > 1:
        histogram.append(longtail_obs)
    if nan_per > 0.0:
        histogram.append(nan_observation)
    return histogram


def histogram(ser, nan_per):
    is_numeric = pd.api.types.is_numeric_dtype(ser.dtype)
    val_counts = ser.value_counts()
    if is_numeric and len(val_counts)>5:
        temp_histo =  numeric_histogram(ser, nan_per)
        if len(temp_histo) > 5:
            #if we had basically a categorical variable encoded into an integer.. don't return it
            return temp_histo
    return categorical_histogram(ser, val_counts, nan_per)

class ColDisplayHints(ColAnalysis):
    requires_summary = ['min', 'max'] # What summary stats does this analysis provide
    provides_summary = [
        'is_numeric', 'is_integer', 'min_digits', 'max_digits', 'histogram', 'type']

    @staticmethod
    def summary(sampled_ser, summary_ser, ser):

        is_numeric = pd.api.types.is_numeric_dtype(sampled_ser)
        is_bool = pd.api.types.is_bool_dtype(sampled_ser)
        _type = "obj"
        if is_bool:
            _type = "boolean"
        elif is_numeric:
            if pd.api.types.is_float_dtype(sampled_ser):
                _type = "float"
            else:
                _type = "integer"
        elif pd.api.types.is_string_dtype(sampled_ser):
            _type = "string"
        base_dict = dict(
            type=_type,
            is_numeric=is_numeric,
            is_integer=pd.api.types.is_integer_dtype(sampled_ser),
            histogram=histogram(sampled_ser, summary_ser['nan_per']))

        if is_numeric and not is_bool:
            base_dict.update({
                'min_digits':int_digits(summary_ser.loc['min']),
                'max_digits':int_digits(summary_ser.loc['max']),
                })
        return base_dict

