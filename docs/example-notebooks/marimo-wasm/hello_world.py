import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd
        
    return pd



@app.cell
async def _():
    import marimo as mo
    import sys

    if "pyodide" in sys.modules:  # a hacky way to figure out if we're running in pyodide
        import micropip

        await micropip.install("buckaroo==0.12.5")
    import buckaroo


    return sys, mo, micropip


if __name__ == "__main__":
    app.run()
