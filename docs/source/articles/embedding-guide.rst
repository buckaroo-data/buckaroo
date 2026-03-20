Buckaroo Embedding Guide
========================

This guide covers everything you need to embed interactive buckaroo tables
in your own applications, documentation, and reports.


Why embed
---------

- **Share DataFrames without Jupyter**: Send a colleague an HTML file they
  can open in any browser. No Python install required.
- **Build data apps**: Integrate the buckaroo viewer into React dashboards,
  internal tools, or customer-facing data products.
- **Static reports**: Generate HTML reports from your pipeline that include
  interactive, sortable tables with summary statistics.
- **Documentation**: Embed live data tables in your docs site (Sphinx,
  MkDocs, or plain HTML).


Choose your embedding mode
--------------------------

Buckaroo offers two static embed modes and one live widget mode:

``embed_type="DFViewer"`` — Lightweight table
    Just the data grid with sortable columns, summary stats pinned at the
    bottom, histograms, and type-aware formatting. Smaller payload. Best
    for documentation, reports, and sharing.

``embed_type="Buckaroo"`` — Full experience
    Everything in DFViewer plus the display switcher bar, multiple computed
    views, and the interactive analysis pipeline. Larger payload. Best for
    data exploration and internal tools.

**anywidget** — Live in notebooks
    The ``BuckarooWidget`` runs inside Jupyter, Marimo, VS Code notebooks,
    and Google Colab via anywidget. Full interactivity including the command
    UI for data cleaning operations. Requires a running Python kernel.

For most embedding use cases, start with ``DFViewer``.


Data size guidelines
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Row count
     - Recommended approach
   * - < 1,000 rows
     - Inline static embed. JSON payload is small (~10-50 KB).
   * - 1,000 - 100,000 rows
     - Static embed still works. Parquet encoding keeps payload
       compact (50-500 KB). Consider sampling for faster page load.
   * - > 100,000 rows
     - Host data separately. Use Parquet range queries on S3/R2 to
       fetch only the visible rows and columns.


Generate a static embed
-----------------------

.. code-block:: python

    from buckaroo.artifact import to_html
    import pandas as pd

    df = pd.read_csv('my_data.csv')
    html = to_html(df, title="My Data", embed_type="DFViewer")

    with open('my-data.html', 'w') as f:
        f.write(html)

The HTML file references ``static-embed.js`` and ``static-embed.css``.
These are shipped in the buckaroo wheel under ``buckaroo/static/``.
Copy them alongside your generated HTML:

.. code-block:: bash

    STATIC=$(python -c "from pathlib import Path; import buckaroo; print(Path(buckaroo.__file__).parent / 'static')")
    cp "$STATIC/static-embed.js" "$STATIC/static-embed.css" ./

**With polars:**

.. code-block:: python

    import polars as pl
    from buckaroo.artifact import to_html

    df = pl.read_parquet('my_data.parquet')
    html = to_html(df, title="Polars Data")

``to_html()`` auto-detects polars DataFrames and uses the polars analysis
pipeline.

**From a file path:**

.. code-block:: python

    from buckaroo.artifact import to_html

    # Reads CSV, Parquet, JSON, or JSONL automatically
    html = to_html('/path/to/data.parquet', title="Direct from file")


Customizing appearance
----------------------

Column config overrides
~~~~~~~~~~~~~~~~~~~~~~~

Pass ``column_config_overrides`` to control per-column display:

.. code-block:: python

    html = to_html(df, column_config_overrides={
        'revenue': {
            'color_map_config': {
                'color_rule': 'color_from_column',
                'map_name': 'RdYlGn',
            }
        },
        'join_key': {
            'color_map_config': {
                'color_rule': 'color_static',
                'color': '#6c5fc7',
            }
        }
    })

Available color rules:

- ``color_from_column``: Color cells based on their value using a named
  colormap (e.g., ``RdYlGn``, ``Blues``, ``Viridis``)
- ``color_categorical``: Map categorical values to a list of colors
- ``color_static``: Constant background color for every cell in the column

Tooltips
~~~~~~~~

Show the value of another column on hover:

.. code-block:: python

    column_config_overrides={
        'name': {
            'tooltip_config': {
                'tooltip_type': 'simple',
                'val_column': 'full_name',
            }
        }
    }


Analysis classes
~~~~~~~~~~~~~~~~

Control which summary statistics are computed:

.. code-block:: python

    from buckaroo.artifact import to_html
    from buckaroo.pluggable_analysis_framework.analysis_management import (
        ColAnalysis,
    )

    # Use extra_analysis_klasses to add custom stats
    # Use analysis_klasses to replace the default set
    html = to_html(df,
                   extra_analysis_klasses=[MyCustomAnalysis],
                   embed_type="Buckaroo")

See :doc:`pluggable` for details on writing custom analysis classes.


Pinned rows
~~~~~~~~~~~

Add custom pinned rows (shown at the bottom of the table):

.. code-block:: python

    html = to_html(df,
                   extra_pinned_rows=[
                       {'index': 'target', 'a': 100, 'b': 200},
                   ])


Integration patterns
--------------------

Static HTML file
~~~~~~~~~~~~~~~~

The simplest approach. Generate the HTML, copy ``static-embed.js`` and
``static-embed.css`` next to it, and open in a browser or serve from any
static file host.

.. code-block:: bash

    cp $(python -c "import buckaroo; print(buckaroo.__path__[0])")/static/static-embed.* ./
    open my-data.html

React component
~~~~~~~~~~~~~~~

For deeper integration, import the React components directly from
``buckaroo-js-core``:

.. code-block:: bash

    npm install buckaroo-js-core

.. code-block:: typescript

    import { DFViewer } from 'buckaroo-js-core';

    function MyTable({ data, config, summaryStats }) {
      return (
        <DFViewer
          df_data={data}
          df_viewer_config={config}
          summary_stats_data={summaryStats}
        />
      );
    }

Sphinx / ReadTheDocs
~~~~~~~~~~~~~~~~~~~~~

Use a ``raw`` directive to embed an iframe pointing to a pre-generated
static HTML file:

.. code-block:: rst

    .. raw:: html

       <iframe src="_static/my-table.html"
               style="width:100%; height:400px; border:none;">
       </iframe>

Generate the HTML with the ``to_html()`` function and place it in your
Sphinx ``_static`` directory.


What's included in the bundle
-----------------------------

The ``static-embed.js`` bundle (1.3 MB minified) includes:

- React 18 + ReactDOM
- AG-Grid Community v33 (table rendering)
- hyparquet (Parquet decoding in the browser)
- recharts (histogram rendering)
- lodash-es (utility functions, tree-shaken)

The bundle is built with esbuild and shipped as an ES module.
