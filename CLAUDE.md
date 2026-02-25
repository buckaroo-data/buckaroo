# Buckaroo Development Guide

## Architecture Philosophy

Buckaroo is a **framework** for building table-based data applications, plus a set of
reference apps built on that framework. This distinction matters when making changes:

- **Framework features** belong in the core (styling config, column config, displayers,
  color rules, etc.). They should be general-purpose and usable by any app built on
  buckaroo — not special-cased for one use case.
- **App-specific behaviour** (e.g. compare tool styling, Jupyter widget defaults) lives
  in the app layer and uses framework primitives to express its intent.
- **Never add CSS hacks or one-off special cases** for a specific app feature. If a
  visual need arises for an app (e.g. "highlight PK columns differently"), the right fix
  is to add a general framework primitive (e.g. a `color_static` color rule) and then
  express the app logic through that primitive.

## Project Layout

```
buckaroo/          Python package — analysis pipeline, server, compare tool
packages/
  buckaroo-js-core/   Core TS/React components, styling config, ag-Grid integration
  js/                 Widget build (Jupyter)
tests/
  unit/              Python unit tests
  pw-tests/          Playwright browser tests
```

## Key Styling Config Concepts

Column behaviour is driven by a JSON `column_config` list passed from Python to JS.
Each entry supports:

- `color_map_config` — cell background coloring (`color_map`, `color_categorical`,
  `color_not_null`, `color_from_column`, `color_static`)
- `tooltip_config` — cell tooltip content
- `merge_rule` — visibility (`"hidden"`)
- `ag_grid_specs` — escape hatch for raw ag-Grid `ColDef` properties

If a visual need requires a new `color_rule` variant, add it to:
1. `DFWhole.ts` — TypeScript interface + union type
2. `Styler.tsx` — `colorXxx()` function + `getStyler()` case
3. Python docs / tests

## Running Tests

```bash
# Python unit tests
pytest tests/unit -v

# Playwright tests (requires built JS + running server)
cd packages/buckaroo-js-core && npx playwright test
```

## JS Build

```bash
cd packages/buckaroo-js-core && npm run build
cd packages/js && npm run build
```
