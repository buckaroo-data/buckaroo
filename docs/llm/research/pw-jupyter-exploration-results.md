# pw-jupyter Exploration Results

**Started:** 2026-03-03
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Baseline:** P=4, 96s, 100% pass rate (commit 4a7fefc)

---

## Experiment 1: Settle Time — COMPLETE

**Conclusion: Settle time is unnecessary. SETTLE_TIME=0 works.**
WebSocket warmup reaches `idle` on all kernels before settle starts.
The 15s default settle adds pure waste. **Saves 15s/run.**

### Results

| Run | Settle | Result | Test Phase | Container State |
|-----|--------|--------|-----------|-----------------|
| S1 | 40s | PASS | 90s | Fresh |
| S2 | 20s | PASS | 91s | Back-to-back (2nd) |
| S3 | 10s | FAIL (timeout) | — | Back-to-back (3rd) — degradation bug, not settle |
| S3b | 10s | PASS | 91s | Fresh — confirms 10s works |
| S4 | 0s | PASS | 92s | Fresh |

### Per-Process Data (S1, settle=40s)
- At settle start (t+0s): Jupyter servers at 14-22% CPU — `ps` cumulative average high from startup burst
- By t+15s: Down to 6-12% (cumulative average declining)
- By t+25s: Down to 4-8% (servers genuinely idle)
- Chromium/kernels: not present during settle (no tests running)
- Memory: 2.1GB of 32GB used, 0 swap — not memory-constrained

### Side Finding: Back-to-Back Degradation Confirmed
S3 (10s, 3rd consecutive run) timed out — batch 1 passed (4/4), batch 2 hung on polars_dfviewer and polars_dfviewer_infinite. Retry with fresh container passed immediately. This confirms the Exp 4 issue is real and surfaces on 3rd run.

---

## Experiment 2: P=4/5 Profiling — IN PROGRESS

Using SETTLE_TIME=0 from Exp 1.

### Run P1 — Instrumented P=4 baseline — COMPLETE

**PASS** — P=4, settle=0, test phase 94s. Fresh container with 1s monitoring interval.

#### Batch Timing
- **Batch 1** (23:24:51→23:25:22): **31s** — test_buckaroo_widget, test_buckaroo_infinite_widget, test_polars_widget, test_polars_infinite_widget
- **Batch 2** (23:25:22→23:25:51): **29s** — test_dfviewer, test_dfviewer_infinite, test_polars_dfviewer, test_polars_dfviewer_infinite
- **Batch 3** (23:25:51→23:26:22): **31s** — test_infinite_scroll_transcript (alone)
- Between-batch gap: ~0s (re-warmup is fast)

#### Per-Process CPU Breakdown

**Batch 1 peak (23:25:01):**

| Process Type | Per-Process CPU | Total CPU | RSS per process |
|-------------|----------------|-----------|----------------|
| Jupyter servers (4) | 10-16% | ~48% | 117-132 MB |
| Chromium renderers (top 4) | 35-147% | ~305% | 209-238 MB |
| Node/Playwright (5) | 11-20% | ~73% | ~130 MB |
| **Total** | | **~426%** | |

**Batch 2 peak (23:25:31):**

| Process Type | Per-Process CPU | Total CPU | RSS per process |
|-------------|----------------|-----------|----------------|
| Jupyter servers (4) | 6-10% | ~28% | 127-138 MB |
| Chromium renderers (top 4) | 37-128% | ~303% | 171-233 MB |
| Node/Playwright (5) | 11-25% | ~74% | ~130 MB |
| **Total** | | **~405%** | |

**Batch 3 (23:26:00) — 1 notebook:**

| Process Type | Per-Process CPU | Total CPU | RSS per process |
|-------------|----------------|-----------|----------------|
| Jupyter servers (4) | 4-7% | ~20% | 136-145 MB |
| Chromium (1 renderer) | 36% | ~36% | 233 MB |
| Node/Playwright (2) | 12-14% | ~27% | ~130 MB |
| **Total** | | **~83%** | |

#### Key Findings
1. **Chromium is the biggest CPU consumer** — 300%+ total during batches 1-2. Each renderer uses 30-147% CPU (multi-core JIT + render pipeline).
2. **Jupyter servers are lightweight** — only 6-16% each, totaling 28-48%.
3. **Python kernel processes not captured** — monitor grep pattern `[i]python.*kernel` didn't match. Fixed for P2 run.
4. **Load average: 1.0-1.5** on 16 vCPU — only **~8% utilized!** Massive CPU headroom.
5. **Memory: 2.3GB/32GB used**, 0 swap — not memory-constrained.
6. **Test phase time is consistent**: 90-94s across all settle values.

#### Implication for P=5
CPU is NOT the bottleneck at P=4. Total load ~400%/1600% = 25%. P=5 should be feasible from a resource perspective. If P=5 fails, the cause is likely timing/contention, not resource exhaustion.

### Run P2 — P=5 first attempt — COMPLETE

**FAIL** — P=5, settle=0, fresh container. rc=124 (timeout at 120s). All 5 servers started and warmed. No test completed.

#### Timeline
- 23:28:33: Test phase starts (5 notebooks, ports 8889-8893)
- 23:28:35-43: All 5 START messages logged (2s stagger between each)
- 23:28:43: Chromium burst — top renderer at 280% CPU, kernels at 22-95%
- 23:28:50: Burst subsides — chromium 42-61%, kernels 5-25%, servers 8-12%
- 23:29:31: **System nearly idle** — all at <5% CPU, load avg 0.45. NO tests have completed.
- 23:30:33: Timeout kills everything. Zero completions.

#### Per-Process Data at Idle-While-Stuck (23:29:31, ~58s into test)

| Process Type | Per-Process CPU | Total CPU | RSS per process | Count |
|-------------|----------------|-----------|----------------|-------|
| Jupyter servers (5) | 4-6% | ~22% | 126-136 MB | 5 |
| Kernels (test) | 4-5% | ~24% | 191-215 MB | 5 |
| Kernels (warmup leftovers) | ~1% | ~4% | 72 MB | 4 |
| Chromium (top 2) | 12-13% | ~25% | 236-245 MB | 2 |
| **Load average** | | **0.45** | | |

#### Critical Finding: P=5 is NOT a Resource Problem

The system goes **idle** (load 0.45 on 16 vCPU) while all 5 tests are stuck. At P=4, batch 1 completes in ~31s. At P=5, 58s later nothing has completed despite <5% CPU on all processes.

This is a **deadlock or waiting-state issue**, not resource contention:
- Total CPU: ~75% of 1600% available = 4.7% utilized
- Memory: well within limits (0 swap)
- All processes alive but doing nothing useful

#### Warmup Kernel Leak
9 kernel processes visible (expected 5 test kernels). 4 warmup kernels still alive at 72MB/~1% CPU — the warmup cleanup didn't fully remove them. These are mostly harmless (low resource) but indicate the warmup kernel DELETE step may have a race condition.

#### Hypothesis for P3
The failure pattern (everything starts, initial burst, then idle stuck) suggests:
1. **Playwright tests waiting for DOM state that never arrives** — possibly the kernel executed but widget didn't render
2. **Between-notebook interference** — 5 concurrent WebSocket connections on different ports may be hitting a browser limit or Playwright worker contention
3. **Harness bug at P=5** — the `test_playwright_jupyter_parallel.sh` batch logic may have an edge case at exactly 5 notebooks/5 servers

### Run P3 — P=5 with `--disable-dev-shm-usage` — COMPLETE

**PASS** — P=5, settle=0, fresh container. Test phase **71s** (vs 94s at P=4).

#### Root Cause Found: `/dev/shm` Exhaustion

Docker defaults `/dev/shm` to 64MB. Chromium uses `/dev/shm` for renderer IPC. At P=5, 5 concurrent Chromium instances exhaust 64MB and silently block on shared memory allocation — not crash, not error, just hang.

**Fix:** Added `--disable-dev-shm-usage` to Chromium launch args in `playwright.config.integration.ts`. This moves IPC to `/tmp` (still tmpfs on Linux, no performance impact). Commit e6ea620.

#### Timing Improvement
- P=4: 94s test phase (batches: 4+4+1)
- P=5: **71s** test phase (batches: 5+4) — **24% faster**, eliminated one batch

#### Jupyter Ecosystem Versions (from uv.lock, verified)
| Package | Version |
|---------|---------|
| jupyterlab | 4.5.0 |
| jupyter_server | 2.15.0 |
| jupyter_client | 8.6.3 |
| ipykernel | 6.29.5 |
| anywidget | 0.9.21 |

> **Note:** An earlier version of this table had incorrect versions (7.2.0, 4.5.5, etc.)
> that were not verified against the lockfile. Corrected 2026-03-04 after confirming
> `uv.lock` has always pinned these exact versions across all builds.

### Run P4 — P=6 first attempt — COMPLETE

**PASS** — P=6, settle=0, fresh container. Test phase **72s** (batches: 6+3).

#### Scaling Summary

| P | Test Phase | Batches | Savings vs P=4 |
|---|-----------|---------|---------------|
| 4 | 94s | 4+4+1 | baseline |
| 5 | 71s | 5+4 | **-23s (24%)** |
| 6 | 72s | 6+3 | **-22s (23%)** |

P=5 and P=6 are nearly identical — the bottleneck is now per-notebook execution time (~25-30s), not batch count. The batch transition overhead is minimal (~1-2s for kernel cleanup + re-warmup).

### Run P=9 — COMPLETE

**PASS** — P=9, settle=0, fresh container. Test phase **49s** (single batch, all 9 notebooks).

| P | Test Phase | Batches | Savings vs P=4 |
|---|-----------|---------|---------------|
| 4 | 94s | 4+4+1 | baseline |
| 5 | 71s | 5+4 | -23s (24%) |
| 6 | 72s | 6+3 | -22s (23%) |
| **9** | **49s** | **9** (single batch) | **-45s (48%)** |

P=9 was previously "conclusively dead" — it was `/dev/shm` all along.

### Experiment 2 Conclusion

**Root cause of all prior P=5/6/9 failures: Docker's 64MB `/dev/shm` default.**
One-line fix (`--disable-dev-shm-usage` in `playwright.config.integration.ts`) unlocks P=9 with zero reliability issues. Test phase cut from 94s to 49s.
This also explains the P=6 regression noted in MEMORY.md ("P=6 worked on old image but regressed on tini image") — the tini image rebuild may have changed `/dev/shm` allocation patterns.

---

## Experiment 2B: Test Reordering — SKIPPED

Not needed. P=9 runs all 9 notebooks in a single batch — reordering is irrelevant.

---

## Experiment 3: Chromium Pre-Warming — COMPLETE (SKIPPED at C1 gate)

**C1 Result:** First Chromium process appears ~2s after test START (23:24:51→23:24:53 in P1 data). Below the 3s gate threshold.

**Conclusion:** Chromium startup overhead is ~2s — not worth the complexity of browser pre-launching. With P=9 single-batch, there's no between-batch restart cost anyway.

---

## Experiment 4: Back-to-Back Degradation — COMPLETE

**Conclusion: Back-to-back degradation is gone.** 5/5 consecutive P=9 runs passed with no restart.

The prior degradation (3rd run failing at P=4) was caused by `/dev/shm` exhaustion accumulating across runs. The `--disable-dev-shm-usage` fix resolved both the P=5+ hang AND the back-to-back issue.

### B1: 5 Consecutive P=9 Runs (no container restart)

| Run | Test Phase | /tmp files | Memory (MB) | Zombies | Stale procs |
|-----|-----------|-----------|-------------|---------|-------------|
| 1 | 49s PASS | 131 | 1317 | 0 | 0 |
| 2 | 49s PASS | 140 | 1304 | 0 | 0 |
| 3 | 48s PASS | 149 | 1301 | 0 | 0 |
| 4 | ~49s PASS | ~160 | ~1298 | 0 | 0 |
| 5 | ~49s PASS | 172 | 1295 | 0 | 0 |

- /tmp grows ~9 files per run (minor Playwright artifacts) — not dangerous
- Memory flat/slightly decreasing (cache freed)
- 0 zombies, 0 stale processes, 0 TIME_WAIT sockets
- No container restart needed between runs

---

## Experiment 5: Concurrent Job Contention — COMPLETE

**Date:** 2026-03-04
**Server:** Vultr 32 vCPU / 64GB (45.76.18.207)
**Baseline:** All jobs launched concurrently with 2s stagger (commit 6a3f4ba)

### Problem

pw-jupyter consistently failed (8/9 notebooks hung) when running concurrently with:
- smoke-test-extras (6 parallel `uv pip install` + smoke tests)
- pw-marimo, pw-wasm-marimo, pw-server (3 Chromium instances)
- test-python-3.{11,12,14} (3 pytest runs with `-n 4` = 12 processes)

Failure was **100% reproducible** across 4 runs, including fresh container restarts and
even the known-good commit c26897f. First 1-2 notebooks passed (started before heavy
jobs ramped up), remaining 7-8 hung with "Shift+Enter attempt N" retries.

Phase 5b (pw-jupyter running alone) passed consistently — confirming contention as root cause.

### Fix: Defer heavy jobs until pw-jupyter completes (commit 45824a0)

Only test-mcp-wheel (lightweight, single process) runs alongside pw-jupyter.
All other heavy jobs start after pw-jupyter finishes.

### Results

| Run | Commit | pw-jupyter | Total CI | Result |
|-----|--------|-----------|----------|--------|
| 1 (concurrent) | 6a3f4ba | HUNG (120s timeout) | 2m28s | FAIL |
| 2 (concurrent) | 6a3f4ba | HUNG (120s timeout) | 2m25s | FAIL |
| 3 (concurrent) | c26897f | HUNG (120s timeout) | 2m25s | FAIL |
| 4 (concurrent, 2GB shm) | 28ae719 | HUNG (120s timeout) | 2m31s | FAIL |
| 5 (phase 5b, alone) | 28ae719 | 107s | 1m47s | PASS |
| 6 (deferred) | 45824a0 | 52s | 2m07s | PASS |
| 7 (deferred, b2b) | 45824a0 | 51s | 2m09s | PASS |

### Key Findings

1. **2GB /dev/shm didn't help** — the hang is CPU/kernel contention, not shared memory
2. **Deferred approach adds ~20s** to total CI (was ~1m45s concurrent, now ~2m09s) because
   heavy jobs can't overlap with pw-jupyter
3. **pw-jupyter is the bottleneck at 51-52s** — everything else fits in the remaining ~75s
4. **Contamination hypothesis disproven** — the issue was always concurrent contention, not
   stale state from failed runs

---

## Experiment 6: Stagger Reduction (1.5s) — COMPLETE

**Server:** Vultr 32 vCPU / 64GB (45.76.18.207)
**Branch:** docs/ci-research

### Results

| Run | Stagger | Result | pw-jupyter | Total CI | Notes |
|-----|---------|--------|-----------|----------|-------|
| 1 | 1.5s | PASS | 47s | ~2m01s | Fresh after b2b |
| 2 (b2b) | 1.5s | FAIL | 120s timeout | — | 4/9 notebooks hung |
| 3 | 2s (reverted) | PASS | 51s | 2m09s | Back to reliable |

### Conclusion

1.5s stagger passes on first run but fails on immediate back-to-back. The extra 0.5s headroom in 2s stagger is necessary for reliable b2b runs. **Reverted to 2s** (commit 5cbd74f).

---

## Experiment 7: Parallelize Marimo Tests — COMPLETE (reverted)

**Goal:** Reduce pw-marimo from 53s by using workers:2.

### Results

| Run | Workers | Result | Notes |
|-----|---------|--------|-------|
| 1 | 2 (unconditional) | FAIL | CI=true not set → evaluated as workers:1 anyway |
| 2 | 2 (+ CI=true env) | FAIL | ERR_CONNECTION_REFUSED — 2 Playwright workers crash single marimo server |
| 3 | 1 (reverted) | PASS | 53s, back to baseline |

### Conclusion

Marimo workers:2 causes ERR_CONNECTION_REFUSED — single marimo server can't handle concurrent Playwright connections. Would need 2 marimo servers on different ports. **Reverted to workers:1** (commit d77aff2). Not worth the complexity for ~20s savings.

---

## Storybook Semver Fix — COMPLETE

**Problem:** After container recreate + pnpm store volume addition, `pnpm storybook` failed with "Cannot find module 'semver'" from inside `.pnpm/@storybook+core@8.6.15/...`.

**Root cause:** Race condition in CI DAG. `playwright-storybook` was in Wave 0 alongside `build-js` (which runs `pnpm install`). Storybook tried to load from node_modules while pnpm install was restructuring it (especially after adding `shamefully-hoist=true` to `.npmrc`).

**Fix:** Moved `playwright-storybook` to start after `build-js` completes (commit 33b31ab). ~5s cost.

### CI Results (commit 33b31ab) — ALL PASS

| Job | Duration |
|-----|----------|
| lint-python | 0s |
| build-js | 5s |
| test-python-3.13 | 23s |
| jupyter-warmup | 20s |
| build-wheel | 8s |
| test-js | 5s |
| playwright-storybook | 27s |
| pw-jupyter (P=9) | 52s |
| test-mcp-wheel | 13s |
| pw-marimo | 53s |
| pw-wasm-marimo | 37s |
| pw-server | 44s |
| smoke-test-extras | 6s |
| **Total** | **2m08s** |

---

## Job Overlap Experiments — COMPLETE

**Goal:** Overlap Playwright jobs with pw-jupyter to reduce sequential wait.

### Progressive Overlap Results

| Config | pw-jupyter | Total CI | Result |
|--------|-----------|----------|--------|
| Baseline (deferred all) | 52s | 2m08s | PASS |
| + pw-marimo | 52s | 2m00s | PASS (2/2 b2b) |
| + pw-wasm + pw-server | 51s | **1m40s** | PASS (2/2 b2b) |
| + test-python (12 workers) | TIMEOUT 120s | — | **FAIL** |
| Reverted to pw-marimo+wasm+server | 51s | 1m40s | PASS |

### Commit Timeline

| Commit | Change | Result |
|--------|--------|--------|
| 49b71ca | Overlap pw-marimo with pw-jupyter | 2m00s PASS |
| 9e67c37 | + pw-wasm-marimo + pw-server | 1m40s PASS |
| 233398a | + test-python (3 × -n 4) | FAIL — pw-jupyter 120s timeout |
| 634452d | Revert test-python overlap | 1m40s PASS (expected) |

### Key Findings

1. **pw-jupyter tolerates 3 extra Chromium instances** (marimo, wasm, server) running concurrently
2. **12 pytest workers (-n 4 × 3) push it over the edge** — kernel contention causes pw-jupyter to timeout
3. **smoke-test-extras** (6 parallel uv pip install) stays deferred — heavy IO
4. **Sweet spot: pw-jupyter + pw-marimo + pw-wasm + pw-server** — 1m40s, reliable b2b
5. **Savings: 28s** (2m08s → 1m40s) from overlapping Playwright jobs

---

## Cloud-Init Hardening — COMPLETE (commit aeb76f7)

**Changes:**
- Added missing directories: `/opt/ci/runner`, `/opt/ci/js-cache`, `/opt/ci/queue`
- Deploy `ci-queue.sh` to `/usr/local/bin/ci-queue` (job queue for webhook)
- Copy CI runner scripts directly (update-runner.sh not suitable for first-run)
- Save Dockerfile hash so subsequent `update-runner.sh` calls work correctly
- Made provider-agnostic (Hetzner, Vultr, or any cloud-init provider)
- Removed obsolete `HETZNER_SERVER_ID` from .env template

---

## Final Summary

**Starting point:** 2m08s, all jobs sequential after pw-jupyter
**Final result:** 1m40s, 4 Playwright jobs overlapping with pw-jupyter

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total CI | 2m08s | 1m40s | **-22%** |
| pw-jupyter | 52s | 52s | unchanged |
| pw-marimo | 53s (sequential) | 52s (parallel) | **hidden behind pw-jupyter** |
| pw-wasm-marimo | 37s (sequential) | 36s (parallel) | **hidden** |
| pw-server | 44s (sequential) | 43s (parallel) | **hidden** |

**Critical path:** warmup (20s) → wheel install (3s) → pw-jupyter (52s) → test-python (24s) = **99s**

### Experiment Status

| # | Experiment | Status | Result |
|---|-----------|--------|--------|
| 1 | CI timeout 4min | Done | Saves iteration time |
| 2 | Contamination | Done | Deferred heavy jobs → reliable |
| 3 | Stagger 1.5s | Done | Unreliable b2b, 2s is minimum |
| 4 | Chromium pre-warming | Skipped | Startup is only ~2s |
| 5 | Single JupyterLab | Skipped | Marginal savings, ZMQ risk |
| 6 | Cloud-init hardening | Done | Fixed missing dirs, ci-queue, provider-agnostic |
| 7 | Parallelize marimo | Done | workers:2 crashes single server |
| 8 | Job overlap | Done | **1m40s** — 4 PW jobs parallel with pw-jupyter |
| 9 | VX1 Zen 5 (16 vCPU) | Done | **UNRELIABLE** — per-core faster but not enough cores |

---

## Experiment 9: VX1 Zen 5 (16 vCPU / 64 GB) — COMPLETE

**Server:** Vultr VX1 16C ($350/mo) — AMD EPYC Turin (Zen 5) @ 2.4 GHz, 16 vCPU, 64 GB
**Goal:** Test whether faster per-core performance (Zen 5 vs Zen 2) compensates for fewer cores (16 vs 32).
**Commit:** 45d10c8 (deferred overlap DAG)

### Setup
1. Destroyed old Rome box (45.76.18.207, 32 vCPU, $315/mo)
2. Created VX1 instance (45.76.229.165, id: 683527e4)
3. Manual setup: Docker CE, repo clone, Docker image build, runner scripts, docker-compose

### Results

| Run | P | Total | pw-jupyter | Restart? | Result |
|-----|---|-------|-----------|----------|--------|
| 1 (cold) | 9 | 2m34s | 47s | N/A | test-python flaky |
| 2 (warm, overlap DAG) | 9 | 1m33s | 48s | No (b2b) | **ALL PASS** |
| 3 (b2b) | 9 | 2m49s | 120s timeout | No | FAIL (6/9 pass) |
| 4 (deferred DAG) | 9 | 1m46s | 46s | Yes | **ALL PASS** |
| 5 (b2b) | 9 | 2m58s | 120s timeout | No | FAIL |
| 6 (restart) | 9 | 2m59s | 120s timeout | Yes | FAIL |
| 7 (restart) | 6 | 2m57s | 120s timeout | Yes | FAIL |
| 8 (phase=5b) | 3 | >240s | 240s timeout | Yes | FAIL |
| 9 (restart) | 9 | 2m59s | 120s timeout | Yes | FAIL (5/9) |
| 10 (restart) | 4 | 2m17s | 1m21s | Yes | **ALL PASS** |
| 11 (b2b) | 4 | 2m57s | 120s timeout | No | FAIL |
| 12 (restart) | 9 | 2m59s | 120s timeout | Yes | FAIL (5/9) |

**Pass rate:** 3/12 runs (25%) — vs 100% on Rome 32 vCPU

### Per-Job Comparison (passing runs only)

| Job | VX1 16v Zen 5 | Rome 32v Zen 2 | Change |
|---|---|---|---|
| jupyter-warmup | **21s** | 45s | **-53%** |
| pw-jupyter | 46-48s | 51s | -6% |
| pw-marimo | 34-36s | 52s | **-33%** |
| pw-wasm-marimo | 23-25s | 37s | **-35%** |
| pw-server | 36-37s | 43s | **-16%** |
| test-python-3.13 | 26-29s | 24s | +13% (contention) |

### Key Findings

1. **Zen 5 is 30-50% faster per-core** for single-threaded workloads (warmup, marimo)
2. **16 vCPU is insufficient for P=9 pw-jupyter** — 9 Chromium + 9 JupyterLab + kernel processes overwhelm 16 cores
3. **Even P=3 and P=4 are unreliable** on this box — passes only after fresh container restart
4. **b2b contamination is severe** — first run sometimes passes, b2b always fails
5. **The contamination is NOT about orphan processes** — after restart, no stale processes exist but tests still hang
6. **Core count matters more than per-core speed** for our heavily parallel Playwright workload

### Conclusion

VX1 16 vCPU is not viable for P=9 pw-jupyter. Need either:
- VX1 32C ($700/mo) — expensive but would combine Zen 5 speed with enough cores
- Stay on Rome 32 vCPU ($315/mo) — reliable, already optimized to 1m40s
- Investigate pw-jupyter to reduce parallelism needs (batch mode, shared browser)
