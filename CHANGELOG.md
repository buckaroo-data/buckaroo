# Changelog

## 0.12.13 — 2026-02-24

### Bug Fixes
- fix: handle zero PRs in release notes; extract CHANGELOG updater to script (#580)
- fix: plain release notes fallback + sync version to 0.12.11 (#579)
- fix: MCP + server reliability, observability, and hardening (#578)

### Other
- for the PR (#577)

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



