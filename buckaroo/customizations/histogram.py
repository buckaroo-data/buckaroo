import pandas as pd
import numpy as np
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis


def force_float(n):
    if isinstance(n, np.floating):
        return n.item()
    else:
        return n
    
def numeric_histogram_labels(endpoints):
    left = endpoints[0]
    labels = []
    for edge in endpoints[1:]:
        
        labels.append("{:.0f}-{:.0f}".format(force_float(left), force_float(edge)))
        left = edge
    return labels

def categorical_dict(len_, val_counts, top_n_positions=7):
    top = min(len(val_counts), top_n_positions)
    top_vals = val_counts.iloc[:top]
        
    rest_vals = val_counts.iloc[top:]
    try:
        histogram = top_vals.to_dict()
    except TypeError:
        top_vals.index = top_vals.index.map(str)
        histogram = top_vals.to_dict()

    full_long_tail = rest_vals.sum()
    unique_count = sum(val_counts == 1)
    long_tail = full_long_tail - unique_count
    if long_tail > 0:
        histogram['longtail'] = np.round((long_tail/len_) * 100,0)
    if unique_count > 0:
        histogram['unique'] = np.round( (unique_count/len_)* 100, 0)
    return histogram    


def categorical_histogram(length:int, val_counts, nan_per:float, top_n_positions=7):
    nan_observation = {'name':'NA', 'NA':np.round(nan_per*100, 0)}
    cd = categorical_dict(length, val_counts, top_n_positions)
    
    histogram = []
    for k,v in cd.items():
        if k in ["longtail", "unique"]:
            continue

        percent = np.round((v/length)*100,0)
        if percent > .3:
            histogram.append({'name':k, 'cat_pop': percent })
    # I want longtail and unique to come last
    for k,v in cd.items():
        if k in ["longtail", "unique"]:
            obs = {'name': k}
            obs[k] = v
            histogram.append(obs)
    if nan_per > 0.0:
        histogram.append(nan_observation)
    return histogram

# histogram_args = TypedDict('histogram_args', {
#     'meat_histogram': Tuple[npt.NDArray[np.intp], npt.NDArray[Any]],
#     'low_tail': float, 'high_tail':float})

# class Histogram_Args(TypedDict):
#     meat_histogram: Tuple[List[int], List[float]]
#     normalized_populations:List[float]
#     low_tail: float
#     high_tail: float

#def numeric_histogram(histogram_args: Histogram_Args , min_, max_, nan_per):
def numeric_histogram(histogram_args, min_, max_, nan_per):
    low_tail, high_tail = histogram_args['low_tail'], histogram_args['high_tail']
    ret_histo = []
    nan_observation = {'name':'NA', 'NA':np.round(nan_per*100, 0)}
    if nan_per == 1.0:
        return [nan_observation]
    
    populations, endpoints = histogram_args['meat_histogram']
    
    labels = numeric_histogram_labels(endpoints)
    #normalized_pop = populations / populations.sum()
    normalized_pop = histogram_args['normalized_populations']
    low_label = "%r - %r" % (force_float(min_), force_float(low_tail))

    ret_histo.append({'name': low_label, 'tail':1})
    for label, pop in zip(labels, normalized_pop):
        ret_histo.append({'name': label, 'population':np.round(pop * 100, 0)})
    high_label = "%r - %r" % (force_float(high_tail), force_float(max_))
    ret_histo.append({'name': high_label, 'tail':1})
    if nan_per > 0.0:
        ret_histo.append(nan_observation)
    return ret_histo


class Histogram(ColAnalysis):
    provides_defaults = dict(
        histogram= [[],[]], histogram_args=[], histogram_bins=[])
                    
    @staticmethod
    def series_summary(sampled_ser, ser):
        """
        https://stackoverflow.com/questions/11882393/matplotlib-disregard-outliers-when-plotting
        """
        if not pd.api.types.is_numeric_dtype(ser):
            return dict(histogram_args={})
        if pd.api.types.is_bool_dtype(ser):
            return dict(histogram_args={})
        if not ser.index.is_unique:
            ser.index = pd.RangeIndex(len(ser))
        vals = ser.dropna()
        if len(vals) == 0:
            return dict(histogram_args={})
        low_tail = np.quantile(vals, 0.01)
        high_tail =  np.quantile(vals, 0.99)
        low_pass  = ser > low_tail 
        high_pass = ser < high_tail
        meat = vals[low_pass & high_pass]
        if len(meat) == 0:
            return dict(histogram_args={})
   
        meat_histogram=np.histogram(meat, 10)
        populations, _ = meat_histogram
        return dict(
            histogram_bins = meat_histogram[1],
            histogram_args=dict(
                meat_histogram=meat_histogram,
                normalized_populations=(populations/populations.sum()).tolist(),
                low_tail=low_tail,
                high_tail=high_tail))

    requires_summary = ['value_counts', 'nan_per', 'is_numeric', 'length',
                        'min', 'max',]


    @staticmethod
    def computed_summary(summary_dict):
        is_numeric = summary_dict['is_numeric']
        value_counts = summary_dict['value_counts']
        nan_per = summary_dict['nan_per']
        if is_numeric and len(value_counts) > 5 and summary_dict['histogram_args']:
            histogram_args = summary_dict['histogram_args']
            min_, max_ = summary_dict['min'], summary_dict['max']
            temp_histo =  numeric_histogram(histogram_args, min_, max_, nan_per)
            if len(temp_histo) > 5:
                #if we had basically a categorical variable encoded into an integer.. don't return it
                return {'histogram': temp_histo}
        length = summary_dict['length']
        return {'histogram':categorical_histogram(length, value_counts, nan_per)}
