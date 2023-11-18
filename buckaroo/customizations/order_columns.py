import pandas as pd
import numpy as np


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

def add_col_rankings(df, sdf):
    sdf.loc['one_distinct'] = 0

    only_ones = (sdf.loc['distinct_count'] <= 1)
    sdf.loc['one_distinct', only_ones[only_ones==True].index.values] = -20
    
    sdf.loc['first_col'] = 0
    sdf.loc['is_duplicate'] = 0
    set_when(sdf, 'is_datetime', 'datetime_score', 11, 0)
    
    set_when(sdf, 'is_integer', 'grouping_score_integer', -3, 0)
    set_when(sdf, 'is_numeric', 'grouping_score_numeric', -3, 5)
