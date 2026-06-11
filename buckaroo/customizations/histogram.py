import math
import numpy as np


def force_float(n):
    if isinstance(n, np.floating):
        return n.item()
    else:
        return n


def _trim(s: str) -> str:
    """Strip trailing zeros after the decimal point only."""
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def fmt_num(value: float, step: float, ref: float) -> str:
    """Format one histogram boundary — SI prefix (K/M/B/T) + step-based precision."""
    if step > 0 and abs(value) < step * 1e-9:
        value = 0.0
    for threshold, suffix in [(1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')]:
        if ref >= threshold:
            scaled = value / threshold
            step_s = step / threshold
            dec = max(0, -math.floor(math.log10(step_s)) + 1) if step_s > 0 else 1
            dec = min(dec, 2)
            return _trim(f"{scaled:.{dec}f}") + suffix
    dec = max(0, -math.floor(math.log10(step)) + 1) if step > 0 else 0
    dec = min(dec, 6)
    return _trim(f"{value:.{dec}f}")


def _join_bounds(lo_s: str, hi_s: str) -> str:
    # any negative bound makes '–' ambiguous: the minus sign and en-dash
    # are near-identical glyphs
    sep = '<>' if (lo_s.startswith('-') or hi_s.startswith('-')) else '–'
    return f"{lo_s}{sep}{hi_s}"


def fmt_bucket(lo: float, hi: float, step: float, ref: float) -> str:
    return _join_bounds(fmt_num(lo, step, ref), fmt_num(hi, step, ref))


def fmt_tail_bucket(lo: float, hi: float, step: float) -> str:
    """Format a tail bucket — per-bound SI prefix so an outlier bound
    doesn't drag a small bound to '0K'."""
    return _join_bounds(fmt_num(lo, step, abs(lo)), fmt_num(hi, step, abs(hi)))


def numeric_histogram_labels(endpoints):
    left = endpoints[0]
    labels = []
    min_val = float(endpoints[0])
    max_val = float(endpoints[-1])
    step = (max_val - min_val) / max(len(endpoints) - 1, 1)
    ref = max(abs(min_val), abs(max_val))
    for edge in endpoints[1:]:
        labels.append(fmt_bucket(float(left), float(edge), step, ref))
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
    normalized_pop = histogram_args['normalized_populations']

    min_f, max_f = force_float(min_), force_float(max_)
    # precision from the meat bucket width — the full min/max range is
    # outlier-inflated and would collapse small tail bounds to '0K'
    e_lo, e_hi = float(endpoints[0]), float(endpoints[-1])
    step = (e_hi - e_lo) / max(len(endpoints) - 1, 1)
    low_label = fmt_tail_bucket(min_f, force_float(low_tail), step)
    ret_histo.append({'name': low_label, 'tail':1})
    for label, pop in zip(labels, normalized_pop):
        ret_histo.append({'name': label, 'population':np.round(pop * 100, 0)})
    high_label = fmt_tail_bucket(force_float(high_tail), max_f, step)
    ret_histo.append({'name': high_label, 'tail':1})
    if nan_per > 0.0:
        ret_histo.append(nan_observation)
    return ret_histo


