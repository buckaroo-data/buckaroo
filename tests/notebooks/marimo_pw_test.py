import marimo

__generated_with = "0.10.7"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd
    from buckaroo.buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget
    return BuckarooInfiniteWidget, BuckarooWidget, pd


@app.cell
def _(BuckarooWidget, pd):
    small_df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
        'age': [30, 25, 35, 28, 32],
        'score': [88.5, 92.3, 76.1, 95.0, 81.7],
    })
    widget = BuckarooWidget(small_df)
    return small_df, widget


@app.cell
def _(BuckarooInfiniteWidget, pd):
    rows = []
    for i in range(200):
        rows.append({'id': i, 'value': i * 10, 'label': f'row_{i}'})
    large_df = pd.DataFrame(rows)
    widget = BuckarooInfiniteWidget(large_df)
    return large_df, rows, widget


if __name__ == "__main__":
    app.run()
