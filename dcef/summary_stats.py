from functools import reduce
import pandas as pd

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
        nan_count = nan_count,
        distinct_count= distinct_count,
        empty_count = empty_count,
        empty_per = empty_count/l,
        unique_per = unique_count/l,
        nan_per = nan_count/l,
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
    num_df =  pd.DataFrame({col:numerize_column(df[col]) for col in corrable_cols})
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

def without(arr, search_keys):
    new_arr = []
    for v in arr:
        if v not in search_keys:
            new_arr.append(v)
    return new_arr

def one_directional_dict(raw_corr_pair):
    # convert from two way links to only one way based on first seen
    seen = []
    ret_corr_pair = {}
    for key, other_key_list in raw_corr_pair.items():
        seen.append(key)
        stripped_other = without(other_key_list, seen)
        if len(stripped_other) > 0:
            ret_corr_pair[key] = stripped_other
    return ret_corr_pair


def all_duplicates(raw_corr_pairs):
    flatlist = reduce(lambda a,b:a+b, raw_corr_pairs.values())
    return set(flatlist)

def order_columns(summary_stats_df, corr_pair_dict):
    sdf = summary_stats_df.copy()
    
    sdf.loc['one_distinct'] = 0
    only_ones = (sdf.loc['distinct_count'] <= 1)
    sdf.loc['one_distinct', only_ones[only_ones==True].index.values] = -20
    
    sdf.loc['is_duplicate'] = 0
    dups = list(all_duplicates(corr_pair_dict))
    sdf.loc['is_duplicate', dups] = -10
    
    sdf.loc['is_first_dup'] = 0
    first_dups = list(one_directional_dict(corr_pair_dict).keys())
    sdf.loc['is_first_dup', first_dups] = 5
    
    col_scores = sdf.loc[['one_distinct', 'is_duplicate', 'is_first_dup']].sum()
    return col_scores.sort_values().index.values[::-1]
    #return sdf

def make_df_metadata(df):
    summary_stats_df = summarize_df(df)
    corr_dict = get_cor_pair_dict(df, summary_stats_df)
    col_order = order_columns(summary_stats_df, corr_dict)
    ordered_df = df[col_order]
    ordered_sdf = summary_stats_df[col_order]
    return [ordered_df, ordered_sdf]

