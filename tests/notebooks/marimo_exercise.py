import marimo

__generated_with = "0.10.7"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd
    import numpy as np
    import anywidget
    from pathlib import Path
    df = pd.DataFrame(
        {'a':[111_111,  77_777, 777_777, 1_000_000, 2_111_111, 1_235_999],
         'b':[111_111, 555_555,       0,    28_123,   482_388,     5_666]})
    return Path, anywidget, df, np, pd


@app.cell
def _():
    from buckaroo.buckaroo_widget import BuckarooWidget, RawDFViewerWidget, BuckarooInfiniteWidget
    return BuckarooInfiniteWidget, BuckarooWidget, RawDFViewerWidget


@app.cell
def _(BuckarooInfiniteWidget, np, pd):
    N=2000
    large_df = pd.DataFrame({'a': np.random.randint(100,size=N), 'b': np.random.rand(N) * 5})
    BuckarooInfiniteWidget(large_df)
    return N, large_df


@app.cell
def _(BuckarooWidget, df):
    BuckarooWidget(df)
    return


if __name__ == "__main__":
    app.run()
