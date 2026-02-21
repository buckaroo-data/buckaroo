import marimo

__generated_with = "0.10.7"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    mo.md("# Buckaroo Widget Test\nThis notebook tests BuckarooWidget and BuckarooInfiniteWidget rendering.")
    return (mo,)


@app.cell
def _():
    import pandas as pd
    from buckaroo.buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget
    return BuckarooInfiniteWidget, BuckarooWidget, pd


@app.cell
def _(mo):
    mo.md("## Small DataFrame (5 rows)\nA simple `BuckarooWidget` with name, age, and score columns.")
    return


@app.cell
def _(BuckarooWidget, pd):
    small_df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
        'age': [30, 25, 35, 28, 32],
        'score': [88.5, 92.3, 76.1, 95.0, 81.7],
    })
    BuckarooWidget(small_df)
    return (small_df,)


@app.cell
def _(mo):
    mo.md("## Large DataFrame (200 rows)\nA `BuckarooInfiniteWidget` demonstrating infinite scroll with a larger dataset.")
    return


@app.cell
def _(BuckarooInfiniteWidget, pd):
    rows = []
    for i in range(200):
        rows.append({'id': i, 'value': i * 10, 'label': f'row_{i}'})
    large_df = pd.DataFrame(rows)
    BuckarooInfiniteWidget(large_df)
    return large_df, rows


@app.cell
def _(mo):
    mo.md("---\n*End of test notebook.*")
    return


if __name__ == "__main__":
    app.run()
