Why Buckaroo Uses Depot for CI
===============================

`Depot <https://depot.dev/>`_ sponsors Buckaroo's CI infrastructure. I
ran a controlled benchmark — 21 runs across different scenarios — to
understand exactly what that sponsorship buys. The results surprised me.

The problem with GitHub Actions
--------------------------------


GitHub Actions is slow, but not in the way I expected. The jobs
themselves are fine — the runners are fast enough. The problem is
queueing. When you have a 23-job pipeline and GitHub is busy, your jobs
don't start simultaneously. They trickle in one at a time over minutes.

When your CI takes 10 minutes because of queueing, you stop pushing
small changes. You batch things up. You skip the test run "just this
once." You merge without waiting for green because you've already
context-switched to something else. Slow CI makes you write worse code.


What Buckaroo's CI does
------------------------

Buckaroo is a DataFrame viewer with a Python backend and TypeScript/React
frontend. It deploys to 8 environments — Jupyter, Marimo, JupyterLite
(WASM), Marimo WASM, VSCode, Google Colab, static embeds, and a
standalone server (used for MCP). I can't manually test each environment
on every code change.

The CI pipeline runs **23 jobs** across 2 waves:

- **Wave 1** (no dependencies): lint, JS build + test, wheel build,
  Python tests across 4 versions with two dependency strategies (8 matrix
  jobs), styling screenshots, docs build
- **Wave 2** (needs the built wheel): 6 Playwright integration suites
  (Storybook, JupyterLab, Marimo, WASM Marimo, Server, Static Embed),
  MCP integration, smoke tests, TestPyPI publish

Three months ago this pipeline had 3 jobs.


LLMs changed the equation
---------------------------

LLM coding changed the way I approach devops. Claude made it possible to
get my Playwright integration tests to a place where I trust them to run
reliably. But LLMs also make testing more important than ever. When
Claude makes a change across 5 files, I need to know in minutes — not 10
minutes — whether it broke something. The tighter the feedback loop, the
more ambitious the changes I can attempt.


The benchmark
--------------

I ran the same 23-job pipeline on both Depot and GitHub Actions runners
across 21 runs over a Sunday night and Monday morning, covering cold
cache, warm cache, parallel, and sequential scenarios. All runs used
2-CPU Linux runners.

Reproduction scripts are in the `buckaroo repo
<https://github.com/buckaroo-data/buckaroo/tree/main/scripts>`_:

.. code-block:: bash

    # Critical path for a single run
    bash scripts/ci_critical_path.sh <run-id>

    # List runs for a PR or branch
    bash scripts/ci_list_runs.sh <pr-number-or-branch>

    # Full timing data as JSON (pipe to ci_timing_table.py)
    bash scripts/ci_all_timings.sh <run-id> [<run-id> ...] \
      | python3 scripts/ci_timing_table.py --labels "Run 1" "Run 2" ...

    # Launch paired cold-cache benchmark runs
    bash scripts/cold_cache_benchmark.sh


The results
------------

Critical path time (excluding the non-blocking Windows job):

.. list-table::
   :header-rows: 1
   :widths: 35 12 12 12 12 5

   * - Scenario
     - Mean
     - Std Dev
     - Min
     - Max
     - n
   * - GitHub, Sunday night, 1 PR
     - 3m09s
     - —
     - 3m09s
     - 3m09s
     - 1
   * - GitHub, Monday, cold, 3 parallel
     - 9m15s
     - ±30s
     - 8m49s
     - 9m49s
     - 3
   * - GitHub, Monday, warm, 3 parallel
     - 8m09s
     - ±158s
     - 5m06s
     - 11m11s
     - 6
   * - GitHub, Monday, warm, sequential
     - 5m19s
     - ±62s
     - 4m25s
     - 6m28s
     - 3
   * - Depot, Monday, cold, 3 parallel
     - 3m53s
     - ±2s
     - 3m50s
     - 3m55s
     - 3
   * - Depot, Monday, warm, 3 parallel
     - 4m08s
     - ±23s
     - 3m38s
     - 4m32s
     - 6

Aggregated across all Monday runs:

.. list-table::
   :header-rows: 1
   :widths: 30 12 12 12 12 5

   * - Runner
     - Mean
     - Std Dev
     - Min
     - Max
     - n
   * - GitHub Actions
     - 7m46s
     - ±143s
     - 4m25s
     - 11m11s
     - 12
   * - Depot
     - 4m03s
     - ±20s
     - 3m38s
     - 4m32s
     - 9

**Depot's standard deviation is ±20 seconds. GitHub's is ±143 seconds.**


What's actually happening
--------------------------

Each Depot runner takes a few seconds longer to provision than a GitHub
runner that's already available — there's a fixed overhead per machine
spin-up. That makes individual job durations slightly longer on Depot.
But it doesn't matter because Depot provisions all runners in parallel.
GitHub provisions them sequentially from a shared pool, so you wait
for each one.

"Wave 1 stagger" is the time between the first and last Wave 1 job
starting — it measures how long the runner takes to provision all the
parallel jobs:

- **Depot**: 14–35 seconds. All jobs start within half a minute.
- **GitHub, Monday morning**: 90–447 seconds. Jobs trickle in over
  1.5–7 minutes as runners become available.

On a Sunday night with one PR, GitHub's stagger was 1 second — identical
to Depot. The difference only shows up under load on Monday morning.

Cache performance is close. Depot reads caches ~30% faster (2.8s vs 4.1s
per step), but GitHub writes caches ~3x faster (0.8s vs 2.1s per step on
Monday). Cache writes happen in post-job cleanup steps and don't affect
the critical path. Neither difference materially changes the overall
timing.


What Depot actually gave me
-----------------------------

Three things, in order of importance:

1. **Consistent provisioning.** Depot provisions all runners within 20
   seconds, every time. GitHub ranges from instant to 7 minutes depending
   on load. When you're pushing 10 times a day and iterating with an LLM,
   unpredictable queue times kill your flow.

2. **Confidence to invest in CI.** Because I knew the infrastructure was
   solid, I actually spent time making CI better — removing unnecessary
   setup steps, parallelizing into two waves, tuning the pipeline. When
   your CI infrastructure feels like a liability, you don't invest in
   it — you avoid it.

Before and after
-----------------

On December 24, 2025 — the day Depot's CTO responded to my sponsorship
request — Buckaroo's CI had **3 jobs**: lint, Python tests, and a wheel
build.

Since then I've added **20 new jobs**:

- **6 Playwright integration suites** — Storybook, JupyterLab, Marimo,
  WASM Marimo, Server, and Static Embed. These catch real bugs — "it
  renders in Jupyter but is blank in Marimo" is the kind of thing I
  don't want to eyeball on every PR.
- **Python tests across 4 versions** with two dependency strategies
  (min pinned + max latest) — 8 matrix jobs total
- **MCP integration tests** — verifying the MCP server works against
  the built wheel
- **Smoke tests** for each optional extras group
- **Styling screenshot comparisons** — before/after captures on every PR
- **Docs build + link checker**
- **TestPyPI publish** on every PR with an install command in the PR
  comment

The critical path completes in about **4 minutes** on Depot. The Windows
job runs longer but is non-blocking (``continue-on-error: true``).


Testing against dependency versions
-------------------------------------

Depending on pandas, PyArrow, and polars simultaneously is tricky. A new
pandas release can change default string dtype behavior. A polars update
can change how Duration columns serialize. PyArrow versions affect
Parquet compatibility.

Buckaroo runs two sets of test suites: the regular suite tests against
the minimum pinned versions in ``pyproject.toml``, and the "Max
Versions" suite tests against the latest releases of every dependency.
This runs across Python 3.11 through 3.14. The goal is to catch
compatibility issues before users do.

This strategy only works if the test suite is fast enough to run both
configurations on every push. On slow CI, you'd run one and hope for
the best.


What I'd tell other open source maintainers
---------------------------------------------

If your CI takes more than 5 minutes and you've been meaning to fix it
but haven't, Depot's `open source sponsorship program
<https://depot.dev/open-source>`_ is worth applying to. The switch is
straightforward — change the ``runs-on`` label in your workflow YAML,
everything else stays the same.

The real value isn't raw speed — individual jobs run at about the same
pace. It's that your jobs all start at once instead of queueing. That
consistency changes your behavior. You push more often, you test more
things, you catch problems earlier. Slow CI is a tax on every decision
you make. Removing that tax compounds.
