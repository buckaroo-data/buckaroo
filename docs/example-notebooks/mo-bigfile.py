import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(
        r"""
    # Dealing with large dataframes

    My cousin called up asking for help with a big dataset that couldn't fit into Excel.  I thought, ahh this will be easy for pandas and Buckaroo.  What followed was an interesting problem and some techniques for working with larger than memory dataframes.

    The file turned out to be a 10GB CSV file with doctor information.  Pat was looking for Anesthesiologists, denoted by code `H367...`.

    You can find the original data here [https://download.cms.gov/nppes/NPI_Files.html](
    https://download.cms.gov/nppes/NPI_Files.html)
    What follows are some techinuqes for working with larger dataframes
    """
    )
    return


@app.cell
def _():
    import pandas as pd
    import buckaroo
    return buckaroo, pd


@app.cell
def _(mo):
    mo.md(r"""Let's read in the file, and look at only 50k rows""")
    return


@app.cell
def _(buckaroo, pd):
    JULY_FILE = "~/NPPES_Data_Dissemination_July_2025/npidata_pfile_20050523-20250713.csv"
    july_df = pd.read_csv(JULY_FILE, nrows=50_000)
    buckaroo.BuckarooInfiniteWidget(july_df)
    return JULY_FILE, july_df


@app.cell
def _(mo):
    mo.md(r"""Here we see that not only are there 10M rows in the file, there are also 330 columns.  Buckaroo only shows up to 250 columns, which is still probably too many because it's tough to navigate. let's look at the last 100 columns""")
    return


@app.cell
def _(july_df):
    july_df[july_df.columns[-100:]]
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    # There are a lot of all null columns

    # Let's do some filtering

    One of the easiest customizations you can do with Buckaroo is adding a post_processing function that you can toggle on and off.

    Let's write the functions first then see how we want to integrate them.
    """
    )
    return


@app.cell
def _(july_df):
    def drop_na_columns(df):
        return df.dropna(axis=1, how='all')
    drop_na_columns(july_df)
    return (drop_na_columns,)


@app.cell
def _(july_df):
    npir = july_df['NPI Reactivation Date']
    ab = npir.notna()
    ab |= july_df['Provider License Number State Code_5'].notna()
    ab.sum()
    return


@app.function
def na_outliers_only(df):
    """
        If a column has 99% NA, for that column filter to only rows that aren't NA,  Union with non na rows of other columns
    """
    mostly_na_columns = []
    for col in df.columns:
        ser = df[col]
        if (df[col].notna().sum() / len(df)) < 0.01:
            mostly_na_columns.append(col)
    all_na_outliers = ~df.all(axis=1) # start with an entirely false series
    for col in mostly_na_columns:
        all_na_outliers |= df[col].notna()
    return df[all_na_outliers]


@app.cell
def _(buckaroo, drop_na_columns, july_df):
    bw = buckaroo.BuckarooInfiniteWidget(drop_na_columns(july_df))

    bw.add_processing(na_outliers_only)
    bw
    return


@app.cell
def _(mo):
    mo.md(r"""# How to access a filtered and processed dataframe""")
    return


@app.cell
def _(buckaroo, july_df):
    bw2 = buckaroo.BuckarooInfiniteWidget(july_df)
    bw2
    return (bw2,)


@app.cell
def _(bw2):
    bw2.dataflow.processed_df.to_csv("~/Chip.csv")
    return


@app.cell
def _():
    import os
    os.system("open ~/Chip.csv")
    return


@app.cell
def _():
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    # But theres something else we can do.
    We can retrieve the code that runs the search. This is because search is part of the lowcode UI which has codegen.

    """
    )
    return


@app.cell
def _(july_df):
    july_df
    return


@app.cell
def _(mo):
    mo.md(
        r"""
    #That's it for the marimo notebook.

    I'm going to hop over to jupyter to figure out how to accomplish this on the entire dataframe,  we will be using polars over there

    """
    )
    return


@app.cell
def _():
    # the following cell when executed over 2m rows, took 4m 33s
    return


@app.function
def clean(df):
    from buckaroo.customizations.pandas_commands import search_df_str
    return search_df_str(df, '367H00000X')
    return df


@app.cell
def _():
    import polars as pl
    from buckaroo.polars_buckaroo import PolarsBuckarooInfiniteWidget
    NROWS = 10_000
    #pldf = pl.read_csv(JULY_FILE, n_rows=NROWS)
    return NROWS, PolarsBuckarooInfiniteWidget, pl


@app.cell
def _(JULY_FILE, NROWS, pl):
    def pl_clean(df):
        df = df.filter(pl.any_horizontal(pl.col(pl.String).str.contains('UNAV')))
        return df
    pl_clean(pl.read_csv(JULY_FILE, n_rows=NROWS))
    return


@app.cell
def _(JULY_FILE, NROWS, pl):
    (pl.scan_csv(JULY_FILE, n_rows=NROWS)
        .filter(pl.any_horizontal(pl.col(pl.String).str.contains('UNAV')))
        .collect())
    return


@app.cell
def _():
    #(pl.scan_csv(JULY_FILE, n_rows=NROWS*10)
    #    .filter(pl.any_horizontal(pl.col(pl.String).str.contains('UNAV')))
    #   .collect())
    return


@app.cell
def _():
    #(pl.scan_csv(JULY_FILE, n_rows=NROWS*50)
    #    .filter(pl.any_horizontal(pl.col(pl.String).str.contains('UNAV')))
    #    .collect())
    return


@app.cell
def _():
    #1.92s 68k rows
    #(pl.scan_csv(JULY_FILE, n_rows=NROWS*50, low_memory=True)
    #    .filter(pl.any_horizontal(pl.col(pl.String).str.contains('UNAV')))
    #    .collect())
    return


@app.cell
def _():
    #1m8s about the same memory usage
    #(pl.scan_csv(JULY_FILE, low_memory=True)
    #    .filter(pl.any_horizontal(pl.col(pl.String).str.contains('367H00000X')))
    #    .collect(streaming=True))
    return


@app.cell
def _():
    #ran in 1m21s
    #pl_367_df = (pl.scan_csv(JULY_FILE, low_memory=True)
    #    .filter(pl.any_horizontal(pl.col(pl.String).str.contains('367H00000X')))
    #    .collect())
    return


@app.cell
def _():
    # 10 seconds
    #pl.scan_csv(JULY_FILE, n_rows=1_000_000, low_memory=True).collect().write_parquet("1m.parq")
    return


@app.cell
def _():
    #pl.scan_csv(JULY_FILE, skip_rows_after_header=15_000_000, n_rows=5).collect()
    return


@app.cell
def _(pl):
    import tempfile
    from datetime import datetime
    import gc

    def pl_to_parq(csv_path, parq_path, chunk_size=1_000_000):
        chunk_start=0
        t_start = datetime.now()
        named_temps = []

        while True:
            try:
                tfile = tempfile.NamedTemporaryFile()
                print(chunk_start, tfile.name, datetime.now() - t_start)
                pl.scan_csv(csv_path, skip_rows_after_header=chunk_start, n_rows=chunk_size).collect().write_parquet(tfile.name)
                tfile.seek(0)
                chunk_start += chunk_size
                named_temps.append(tfile)

                #gc.collect()
            except pl.exceptions.NoDataError:
                break
        dfs = [pl.read_parquet(f) for f in named_temps]
        pl.concat(dfs).write_parquet(parq_path)
    #pl_to_parq("~/300k_july.csv", parq_path="~/300k_july.parq", chunk_size=100_000)
    #pl_to_parq("~/3m_july.csv", parq_path="~/3m_july.parq")
    return


@app.cell
def _(PolarsBuckarooInfiniteWidget, pldf):
    PolarsBuckarooInfiniteWidget(pldf[:50])
    return


@app.cell
def _(drop_na_columns, july_df):
    na_outliers_only(drop_na_columns(july_df))
    return


@app.cell
def _():
    #filterd_df = bw.dataflow.processed_df
    return


@app.cell
def _():
    import marimo as mo
    return (mo,)


if __name__ == "__main__":
    app.run()
