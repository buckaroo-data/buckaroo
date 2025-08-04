# Understanding the docs system

docs builds are run on PRs. From the PR if you click on the details of the *read the docs* task it will take you to the Read the docs build.  If that build was succesful, it will take you to the docs for that commit. otherwise it will take you to the build logs.



You can click on preview links [here](???) or by navigating through the PR here

Here is a preview link for a succesful build:
https://buckaroo-data--420.org.readthedocs.build/en/420/
from there
- ./scripts/marimo_wasm_output.sh buckaroo_ddd_tour.py run
produces the following working directory
https://buckaroo-data--420.org.readthedocs.build/en/420/example_notebooks/buckaroo_ddd_tour/

This is a work in progress

--

## marimo wasm notebook peculariaties

generally I include a code block at the bottom that looks like this
```
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
```


That makes sure that pyodide install buckaroo and there isn't an error loop

## Adding files to the built notebook
for now any file added to `docs/example-notebooks/marimo-wasm/public` will be avilable to all notebooks

accessing them in the notebook is tricky
`citibike_df = pd.read_parquet(mo.notebook_location() / "public" / "citibike-trips-2016-04.parq")`
follow this bug for more
https://github.com/marimo-team/marimo/issues/5901


### serving wasm
for local dev
npx http-server -o ./
this is much faster than the python server
