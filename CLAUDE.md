# Buckaroo

DataFrame viewer widget for Jupyter + standalone browser. Python backend (uv/hatch), TypeScript/React frontend (AG-Grid, pnpm workspaces).

## Project Layout

```
buckaroo/              Python package — analysis pipeline, server, compare tool, MCP
packages/
  buckaroo-js-core/    Core TS/React components, AG-Grid integration, Storybook
  buckaroo-widget/     anywidget wrapper (esbuild)
tests/
  unit/                Python unit tests (pytest)
scripts/               Build, test, release scripts
```

## Build & Test

```bash
# Full build (JS + Python wheel)
./scripts/full_build.sh

# Python
uv sync --dev --all-extras
pytest -vv tests/unit/
uv run ruff check --fix

# JavaScript
cd packages && pnpm install
cd packages/buckaroo-js-core && pnpm run build && pnpm test
cd packages/buckaroo-js-core && pnpm run test:pw    # Playwright E2E against Storybook

# Storybook (component dev)
cd packages/buckaroo-js-core && pnpm storybook
```

Test suite should complete in under 40 seconds. If it doesn't, something is wrong.

## CI

Runs on push to main and PRs. Key jobs: LintPython, TestJS, BuildWheel, TestPython (3.11-3.14), Playwright (Storybook, Jupyter, Marimo, WASM). Uses `depot-ubuntu-latest` runners.

## Architecture Notes

- **Column renaming**: Internally rewrites column names to a,b,c... — use `orig_col_name` to map back to real names.
- **Styling config**: Column behaviour driven by `column_config` JSON from Python→JS. Supports `color_map_config`, `tooltip_config`, `merge_rule`, `ag_grid_specs`.
- **Adding a new color rule**: Update `DFWhole.ts` (TS interface), `Styler.tsx` (function + case), Python docs/tests.
- **gridUtils.ts**: `dfToAgrid` must use `lcc3` (pinned), not `lcc2`. Linter may revert this — commit promptly.
- **`provides_defaults` in ColAnalysis**: Use `np.nan` not `0` for numeric stats fallbacks.

## Code Style

- No bare `except:` — use `except Exception:` (bare catches SystemExit).
- Don't put imports inside functions unless absolutely necessary.
- Prefer surgical, generalizable changes — don't special-case code to pass tests.
- Slot new tests into existing test files when possible.

## Release Process

1. Update CHANGELOG.md
2. Tag (no 'v' prefix): `git tag 0.12.13`
3. Push tag: `git push origin tag 0.12.13`
4. Release workflow generates notes and publishes to PyPI
