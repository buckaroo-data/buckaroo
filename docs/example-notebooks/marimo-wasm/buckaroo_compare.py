import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _(BuckarooCompare, pd):
    # Create sample DataFrames
    df_a = pd.DataFrame({
        'a': [2, 3, 4, 5, 6, 7, 8],
        'b': [5, 4, 9, 4, 6, 7, 8],
        'same': [1,2,3,4,5,6,7],
        'c': [ 'foo', 'bar', None, None, 'bar', 'bar', 'foo']})

    # a doesn't line up 
    df_b = pd.DataFrame({
        'a': [3, 4, 5, 6, 7, 8, 9],
        'b': [4, 9, 7, 4, 4, 6, 4],
        'same': [2,3,4,5,6,7, 8],
        'd': ['foo', 'baz', 'baz', None, None, 'bar', 'bar'],
    })  # Notice the difference in the last row

    BuckarooCompare(df_a, df_b, join_columns=['a'], how='outer')
    return


@app.cell
async def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import sys
    if "pyodide" in sys.modules:  # make sure we're running in pyodide/WASM
        import micropip

        await micropip.install("buckaroo")
    import buckaroo
    from buckaroo import BuckarooInfiniteWidget, BuckarooWidget
    from buckaroo.dataflow.styling_core import merge_sds
    from buckaroo.dataflow.dataflow_extras import exception_protect
    import logging
    logger = logging.getLogger()
    return BuckarooInfiniteWidget, BuckarooWidget, logging, merge_sds, pd


@app.cell
def _(pd):

    def col_join_dfs(df1, df2, join_columns, how):
        df2_suffix = "|df2"
        for col in df1.columns:
            if df2_suffix in col:
                raise Exception("|df2 is a sentinel column name used by this tool, and it can't be used in a dataframe passed in, {col} violates that constraint")
        for col in df2.columns:
            if df2_suffix in col:
                raise Exception("|df2 is a sentinel column name used by this tool, and it can't be used in a dataframe passed in, {col} violates that constraint")

        df1_name, df2_name = "df_1", "df_2"

        col_order = df1.columns.to_list()
        for col in df2.columns:
            if col in col_order:
                #sckip columns in common
                continue
            col_order.append(col)
        eqs = {}

        for col in col_order:
            if col in df1.columns and col in df2.columns:
                eqs[col] = {'diff_count': (df1[col] != df2[col]).sum()}
            else:
                if col in df1.columns:
                    eqs[col] = {'diff_count': df1_name}
                else:
                    eqs[col] = {'diff_count': df2_name}
        column_config_overrides = {}


        eq_map = ["pink", "#73ae80", "#90b2b3", "#6c83b5"];
        for col in col_order:
            eq_col = eqs[col]['diff_count']

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
    return (col_join_dfs,)


@app.cell
def _(
    BuckarooInfiniteWidget,
    BuckarooWidget,
    col_join_dfs,
    logging,
    merge_sds,
):
    def BuckarooCompare(df1, df2, join_columns, how):
        #shoving all of this into a function is a bit of a hack to geta closure over cmp
        # ideally this would be better integrated into buckaroo via a special type of command
        # in the low code UI,  That way this could work alongside filtering and other pieces

        logger = logging.getLogger()
        logger.setLevel(logging.CRITICAL)

        logger.setLevel(logging.WARNING)



        base_a_klasses = BuckarooWidget.analysis_klasses.copy()
        class DatacompyBuckarooWidget(BuckarooWidget):
            analysis_klasses = base_a_klasses


        joined_df, column_config_overrides, init_sd = col_join_dfs(df1, df2, join_columns[0], how)

        #this is a bit of a hack and we are doing double work, for a demo it's expedient
        df1_bw = BuckarooInfiniteWidget(df1)
        df1_histogram_sd = {k: {'df1_histogram': v['histogram']} for k,v in df1_bw.dataflow.merged_sd.items()}

        df2_bw = BuckarooInfiniteWidget(df2)
        df2_histogram_sd = {k: {'df2_histogram': v['histogram']} for k,v in df2_bw.dataflow.merged_sd.items()}
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
            {'primary_key_val': 'diff_count',      'displayer_args': {'displayer': 'obj'}}
            ],
            debug=False
        )
        logger.setLevel(logging.WARNING)

        return dcbw
    return (BuckarooCompare,)


@app.cell
def _(pd):
    df_c = pd.DataFrame({
        'a': [2, 3, 4, 5, 6, 7, 8],
        'b': [ 5, 4, 4, 4, 6, 4, 4],
        'd': ['baz', 'baz', 'bar', None, None, 'bar', 'bar'],
        'f': [10, 1, 200, 150, 140, 130, 120]
    })  # Notice the difference in the last row
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
