import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
async def _():
    import marimo as mo
    import pandas as pd
    import sys

    if "pyodide" in sys.modules:
        import micropip
        await micropip.install("buckaroo", keep_going=True)

    import buckaroo
    from buckaroo import BuckarooWidget, BuckarooInfiniteWidget
    from buckaroo.marimo_utils import marimo_monkeypatch

    marimo_monkeypatch()

    return mo, pd, buckaroo, BuckarooWidget, BuckarooInfiniteWidget


@app.cell
def _(mo):
    mo.md("""
    # Buckaroo in Marimo WASM

    This notebook demonstrates Buckaroo widgets running in Pyodide/WASM.
    All Python code runs in your browser - no server needed!
    """)
    return


@app.cell
def _(mo, pd, BuckarooWidget):
    mo.md("## Small DataFrame (5 rows)")
    small_df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
        'age': [30, 25, 35, 28, 32],
        'score': [88.5, 92.3, 76.1, 95.0, 81.7],
    })

    mo.md("View the data below:")
    BuckarooWidget(small_df)
    return small_df


@app.cell
def _(mo, pd, BuckarooInfiniteWidget):
    mo.md("## Large DataFrame (200 rows) - Infinite Scroll")
    rows = []
    for i in range(200):
        rows.append({'id': i, 'value': i * 10, 'label': f'row_{i}'})
    large_df = pd.DataFrame(rows)

    mo.md("Scroll through the large dataset:")
    BuckarooInfiniteWidget(large_df)
    return large_df


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---

    **Note:** This notebook runs entirely in your browser via Pyodide (Python WASM).
    First load takes 15-30 seconds while Python initializes.
    """)
    return


if __name__ == "__main__":
    app.run()
