import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
async def _():
    import marimo as mo
    import pandas as pd
    import sys
    import types

    if "pyodide" in sys.modules:
        import micropip

        # Install buckaroo's dependencies that work in Pyodide first,
        # explicitly skipping fastparquet (C extension, not available in WASM).
        # Then install buckaroo itself with deps=False.
        await micropip.install(
            ["anywidget", "graphlib_backport", "cloudpickle"],
            keep_going=True,
        )
        await micropip.install("buckaroo", deps=False)

        # Create a minimal fastparquet stub so buckaroo can import.
        # buckaroo.serialization_utils imports fastparquet.json at module level;
        # the parquet serialization path won't work in WASM, but JSON fallback does.
        if "fastparquet" not in sys.modules:
            _fp = types.ModuleType("fastparquet")
            _fp_json = types.ModuleType("fastparquet.json")

            class _StubBaseImpl:
                pass

            _fp_json.BaseImpl = _StubBaseImpl
            _fp_json._get_cached_codec = lambda: None
            _fp.json = _fp_json
            sys.modules["fastparquet"] = _fp
            sys.modules["fastparquet.json"] = _fp_json

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
