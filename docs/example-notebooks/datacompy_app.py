import pandas as pd
import datacompy

from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
from buckaroo import BuckarooWidget
from buckaroo.dataflow.dataflow_extras import (
    merge_sds, exception_protect)
from traitlets import observe
from IPython.utils import io
import logging


def col_join_dfs(df1, df2, cmp):
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
            eqs[col] = {'unequality': col_stat['unequal_cnt']}
        else:
            if col in df1.columns:
                eqs[col] = {'unequality': df1_name}
            else:
                eqs[col] = {'unequality': df2_name}
    ret_df_columns = {}
    column_config_overrides = {}

    for col in col_order:
        eq_col = eqs[col]['unequality']
        if eq_col == df1_name:
            #it's only in df1
            ret_df_columns[col] = df1[col]
        elif eq_col == df2_name:
            #it's only in df2
            ret_df_columns[col] = df2[col]
        elif eq_col == 0:
            #columns are exactly the same
            ret_df_columns[col] = df1[col]
        else:
            ret_df_columns[col] = df1[col]
            #|df2 is a magic value, not a super fan, but it's also unlikely
            df2_col_name = col+"|df2"
            
            ret_df_columns[df2_col_name] = df2[col]

            
            column_config_overrides[df2_col_name] = {'merge_rule': 'hidden'}
            column_config_overrides[col] = {
                'tooltip_config': { 'tooltip_type':'simple', 'val_column': df2_col_name},
                'color_map_config': {
                    'color_rule': 'color_not_null',
                    'conditional_color': 'red',
                    'exist_column': df2_col_name},
            }

    ret_df = pd.DataFrame(ret_df_columns)
    for col, v in eqs.items():
        if v['unequality'] in ["df1", "df2"]:
            continue
        if v['unequality'] > 0:
            df2_col_name = col+"|df2"
            ret_df.loc[~(df1[col] == df2[col]), df2_col_name] = None

        
    return ret_df, column_config_overrides, eqs



def hide_orig_columns(orig_df, new_df):
    """
    convience method used for post_processing_functions that change the shape/name of columns,
    provides a summary_dict that removes all columns from the orig_df that don't occur in new_df
    """
    remove_columns = orig_df.columns.difference(new_df.columns)
    return {k: {'merge_rule': 'hidden'} for k in remove_columns}

def DatacompyBuckaroo(df1, df2):
    #shoving all of this into a function is a bit of a hack to geta closure over cmp
    # ideally this would be better integrated into buckaroo via a special type of command
    # in the low code UI,  That way this could work alongside filtering and other pieces
    
    logger = logging.getLogger()
    logger.setLevel(logging.CRITICAL)


    cmp = datacompy.Compare(
            df1, df2,
            join_columns='a',  # Column to join DataFrames on
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


    joined_df, column_config_overrides, init_sd = col_join_dfs(df1, df2, cmp)

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
        {'primary_key_val': 'unequality',      'displayer_args': {'displayer': 'obj'}}
        ],
        debug=False
    )
    logger.setLevel(logging.WARNING)

    return dcbw
