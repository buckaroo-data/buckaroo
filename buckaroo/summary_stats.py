from functools import reduce
import pandas as pd
import numpy as np


def summarize_string(ser):
    l = len(ser)
    val_counts = ser.value_counts()
    distinct_count= len(val_counts)
    nan_count = l - len(ser.dropna())
    unique_count = len(val_counts[val_counts==1])
    empty_count = val_counts.get('', 0)

    #[pd.api.types.is_integer_dtype(df2[col]) for col in df2.columns]
    #[pd.api.types.is_numeric_dtype(df2[col]) for col in df2.columns]

    return dict(
        dtype=ser.dtype,
        length=l,
        nan_count = nan_count,
        distinct_count= distinct_count,
        empty_count = empty_count,
        empty_per = empty_count/l,
        unique_per = unique_count/l,
        nan_per = nan_count/l,
        is_numeric=pd.api.types.is_numeric_dtype(ser),
        is_integer=pd.api.types.is_integer_dtype(ser),
        mode=ser.mode().values[0])

def summarize_numeric(ser):

    num_stats = dict(
        min=ser.min(),
        max=ser.max(),
        mean=ser.mean())
    num_stats.update(summarize_string(ser))
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
    ser_uniq = ser.unique()
    name_to_idx = {name:idx for idx, name in enumerate(ser_uniq)}
    #needs to be vectorized
    num_categorical = ser.apply(lambda x:name_to_idx[x])
    return num_categorical

def get_cor_pair_dict(df, summary_stats):
    #we need to remove columns with only nans or a single value, they mess up corr()

    #this needs to be vectorized
    corrable_cols = [col for col in df if summary_stats[col]['distinct_count'] > 1]
    #print("corrable_cols", corrable_cols)
    #num_df =  pd.DataFrame({col:numerize_column(df[col]) for col in corrable_cols})

    num_df =  pd.DataFrame({col:make_num_categorical(df[col]) for col in corrable_cols})

    corr_df = num_df.corr()
    high_corr_df = corr_df[corr_df > 0.99]
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
    return first_cols, rest_cols

def order_columns(summary_stats_df, corr_pair_dict):
    sdf = summary_stats_df.copy()
    sdf.loc['one_distinct'] = 0

    only_ones = (sdf.loc['distinct_count'] <= 1)
    sdf.loc['one_distinct', only_ones[only_ones==True].index.values] = -20
    
    sdf.loc['first_col'] = 0
    sdf.loc['is_duplicate'] = 0
    
    set_when(sdf, 'is_integer', 'grouping_score_integer', -3, 0)
    set_when(sdf, 'is_numeric', 'grouping_score_numeric', -3, 5)
    grouping_col_scores = sdf.loc[['grouping_score_integer', 'grouping_score_numeric']].sum()
    duplicate_col_rankings = grouping_col_scores.sort_values().index[::-1].values

    groupings = find_groupings(corr_pair_dict)
    first_cols, duplicate_cols = order_groupings(groupings, duplicate_col_rankings)
    
    sdf.loc['first_col':, first_cols] = 5
    sdf.loc['is_duplicate':, duplicate_cols] = -5
    
    col_scores = sdf.loc[['one_distinct', 'first_col', 'is_duplicate']].sum()
    return col_scores.sort_values().index.values[::-1]

def reorder_columns(df):
    tdf_stats = summarize_df(df)
    cpd = get_cor_pair_dict(df, tdf_stats)
    col_order = order_columns(tdf_stats, cpd)
    return df[col_order]

def make_df_metadata(df):
    summary_stats_df = summarize_df(df)
    corr_dict = get_cor_pair_dict(df, summary_stats_df)
    col_order = order_columns(summary_stats_df, corr_dict)
    ordered_df = df[col_order]
    ordered_sdf = summary_stats_df[col_order]
    return [ordered_df, ordered_sdf]

