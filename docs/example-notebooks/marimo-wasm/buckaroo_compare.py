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
def _():
    from buckaroo.compare import col_join_dfs
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


        joined_df, column_config_overrides, init_sd = col_join_dfs(df1, df2, join_columns, how)

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
