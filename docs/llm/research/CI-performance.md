# CI Performance Research

**Date:** 2026-03-01
**Pipeline:** `.github/workflows/checks.yml`
**Runner provider:** [Depot](https://depot.dev)

## Summary

Buckaroo's CI runs 22 jobs across two waves on Depot GitHub Actions runners. The pipeline is **I/O-bound** — faster CPUs provide no measurable speedup. The blocking critical path is **~3.5 minutes**. Total cost is **~$0.18/run** on 2-CPU runners.

Tested 2-CPU, 4-CPU, and 8-CPU Depot runners (2 runs each, 4 test PRs total). Bigger runners cost 1.6–2.7x more with zero improvement. Run-to-run variance (±20s) exceeds differences between tiers.

---

## Pipeline Structure

Two waves of parallel jobs:

**Wave 1** (no dependencies, all start immediately):
- LintPython, TestJS, BuildWheel, CheckDocs, StylingScreenshots
- TestPython × 4 versions (3.11, 3.12, 3.13, 3.14)
- TestPythonMaxVersions × 4 versions
- TestPythonWindows

**Wave 2** (`needs: [BuildWheel]`):
- TestStorybook, TestServer, TestJupyterLab, TestMarimo, TestWASMMarimo
- TestMCPWheel, SmokeTestExtras, PublishTestPyPI

---

## Latency: Commit to Code Running

Measured via live experiment — created a PR and timed each phase with second-level precision.

```
git commit          T+0s
git push complete   T+6s     (local git + SSH)
GH webhook fires    T+10s    (run created)
Job assigned        T+12s    (queued to runner)
"Set up job" starts T+30s    (Linux) / T+97s (Windows)
```

| Phase | Latency |
|-------|---------|
| Commit → push complete | 6s |
| Push → GitHub run created | 4s |
| Run created → job assigned | 2s |
| **Depot Linux provisioning** | **18s** |
| **Depot Windows provisioning** | **85s** |

**GitHub adds ~6s.** The rest is Depot runner boot time.

### BuildWheel → Wave 2 Gap

Measured across 5 runs:

| Phase | Time |
|-------|------|
| BuildWheel completes → jobs queued | 2–16s |
| Jobs queued → "Set up job" starts | 17–25s |
| **Total dead time on critical path** | **20–35s** |

This provisioning gap is paid every wave transition. Not controllable.

---

## Runner Tier Comparison

### Methodology

Created test branches changing `depot-ubuntu-latest` → `depot-ubuntu-latest-{4,8}` and `depot-windows-2025` → `depot-windows-2025-{4,8}`. Ran each tier twice via separate PRs.

### Per-Job Results (format: run 1 / run 2)

| Job | 2-CPU (baseline) | 4-CPU | 8-CPU |
|-----|---------|-------|-------|
| Python / Lint | 0:32 | 0:31 / 0:32 | 0:33 / 0:29 |
| JS / Build + Test | 0:53 | 0:51 / 0:49 | 0:50 / 0:48 |
| Build JS + Python Wheel | 0:59 | 1:00 / 0:52 | 0:50 / 1:36 |
| Docs / Build + Check Links | 1:05 | 1:05 / 1:00 | 0:54 / 1:00 |
| Python / Test (3.11) | 1:45 | 1:43 / 2:01 | 1:40 / 1:41 |
| Python / Test (3.12) | 1:44 | 1:42 / 1:49 | 1:41 / 1:44 |
| Python / Test (3.13) | 1:39 | 1:44 / 1:36 | 1:36 / 2:00 |
| Python / Test (3.14) | 1:35 | 1:34 / 1:52 | 1:33 / 1:34 |
| MaxVer (3.11) | 1:41 | 1:40 / 1:37 | 1:40 / 1:39 |
| MaxVer (3.12) | 1:41 | 1:41 / 1:39 | 1:40 / 2:03 |
| MaxVer (3.13) | 1:41 | 1:41 / 1:38 | 1:39 / 1:37 |
| MaxVer (3.14) | 1:37 | 1:32 / 1:42 | 1:34 / 1:34 |
| Smoke / Optional Extras | 0:47 | 0:47 / 0:47 | 0:45 / 0:43 |
| MCP / Integration | 0:48 | 0:48 / 1:01 | 0:44 / 0:44 |
| Marimo Playwright | 1:30 | 1:28 / 1:37 | 1:22 / 1:24 |
| WASM Marimo Playwright | 1:40 | 1:05 / 1:10 | 1:16 / 1:12 |
| Server Playwright | 2:05 | 1:35 / 1:38 | 1:34 / 1:37 |
| Storybook Playwright | 1:53 | 1:49 / 1:45 | 2:08 / 2:14 |
| JupyterLab Playwright | 2:03 | 2:08 / 2:01 | 2:34 / 2:18 |
| Windows | 8:02 | 8:20 / 7:14 | 7:54 / 7:24 |

### Observations

- **No consistent speedup.** Variance between runs of the same tier is larger than differences between tiers.
- **Some jobs slower on bigger runners.** Storybook Playwright: 1:53 (2-CPU) → 2:08/2:14 (8-CPU). JupyterLab Playwright: 2:03 → 2:34/2:18.
- **Windows unaffected.** 8:02 → 7:14–8:20 range across all tiers.

### Cost

| Tier | Linux $/min | Windows $/min | Cost/run | vs 2-CPU |
|------|-------------|---------------|----------|----------|
| 2-CPU | $0.004 | $0.008 | **$0.18** | 1x |
| 4-CPU | $0.008 | $0.016 | **$0.28** | 1.6x |
| 8-CPU | $0.016 | $0.032 | **$0.49** | 2.7x |

**Verdict: Stay on 2-CPU.** Paying 1.6–2.7x more for no improvement.

---

## Where Time Goes Inside Jobs

Step-level analysis from a baseline 2-CPU run.

### Typical Linux Job (Python / Test 3.13 — 1m39s total)

```
Set up job           2s
Checkout             5s
Install uv           3s
Setup js files       1s
Install the project  1s
Run tests           62s  ← actual work
Codecov              4s
Post steps           1s
```

12s overhead, 62s useful work (84% efficient).

### BuildWheel (0:59 total)

```
Set up job           2s
Checkout             6s
Install uv           5s
Setup pnpm + Node    3s
Install pnpm deps    2s
Install project      2s
Build JS + wheel    16s  ← actual work
Upload artifacts     1s
```

20s overhead, 16s useful work. The build itself is fast.

### Windows (8:02 total)

```
Set up job            2s
Checkout             43s  ← 9x slower than Linux
Install uv         3m29s  ← 70x slower than Linux
Setup js files        1s
Install project      27s  ← 27x slower than Linux
Run tests          1m52s  ← actual work
Post steps            3s
```

**4m41s of overhead for 1m52s of tests (28% efficient).** The `Install uv` step alone is 3.5 minutes. Already has `continue-on-error: true`.

### Playwright Jobs (JupyterLab — 2:03 total, longest wave 2 job)

```
Set up job           2s
Checkout             5s
Install uv           3s
Setup pnpm + Node    7s
Install pnpm deps    2s
Download artifacts   0s
Install project      2s
Cache Playwright     2s
Run tests           77s  ← actual work
Post steps           1s
```

23s overhead, 77s useful work. These tests validate the built wheel — they must depend on BuildWheel.

---

## Critical Path Analysis

```
0:00   Wave 1 starts
0:59   BuildWheel completes (16s actual build + 43s overhead)
1:24   Wave 2 starts running (~25s Depot provisioning gap)
3:27   JupyterLab Playwright completes (longest wave 2 job)
```

**Blocking critical path: ~3:27.** Window job (8:02) runs in parallel but is non-blocking (`continue-on-error: true`).

---

## Path-Gated Optimizations (PR-only, merge queue runs full CI)

The key insight: **`merge_group` always runs the full pipeline** (current behavior, no changes). The optimizations below only apply to the `pull_request` event, where fast iteration matters more than exhaustive coverage.

### Approach: Two-tier CI

```
pull_request:   Run reduced CI based on what changed
merge_group:    Run full CI (current behavior, unchanged)
push to main:   Run full CI (current behavior, unchanged)
```

This is safe because nothing merges without passing the merge queue.

### How Often Do PRs Touch JS vs Python vs file_cache?

Analysis of the last 20 merged PRs:

| Area | PRs touching it | % of PRs |
|------|----------------|----------|
| `packages/` (JS) | 9 of 20 | 45% |
| `buckaroo/file_cache/` | 0 of 20 | 0% |
| Python only (no JS) | 11 of 20 | 55% |

### Optimization 1: Skip JS-only jobs when `packages/` unchanged

Buckaroo is an integrated system — Python drives JS rendering, so **Playwright integration tests must always run** regardless of what changed. A Python-only change to styling, stats, or column config can break what renders in the browser.

However, when `packages/` hasn't changed, the **JS unit tests** are redundant — they'd be testing the same JS code that already passed on `main`.

When a PR only touches Python code:
- Skip `TestJS` (0:53) — JS unit tests, no Python involvement
- `BuildWheel` uses cached JS build artifacts from `main` instead of rebuilding the JS (still builds the Python wheel around them)

**What still runs on Python-only PRs (everything else):**
- LintPython, CheckDocs, BuildWheel (with cached JS), all Python test matrix entries
- All Playwright integration tests (Storybook, Server, JupyterLab, Marimo, WASM Marimo)
- SmokeTestExtras, TestMCPWheel, StylingScreenshots

**Impact for the 55% of PRs that are Python-only:**
- Saves 1 job (~$0.004) and a small amount of BuildWheel time
- The main win is `BuildWheel` completing faster (skip the 16s esbuild), which means wave 2 Playwright jobs start ~16s sooner
- Critical path drops from ~3:27 to ~3:11

This is a modest win. The real value is correctness: by caching known-good JS artifacts, Python-only PRs are tested against the exact JS that's on `main`, not a redundant rebuild of the same source.

### Optimization 2: Skip file_cache tests when `buckaroo/file_cache/` unchanged

The `tests/unit/file_cache/` suite is **74% of total Python test time**:

| Test group | Tests | Time | % of total |
|---|---|---|---|
| `tests/unit/file_cache/` | 51 | **42.8s** | **74%** |
| Everything else | 570 | **14.9s** | **26%** |

This is because `mp_timeout` tests spawn real subprocesses with real timeouts (0.8–1.0s each, some at 3×). Each test that exercises a timeout path waits for the actual timeout to expire.

In the last 20 merged PRs, **zero** touched `buckaroo/file_cache/`. When it does get touched, it's critical to test thoroughly. But running 43s of subprocess timeout tests on every Python-only PR that changes a formatter or stat function is waste.

**Mechanism:** Use `dorny/paths-filter` to detect changes to `buckaroo/file_cache/**` or `tests/unit/file_cache/**`. If unchanged:
- Add `-m "not file_cache"` to the pytest invocation (requires adding a `file_cache` marker to the tests)
- Or simpler: `--ignore=tests/unit/file_cache`

**Impact:**
- Python test jobs drop from ~62s to ~15s actual test time
- Total job time drops from ~1:40 to ~0:30 per matrix entry
- 8 matrix entries × ~70s saved = ~9.3 minutes of job-time saved
- At $0.004/min = ~$0.04 saved per run
- **Critical path drops by ~47s** (Python tests are no longer on the critical path at all — BuildWheel→Playwright becomes the bottleneck again, but only when JS changes)

### Combined Impact

For the **55% of PRs that are Python-only and don't touch file_cache** (the common case):

| | Current | Optimized | Saved |
|--|---------|-----------|-------|
| Jobs run | 22 | 21 | 1 fewer |
| Python test time | ~62s | ~15s | **~47s** |
| Critical path | ~3:27 | ~2:40 | **~47s** |
| Cost/run | ~$0.18 | ~$0.14 | ~$0.04 |

The critical path improvement comes from file_cache skipping — Python tests drop from ~1:40 to ~0:30 per job, so they're no longer close to the Playwright critical path. The JS artifact caching shaves ~16s off BuildWheel, letting wave 2 start slightly sooner.

For the **45% of PRs that touch JS but not file_cache**:

| | Current | With file_cache skip | Saved |
|--|---------|---------------------|-------|
| Jobs run | 22 | 22 | 0 |
| Critical path | ~3:27 | ~2:40 | **~47s** |
| Cost/run | ~$0.18 | ~$0.14 | ~$0.04 |

The merge queue always runs the full 22-job pipeline regardless.

---

## Other Optimization Opportunities

### Move Windows to nightly schedule

| | Current | Proposed |
|--|---------|----------|
| Trigger | Every PR | `schedule` cron + push to main |
| Savings | — | $0.06/run |
| Risk | None | Late detection of Windows-specific bugs |

Already `continue-on-error: true` so it cannot block merges. Running it on every PR burns $0.06 and 8 minutes of wall-clock noise for a job that by definition can't fail the build.

### Reduce Python matrix from 8 → 3 jobs

Currently 4 Python versions × 2 dep strategies = 8 jobs. Proposed:
- Normal deps: 3.11 + 3.14 (oldest + newest)
- Max versions: 3.14 only

Middle versions (3.12, 3.13) rarely catch issues that 3.11 + 3.14 don't. Saves ~$0.03/run and 5 fewer runners to provision. (Could also be PR-only, with merge queue running the full matrix.)

### Path-filter Styling Screenshots

Only run when PRs touch styling-related files (`styling*.py`, `Styler.tsx`, etc.). Most PRs don't touch styling code. When it does run it takes 2:10 (two Storybook cold starts).

### Merge small jobs to reduce provisioning overhead

Each job pays ~20s Depot provisioning + ~15s setup. Candidates:
- **MCP + Smoke** → one job (both need just uv + wheel, 48s + 47s actual)
- **Marimo + WASM Marimo** → one job (identical 23s setup each)

No wall-clock improvement (they run in parallel), but reduces total job-minutes and Depot costs.

### Drop codecov from 3 of 4 Python test entries

Only one coverage report needed. Saves ~12s total.

### What won't help

- **Faster runners** — proven by 4-run experiment. I/O-bound workload.
- **Removing BuildWheel dependency from Playwright** — those tests validate the built wheel works as shipped. That's the point.

---

## Depot Pricing Reference

| Plan | Price | Included | Overage |
|------|-------|----------|---------|
| Developer | $20/mo | 2,000 min | — |
| Startup | $200/mo | 20,000 min | $0.004/min |
| Business | Custom | Custom | Custom |

Runner rates (per minute, billed per second, no minimum):

| Size | Linux | Windows |
|------|-------|---------|
| 2 CPU / 8 GB | $0.004 | $0.008 |
| 4 CPU / 16 GB | $0.008 | $0.016 |
| 8 CPU / 32 GB | $0.016 | $0.032 |
| 16 CPU / 64 GB | $0.032 | $0.064 |

### Monthly cost at current usage (2-CPU)

| Runs/month | Total minutes | Cost |
|------------|--------------|------|
| 50 | ~1,900 | ~$9 |
| 100 | ~3,800 | ~$18 |
| 200 | ~7,600 | ~$36 |

Fits comfortably on Developer plan at moderate usage.
