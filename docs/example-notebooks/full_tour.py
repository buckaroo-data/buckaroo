import marimo

__generated_with = "0.12.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    # Tour of Buckaroo
    Buckaroo expedites the core task of data work - looking at the data - by showing histograms and summary stats with every DataFrame.

    This notebook gives a tour of Buckaroo features.

    * Fast - Instantly scrollable dataframes
    * Histograms and Summary stats
    * Sorting and Search
    * Autocleaning and the lowcode UI
    * Styling and other customizations
    """
    )
    return


@app.cell
def _(pd):
    citibike_df = pd.read_parquet("./citibike-trips-2016-04.parq")
    citibike_df
    return (citibike_df,)


@app.cell
def _(mo):
    import buckaroo  # for most notebook environments


    mo.md("""## Running buckaroo

    Buckaroo runs in many python notebook environments including Jupyter Notebook, Jupyter Lab, [Marimo](https://marimo.io/), VS Code, and Google Colab.

    to get started install buckaroo in your python environment with pip or uv
    ```bash
    pip install buckaroo
    uv add buckaroo
    ```
    then run 
    ```python
    import buckaroo```
    in the notebook.  Buckaroo will become the default way of displaying dataframes in that environment.
    """)
    return (buckaroo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Demonstrating Buckaroo on Citibike data.
    Click `main` below Σ to toggle the summary stats view.

    You can click on column headers like "tripduration" to cycle through sort.
    """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Histograms

    Histograms are built into Buckaroo. They enable users to quickly identify distributions of data in columns
    ### Common histogram shapes

    The following shows the most common shapes you will see in histograms, allowing you to quickly identify patterns

    Notice the three columns on the right. Those are categorical histograms as opposed to numerical histograms
    ## Categorical histograms

    Categorical histograms have special colors and patterns for NA/NaN, longtail (values that occur at least twice) and unique Categorical histograms are always arranged from most frequent on the left to least frequent on the right.

    When a column is numerical, but has less than 5 distinct values it is displayed with a categorical histogram, because the numbers were probably flags
    """
    )
    return


@app.cell(hide_code=True)
def _(bimodal, np, pd, random_categorical):
    N = 4000

    # random_categorical and bimodal are defined in a hidden code block at the top of this notebook
    histogram_df = pd.DataFrame(
        {
            "normal": np.random.normal(25, 0.3, N),
            "3_vals": random_categorical({"foo": 0.6, "bar": 0.25, "baz": 0.15}, unique_per=0, na_per=0, longtail_per=0, N=N),
            "all_unique": random_categorical({}, unique_per=1, na_per=0, longtail_per=0, N=N),
            "bimodal": bimodal(20, 40, N),
            "longtail_unique": random_categorical({1:.3, 2:.1}, unique_per=.1, na_per=.3, longtail_per=.2, N=N),
            "one": [1] * N,
            "increasing": [i for i in range(N)],

            "all_NA": pd.Series([pd.NA] * N, dtype="UInt8"),
            "half_NA": random_categorical({1: 0.55}, unique_per=0, na_per=0.45, longtail_per=0.0, N=N),

            "longtail": random_categorical({}, unique_per=0, na_per=0.2, longtail_per=0.8, N=N),
        }
    )
    histogram_df
    return N, histogram_df


@app.cell(hide_code=True)
def _(pd):
    dirty_df = pd.DataFrame(
        {
            "a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
            "b": [
                "3",
                "4",
                "a",
                "5",
                "5",
                "b9",
                None,
                " 9",
                "9-",
                11,
                "867-5309",
                "-9",
                None,
            ],
            "us_dates": [
                "",
                "07/10/1982",
                "07/15/1982",
                "7/10/1982",
                "17/10/1982",
                "03/04/1982",
                "03/02/2002",
                "12/09/1968",
                "03/04/1982",
                "",
                "06/22/2024",
                "07/4/1776",
                "07/20/1969",
            ],
            "mostly_bool": [
                True,
                "True",
                "Yes",
                "On",
                "false",
                False,
                "1",
                "Off",
                "0",
                " 0",
                "No",
                1,
                None,
            ],
        }
    )
    return (dirty_df,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Auto cleaning and the lowcode UI
    Dealing with dirty data accounts for a large portion of the time in doing data work. We know what good data looks like, and we know the individual pandas commands to clean columns. But we have to type the same commands over and over again.

    This also shows the Lowcode UI, which is revealed by clicking the checkbox below λ (lambda).  The lowcode UI has a series of commands that can be executed on columns. Commands are added to the operations timeline (similar to CAD timelines).

    Additonal resources

    * [Autocleaning notebook](https://marimo.io/p/@paddy-mullen/buckaroo-auto-cleaning)
    * [Autocleaning in depth](https://www.youtube.com/watch?v=A-GKVsqTLMI) Video explaining how to write your own autocleaning methods and heuristic strategies
    * [JLisp explanation](https://youtu.be/3Tf3lnuZcj8) The lowcode UI is backed by a small lisp interpreter, this video explains how it works. Don't worry, you will never have to touch lisp to use buckaroo.
    * [JLisp notebook](https://marimo.io/p/@paddy-mullen/jlisp-in-buckaroo)
    """
    )
    return


@app.cell
def _(dirty_df, sys):
    from buckaroo.buckaroo_widget import AutocleaningBuckaroo
    sys #necessary so this runs after the main important block at the bottom
    AutocleaningBuckaroo(dirty_df)
    return (AutocleaningBuckaroo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Styling Buckaroo

    Buckaroo offers many ways to style tables.  Here is an example of applying a heatmap to a column. This colors the `bimodal` column based on the value of the `normal` column.

    You can see more styles in the [Buckaroo Styling Gallery](https://marimo.io/p/@paddy-mullen/buckaroo-styling-gallery).
    """
    )
    return


@app.cell
def _(BuckarooInfiniteWidget, histogram_df):
    BuckarooInfiniteWidget(histogram_df, column_config_overrides={"bimodal": {"color_map_config": {"color_rule": "color_map", "map_name": "DIVERGING_RED_WHITE_BLUE", "val_column": "normal"}}})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Extending Buckaroo
    Buckaroo is very extensible. I think of Buckaroo as a framework for building table applications, and an exploratory data analysis tool built with that framework.

    Let's start with a post processing function. Post processing functions let you modify the displayed dataframe with a simple function.  In this case we will make a "only_outliers" function which only shows the 1st and 99th quintile of each numeric row

    the `.add_processing` decorator adds the post processing function to the BuckarooWidget and enables it
    to cycle between post processing functions click below `post_processing`  Note how total_rows stays constant and filtered changes.

    Custom summary stats and styling configurations can also be added. The [Extending Buckaroo](https://www.youtube.com/watch?v=GPl6_9n31NE) video explains how.
    """
    )
    return


@app.cell
def _(BuckarooInfiniteWidget, citibike_df, pd):
    bw = BuckarooInfiniteWidget(citibike_df)

    @bw.add_processing
    def outliers(df):
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=["int64", "float64"]).columns:
            ser = df[col]
            p1, p99 = ser.quantile(0.01), ser.quantile(0.99)
            mask |= (ser <= p1) | (ser >= p99)
        return df[mask]
    bw
    return bw, outliers


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## Try Buckaroo
    Give buckaroo a try.  It works in Marimo, Jupyter, VSCode, and Google Colab
    ```
    pip install buckaroo
    # or 
    uv add buckaroo
    ```

    Give us a star on [github](https://github.com/paddymul/buckaroo)
    """
    )
    return


@app.cell(hide_code=True)
async def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import sys

    if "pyodide" in sys.modules:  # make sure we're running in pyodide/WASM
        import micropip

        await micropip.install("buckaroo")
    from buckaroo import BuckarooInfiniteWidget
    return BuckarooInfiniteWidget, micropip, mo, np, pd, sys


@app.cell(hide_code=True)
def _(np, pd):
    # because this doesn't import numpy and the first block does, this will run after


    def bimodal(mean_1, mean_2, N, sigma=5):
        X1 = np.random.normal(mean_1, sigma, int(N / 2))
        X2 = np.random.normal(mean_2, sigma, int(N / 2))
        X = np.concatenate([X1, X2])
        return X


    def rand_cat(named_p, na_per, N):
        choices, p = [], []
        named_total_per = sum(named_p.values()) + na_per
        total_len = int(np.floor(named_total_per * N))
        if named_total_per > 0:
            for k, v in named_p.items():
                choices.append(k)
                p.append(v / named_total_per)
            choices.append(pd.NA)
            p.append(na_per / named_total_per)
            return [np.random.choice(choices, p=p) for k in range(total_len)]
        return []


    def random_categorical(named_p, unique_per, na_per, longtail_per, N):
        choice_arr = rand_cat(named_p, na_per, N)
        discrete_choice_len = len(choice_arr)

        longtail_count = int(np.floor(longtail_per * N)) // 2
        extra_arr = []
        for i in range(longtail_count):
            extra_arr.append("long_%d" % i)
            extra_arr.append("long_%d" % i)

        unique_len = N - (len(extra_arr) + discrete_choice_len)
        for i in range(unique_len):
            extra_arr.append("unique_%d" % i)
        all_arr = np.concatenate([choice_arr, extra_arr])
        np.random.shuffle(all_arr)
        try:
            return pd.Series(all_arr, dtype="UInt64")
        except:
            return pd.Series(all_arr, dtype=pd.StringDtype())
    return bimodal, rand_cat, random_categorical


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
