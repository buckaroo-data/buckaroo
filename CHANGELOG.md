# Changelog

## Unreleased

### Security (server) — BREAKING

The standalone / MCP server (`buckaroo.server`) now authenticates requests,
following Jupyter's model. **This is a breaking change for clients that
reach the server without a token**: update them to pass one, or run with
`BUCKAROO_TOKEN=""` to opt out on a trusted machine.

- Token auth on by default. The server mints a token at startup (printed to
  stderr, written to a 0600 connection file at
  `~/.buckaroo/runtime/buckaroo-<port>.json`), or honors `BUCKAROO_TOKEN`.
  Pass it as `Authorization: token <t>`, `?token=<t>`, or the cookie the
  page sets. `BUCKAROO_TOKEN=""` disables auth.
- WebSocket origin policy is now same-origin plus an allowlist
  (`--allow-origin` / `BUCKAROO_ALLOW_ORIGIN`, `*` for all), replacing the
  permissive default. `BUCKAROO_STRICT_ORIGIN` is removed.
- `Host`-header check refuses non-loopback hosts (DNS-rebinding defense;
  `BUCKAROO_ALLOW_REMOTE_ACCESS=1` to disable).
- XSRF cookies on; `/s/` sends a `frame-ancestors` CSP.
- `/health` is now minimal (`{status, version}`); pid/paths moved to the
  token-authenticated `/diagnostics`. The MCP tool reads the connection file
  for the pid and only kills a process it can confirm is a buckaroo server.
- Session ids are validated (`[A-Za-z0-9._-]`, ≤128) and escaped where the
  `/s/` page renders them, closing a reflected-XSS vector; the browser-focus
  path no longer interpolates them into AppleScript.

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



