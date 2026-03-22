Why Buckaroo Uses Depot for CI
===============================

`Depot <https://depot.dev/>`_ sponsors Buckaroo's CI infrastructure and
I really appreciate that. This article explains why I switched and what
changed.

The problem with GitHub Actions
--------------------------------

GitHub Actions is slow and the cache is slower. I have known this for a
long time. I believe in CI, but it is hard to set up, and then once you
get it running it's way slower than it needs to be. It's like being
saddled with a teammate who won't pull their weight and has no interest
in changing — it demotivates you.

When your CI takes 10+ minutes, you stop pushing small changes. You
batch things up. You skip the test run "just this once." You merge
without waiting for green because you've already context-switched to
something else. Slow CI makes you write worse code.

What Buckaroo's CI actually does
---------------------------------

Buckaroo is a complex project with a significant Python and TypeScript
codebase. The full package is deployed to 8 environments:

- Jupyter (notebook + lab)
- Marimo
- JupyterLite (WASM/Pyodide)
- Marimo WASM
- VSCode (can't integration-test this one)
- Google Colab (same)
- Static self-contained embeds
- Buckaroo server (used for the MCP server)

The CI pipeline runs 22 jobs across 2 waves: linting, JS build + test,
a Python wheel build, then 6 Playwright integration test suites
(Storybook, JupyterLab, Marimo, WASM Marimo, Server, Static Embed),
Python tests across 4 versions (3.11–3.14), an MCP integration test,
styling screenshot comparisons, and a docs build.

Integration testing in particular is really important — I can't manually
test each environment for each code change. When a change breaks Marimo
but not Jupyter, I need to know before it ships.

LLMs changed the equation
---------------------------

LLM coding has changed the way I approach devops. First, it makes it
easier to accomplish devops changes — this is great. Claude in
particular has made it possible to get my Playwright integration tests
to a place where I really trust them to run reliably. That has been
awesome.

At the same time, LLMs make testing more important than ever. I cannot
move fast with LLMs without a solid test suite that runs fast. When
Claude makes a change across 5 files, I need to know in minutes — not
10 minutes — whether it broke something. The tighter the feedback loop,
the more ambitious the changes I can attempt.

What Depot changed
-------------------

The CTO responded to my request for open source sponsorship on
Christmas Eve. Since then:

- **Critical path: ~3.5 minutes.** From push to all-green (ignoring
  the non-blocking Windows job). 22 jobs, 3.5 minutes. That's fast
  enough that I don't context-switch away.
- **Commit to first step running: ~30 seconds** on Linux. GitHub adds
  about 6 seconds of latency. Depot provisions a runner in ~18 seconds.
  On GitHub's own runners this used to be minutes.
- **Cost: ~$0.18 per run** on 2-CPU runners. I tested 4-CPU and 8-CPU
  runners too — no measurable speedup. The workload is I/O-bound
  (package installs, Playwright browser launches), not CPU-bound.
  Bigger runners just cost more for the same wall-clock time.
- **~$9–18/month** at my typical push cadence. The Developer plan
  ($20/month, 2,000 included minutes) covers about 52 full CI runs.

The numbers
------------

Here's what the pipeline looks like on Depot 2-CPU runners:

.. list-table::
   :header-rows: 1
   :widths: 40 15 15

   * - Job
     - Duration
     - % Useful Work
   * - Python / Test (avg across versions)
     - 1m 41s
     - 84%
   * - JupyterLab Playwright
     - 2m 03s
     - 77%
   * - Storybook Playwright
     - 1m 53s
     - 81%
   * - Server Playwright
     - 2m 05s
     - 74%
   * - Marimo Playwright
     - 1m 30s
     - 68%
   * - WASM Marimo Playwright
     - 1m 40s
     - 70%
   * - Build JS + Python Wheel
     - 0m 59s
     - 44%
   * - JS / Build + Test
     - 0m 53s
     - —
   * - Windows (non-blocking)
     - 8m 02s
     - 28%

The "% Useful Work" column is actual test/build time vs. setup overhead
(checkout, install dependencies, provision). Most jobs are 70–84%
useful, which is good. Windows is 28% useful because ``uv install``
takes 3m29s on Windows vs. 3 seconds on Linux.


Before and after
-----------------

Before Depot, Buckaroo's CI had **4 jobs**: lint and Python tests on 3
versions. That took about 6 minutes on GitHub Actions runners.

Today Buckaroo's CI has **23 jobs**: lint, JS build + test, wheel build,
Python tests across 4 versions with two dependency strategies, 6
Playwright integration suites, MCP integration, smoke tests, docs build,
styling screenshots, TestPyPI publish, and Windows. That takes about
**7 minutes** on Depot.

Six times more jobs in roughly the same wall-clock time. The fast
runners made it practical to add all of those integration tests — if
each new test suite added 5 minutes, I never would have added them.


Testing against dependency versions
-------------------------------------

Depending on pandas, PyArrow, and polars simultaneously is tricky.
These are complex packages with their own release cadences and breaking
changes. A new pandas release can change default string dtype behavior.
A polars update can change how Duration columns serialize. PyArrow
versions affect Parquet compatibility.

Buckaroo runs two sets of test suites: the regular suite tests against
the minimum pinned versions in ``pyproject.toml``, and the "Max
Versions" suite tests against the latest releases of every dependency.
This runs across Python 3.11 through 3.14. The goal is to catch
compatibility issues before users do — if polars 1.x breaks something,
I want to know from CI, not from a bug report.

This strategy only works if the test suite is fast enough to run both
configurations on every push. On slow CI, you'd run one and hope for
the best.


What I'd tell other open source maintainers
---------------------------------------------

If your CI takes more than 5 minutes and you've been meaning to fix it
but haven't, Depot's `open source sponsorship program
<https://depot.dev/open-source>`_ is worth applying to. The switch was
straightforward — change the ``runs-on`` label in your workflow YAML,
everything else stays the same.

The real value isn't the raw speed. It's that fast CI changes your
behavior. You push more often, you test more things, you catch problems
earlier. Slow CI is a tax on every decision you make. Removing that tax
compounds.
