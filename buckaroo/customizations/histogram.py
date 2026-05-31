import numpy as np


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
            # str(k) important because the key must be a string, not a number or boolean
            """
            Warning: Received `true` for a non-boolean attribute `name`.

            If you want to write it to the DOM, pass a string instead: name="true" or name={value.toString()}.
            path
            Rectangle2@http://localhost:6006/node_modules/...
            """
            histogram.append({'name':str(k), 'cat_pop': percent })

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


