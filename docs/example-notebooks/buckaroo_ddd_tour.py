import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _():
    from buckaroo import ddd_library as ddd
    from buckaroo.marimo_utils import marimo_unmonkeypatch; marimo_unmonkeypatch()

    return ddd, marimo_unmonkeypatch


@app.cell
def _(buckaroo, mo):
    from great_tables import GT
    from itables.widget import ITable
    def plain_disp(df):
        return mo.plain(df)
    def default_disp(df):
        return df

    def buckaroo_disp(df):
        return buckaroo.BuckarooInfiniteWidget(df ) #, pinned_rows=[])
    def great_tables_disp(df):
        try:
            return GT(df)
        except Exception as e:
            return e
    def itables_disp(df):
        return ITable(df)

    disp_options = {
        'plain': plain_disp,
        'default': default_disp,
        'buckaroo': buckaroo_disp,
        'great_tables': great_tables_disp,
        'itables': itables_disp
    
    }



    disp_func_dropdown = mo.ui.dropdown(
    options=disp_options,
    value='buckaroo',
    label='choose display widget')

    return (disp_func_dropdown,)


@app.cell
def _(disp_func_dropdown, dropdown_dict, marimo_unmonkeypatch, mo):
    # Welcome to the the Buckaroo styling gallery

    # Give Marimo and this gallery a little bit of time to load. The rest of the app and explanatory text will load in about 30 seconds. A lot is going on, python is being downloaded to run via Web Assembly in your browser.
    marimo_unmonkeypatch()
    disp_func = disp_func_dropdown.value 
    mo.vstack(
        [
         dropdown_dict,
         disp_func_dropdown,
         disp_func(dropdown_dict.value[0]),
        mo.md(dropdown_dict.value[1])])
    return


@app.cell
def _(buckaroo, mo):

    def get_code(df):
        return mo.ui.code_editor(buckaroo.BuckarooInfiniteWidget(df).get_story_config())

    return


@app.cell
def _():
    #mo.ui.code_editor(buckaroo.BuckarooInfiniteWidget(ddd.get_multiindex_index_df()).get_story_config())
    return


@app.cell
def _():
    #mo.ui.data_explorer(ddd.df_with_infinity())
    return


@app.cell
def _():
    #get_code(ddd.get_multiindex3_index_df())
    return


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_basic_df()

    _explain_md = """
    ##  basic_df
     This is a simple basic dataframe with column 'a'
    """
    basic_df_config = (_df, _explain_md)
    return (basic_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_basic_df2()

    _explain_md = """
    ##  basic_df2
     This dataframe has foo_col and bar_col for testing
    """
    basic_df2_config = (_df, _explain_md)
    return (basic_df2_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_basic_df_with_named_index()

    _explain_md = """
    ##  basic_df_with_named_index
     This dataframe has a named index called 'named_index'
    """
    basic_df_with_named_index_config = (_df, _explain_md)
    return (basic_df_with_named_index_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex_with_names_cols_df()

    _explain_md = """
    ##  multiindex_with_names_cols_df
     This dataframe has a multi_index columns with level names
    """
    multiindex_with_names_cols_df_config = (_df, _explain_md)
    return (multiindex_with_names_cols_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_tuple_cols_df()

    _explain_md = """
    ##  tuple_cols_df
     This dataframe has tuple column names from flattened multi_index
    """
    tuple_cols_df_config = (_df, _explain_md)
    return (tuple_cols_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex_index_df()

    _explain_md = """
    ##  multiindex_index_df
     This dataframe has a multi_index on the row index
    """
    multiindex_index_df_config = (_df, _explain_md)
    return (multiindex_index_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex3_index_df()

    _explain_md = """
    ##  multiindex3_index_df
     This dataframe has a 3-level multi_index on the row index
    """
    multiindex3_index_df_config = (_df, _explain_md)
    return (multiindex3_index_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex_index_multiindex_with_names_cols_df()

    _explain_md = """
    ##  multiindex_index_multiindex_with_names_cols_df
     This dataframe has multi_index on both rows and columns with named column levels
    """
    multiindex_index_multiindex_with_names_cols_df_config = (_df, _explain_md)
    return (multiindex_index_multiindex_with_names_cols_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex_index_with_names_multiindex_cols_df()

    _explain_md = """
    ##  multiindex_index_with_names_multiindex_cols_df
     This dataframe has multi_index on both rows (with names) and columns
    """
    multiindex_index_with_names_multiindex_cols_df_config = (_df, _explain_md)
    return (multiindex_index_with_names_multiindex_cols_df_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_multiindex_with_names_both()

    _explain_md = """
    ##  multiindex_with_names_both
     This dataframe has multi_index with names on both rows and columns
    """
    multiindex_with_names_both_config = (_df, _explain_md)
    return (multiindex_with_names_both_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.df_with_infinity()

    _explain_md = """
    ##  df_with_infinity
     This dataframe contains NaN, infinity, and negative infinity values
    """
    df_with_infinity_config = (_df, _explain_md)
    return (df_with_infinity_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.df_with_col_named_index()

    _explain_md = """
    ##  df_with_col_named_index
     This dataframe has a column actually named 'index'
    """
    df_with_col_named_index_config = (_df, _explain_md)
    return (df_with_col_named_index_config,)


@app.cell(hide_code=True)
def _(ddd):

    _df = ddd.get_df_with_named_index()

    _explain_md = """
    ##  df_with_named_index
     This dataframe has a named index called 'foo'
    """
    df_with_named_index_config = (_df, _explain_md)
    return (df_with_named_index_config,)


@app.cell
def _(
    basic_df2_config,
    basic_df_config,
    basic_df_with_named_index_config,
    df_with_col_named_index_config,
    df_with_infinity_config,
    df_with_named_index_config,
    mo,
    multiindex3_index_df_config,
    multiindex_index_df_config,
    multiindex_index_multiindex_with_names_cols_df_config,
    multiindex_index_with_names_multiindex_cols_df_config,
    multiindex_with_names_both_config,
    multiindex_with_names_cols_df_config,
    tuple_cols_df_config,
):
    # The DFs and configs are defined in the above hidden cells.  Unhide them for details
    dfs = {
        'basic_df_config': basic_df_config,
        'basic_df2_config': basic_df2_config,
        'basic_df_with_named_index_config': basic_df_with_named_index_config,
       # 'multiindex_cols_df_config': multiindex_cols_df_config,
        'multiindex_with_names_cols_df_config': multiindex_with_names_cols_df_config,
        'tuple_cols_df_config': tuple_cols_df_config,
        'multiindex_index_df_config': multiindex_index_df_config,
        'multiindex3_index_df_config': multiindex3_index_df_config,

        #'multi_index_with_names_index_df_config': multi_index_with_names_index_df_config,
        'multiindex_index_multiindex_with_names_cols_df_config': multiindex_index_multiindex_with_names_cols_df_config,
        'multiindex_index_with_names_multiindex_cols_df_config': multiindex_index_with_names_multiindex_cols_df_config,
        'multiindex_with_names_both_config': multiindex_with_names_both_config,
        'df_with_infinity_config': df_with_infinity_config,
        'df_with_col_named_index_config': df_with_col_named_index_config,
        'df_with_named_index_config': df_with_named_index_config,
    }

    dropdown_dict = mo.ui.dropdown(
        options=dfs,
        value="df_with_infinity_config",
        label="Choose the config",
    )

    return (dropdown_dict,)


@app.cell(hide_code=True)
async def _():
    import marimo as mo
    import pandas as pd
    import sys

    if "pyodide" in sys.modules:  # a hacky way to figure out if we're running in pyodide
        import micropip

        await micropip.install("buckaroo")

    import buckaroo
    from buckaroo import BuckarooInfiniteWidget


    # Extra utility functions and marimo overrides
    import numpy as np
    from buckaroo.marimo_utils import marimo_monkeypatch, BuckarooDataFrame as DataFrame

    # this overrides pd.read_csv and pd.read_parquet to return BuckarooDataFrames which overrides displays as BuckarooWidget, not the default marimo table
    marimo_monkeypatch()
    import json
    import re


    def format_json(obj):
        """
        Formats obj to json  string to remove unnecessary whitespace.
        Returns:
            The formatted JSON string.
        """
        json_string = json.dumps(obj, indent=4)
        # Remove whitespace before closing curly braces
        formatted_string = re.sub(r"\s+}", "}", json_string)
        # formatted_string = json_string
        return formatted_string
    return buckaroo, mo


if __name__ == "__main__":
    app.run()
