import marimo

__generated_with = "0.11.22"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
async def _(mo):
    import pandas as pd
    import numpy as np
    import sys
    if "pyodide" in sys.modules: # a hacky way to figure out if we're running in pyodide
        import micropip
        await micropip.install("buckaroo")

    from buckaroo.buckaroo_widget import BuckarooInfiniteWidget, BuckarooWidget


    def BWOrig(df):
        return mo.ui.anywidget(BuckarooWidget(df))


    def BWI(df):
        return mo.ui.anywidget(BuckarooInfiniteWidget(df))
    return (
        BWI,
        BWOrig,
        BuckarooInfiniteWidget,
        BuckarooWidget,
        micropip,
        np,
        pd,
        sys,
    )


@app.cell
def _(BWI, np, pd):
    ROWS = 1_300_000
    typed_df = pd.DataFrame(
        {
            "int_col": np.random.randint(1, 50, ROWS),
            "float_col": np.random.randint(1, 30, ROWS) / 0.7,
            "str_col": ["foobar"] * ROWS,
        }
    )
    widget1 = BWI(typed_df)
    widget1
    return ROWS, typed_df, widget1


@app.cell
def _(widget1):
    widget1
    return


@app.cell
def _(widget1):
    widget1
    return


@app.cell
def _(BWI, np, pd):
    ROWS2 = 34_0
    typed_df2 = pd.DataFrame(
        {
            "int_col2": np.random.randint(1, 50, ROWS2),
            "float_col2": np.random.randint(1, 30, ROWS2) / 0.7,
            "str_col2": ["foobar"] * ROWS2,
        }
    )
    widget2 = BWI(typed_df2)
    widget2
    return ROWS2, typed_df2, widget2


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
