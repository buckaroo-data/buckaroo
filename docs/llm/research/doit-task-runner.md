# doit Task Runner Research

**Date:** 2026-03-01
**Context:** Evaluated as CI orchestration tool for Hetzner self-hosted CI. Conclusion: good tool, wrong model for our needs.

## What doit Is

Python-based task runner (like Make but in Python). Tasks defined in `dodo.py`, connected by file dependencies. DAG scheduler runs independent tasks in parallel (`doit -n 4`). Fail-fast on first failure. Actively maintained since 2008.

- Site: https://pydoit.org
- Install: `pip install doit`
- Config: `dodo.py` in project root

## How It Works

```python
# dodo.py
def task_build_js():
    return {
        'actions': ['cd packages/buckaroo-js-core && pnpm build'],
        'targets': ['packages/buckaroo-js-core/dist/index.js'],
    }

def task_build_wheel():
    return {
        'actions': ['hatch build'],
        'file_dep': ['packages/buckaroo-js-core/dist/index.js'],
        'targets': ['dist/buckaroo-0.0.0-py3-none-any.whl'],
    }

def task_pw_jupyter():
    return {
        'actions': ['bash scripts/test_playwright_jupyter.sh'],
        'file_dep': ['dist/buckaroo-0.0.0-py3-none-any.whl'],
    }
```

`doit -n 8` resolves the DAG automatically: build_js → build_wheel → pw_jupyter, with independent tasks running in parallel.

## Strengths

- **Pure Python** — no DSL, no YAML, just functions returning dicts
- **File-based dependencies** — tasks declare `file_dep` (inputs) and `targets` (outputs), doit connects the graph
- **Parallel execution** — `-n N` flag, scheduler handles ordering
- **Fail-fast** — stops on first failure
- **Incremental** — skips tasks when inputs haven't changed (like Make)
- **Mature** — 17+ years, good docs, used by Nikola static site generator
- **Zero infrastructure** — just a Python package, runs anywhere

## Why It Doesn't Fit Our CI Use Case

**Tasks are atomic.** A task runs to completion, then dependents start. There's no way for a running task to emit an intermediate artifact that unblocks a dependent while the task continues.

Our build pattern is:

```
build_js (12s) → emit JS bundle → build_wheel (5s) → emit wheel
```

With doit, these must be 3 separate tasks. That's fine for the DAG, but it means:

1. The build "job" is fragmented across 3 scheduler slots
2. No way to express "build_js and build_wheel are really one logical job that produces artifacts at two points"

What we actually want:

```
t=0   [build job starts]
t=12  JS bundle ready → pw_storybook, test_js start immediately
t=17  wheel ready → pw_jupyter, pw_marimo, pw_server start immediately
t=??  [build job continues with pytest, lint, etc.]
```

This is a **streaming dependency** pattern — a single task emitting artifacts mid-execution to unblock others. doit (and Make, and every DAG runner) models tasks as atomic units. The right tool for this is either:

- A CI system (GitHub Actions does this with artifact upload + dependent jobs)
- A custom asyncio script with `Event` objects (~50 lines)

## Where doit Would Work

If we accepted splitting the build into separate tasks (build_js, build_wheel, lint, test_js, test_python, pw_storybook, pw_jupyter, etc.), doit would orchestrate them well. The tradeoff: ~5s of scheduler overhead between build_js completing and build_wheel starting (task teardown + next task pickup), and the `dodo.py` needs `uptodate: [False]` on every task since CI always runs everything.

This is a reasonable fallback if the custom asyncio approach proves too brittle.

## Other Tools Evaluated

| Tool | Verdict | Why |
|------|---------|-----|
| **pypyr** | YAML-based alternative to doit | Same atomic-task limitation |
| **invoke** | Too simple | No DAG, no parallel |
| **nox** | Wrong domain | Multi-env Python testing, not CI orchestration |
| **snakemake** | Overkill | Bioinformatics DSL, steep learning curve |
| **luigi** | Outdated | Heavy, no mid-task emission either |
| **airflow/prefect** | Way overkill | Enterprise data pipeline orchestration |
| **Make** | Works but unreadable | Same atomic-task model, worse syntax for complex logic |
