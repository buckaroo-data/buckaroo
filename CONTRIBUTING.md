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

### Git hooks

The repo ships pre-commit / pre-push hooks under `.githooks/`. Point git at
them once per clone:

```bash
git config core.hooksPath .githooks
```

The shims defer to [pre-commit](https://pre-commit.com/) to run the checks
declared in `.pre-commit-config.yaml` (lint on commit, full-tree ruff +
`paddy_format --check` on push — same as CI's `Python / Lint` job). Make
sure pre-commit is on your PATH:

```bash
uv tool install pre-commit
```

Tracking the hooks under `.githooks/` instead of relying on `pre-commit
install`'s generated shims means every clone runs identical hook code,
and updates propagate via `git pull`.


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
