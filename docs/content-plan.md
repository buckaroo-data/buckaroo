
# Content Plan

## Published (merged or ready to merge)

### Dastardly DataFrame Dataset (PR #641)
Published at `docs/source/articles/dastardly-dataframe-dataset.rst`. Covers DDD with static embeds, full dtype coverage table, weird types for pandas and polars. Includes Polars DDD (issue #622).

### How types and data move from engine to browser
Published at `docs/source/articles/types-to-display.rst`. Column renaming (a,b,c..z,aa,ab), type coercion before parquet, fastparquet encoding, base64 transport, hyparquet decode in browser, displayer/formatter dispatch. Full pipeline trace for a single cell value.

### So you want to write a DataFrame viewer
Published at `docs/source/articles/so-you-want-to-write-a-dataframe-viewer.rst`. Comparison of open source DataFrame viewers (Buckaroo, Perspective, iTables, Great Tables, DTale, Mito, Marimo, ipydatagrid, quak). Research in `~/personal/buckaroo-writing/research/`.

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


