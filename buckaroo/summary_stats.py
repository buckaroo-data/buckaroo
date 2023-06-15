from functools import reduce
import pandas as pd
from pandas.io.json import dumps as pdumps
import numpy as np




def probable_datetime(ser):
    s_ser = ser.sample(np.min([len(ser), 500]))
    try:
        dt_ser = pd.to_datetime(s_ser)
        #pd.to_datetime(1_00_000_000_000_000_000) == pd.to_datetime('1973-01-01') 
        if dt_ser.max() < pd.to_datetime('1973-01-01'):
            return False
        return True
        
    except Exception as e:
        return False

def get_mode(ser):
    mode_raw = ser.mode()
    if len(mode_raw) == 0:
        return np.nan
    else:
        return mode_raw.values[0]

def int_digits(n):
    if n == 0:
        return 1
    if np.sign(n) == -1:
        return int(np.floor(np.log10(np.abs(n)))) + 2
    return int(np.floor(np.log10(n)+1))


def histogram(ser):
    raw_counts, bins = np.histogram(ser, 10)
    scaled_counts = np.round(raw_counts/raw_counts.sum(),2)
    return [scaled_counts, bins]

def table_sumarize_num_ser(ser):
    if len(ser) == 0:
        return dict(is_numeric=False)
    return dict(
        is_numeric=True,
        is_integer=pd.api.types.is_integer_dtype(ser),
        min_digits=int_digits(ser.min()),
        max_digits=int_digits(ser.max()),
        histogram=histogram(ser))

def table_sumarize_obj_ser(ser):
    return dict(
        is_numeric=False)

def table_sumarize_ser(ser):
    if pd.api.types.is_numeric_dtype(ser.dtype):
        return table_sumarize_num_ser(ser.dropna())
    else:
        return table_sumarize_obj_ser(ser)
    
def table_sumarize(df):
    table_hints = {col:table_sumarize_ser(df[col]) for col in df}
    table_hints['index'] = table_sumarize_ser(df.index)
    return table_hints


def summarize_string(ser):
    l = len(ser)
    val_counts = ser.value_counts()
    distinct_count= len(val_counts)
    nan_count = l - len(ser.dropna())
    unique_count = len(val_counts[val_counts==1])
    empty_count = val_counts.get('', 0)

    return dict(
        dtype=ser.dtype,
        length=l,
        min='',
        max='',
        mean='',
        nan_count = nan_count,
        distinct_count= distinct_count,
        distinct_per = distinct_count/l,
        empty_count = empty_count,
        empty_per = empty_count/l,
        unique_per = unique_count/l,
        nan_per = nan_count/l,
        is_numeric=pd.api.types.is_numeric_dtype(ser),
        is_integer=pd.api.types.is_integer_dtype(ser),
        is_datetime=probable_datetime(ser),
        mode=get_mode(ser))

def summarize_numeric(ser):

    num_stats = summarize_string(ser)
    num_stats.update(dict(
        min=ser.min(),
        max=ser.max(),
        mean=ser.mean()))

    return num_stats

def summarize_column(ser):
    if pd.api.types.is_numeric_dtype(ser.dtype):
        return summarize_numeric(ser)
    else:
        return summarize_string(ser)

def summarize_df(df):
    summary_df = pd.DataFrame({col:summarize_column(df[col]) for col in df})
    return summary_df

def make_num_categorical(ser):
    return ser.dropna().astype('category', errors='ignore').cat.codes

def get_cor_pair_dict(df, sdf):

    corrable_cols = sdf.columns[
        (sdf.loc['distinct_count'] > 1) &
        ((sdf.loc['distinct_per'] < .3) |
         (sdf.loc['distinct_count'] < 50))]

    num_df =  pd.DataFrame({col:make_num_categorical(df[col]) for col in corrable_cols})

    corr_df = num_df.corr()
    high_corr_df = corr_df[corr_df > 0.6]
    
    #print(high_corr_df)

    cor_dict = {}
    for col in high_corr_df.columns:
        #columns with high correlation that aren't the column itself
        other_cor_cols = high_corr_df[col].dropna().drop(col)
        cor_cols = other_cor_cols.index.values
        if len(cor_cols) > 0:
            cor_dict[col] = cor_cols.tolist()
    return cor_dict

def set_when(df, cond_row_name, target_row_name, true_val, false_val):
    true_row = df.loc[cond_row_name]
    df.loc[target_row_name] = false_val
    df.loc[target_row_name, true_row[true_row==True].index.values] = true_val
    return df

def without(arr, search_keys):
    new_arr = []
    for v in arr:
        if v not in search_keys:
            new_arr.append(v)
    return new_arr

def find_groupings(corr_pairs):
    all_groupings = []
    for key, other_key_list in corr_pairs.items():
        ab = other_key_list.copy()
        ab.append(key)
        all_groupings.append(set(ab))
    return np.unique(all_groupings)

def order_groupings(grps, ranked_cols):
    first_cols, rest_cols = [], []
    for col in ranked_cols:
        for grp in grps:
            if col in grp:
                first_cols.append(col)
                rest_cols.extend(list(without(grp, [col])))
                grps = without(grps, [grp])
    return list(set(first_cols)), list(set(rest_cols))

def order_columns(sdf, corr_pair_dict):
    grouping_col_scores = sdf.loc[['grouping_score_integer', 'grouping_score_numeric']].sum()
    duplicate_col_rankings = grouping_col_scores.sort_values().index[::-1].values

    groupings = find_groupings(corr_pair_dict)
    #print("groupings", groupings)
    first_cols, duplicate_cols = order_groupings(groupings, duplicate_col_rankings)
    
    #print("duplicate_cols", duplicate_cols)
    sdf.loc['first_col':, first_cols] = 5
    sdf.loc['is_duplicate':, duplicate_cols] = -5
    #print(sdf.index)
    col_scores = sdf.loc[['one_distinct', 'first_col', 'datetime_score', 'is_duplicate']].sum()
    return col_scores.sort_values().index.values[::-1]

def reorder_columns(df):
    tdf_stats = summarize_df(df)
    cpd = get_cor_pair_dict(df, tdf_stats)
    # try:
    col_order = order_columns(tdf_stats, cpd)
    return df[col_order]

def get_outlier_idxs(ser):
    if not pd.api.types.is_numeric_dtype(ser.dtype):
        return []
    outlier_idxs = []
    outlier_idxs.extend(ser.nlargest(5).index)
    outlier_idxs.extend(ser.nsmallest(5).index)
    return outlier_idxs

def sample(df, sample_size=500, include_outliers=True):
    if len(df) <= sample_size:
        return df
    sdf = df.sample(np.min([sample_size, len(df)]))
    if include_outliers:
        outlier_idxs = []
        for col in df.columns:
            outlier_idxs.extend(get_outlier_idxs(df[col]) )
        outlier_idxs.extend(sdf.index)
        uniq_idx = np.unique(outlier_idxs)
        return df.loc[uniq_idx]
    return sdf

def add_col_rankings(df, sdf):
    sdf.loc['one_distinct'] = 0

    only_ones = (sdf.loc['distinct_count'] <= 1)
    sdf.loc['one_distinct', only_ones[only_ones==True].index.values] = -20
    
    sdf.loc['first_col'] = 0
    sdf.loc['is_duplicate'] = 0
    set_when(sdf, 'is_datetime', 'datetime_score', 11, 0)
    
    set_when(sdf, 'is_integer', 'grouping_score_integer', -3, 0)
    set_when(sdf, 'is_numeric', 'grouping_score_numeric', -3, 5)

FAST_SUMMARY_WHEN_GREATER = 1_000_000
class DfStats(object):
    def __init__(self,
            df,
            annotate_funcs=[add_col_rankings],
            # summary_func=summary_stats.summarize_df,
            # order_col_func=summary_stats.order_columns):
            summary_func=summarize_df,
            order_col_func=order_columns):

        rows = len(df)
        cols = len(df.columns)
        item_count = rows * cols


        if item_count > FAST_SUMMARY_WHEN_GREATER:
            df = df.sample(np.min([50_000, len(df)]))
        self.df = df
        self.sdf = summary_func(df)
        for func in annotate_funcs:
            func(df, self.sdf)
        try:
            self.cpd = get_cor_pair_dict(self.df, self.sdf)
            self.col_order = order_col_func(self.sdf, self.cpd)
        except Exception as e:
            print(e)
            self.col_order = self.df.columns

        
