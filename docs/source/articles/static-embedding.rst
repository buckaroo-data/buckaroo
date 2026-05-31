Static Embedding & the Incredible Shrinking Widget
====================================================

Buckaroo started as a Jupyter widget. You had to install Python, install
Jupyter, install buckaroo, start a kernel, and run a cell — just to see a
table. Then came Marimo and Pyodide, which cut out the kernel but still
needed a Python runtime in the browser.

Now there's a third option: **static embedding**. A single HTML file that
renders a fully interactive buckaroo table with no server, no kernel, no
Python runtime. Just a browser.

How it works
------------

.. code-block:: python

    from buckaroo.artifact import to_html
    import pandas as pd

    df = pd.read_csv('sales.csv')
    html = to_html(df, title="Sales Data", embed_type="DFViewer")

    with open('sales.html', 'w') as f:
        f.write(html)

That's it. ``to_html()`` does the following:

1. Runs the buckaroo analysis pipeline on the DataFrame — computing dtypes,
   summary stats, histograms, column configs
2. Serializes the data to **base64-encoded Parquet** (much more compact than
   JSON, especially for numeric columns)
3. Wraps everything in an HTML template that references ``static-embed.js``
   and ``static-embed.css``

The resulting HTML is self-describing. The JS bundle reads the embedded JSON,
decodes the Parquet payload using `hyparquet <https://github.com/hyparam/hyparquet>`_,
and renders the table with AG-Grid — all client-side.

Two embedding modes
-------------------

``embed_type="DFViewer"`` (default)
    Lightweight table viewer with summary stats pinned at the bottom.
    Includes dtypes, histograms, and basic statistics. Smaller payload.

``embed_type="Buckaroo"``
    The full buckaroo experience: display switcher bar, multiple computed
    views (main data, summary stats, other analysis outputs), and the
    interactive analysis pipeline UI. Larger payload but more powerful.

For most documentation and sharing use cases, ``DFViewer`` is the right
choice.


Bundle size
-----------

The ``static-embed.js`` bundle is currently **1.3 MB** (minified). This
includes React, AG-Grid, hyparquet, recharts (for histograms), and lodash-es.

How does this compare to the data industry?

========================== ==================
Site                       Total page weight
========================== ==================
MongoDB                    11.5 MB
Confluent                  10.7 MB
Snowflake                  8.4 MB
Elastic                    6.1 MB
dbt Labs                   5.0 MB
Fivetran                   3.4 MB
Datadog                    2.3 MB
Palantir                   2.0 MB
Databricks                 1.6 MB
**Buckaroo static embed**  **~1.3 MB + data**
========================== ==================

Confluent ships 9.2 MB of JavaScript to show you a marketing page. MongoDB
loads a 1.7 MB Optimizely tracking script before you see a single word of
content. Buckaroo delivers an interactive data viewer — with histograms,
sortable columns, summary stats, and type-aware formatting — in less than
Palantir's homepage JavaScript alone.

And that 1.3 MB includes the *viewer itself*. Your data is on top of that,
but Parquet-encoded data is compact: a 10,000-row DataFrame with 10 columns
typically adds 50-200 KB depending on column types.


What we did to get here
-----------------------

Recent releases shipped several size optimizations:

**lodash → lodash-es** (`#624 <https://github.com/buckaroo-data/buckaroo/pull/624>`_)
    Migrated from the CommonJS lodash bundle (which includes every function)
    to lodash-es, which is tree-shakeable. Only the functions actually used
    end up in the bundle.

**AG Grid v32 → v33** (`#625 <https://github.com/buckaroo-data/buckaroo/pull/625>`_)
    AG Grid v33 unified its package structure. Instead of importing from
    multiple packages (``@ag-grid-community/core``, ``@ag-grid-community/client-side-row-model``,
    etc.), there's now a single ``ag-grid-community`` package with module
    registration. This lets the bundler do a single pass of tree-shaking
    instead of trying to deduplicate across packages.

**Minification** (`#624 <https://github.com/buckaroo-data/buckaroo/pull/624>`_)
    The ``widget.js`` and ``static-embed.js`` bundles are now minified with
    esbuild. Previously they shipped unminified.

**Parquet encoding**
    Switching from JSON arrays to Parquet for the data payload was itself
    a size win. A DataFrame with 1000 rows of integers takes ~4 KB in
    Parquet vs ~12 KB in JSON. The savings compound with row count.


What's next: CDN-hosted viewer
------------------------------

Today, every static embed includes the full 1.3 MB viewer bundle. If you
generate 10 pages, you serve 13 MB of identical JavaScript.

The next step is publishing ``static-embed.js`` to a CDN (e.g., jsDelivr or
a Cloudflare R2 bucket). Each embed page would reference the CDN URL instead
of a local file. The per-page payload drops to just the data — typically
under 200 KB.

This also opens the door to embedding buckaroo tables directly in
GitHub READMEs (via ``<img>`` or GitHub Pages), documentation sites, and
email reports.


For larger data: Parquet range queries
--------------------------------------

Static embeds work great for data that fits in a single HTML file — up to
about 100K rows before the file gets unwieldy. Beyond that, the data should
live separately.

Parquet files are designed for partial reads. The file footer contains a
directory of column chunks with byte offsets. A client can fetch just the
columns and row groups it needs using HTTP range requests — no server
required, just a file on object storage (S3, Cloudflare R2, GCS).

This is the subject of a future post, but the architecture looks like:

1. Parquet file on a private R2 bucket
2. Cloudflare Worker generates a time-limited presigned URL
3. Browser-side buckaroo fetches column chunks via ``Range`` headers
4. Data never flows through your server

See the content plan for details.


Try it
------

.. code-block:: bash

    pip install buckaroo

.. code-block:: python

    from buckaroo.artifact import to_html
    import pandas as pd

    # Any DataFrame works
    df = pd.read_csv('your_data.csv')
    html = to_html(df, title="My Data")

    with open('my-data.html', 'w') as f:
        f.write(html)

    # Full buckaroo experience (larger bundle, more features)
    html_full = to_html(df, title="My Data", embed_type="Buckaroo")

The generated HTML references ``static-embed.js`` and ``static-embed.css``
which are included in the ``buckaroo`` Python package under
``buckaroo/static/``. Copy those files alongside your HTML, or serve them
from a web server.
