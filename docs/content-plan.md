
# Content Plan

## Published (merged or ready to merge)

### Dastardly DataFrame Dataset (PR #641)
Published at `docs/source/articles/dastardly-dataframe-dataset.rst`. Covers DDD with static embeds, full dtype coverage table, weird types for pandas and polars. Includes Polars DDD (issue #622).

### How types and data move from engine to browser
Published at `docs/source/articles/types-to-display.rst`. Column renaming (a,b,c..z,aa,ab), type coercion before parquet, fastparquet encoding, base64 transport, hyparquet decode in browser, displayer/formatter dispatch. Full pipeline trace for a single cell value.

### So you want to write a DataFrame viewer
Published at `docs/source/articles/so-you-want-to-write-a-dataframe-viewer.rst`. Comparison of open source DataFrame viewers (Buckaroo, Perspective, iTables, Great Tables, DTale, Mito, Marimo, ipydatagrid, quak). Research in `~/personal/buckaroo-writing/research/`.

### Why Buckaroo uses Depot for CI
Draft at `docs/source/articles/why-depot.rst`. Depot sponsorship story. Honest benchmarking: Depot isn't measurably faster than GitHub runners (I/O-bound workload), but consistent provisioning + no minute quotas gave confidence to grow from 3 to 23 CI jobs. Pending: email to Depot CTO for input before publishing.

## Planned

### Static embedding improvements
- Publish JS to CDN → reduced embed size. Talk about the journey: Jupyter → Marimo/Pyodide → static embedding → smaller static embedding
- Page weight comparison: dbt (501KB compressed, 28MB total, 1.41s DCL), Snowflake (128kb/1.28mb/22.51mb/445ms), Databricks (127kb/797kb/313ms)
- Customizing buckaroo via API for embeds — show styling, link to styling docs
- Static search — maybe, take a crack at it
- Link to the static embedding guide

### Styling buckaroo chrome
Based on https://github.com/buckaroo-data/buckaroo/pull/583

### Buckaroo embedding guide
- Why to embed buckaroo
- Which config makes sense for you — along with data sizes reasoning
- Customizing appearance
- Customizing buckaroo

### Embedding buckaroo for bigger data
Parquet range queries on S3/R2 buckets. Sponsored by Cloudflare?

### How I made Buckaroo fast
The philosophy: do the right things fast, but mostly just do less. Not a performance optimization article — it's about architecture decisions that avoid work entirely.
- Column renaming to a,b,c means shorter keys everywhere, no escaping
- Parquet instead of JSON: moved from Python JSON serialization (the slowest part of the original render) to binary Parquet. Faster encoding, smaller payloads, type preservation for free
- Sampling: don't process the whole DataFrame. Sample first, compute stats on the sample, display the sample. The user sees 500 rows, not 500,000
- Summary stats: compute once, cache. Don't recompute on every view switch
- hyparquet decodes in the browser — no round-trip to the server for data
- LRU cache on decoded Parquet so switching between main/stats views doesn't re-decode
- AG-Grid does the hard rendering work (virtual scrolling, column virtualization) — don't fight it, feed it clean data
- The lesson: most "performance work" was removing unnecessary work, not optimizing hot paths

### Testing Buckaroo: unit tests, integration tests, and everything in between
How a solo developer tests a project that spans Python + TypeScript across 8 deployment environments.
- **Python unit tests** (pytest): serialization, stats computation, type coercion, column renaming. Fast, reliable, the foundation. ~60s for the full suite
- **JS unit tests** (vitest): component logic, displayer/formatter functions, parquet decoding. Run in Node, no browser needed
- **Playwright integration tests** (6 suites): Storybook (component rendering), JupyterLab (full widget lifecycle), Marimo, WASM Marimo, Server (MCP/standalone), Static Embed. These catch "it works in Jupyter but is blank in Marimo" — the bugs you can't find any other way
- **Styling screenshot comparisons**: before/after captures on every PR using Storybook + Playwright. Catches visual regressions (column width changes, color map shifts) that no unit test can detect
- **Smoke tests**: install the wheel with each optional extras group (`[mcp]`, `[notebook]`, etc.) and verify imports work. Catches dependency conflicts
- **MCP integration tests**: install the wheel, start the MCP server, make a `tools/call` request, verify the response includes static assets
- **Dual dependency strategy**: run all Python tests twice — once with minimum pinned versions, once with `--resolution=highest`. Catches pandas/polars/pyarrow compatibility issues before users do
- **The DDD as a test suite**: the Dastardly DataFrame Dataset isn't just documentation — each weird DataFrame exercises edge cases through the full serialization → display pipeline
- What I don't test: VSCode, Google Colab (no headless automation), visual pixel-perfect matching (too brittle)
- The lesson: integration tests are worth the CI investment. Most real bugs are at boundaries (Python→Parquet→JS→AG-Grid), not inside any one layer

