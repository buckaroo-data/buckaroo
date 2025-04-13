import marimo

__generated_with = "0.12.2"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        # Tour of Buckaroo
        Buckaroo expedites the core task of data work by showing histograms and summary stats with every DataFrame.
        """
    )
    return


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import buckaroo
    from buckaroo import BuckarooInfiniteWidget
    return BuckarooInfiniteWidget, buckaroo, mo, pd


@app.cell(hide_code=True)
def _(pd):
    # Extra utility functions and marimo overrides
    import numpy as np
    from buckaroo.marimo_utils import marimo_monkeypatch, BuckarooDataFrame as DataFrame

    # this overrides pd.read_csv and pd.read_parquet to return BuckarooDataFrames which overrides displays as BuckarooWidget, not the default marimo table
    marimo_monkeypatch()

    def bimodal(mean_1, mean_2, N, sigma=5):
        X1 = np.random.normal(mean_1, sigma, int(N/2))
        X2 = np.random.normal(mean_2, sigma, int(N/2))
        X = np.concatenate([X1, X2])
        return X

    def rand_cat(named_p, na_per, N):
        choices, p = [], []
        named_total_per = sum(named_p.values()) + na_per
        total_len = int(np.floor(named_total_per * N))
        if named_total_per > 0:
            for k, v in named_p.items():
                choices.append(k)
                p.append(v/named_total_per)
            choices.append(pd.NA)
            p.append(na_per/named_total_per)    
            return [np.random.choice(choices, p=p) for k in range(total_len)]
        return []

    def random_categorical(named_p, unique_per, na_per, longtail_per, N):
        choice_arr = rand_cat(named_p, na_per, N)
        discrete_choice_len = len(choice_arr)

        longtail_count = int(np.floor(longtail_per * N))//2
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
            return pd.Series(all_arr, dtype='UInt64')
        except:
            return pd.Series(all_arr, dtype=pd.StringDtype())
    return (
        DataFrame,
        bimodal,
        marimo_monkeypatch,
        np,
        rand_cat,
        random_categorical,
    )


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


@app.cell
def _(pd):
    citibike_df = pd.read_parquet('./citibike-trips-2016-04.parq')
    citibike_df
    return (citibike_df,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Histograms

        Histograms are built into Buckaroo. They enable users to quickly identify distributions of data in columns
        ### Common histogram shapes

        The following shows the most common shapes you will see in histograms, allowing you to quickly identify patterns

        Notice the three columns on the right. Those are categorical histograms as opposed to numerical histograms
        """
    )
    return


@app.cell
def _(DataFrame, bimodal, np, random_categorical):
    N = 4000
    #random_categorical and bimodal are defined in a hidden code block at the top of this notebook
    histogram_df = DataFrame({
        'normal': np.random.normal(25, .3, N),
        'exponential' :  np.random.exponential(1.0, N) * 10,
        'increasing':[i for i in range(N)],
        'one': [1]*N,
        'dominant_categories': random_categorical({'foo': .6, 'bar': .25, 'baz':.15}, unique_per=0, na_per=0, longtail_per=0, N=N),
        'all_unique_cat': random_categorical({}, unique_per=1, na_per=0, longtail_per=0, N=N),
        'bimodal' :  bimodal(20,40, N)})
    histogram_df
    return N, histogram_df


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Categorical histograms

        Categorical histograms have special colors and patterns for NA/NaN, longtail (values that occur at least twice) and unique Categorical histograms are always arranged from most frequent on the left to least frequent on the right.

        When a column is numerical, but has less than 5 distinct values it is displayed with a categorical histogram, because the numbers were probably flags
        """
    )
    return


@app.cell
def _(DataFrame, N, pd, random_categorical):
    DataFrame({
        'all_NA' :               pd.Series([pd.NA] * N, dtype='UInt8'),
        'half_NA' :              random_categorical({1: .55}, unique_per=0,   na_per=.45, longtail_per=.0, N=N),
        'dominant_categories':   random_categorical({'foo': .45, 'bar': .2, 'baz':.15}, unique_per=.2, na_per=0, longtail_per=0, N=N),
        'longtail' :             random_categorical({},      unique_per=0,   na_per=.2, longtail_per=.8, N=N),
        'longtail_unique' :      random_categorical({},      unique_per=0.5, na_per=.0, longtail_per=.5, N=N)})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Extending Buckaroo
        Buckaroo is very extensible.  Let's start with a post processing function. Post processing functions let you modify the displayed dataframe with a simple function.  In this case we will make a "only_outliers" function which only shows the 1st and 99th quintile of each numeric row

        the `.add_processing` decorator adds the post processing function to the BuckarooWidget and enables it
        to cycle between post processing functions click below `post_processing`  Note how total_rows stays constant and filtered changes
        """
    )
    return


@app.cell
def _(BuckarooInfiniteWidget, citibike_df, pd):
    bw = BuckarooInfiniteWidget(citibike_df)
    @bw.add_processing
    def outliers(df):
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=['int64', 'float64']).columns:
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
        ## Styling Buckaroo

        Buckaroo offers many ways to style tables.  Here is an example of applying a heatmap to a column. This colors the `exponential` column based on the value of the `normal` column.
        """
    )
    return


@app.cell
def _(BuckarooInfiniteWidget, histogram_df):
    BuckarooInfiniteWidget(histogram_df,
        column_config_overrides={
            'exponential': {'color_map_config': {
              'color_rule': 'color_map',
              'map_name': 'DIVERGING_RED_WHITE_BLUE',
              'val_column': 'normal'
            }}})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Try Buckaroo
        Give buckaroo a try.  It works in Marimo, Jupyter, VSCode, and Google Colab
        ```
        pip install buckaroo
        ```

        Give us a star on [github](https://github.com/paddymul/buckaroo)
        """
    )
    return


if __name__ == "__main__":
    app.run()
