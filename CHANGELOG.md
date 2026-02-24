# Changelog

# Output 2 — CHANGELOG.md Entry

## 0.12.10 — 2026-02-24

Light/dark theme support, pluggable analysis framework v2, lazy polars mode for large datasets, marimo widget integration, and major CI/CD automation improvements.

### Features

- Add light/dark theme support with automatic OS preference detection (#516)
- Add pluggable analysis framework v2 with `@stat` decorator, typed DAG, and error propagation (#515)
- Add lazy polars mode to headless server for streaming arbitrarily large datasets (#510)
- Add marimo widget static assets and set marimo≥0.19.7 minimum version (#511)
- Add per-request `no_browser` field to `/load` POST body (#568)
- Add `version` field to `/health` endpoint and auto-kill stale servers (#496)
- Wire polars widgets to DfStatsV2 with polars-native `@stat` functions (#517)

### Fixes

- Fix pandas 3.0+ compatibility: replace removed `is_numeric()` with `is_numeric_dtype()` (#570)
- Add `pandas` to `[marimo]` extras — required at module level (#570)
- Fix summary stats count/freq rows to inherit column alignment (#545)
- Fix WASM marimo test with Pyodide-bundled fastparquet and pyarrow (#532)
- Fix marimo Playwright tests by using bare widget expressions (#531)
- Fix MCP app search not updating table data (#495)
- Fix MCP app summary stats view showing no rows (#494)
- Fix blank rows when scrolling small DataFrames (#483)
- Add `GH_TOKEN` to automated release workflow (#576)
- Fix TestPyPI installs with `--index-strategy unsafe-best-match` (#564)

### Performance

- Optimize CI by consolidating workflows and eliminating duplicate builds (#533, #523, #525)
- Skip unnecessary dependencies in lint job (#527)
- Add timeouts to all CI jobs (#525)

### Testing

- Add 61 new tests for pandas_commands.py (49% → 78% coverage) (#474)
- Add pandas 3.0 compatibility regression tests (#473)
- Add DFViewerInfinite unit tests with TSX Jest discovery (#573)
- Add Playwright end-to-end tests for marimo notebooks (#497)
- Add light/dark theme screenshot audit (#499)
- Add MCP server integration tests (#572)

### CI/CD

- Add automated release workflow with version bumping and PyPI publishing (#574)
- Consolidate ci.yml + build.yml into checks.yml (#533)
- Add smoke tests for each optional extras group (#551)
- Make marimo Playwright tests required — no longer soft-fail (#542)
- Publish dev wheel to TestPyPI on every PR with PR comments (#537)
- Extract JupyterLab Playwright tests to dedicated job (#534)
- Extract JS build/Jest to separate job, run in parallel (#523)
- Add non-blocking Windows Python 3.13 test job (#547)
- Add Dependabot and weekly dependency compatibility checks (#550)
- Add actionlint pre-commit hook for GitHub Actions validation (#498)
- Fix dead if-conditions in build.yml (#528)
- Skip unnecessary dependencies in lint job (#527)

### Dependencies

- Bump actions/github-script to 8 (#567)
- Bump actions/checkout to 6 (#566)
- Bump actions/cache to 5 (#565)
- Bump actions/setup-node to 6 (#563)
- Bump astral-sh/setup-uv to 7 (#562)

## 0.8.3 2025-01-23
Fixes #299 Update height of ag-grid
Fixes tooltips so they can display values from other columns
adds color_categorical color_map_config
allows color_map_configs to accept a list of colors
improvements to datacompy_app

## 0.8.2 2025-01-15

This release makes it easier to build apps on top of buckaroo.

Post processing functions can now hide columns
CustomizableDataflow (which all widgets extend) gets a new parameter of `init_sd` which is an initial summary_dict.  This makes it easier to hard code summary_dict values.

More resiliency around styling columns.  Previously if calls to `style_column` failed, an error would be thrown and the column would be hidden or an error thrown, now a default obj displayer is used.

[Datacompy_app](https://github.com/capitalone/datacompy/issues/372) example built utilizing this new functionality.  This app compares dataframes with the [datacompy](https://github.com/capitalone/datacompy) library


## 0.8.0 2024-12-27
This is a big release that changes the JS build flow to be based on anywidget.  Anywidget should provide greater compatability with other notebook like environments such as Google Colab, VS Code notebooks, and marimo.

It also moves the js code to `packages/buckaroo_js_core` This is a regular react js component library built with vite.  This should make it easier for JS devs to understand buckaroo.

None of the end user experience should change with this release.



