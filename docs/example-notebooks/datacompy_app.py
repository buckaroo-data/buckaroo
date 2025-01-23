import pandas as pd
import datacompy

from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
from buckaroo import BuckarooWidget
from buckaroo.dataflow.dataflow_extras import (
    merge_sds, exception_protect)
from traitlets import observe
from IPython.utils import io
import logging


def col_join_dfs(df1, df2, cmp, join_columns, how):
    df2_suffix = "|df2"
    for col in df1.columns:
        if df2_suffix in col:
            raise Exception("|df2 is a sentinel column name used by this tool, and it can't be used in a dataframe passed in,  {col} violates that constraint")
    for col in df2.columns:
        if df2_suffix in col:
            raise Exception("|df2 is a sentinel column name used by this tool, and it can't be used in a dataframe passed in,  {col} violates that constraint")
        
    df1_name = cmp.df1_name
    df2_name = cmp.df2_name

    col_order = df1.columns.to_list()
    for col in df2.columns:
        if col in col_order:
            continue
            
        col_order.append(col)
    eqs = {}
    def get_col_stat(col_name):
        for obj in cmp.column_stats:
            if obj['column'] == col_name:
                return obj
        return None
            
    for col in col_order:
        col_stat = get_col_stat(col)
        if col_stat:
            eqs[col] = {'inequality': col_stat['unequal_cnt']}
        else:
            if col in df1.columns:
                eqs[col] = {'inequality': df1_name}
            else:
                eqs[col] = {'inequality': df2_name}

    column_config_overrides = {}



    eq_map = ["pink", "#73ae80", "#90b2b3", "#6c83b5"];
    for col in col_order:
        eq_col = eqs[col]['inequality']

    m_df = pd.merge(df1, df2, on=join_columns, how=how, suffixes=["", df2_suffix])
    for b_col in m_df.columns:
        if b_col.endswith("|df2"):
            a_col = b_col.removesuffix(df2_suffix)

    
    df_1_membership = m_df['a'].isin(df1[join_columns]).astype('Int8') 
    df_2_membership = (m_df['a'].isin(df2[join_columns]).astype('Int8') *2)
    m_df['membership'] = df_1_membership + df_2_membership
    column_config_overrides['membership'] = {'merge_rule': 'hidden'}
    both_columns = [c for c in m_df.columns if df2_suffix in c] #columns that occur in both
    for b_col in both_columns:
        a_col = b_col.removesuffix(df2_suffix)
        col_neq = (m_df[a_col] == m_df[b_col]).astype('Int8') * 4 

        eq_col = a_col + "|eq"
        #by adding 2 and 4 to the boolean columns we get unique values
        #for combinations of is_null and value equal
        # this is then colored on the column
        
        m_df[eq_col] = col_neq + m_df['membership']

        column_config_overrides[b_col] = {'merge_rule': 'hidden'}
        column_config_overrides[eq_col] = {'merge_rule': 'hidden'}
        column_config_overrides[a_col] = {
            'tooltip_config': { 'tooltip_type':'simple', 'val_column': b_col},
            'color_map_config': {
                'color_rule': 'color_categorical',
                'map_name': eq_map,
                'val_column': eq_col }}
        
    #where did the row come from 
    column_config_overrides[join_columns] =  {'color_map_config': {
          'color_rule': 'color_categorical',
          'map_name': eq_map,
          'val_column': 'membership'
        }}
    return m_df, column_config_overrides, eqs



def hide_orig_columns(orig_df, new_df):
    """
    convience method used for post_processing_functions that change the shape/name of columns,
    provides a summary_dict that removes all columns from the orig_df that don't occur in new_df
    """
    remove_columns = orig_df.columns.difference(new_df.columns)
    return {k: {'merge_rule': 'hidden'} for k in remove_columns}

def DatacompyBuckaroo(df1, df2, join_columns, how):
    #shoving all of this into a function is a bit of a hack to geta closure over cmp
    # ideally this would be better integrated into buckaroo via a special type of command
    # in the low code UI,  That way this could work alongside filtering and other pieces
    
    logger = logging.getLogger()
    logger.setLevel(logging.CRITICAL)


    
    cmp = datacompy.Compare(
            df1, df2,
            join_columns,
            abs_tol=0,  # Absolute tolerancej
            rel_tol=0) # Relative tolerance
    logger.setLevel(logging.WARNING)
    def get_df_header(cmp):
        df_header = pd.DataFrame({        
            "DataFrame": [cmp.df1_name, cmp.df2_name],
            "Columns": [cmp.df1.shape[1], cmp.df2.shape[1]],
            "Rows": [cmp.df1.shape[0], cmp.df2.shape[0]]})
        return df_header.T
    
    def column_summary(cmp):
        df1_name = cmp.df1_name
        df2_name = cmp.df2_name
        col_df = pd.DataFrame({
            "Columns in common":[len(cmp.intersect_columns())],
            f"Columns in {df1_name} not in {df2_name}":[ cmp.df1_unq_columns().items],
            f"Columns in {df2_name} not in {df1_name}":[ cmp.df2_unq_columns().items]})
        return col_df.T
    
    def row_summary(cmp):
        # write pad arr function to pad array to number of join columns
        match_criteria = "index"
        if not cmp.on_index:
            match_criteria = ", ".join(cmp.join_columns)
            has_dupes = cmp._any_dupes
            df1_name = cmp.df1_name
            df2_name = cmp.df2_name
    
        row_df = pd.DataFrame({
            "Matched On": [match_criteria],
            "Any Duplicates on match values": [has_dupes],
            "Number of rows in common": cmp.intersect_rows.shape[0],
            f"Number of rows in {df1_name} but not in {df2_name}": cmp.df1_unq_rows.shape[0],
            f"Number of rows in {df2_name} but not in {df1_name}": cmp.df2_unq_rows.shape[0],
            "Number of rows with some compared columns unequal": [cmp.intersect_rows.shape[0] - cmp.count_matching_rows()],
            "Number of rows with all compared columns equal": [cmp.count_matching_rows()]
        })
        return row_df.T
    
    def column_matching(cmp):
        unequal_count = len([col for col in cmp.column_stats if col["unequal_cnt"] > 0])
        equal_count = len([col for col in cmp.column_stats if col["unequal_cnt"] == 0])
        total_unequal_count = sum(col["unequal_cnt"] for col in cmp.column_stats)
    
        col_df = pd.DataFrame({
            "Number of columns compared with some values unequal": [unequal_count],
            "Number of columns with all values equal": [equal_count],
            "Total number of values which compare unequal": [total_unequal_count]})
        return col_df.T
    
    def match_stats(cmp, sample_count=10):
        match_stats = []
        match_sample = []
        any_mismatch = False
        for column in cmp.column_stats:
            if not column["all_match"]:
                any_mismatch = True
                match_stats.append({
                    "Column": column["column"],
                    f"{cmp.df1_name} dtype": column["dtype1"],
                    f"{cmp.df2_name} dtype": column["dtype2"],
                    "# Unequal": column["unequal_cnt"],
                    "Max Diff": column["max_diff"],
                    "# Null Diff": column["null_diff"]})
            if column["unequal_cnt"] > 0:
                match_sample.append(
                    cmp.sample_mismatch(
                        column["column"], sample_count, for_display=True))
    
        df_match_stats = pd.DataFrame(match_stats)
        df_match_stats.sort_values("Column", inplace=True)
        return df_match_stats.T

    class DfHeader(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            ab = get_df_header(cmp)
            print("ab", ab)
            return [ab, hide_orig_columns(df, ab)]
        post_processing_method = "Df Headers"


    class ColumnSummary(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            col_summary_df = column_summary(cmp)
            return [col_summary_df, hide_orig_columns(df, col_summary_df)]
        post_processing_method = "Column Summary"

    class RowSummary(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            new_df = row_summary(cmp)
            return [new_df, hide_orig_columns(df, new_df)]
        post_processing_method = "Row Summary"

    class ColumnMatching(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            new_df = column_matching(cmp)
            return [new_df, hide_orig_columns(df, new_df)]
        post_processing_method = "Column Matching"

    class MatchStats(ColAnalysis):
        @classmethod
        def post_process_df(kls, df):
            new_df = match_stats(cmp)
            return [new_df, hide_orig_columns(df, new_df)]
        post_processing_method = "Match Stats"

        
    datacompy_post_processing_klasses = [
        DfHeader, ColumnSummary, RowSummary, ColumnMatching, MatchStats]
    
    base_a_klasses = BuckarooWidget.analysis_klasses.copy()
    base_a_klasses.extend(datacompy_post_processing_klasses)
    class DatacompyBuckarooWidget(BuckarooWidget):
        analysis_klasses = base_a_klasses


    joined_df, column_config_overrides, init_sd = col_join_dfs(df1, df2, cmp, join_columns[0], how)

    #this is a bit of a hack and we are doing double work, for a demo it's expedient
    df1_bw = BuckarooWidget(df1)
    df1_histogram_sd = {k: {'df1_histogram': v['histogram']} for k,v in df1_bw.merged_sd.items()}

    df2_bw = BuckarooWidget(df2)
    df2_histogram_sd = {k: {'df2_histogram': v['histogram']} for k,v in df2_bw.merged_sd.items()}
    full_init_sd = merge_sds(
        {'index':{}}, # we want to make sure index is the first column recognized by buckaroo
        init_sd,
        df1_histogram_sd, df2_histogram_sd
    )
    logger.setLevel(logging.CRITICAL)
    dcbw = DatacompyBuckarooWidget(
        joined_df, column_config_overrides=column_config_overrides, init_sd=full_init_sd,
        pinned_rows=[
        {'primary_key_val': 'dtype',           'displayer_args': {'displayer': 'obj'}},
        {'primary_key_val': 'df1_histogram',   'displayer_args': {'displayer': 'histogram'}},
        {'primary_key_val': 'df2_histogram',   'displayer_args': {'displayer': 'histogram'}},
        {'primary_key_val': 'inequality',      'displayer_args': {'displayer': 'obj'}}
        ],
        debug=False
    )
    logger.setLevel(logging.WARNING)

    return dcbw
