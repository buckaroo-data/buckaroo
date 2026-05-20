# Contributing to Buckaroo

We love contributions! This guide covers development setup, building, testing, and releasing.

## Development setup

### Prerequisites
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- [pnpm](https://pnpm.io/) for JavaScript dependency management
- Node.js >= 18
- Python >= 3.11

### Python

```bash
git clone https://github.com/buckaroo-data/buckaroo.git
cd buckaroo
uv sync --dev --all-extras
```

### JavaScript

```bash
cd packages/buckaroo-js-core
pnpm install
```

### Full build (JS + Python wheel)

```bash
./scripts/full_build.sh
```


## Running tests

### Python

```bash
uv run pytest tests/unit/ -v
uv run ruff check --fix
```

### JavaScript

```bash
cd packages/buckaroo-js-core
pnpm test
```

### Storybook (component development)

```bash
cd packages/buckaroo-js-core
pnpm storybook
# open http://localhost:6006
```

Build a static Storybook site:
```bash
cd packages/buckaroo-js-core
pnpm build-storybook
```

### Playwright (UI tests against Storybook)

Install browsers:
```bash
cd packages/buckaroo-js-core
pnpm exec playwright install
```

Run tests:
```bash
pnpm test:pw --reporter=line
```

Useful variants:
```bash
pnpm test:pw:headed   # visible browser
pnpm test:pw:ui       # Playwright UI
pnpm test:pw:report   # open HTML report
```


## Adding dependencies

```bash
uv add <package>                              # main dependency
uv add --group <group> <package>              # extras group
```


## Release process

1. Update `CHANGELOG.md`
2. Trigger the **Release** workflow via GitHub Actions (`workflow_dispatch`), choosing `patch`, `minor`, or `major`
3. The workflow bumps the version in `pyproject.toml`, creates the tag, builds, publishes to PyPI, and creates a GitHub release


## Reporting issues

We welcome [issue reports](https://github.com/buckaroo-data/buckaroo/issues). Please choose the proper issue template so we get the necessary information.
