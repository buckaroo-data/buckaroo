.. _embedding:

Embedding Buckaroo
==================

Buckaroo started life as a Jupyter widget. It still works that way — the table
that pops up after ``import buckaroo`` is the same component you'll be
embedding. But there are now several other ways to render that component
outside of a notebook: static HTML files, custom web pages, a standalone
server, and JS apps. This guide is a map of those options so you can pick
the one that fits your use case.

The decision comes down to two axes:

1. **Which widget?** Full Buckaroo UI (status bar, summary stats, command UI,
   sampling toggle) vs. a plain DFViewer table. Eager-loaded base vs.
   infinite-scrolling.
2. **Which deployment?** Notebook kernel, static HTML, custom HTML + JS,
   Buckaroo server, or a JS app via npm.

Pick a widget and a deployment — almost any combination works.


Widget types
------------

There are two orthogonal choices that produce four widget classes.

**Buckaroo vs. DFViewer** — how much UI shows up:

- **BuckarooWidget** is the full experience. Above the table is the status
  bar with toggles for summary statistics (``Σ``), command-edit mode (``λ``),
  sampling (``Ξ``), and help (``?``). Below the status bar there's a tabbed
  display switcher. Use this when you want users to *explore and clean* data.
- **DFViewer** is just the data grid — sortable columns, formatting,
  histograms in the header, but no status bar, no command UI, no summary
  stats panel. Use this when you want a styled read-only table inside a
  larger app or page.

**Base vs. Infinite** — how rows reach the browser:

- **Base** widgets serialize the entire (sampled) DataFrame up front and
  ship it to the browser in one shot. Sampling kicks in around 10k rows by
  default to keep payloads reasonable.
- **Infinite** widgets stream rows on demand. The browser asks for a row
  range; the Python side serializes that slice as parquet and sends it
  back. Sorting is also pushed to the server. This scales to dataframes
  that won't fit in the browser, at the cost of a live Python connection.

The four classes are:

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * -
     - **Base** (eager)
     - **Infinite** (lazy)
   * - **Buckaroo** (full UI)
     - ``BuckarooWidget``
     - ``BuckarooInfiniteWidget``
   * - **DFViewer** (table only)
     - ``DFViewer`` (helper)
     - ``DFViewerInfinite``

For polars, swap the prefix: ``PolarsBuckarooWidget``,
``PolarsBuckarooInfiniteWidget``, ``PolarsDFViewer``. For xorq
(ibis expressions): ``XorqBuckarooWidget``,
``XorqBuckarooInfiniteWidget``. The xorq path doesn't currently
expose a DFViewer-only variant — it ships with the full Buckaroo UI.

Picking between them:

- Default to ``BuckarooWidget`` in notebooks. It's the full pitch.
- Use ``DFViewer`` when Buckaroo is a component of a larger UI you've
  already built (a static report page, a dashboard).
- Use the Infinite variants when the dataframe is too big to ship
  eagerly, or when you want server-side sorting on the full set rather
  than only the sampled subset.


Backends: pandas, polars, and xorq
----------------------------------

Buckaroo supports three backends. The selection happens at the import
path:

.. code-block:: python

    # Pandas
    from buckaroo import BuckarooWidget, BuckarooInfiniteWidget, DFViewer

    # Polars
    from buckaroo.polars_buckaroo import (
        PolarsBuckarooWidget, PolarsBuckarooInfiniteWidget, PolarsDFViewer)

    # Xorq / ibis expressions
    from buckaroo.xorq_buckaroo import (
        XorqBuckarooWidget, XorqBuckarooInfiniteWidget)

The user-facing UI is identical across all three — same status bar,
same column histograms, same command UI. What differs is internal:
the analysis classes (mean, median, null counts, histograms, etc.)
are implemented against each library's native API, so neither pandas
nor polars pays a conversion cost to render, and xorq pushes
computation down to whatever backend is behind the expression.

A few entry points accept either pandas or polars frames and dispatch
by type. The static-embed helpers (``prepare_buckaroo_artifact``,
``to_html``) inspect the input and pick the right widget class for
you. ``LazyFrame`` is collected to a ``DataFrame`` first.

Polars is an optional dependency: ``pip install buckaroo[polars]``.
Without it, the polars import paths simply aren't there, and the pandas
classes work the same.

**xorq** is a third backend, built on
`xorq <https://github.com/letsql/xorq>`_/ibis, that takes an
*expression* rather than a materialized frame. The stat pipeline
compiles to a small, fixed number of batched SQL queries: one
``expr.aggregate(...)`` for length / null-count / min / max /
distinct-count across every column, plus the histogram queries.
Computation stays in the engine — the only thing pulled into Python
is a display-sized sample (``expr.limit(N).execute()``). This means
Buckaroo can render summary statistics over DuckDB, Postgres,
Snowflake, BigQuery, and any other ibis-supported engine without
materializing the table.

.. code-block:: python

    import xorq.api as xo
    from buckaroo.xorq_buckaroo import XorqBuckarooInfiniteWidget

    con = xo.connect()                            # built-in datafusion
    expr = con.read_parquet("citibike-trips.parquet")
    XorqBuckarooInfiniteWidget(expr)

The default backend is xorq's built-in datafusion engine. Swap to
duckdb, postgres, etc. by registering the table on the relevant
connection:

.. code-block:: python

    con = xo.duckdb.connect("warehouse.db")
    expr = con.table("trips").filter(con.table("trips").year == 2024)
    XorqBuckarooInfiniteWidget(expr)

The Infinite variant is usually what you want for xorq — each scroll
window pushes a ``LIMIT/OFFSET`` to the backend and streams the
resulting Arrow window straight to the browser. Postprocessing is
expression-to-expression: register a function that takes the current
expression and returns a new one, and stats keep pushing down to the
engine.

Install with ``pip install 'buckaroo[xorq]'``. See :doc:`xorq-stats`
for a walkthrough of the underlying stat pipeline and how to add
custom aggregates.


Embedding modes
---------------

The Python widget has the same surface area in every mode. What changes
is *where* the JS bundle runs and *how* data gets to it.


1. Notebook (anywidget)
~~~~~~~~~~~~~~~~~~~~~~~

This is the original deployment. Buckaroo is an
`anywidget <https://github.com/manzt/anywidget>`_, so it works in any
notebook host that speaks the Jupyter widget protocol — Jupyter Lab,
classic Notebook 7, marimo, VS Code, JupyterLite, Google Colab.

.. code-block:: python

    import pandas as pd
    from buckaroo import BuckarooWidget

    df = pd.read_csv("sales.csv")
    BuckarooWidget(df)

The kernel runs your Python; ``anywidget`` ships ``widget.js`` to the
front end and wires up the bidirectional traitlet sync. For Infinite
widgets the kernel also handles row-range requests over the comm
channel.

When to use it: you're already in a notebook. ``import buckaroo``
also installs Buckaroo as the default DataFrame display, so a bare
``df`` cell renders the widget — no widget class needed.


2. Static HTML
~~~~~~~~~~~~~~

``buckaroo.to_html()`` renders a complete HTML document with the data
embedded as base64-encoded parquet inside a ``<script>`` tag. The page
references two static assets (``static-embed.js`` and
``static-embed.css``) that ship with Buckaroo.

.. code-block:: python

    from buckaroo import to_html
    import pandas as pd

    df = pd.read_csv("sales.csv")
    html = to_html(df, title="Q4 Sales", embed_type="DFViewer")
    open("sales.html", "w").write(html)

There is no Python at view time. The browser parses the embedded
parquet, resolves it through the same React component used in the
notebook widget, and renders. ``embed_type="DFViewer"`` (the default)
gives the plain table; ``embed_type="Buckaroo"`` includes the status
bar and the summary-stats switcher.

You'll need to copy ``static-embed.js`` and ``static-embed.css`` from
``buckaroo/static/`` next to the generated HTML. The static-embed
bundle is built with ``pnpm --filter buckaroo-widget run build:static``;
released wheels include it.

If shipping those two files alongside the HTML is inconvenient — a
Gist, an email attachment, a one-off upload — use the CDN pattern
under mode 3 below as a drop-in replacement. The artifact JSON is
the same; only the ``<script>`` / ``<link>`` block at the top of the
page changes (esm.sh URLs + import map instead of local
``static-embed.js`` / ``static-embed.css``). The result is a single
self-contained ``.html`` file that works anywhere with a network
connection.

Limitations:

- Eager only — the full sampled dataframe is in the page. No infinite
  scroll, no kernel-side sorting on the full set.
- No command UI. Operations require a Python runtime; the static
  bundle doesn't include one.
- Data is sampled the same way it would be in a notebook (default
  10k rows for the eager path).

When to use it: read-only deliverables. Email-able reports, GitHub
Pages, an attachment in a ticket, a docs site. The page is fully
self-contained once you've placed it next to the static assets.


3. HTML + JS (artifact)
~~~~~~~~~~~~~~~~~~~~~~~

When you want Buckaroo *inside* an existing page rather than as the
whole page, skip ``to_html()`` and grab the artifact dict directly:

.. code-block:: python

    from buckaroo import prepare_buckaroo_artifact, artifact_to_json

    artifact = prepare_buckaroo_artifact(df, embed_type="DFViewer")
    json_str = artifact_to_json(artifact)
    # serve json_str to your page however you want

The artifact contains the parquet-encoded data, the column display
config, and (in Buckaroo mode) the status-bar state. There are two
ways to feed it to the JS side: drop it into a page that loads the
prebuilt ``static-embed.js`` bundle (no build step), or import the
React components from ``buckaroo-js-core`` and render them yourself.

**Raw JS — prebuilt bundle (works today).** The
``static-embed.js`` bundle that ships with the wheel
(``buckaroo/static/static-embed.js``) is an ESM module that
auto-initialises on load. Its contract is two DOM hooks: a
``<script id="buckaroo-data" type="application/json">`` containing
the artifact JSON, and a ``<div id="root">`` to mount into. Any HTML
file matching that contract will render — no JS to write:

.. code-block:: html

    <!DOCTYPE html>
    <html>
    <head>
      <link rel="stylesheet" href="static-embed.css">
      <style>#root { width: 100%; height: 100vh; }</style>
    </head>
    <body>
      <div id="root"></div>
      <script id="buckaroo-data" type="application/json">
        <!-- artifact JSON written here verbatim; see note below -->
      </script>
      <script type="module" src="static-embed.js"></script>
    </body>
    </html>

``to_html()`` emits this same template. To embed into an existing
page, drop the ``#buckaroo-data`` block and the two ``<script>`` /
``<link>`` tags into your own markup and render the JSON from your
backend (Flask, Django, Sphinx extension, etc.).

**Don't HTML-escape the JSON.** The bundle reads ``#buckaroo-data``
via ``textContent`` and hands it straight to ``JSON.parse``. Most
server-side templating engines autoescape ``{{ ... }}`` by default,
which turns ``"`` into ``&#34;`` and breaks parsing. Use your
framework's "already safe" path and also defuse any ``</script>``
sequence in the JSON so it cannot break out of the block:

.. code-block:: python

    # Flask / Jinja2
    import json
    artifact_json = json.dumps(artifact).replace("</", "<\\/")
    return render_template("page.html", artifact_json=artifact_json)

.. code-block:: jinja

    {# page.html — `| safe` skips Jinja autoescaping #}
    <script id="buckaroo-data" type="application/json">
      {{ artifact_json | safe }}
    </script>

.. code-block:: django

    {# Django: json_script emits the <script type="application/json">
       wrapper itself and escapes "<", ">", "&" safely. #}
    {{ artifact|json_script:"buckaroo-data" }}

For *late-bound* data (fetch from an endpoint after page load), set
``#buckaroo-data`` from JS *before* loading the module, since the
bundle reads it once at startup:

.. code-block:: html

    <div id="root"></div>
    <script id="buckaroo-data" type="application/json"></script>
    <link rel="stylesheet" href="/static/static-embed.css">
    <script type="module">
      const r = await fetch("/api/my-table.json");
      document.getElementById("buckaroo-data").textContent = await r.text();
      await import("/static/static-embed.js");
    </script>

Copy ``static-embed.js`` and ``static-embed.css`` from
``buckaroo/static/`` into whatever your site serves as static
assets. The bundle is built with
``pnpm --filter buckaroo-widget run build:static``; released wheels
include it.

**Raw JS — CDN-hosted npm (no local files, no build step).**
Since ``buckaroo-js-core`` is on npm, you can load it from esm.sh
(or jsDelivr / unpkg) and skip both the prebuilt static-embed
bundle *and* the local file copy. This also doubles as a
CDN-flavoured replacement for ``to_html()`` (mode 2) — the page
below is the same shape as ``to_html()``'s output, but the
``<script>`` / ``<link>`` block references esm.sh instead of a
sibling ``static-embed.js`` / ``static-embed.css``, so the
resulting ``.html`` is a single fully self-contained file you can
email or upload anywhere. Drop it on any static host, fill in
``#buckaroo-data`` from your backend (or paste the artifact JSON in
directly for a one-shot report), and it renders:

.. code-block:: html

    <!DOCTYPE html>
    <html>
    <head>
      <link rel="stylesheet" href="https://esm.sh/buckaroo-js-core@0.14.5/dist/style.css">
      <style>#root { width: 100%; height: 100vh; }</style>
      <script type="importmap">
      {
        "imports": {
          "react": "https://esm.sh/react@18.3.1",
          "react/jsx-runtime": "https://esm.sh/react@18.3.1/jsx-runtime",
          "react-dom": "https://esm.sh/react-dom@18.3.1",
          "react-dom/client": "https://esm.sh/react-dom@18.3.1/client",
          "buckaroo-js-core": "https://esm.sh/*buckaroo-js-core@0.14.5"
        }
      }
      </script>
    </head>
    <body>
      <div id="root"></div>
      <script id="buckaroo-data" type="application/json">
        <!-- artifact JSON written here verbatim by your backend -->
      </script>
      <script type="module">
        import { createElement } from "react";
        import { createRoot } from "react-dom/client";
        import {
          BuckarooStaticTable,
          resolveDFDataAsync,
          preResolveDFDataDict,
        } from "buckaroo-js-core";

        const artifact = JSON.parse(
          document.getElementById("buckaroo-data").textContent
        );
        const [dfData, summaryStats] = await Promise.all([
          resolveDFDataAsync(artifact.df_data),
          resolveDFDataAsync(artifact.summary_stats_data),
        ]);
        const resolved = {
          embed_type: artifact.embed_type ?? "DFViewer",
          df_data: dfData,
          df_viewer_config: artifact.df_viewer_config,
          summary_stats_data: summaryStats,
        };
        if (artifact.embed_type === "Buckaroo" && artifact.df_data_dict) {
          resolved.df_data_dict = await preResolveDFDataDict(artifact.df_data_dict);
          resolved.df_data_dict.main = dfData;
          resolved.df_display_args = artifact.df_display_args;
          resolved.df_meta = artifact.df_meta;
          resolved.buckaroo_options = artifact.buckaroo_options;
          resolved.buckaroo_state = artifact.buckaroo_state;
        }
        createRoot(document.getElementById("root")).render(
          createElement(BuckarooStaticTable, { artifact: resolved })
        );
      </script>
    </body>
    </html>

Two non-obvious bits that make this work:

- **Import map + esm.sh's "starred" build** (``https://esm.sh/*buckaroo-js-core@0.14.5``).
  Without these, you end up with two React module instances — one
  that ``createRoot`` renders with, another that the components
  inside ``buckaroo-js-core`` call ``useState`` on — and the package
  blows up with ``TypeError: can't access property "useState", i.H
  is null``. The starred URL tells esm.sh to leave every bare
  import (``react``, ``react-dom``, ``react/jsx-runtime``)
  unresolved; the import map then points all of them at the same
  pinned React, so the package and the page share one instance.
- **Pin the version.** Use ``@0.14.5``, not ``@latest`` — esm.sh
  caches aggressively and a future minor can change the package's
  internal API or React-version range without warning.

Swap ``esm.sh`` for ``cdn.jsdelivr.net/npm/buckaroo-js-core@0.14.5/+esm``
or ``unpkg.com`` if you prefer; esm.sh is the easiest default
because it serves the un-resolved (starred) build for you. With
jsDelivr / unpkg you'd need a bundler-style build or your own
peer-dep shim — they don't have an equivalent of the ``*`` prefix.

**TypeScript — server embed with the React component.**
If your page is already a React app (Next.js, Remix, a Vite SPA, an
internal dashboard), skip the prebuilt bundle and mount the
component yourself. ``npm install buckaroo-js-core``. The flow has
two halves — a backend that serializes the artifact, and a React
component that resolves it and hands it to ``BuckarooStaticTable``.

The Python side is the same ``prepare_buckaroo_artifact`` /
``artifact_to_json`` call shown above; serve the resulting JSON
either inline in the page (the ``#buckaroo-data`` block, escaped
exactly like the raw-JS path) or as a ``GET /api/<table>.json``
endpoint your React code fetches.

On the JS side, import ``BuckarooStaticTable`` and the resolver
helpers and feed them the artifact:

.. code-block:: tsx

    import {
        BuckarooStaticTable,
        resolveDFDataAsync,
        preResolveDFDataDict,
    } from "buckaroo-js-core";
    import "buckaroo-js-core/dist/style.css";

    export async function loadArtifact(url: string) {
        const artifact = await fetch(url).then((r) => r.json());
        const [dfData, summaryStats] = await Promise.all([
            resolveDFDataAsync(artifact.df_data),
            resolveDFDataAsync(artifact.summary_stats_data),
        ]);
        const resolved: any = {
            embed_type: artifact.embed_type ?? "DFViewer",
            df_data: dfData,
            df_viewer_config: artifact.df_viewer_config,
            summary_stats_data: summaryStats,
        };
        if (artifact.embed_type === "Buckaroo" && artifact.df_data_dict) {
            resolved.df_data_dict = await preResolveDFDataDict(artifact.df_data_dict);
            resolved.df_data_dict.main = dfData;
            resolved.df_display_args = artifact.df_display_args;
            resolved.df_meta = artifact.df_meta;
            resolved.buckaroo_options = artifact.buckaroo_options;
            resolved.buckaroo_state = artifact.buckaroo_state;
        }
        return resolved;
    }

    export function MyTable({ artifact }: { artifact: any }) {
        return (
            <div className="buckaroo_anywidget" style={{ width: "100%", height: "100vh" }}>
                <BuckarooStaticTable artifact={artifact} />
            </div>
        );
    }

This is the same path ``static-embed.tsx`` uses internally
(see ``packages/js/static-embed.tsx``); you're substituting your own
page shell and your own backend transport. The parquet payload in
``df_data`` (and the per-tab payloads in ``df_data_dict`` for the
full Buckaroo UI) is what ``resolveDFDataAsync`` /
``preResolveDFDataDict`` decode — skip that step and the table
renders empty.

Same eager-only limitations as static HTML in either path.

When to use it: embedding into a Sphinx docs page, a marketing site,
a CMS-rendered article, a multi-table dashboard. You control the
surrounding HTML and CSS; Buckaroo just renders into a div you give it.


4. Buckaroo server
~~~~~~~~~~~~~~~~~~

The Buckaroo server is a Tornado application that loads files
server-side and serves the table over WebSocket. It's the Infinite
widget without a notebook.

Start it:

.. code-block:: bash

    python -m buckaroo.server --port 8700

Then load a file:

.. code-block:: bash

    curl -X POST http://localhost:8700/load \
        -H 'Content-Type: application/json' \
        -d '{"session":"sales", "path":"/data/sales.parquet", "mode":"viewer"}'

The server reads the file (pandas or polars depending on extension and
what's installed), creates a session, and (by default) opens a browser
to ``/s/sales``. The page connects back via WebSocket and pulls row
ranges on demand.

``mode`` controls the widget type:

- ``"viewer"`` — DFViewer with infinite scroll (default).
- ``"buckaroo"`` — full BuckarooWidget UI with summary stats and
  command editing.
- ``"lazy"`` — for polars LazyFrames; pushes operations down to polars.

The server is also what powers Buckaroo's MCP integration. ``claude mcp
add buckaroo-table -- uvx --from "buckaroo[mcp]" buckaroo-table`` plugs
the server into Claude Code so the assistant can open data files in
your browser.

When to use it: dataframes too big to ship eagerly; a stable URL you
want to revisit; integration with external tools (MCP, scripts,
``curl``); team viewing of files on a shared host.


5. Full JS embedding via npm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``npm install buckaroo-js-core`` and import the React components
directly — no Python required at any point. Build the
``df_viewer_config`` and the row data on the JS side (typically from
a parquet file fetched over HTTP, or from your own backend) and feed
it to ``DFViewer`` or ``BuckarooStaticTable``. This is the same set
of components the static-embed bundle and the server-embed path
above use.

The Storybook stories drive the components from raw JS data with no
Python on the other end. Run them locally with:

.. code-block:: bash

    cd packages/buckaroo-js-core && pnpm storybook
    # then open http://localhost:6006

The most directly relevant stories:

- `DFViewer.stories.tsx <https://github.com/buckaroo-data/buckaroo/blob/main/packages/buckaroo-js-core/src/stories/DFViewer.stories.tsx>`_ —
  plain table fed by a JS ``df_data`` array and a ``df_viewer_config``
  object. Closest match to what an npm consumer will write.
- `DFViewerInfiniteShadow.stories.tsx <https://github.com/buckaroo-data/buckaroo/blob/main/packages/buckaroo-js-core/src/stories/DFViewerInfiniteShadow.stories.tsx>`_ —
  the infinite-scroll variant with a JS-side mock datasource, showing
  the row-fetch contract you'd implement against your backend.
- `BuckarooWidgetTest.stories.tsx <https://github.com/buckaroo-data/buckaroo/blob/main/packages/buckaroo-js-core/src/stories/BuckarooWidgetTest.stories.tsx>`_ —
  the full BuckarooWidget with status bar, summary stats, and a JS-side
  shim that handles search via ``quick_command_args``. Useful for
  understanding what the widget expects from the host app once Python
  is out of the picture.
- `Styling.stories.tsx <https://github.com/buckaroo-data/buckaroo/blob/main/packages/buckaroo-js-core/src/stories/Styling.stories.tsx>`_
  and
  `ThemeCustomization.stories.tsx <https://github.com/buckaroo-data/buckaroo/blob/main/packages/buckaroo-js-core/src/stories/ThemeCustomization.stories.tsx>`_ —
  same theming and column-config dicts described in
  :doc:`theme-customization` and :doc:`data_flow`, but assembled in JS.


Interactive features and where they work
----------------------------------------

Two of Buckaroo's status-bar features need a live Python runtime to
function: they translate user input into a transform that re-runs on
the source DataFrame, then reship the result to the browser.

- **Search** — the search box on the status bar (``quick_command_args``)
  runs the ``Search`` command, which filters the dataframe with
  ``df[col].str.find(...)`` across string columns.
- **Post-processing** — the post-processing dropdown picks a
  ``post_processing_method``, which calls a Python function that
  rewrites the cleaned dataframe (e.g. add a derived column, reshape,
  or roll up).

Both flow through the same path: the front end mutates
``buckaroo_state``, the Python side observes the change, the dataflow
recomputes ``processed_df``, and the new data goes back over the wire.
No Python = no recompute.

Both also require the full BuckarooWidget UI — DFViewer doesn't have
a status bar, so there's nowhere to type a search term or pick a
post-processing method.

.. list-table::
   :header-rows: 1
   :widths: 38 24 38

   * - Deployment
     - Search & post-processing
     - Why
   * - Notebook ``BuckarooWidget`` / ``BuckarooInfiniteWidget``
     - Yes
     - Kernel runs the transform
   * - Notebook ``XorqBuckarooWidget`` / ``XorqBuckarooInfiniteWidget``
     - Yes
     - Kernel rewrites the ibis expression and pushes the new query down
   * - Notebook ``DFViewer``
     - No
     - No status bar
   * - Static HTML (``to_html``)
     - No
     - No Python at view time
   * - HTML + JS artifact
     - No
     - No Python at view time
   * - Buckaroo server, ``mode="buckaroo"``
     - Yes
     - Server holds a dataflow and re-runs it on state change
   * - Buckaroo server, ``mode="viewer"`` / ``mode="lazy"``
     - No
     - No dataflow on the session, no status bar

Sorting and infinite-scroll row fetching are not in this bucket — sort
is pushed to Python in the Infinite/server path but works without it
elsewhere (the eager paths sort what's already in the browser). It's
specifically search and post-processing that fall off when there's no
Python on the other end.

If you need search in a static deliverable, the workaround is to apply
the filter in Python before generating the artifact and ship a
narrowed DataFrame.


Quick chooser
-------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Situation
     - Use
   * - Exploring data in a notebook
     - ``BuckarooWidget`` (notebook / anywidget)
   * - Sharing a one-off report
     - ``to_html()`` (static HTML)
   * - Buckaroo inside a docs page or CMS
     - ``prepare_buckaroo_artifact()`` + your own HTML
   * - Big file, want infinite scroll without a notebook
     - Buckaroo server
   * - Data lives in DuckDB / Postgres / Snowflake / BigQuery
     - ``XorqBuckarooInfiniteWidget`` (notebook, push-down stats)
   * - Letting Claude Code view data files
     - Buckaroo server via MCP (``buckaroo[mcp]``)
   * - JS app, no Python at view time, npm install
     - ``buckaroo-js-core`` (npm) — see "Full JS embedding via npm"
   * - Read-only table inside an existing app
     - ``DFViewer`` family (any deployment)
   * - Full clean-and-explore UI
     - ``BuckarooWidget`` family (any deployment)


Styling and theming
-------------------

All embedding modes accept the same display-configuration options.
``component_config`` (theme, layout) and ``column_config_overrides``
(per-column color maps, tooltips, displayer choice) are passed on
widget construction in the notebook, embedded into the artifact for
static modes, and POSTed to ``/load`` for the server.

- :doc:`theme-customization` — color schemes, accent colors, spacing,
  light/dark mode, and the full ``component_config.theme`` reference.
- :doc:`data_flow` — column-level styling: ``color_map_config``,
  conditional formatting, post-processing functions, custom style
  methods.

The same theme dict applied to a notebook widget will look identical
in a static HTML embed and a server-rendered session.
