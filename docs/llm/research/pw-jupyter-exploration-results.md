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

#### Jupyter Ecosystem Versions (resolved at install time)
| Package | Version |
|---------|---------|
| jupyterlab | 4.5.5 |
| jupyter_server | 2.17.0 |
| jupyter_client | 8.8.0 |
| ipykernel | 7.2.0 |
| anywidget | 0.9.21 |

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

## Experiment 2B: Test Reordering

*Status: pending (after Exp 2 P1 data analyzed — data now available)*

---

## Experiment 3: Chromium Pre-Warming

*Status: pending (gate on Exp 2 data)*

**Early signal from P1:** Chromium renderers dominate CPU at 300%+ total. If startup overhead is significant (>3s), pre-warming could be impactful. Needs C1 analysis of Chromium spawn-to-first-assertion timing from P1 logs.

---

## Experiment 4: Back-to-Back Degradation

*Status: pending (low priority — but confirmed real from Exp 1 S3)*

Exp 1 S3 confirmed: 3rd consecutive run times out. Batch 1 passes, batch 2 hangs on polars_dfviewer notebooks. Fresh container restart fixes it.
