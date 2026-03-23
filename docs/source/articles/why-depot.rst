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
Christmas Eve.

I benchmarked the same 23-job pipeline on both Depot and GitHub
Actions runners — 3 parallel runs of each, on a Monday morning. Here's
what I found:

.. list-table::
   :header-rows: 1
   :widths: 35 20 20 20

   * - Scenario
     - Critical Path (mean)
     - Wave 1 Stagger
     - Variance
   * - GitHub, Sunday night, 1 PR
     - 3m15s
     - 0s
     - —
   * - GitHub, Monday AM, sequential
     - 5m19s
     - 90s
     - 4m25s – 6m28s
   * - GitHub, Monday AM, 3 parallel
     - 5m58s
     - 114s
     - 5m06s – 6m38s
   * - Depot, Monday AM, 3 parallel
     - 4m18s
     - 19s
     - 4m02s – 4m31s

"Wave 1 stagger" is the time between the first and last Wave 1 job
starting. On GitHub, Wave 1 jobs trickle in over 1–3 minutes as runners
become available. On Depot, they all start within 20 seconds.

The per-job times are actually slightly slower on Depot — every
individual job takes a few seconds longer. But it doesn't matter
because Depot starts all jobs simultaneously. GitHub's queueing delay
dwarfs any per-job difference.

The critical insight: **GitHub's performance ranges from 3m15s to
6m38s** depending on time of day and how many other repos are competing
for runners. **Depot is 4m02s–4m31s regardless.** That consistency is
worth more than raw speed.

What Depot actually gave me was three things:

- **Consistent provisioning.** Depot provisions a runner in ~20 seconds,
  every time. GitHub Actions runners can be just as fast on a Sunday
  night, but on a Monday morning they queue for minutes. When you're
  pushing 10 times a day and iterating with an LLM, unpredictable queue
  times kill your flow. Depot removed that variance.

- **No minute quotas to worry about.** With Depot's open source
  sponsorship, I stopped thinking about whether adding another test
  suite was "worth the minutes." That sounds small, but it changed my
  behavior completely. I went from 3 CI jobs to 23 in three months.

- **Confidence to invest in CI.** Because I knew the infrastructure was
  solid — reliable runners, no quota pressure — I actually spent time
  making CI better. I removed pnpm from Python test jobs that didn't
  need it. I parallelized the pipeline into two waves. I tuned the
  setup steps. When your CI infrastructure feels like a liability, you
  don't invest in it — you avoid it.

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

The "% Useful Work" column is actual test/build time vs. setup overhead
(checkout, install dependencies, provision). Most jobs are 70–84%
useful.


Before and after
-----------------

On December 24, 2025 — the day Depot's CTO responded to my sponsorship
request — Buckaroo's CI had **3 jobs**: lint, Python tests, and a
wheel build. That was it.

Since then I've added **20 new jobs**:

- **6 Playwright integration suites** — Storybook, JupyterLab, Marimo,
  WASM Marimo, Server, and Static Embed. These are the tests that
  actually catch real bugs — "it renders in Jupyter but is blank in
  Marimo" is the kind of thing I don't want to eyeball on every PR.
- **Python tests across 4 versions** with two dependency strategies
  (min pinned + max latest) — 8 matrix jobs total
- **MCP integration tests** — verifying the MCP server works against
  the built wheel
- **Smoke tests** for each optional extras group
- **Styling screenshot comparisons** — before/after captures on every PR
- **Docs build + link checker**
- **TestPyPI publish** on every PR with an install command in the PR
  comment

The pipeline now runs **23 jobs** and the critical path completes in
about **3.5 minutes** (the Windows job runs longer but is non-blocking
— ``continue-on-error: true``). Before Depot, 3 jobs took about 5
minutes on GitHub Actions runners.

The fast runners didn't just make existing tests faster — they made it
practical to keep adding tests. If each new Playwright suite added 5
minutes of wall-clock time, I never would have added 6 of them.


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
