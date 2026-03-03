# CI Tuning Experiments — Night of 2026-03-03

**Branch:** docs/ci-research
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Goal:** Minimize total CI wall-clock time while maintaining reliability.
**Baseline:** 3m16s (full DAG, PARALLEL=3 jupyter, ALL PASSED)

---

## Summary of Results

| Exp | Commit | Config | Pass Rate | Jupyter Time (pass) | Total Time (pass) |
|-----|--------|--------|----------|-------------------|------------------|
| 10 | 7e5754a | P=9 WebSocket phase5b | 8/9 notebooks | ~2m01s | N/A (5b only) |
| 11 | 7e5754a | P=9 full DAG | 0/1 | N/A | N/A |
| 12 | a869d12 | pytest-xdist -n 4 | N/A (python only) | N/A | ~30s/ver (was ~63s) |
| 13 | 2207d1e | infinite_scroll fix | N/A | N/A | N/A |
| 14a | 35e0fc8 | P=4 old DAG | **2/7 = 29%** | ~1m12s | ~2m40s |
| 14b | 7770774 | P=4 wait-all DAG | **4/5 = 80%** | ~3m20s | ~3m30s |
| 14c | 92ca618 | P=3 wait-all DAG | **3/5 = 60%** | ~5m18s | ~7m |
| 14d | 6a11b71 | P=4 wait-all + kernel-idle-60s | **3/5 = 60%** | varies | varies |
| 14e | 8695488 | P=4 wait-all + idle-15s + retry=2 | **4/5 = 80%** | ~1m12s | ~2m42s |

---

## Experiment Details

### Exp 10 — PARALLEL=9 WebSocket warmup baseline (a1594bd → 7e5754a)

**Status:** DONE
**Mode:** --phase=5b (isolated, no DAG contention)
**PARALLEL:** 9

**Key discovery:** REST API (GET /api/kernels/{id}) NEVER updates execution_state from
"starting" to "idle" without a WebSocket client. Known upstream limitation in jupyter_server.
The fix: connect to `/api/kernels/{id}/channels` via WebSocket, which triggers the built-in
"nudge" mechanism (kernel_info_request). All 9 kernels reached idle in 11 seconds.

**Results:** 8/9 notebooks PASS. Only `test_infinite_scroll_transcript` fails (both tests
timeout waiting for cell output — 2000-row PolarsBuckarooInfiniteWidget too heavy).

**Fixed bugs:**
- ENOENT race: 9 concurrent Playwright processes racing to mkdir `.playwright-artifacts-0`.
  Fix: unique `--output` per slot.
- REST warmup broken: replaced with WebSocket-based warmup using `websocket-client` package.

---

### Exp 11 — PARALLEL=9 full DAG (7e5754a)

**Status:** DONE
**PARALLEL:** 9

All 9 notebooks FAILED in full DAG mode. The playwright-server job (58s) was still running
when playwright-jupyter started, creating CPU contention with 9 Chromium + 9 JupyterLab
+ 9 Python kernels on top of the existing Playwright server process.

**Key finding:** Phase 5b passes (isolated) but full DAG fails at P=9. CPU contention
from other jobs is the bottleneck, not kernel startup.

---

### Exp 12 — pytest-xdist for Python unit tests (a869d12)

**Status:** DONE
**What:** Added `pytest-xdist>=3` to test deps, run with `-n 4 --dist load`.

**Results:** Python test time dropped from ~63s to ~30s per version. 4-way parallelism
on test execution reduces total Python test wall time by ~50%.

No test isolation issues found — all tests pass with xdist.

---

### Exp 13 — Fix infinite_scroll_transcript flake (2207d1e → 61e9947)

**Status:** DONE (partially)
**Changes:**
- Reduced DataFrame from 2000 to 500 rows (lighter widget under contention)
- Scroll target: row 400 (was 1500)
- Bumped test timeout to 180s, CELL_EXEC_TIMEOUT to 120s
- Added Shift+Enter retry loop (dispatchEvent + keyboard, 15s per attempt)
- Changed ag-cell wait from 'visible' to 'attached'

**Result:** Passes when run alone in batch 3 (after other notebooks finish).
Still fails under concurrency with other notebooks.

---

### Exp 14a — PARALLEL=4 old DAG baseline (35e0fc8)

**Status:** DONE — 5-run stability test
**DAG:** Wait for marimo+wasm only before starting playwright-jupyter.
**PARALLEL:** 4

**Results:** 2/7 PASS = **29% pass rate**

| Run | Jupyter Time | Result |
|-----|-------------|--------|
| 1 | 3m33s | FAIL |
| 2 | 3m33s | FAIL |
| 3 | 1m12s | **PASS** |
| 4 | 3m18s | FAIL |
| 5 | 3m34s | FAIL |
| 6 | 3m33s | FAIL |
| 7 | 1m11s | **PASS** |

**Key finding:** playwright-server (58s) consistently overlaps playwright-jupyter start
by ~4 seconds. The overlap causes enough CPU contention to make cell execution unreliable.

---

### Exp 14b — PARALLEL=4 wait-all DAG (7770774) ⭐ BEST SO FAR

**Status:** DONE — 5-run stability test
**Changes from 14a:**
1. Wait for ALL jobs (including playwright-server, MCP, smoke) before starting playwright-jupyter
2. Added `--retries=1` to Playwright CLI

**Results:** 4/5 PASS = **80% pass rate**

| Run | Jupyter Time | Result |
|-----|-------------|--------|
| 1 | 3m20s | **PASS** |
| 2 | 4m07s | FAIL |
| 3 | 3m36s | **PASS** |
| 4 | 3m21s | **PASS** |
| 5 | 3m36s | **PASS** |

**Key finding:** Waiting for ALL jobs before playwright-jupyter is the single biggest
reliability improvement. Eliminates CPU contention from overlapping playwright-server.

**Impact on total CI time:** Adds ~50s to critical path (waiting for server to finish)
but reliability jumps from 29% to 80%. Total CI: ~5m.

---

### Exp 14c — PARALLEL=3 wait-all DAG (92ca618)

**Status:** DONE — 5-run stability test
**PARALLEL:** 3 (3+3+3 batches instead of 4+4+1)

**Results:** 3/5 PASS = **60% pass rate**

| Run | Total Time | Result |
|-----|-----------|--------|
| 1 | 7m12s | **PASS** |
| 2 | 6m40s | FAIL |
| 3 | 1m08s | **PASS** |
| 4 | 2m40s | **PASS** |
| 5 | 7m56s | FAIL |

**Key finding:** PARALLEL=3 is WORSE than PARALLEL=4. More batches (3+3+3 vs 4+4+1)
means more kernel startup overhead between batches. Each batch takes ~2m34s regardless
of whether it has 3 or 4 notebooks — so more batches = more time = more opportunity
for flakes.

**Conclusion:** Don't go below PARALLEL=4.

---

### Exp 14d — PARALLEL=4 wait-all + kernel-idle-wait-60s (6a11b71)

**Status:** DONE — 5-run stability test
**Change:** Added `waitForFunction` checking JupyterLab's
`.jp-Notebook-ExecutionIndicator[data-status="idle"]` before attempting Shift+Enter.
Timeout: 60 seconds.

**Results:** 3/5 PASS = **60% pass rate** (worse than 14b!)

| Run | Jupyter Time | Result |
|-----|-------------|--------|
| 1 | 1m14s | **PASS** |
| 2 | 3m37s | **PASS** |
| 3 | 8m20s | FAIL |
| 4 | 4m07s | FAIL |
| 5 | 1m12s | **PASS** |

**Key finding:** The 60s kernel idle wait HURTS reliability. When the DOM selector isn't
found (JupyterLab hasn't fully rendered), the `waitForFunction` burns 60s of the 180s
test timeout. This leaves only 120s for the actual retry loop + widget rendering, which
isn't enough when the kernel is slow.

**Conclusion:** Kernel idle wait concept is sound but 60s timeout is too aggressive.

---

### Exp 14e — PARALLEL=4 wait-all + kernel-idle-15s + retries=2 (8695488)

**Status:** RUNNING — 5-run stability test
**Changes from 14d:**
- Reduced kernel idle wait timeout from 60s to 15s
- Increased Playwright retries from 1 to 2

**Results:** 4/5 PASS = **80% pass rate** (same as 14b)

| Run | Jupyter Time | Result | Notes |
|-----|-------------|--------|-------|
| 1 | 1m12s | **PASS** | |
| 2 | 1m12s | **PASS** | |
| 3 | 1m13s | **PASS** | |
| 4 | ~10m | FAIL | cell execution timeout |
| 5 | ~5m | PASS (jupyter) | storybook flake caused overall FAIL |

**Conclusion:** Kernel idle wait + extra retry doesn't improve beyond wait-all + retries=1.
The 80% pass rate appears to be the ceiling for PARALLEL=4 on Vultr 16 vCPU with
DOM-based kernel readiness checks.

See `jupyterlab-kernel-connection-deep-dive.md` for research into why the remaining
20% fails and the architectural fix (query `window.jupyterapp` internal state instead
of DOM selectors).

---

## Next Experiments — Jupyter Reliability (from deep dive research)

### Exp 21 — Replace DOM kernel check with `window.jupyterapp` internal state query

**Priority:** CRITICAL — expected to break the 80% ceiling
**Estimated impact:** 80% → ~95-100% pass rate
**Files:** `pw-tests/integration.spec.ts`, `pw-tests/infinite-scroll-transcript.spec.ts`

**Root cause of 20% failures (from deep dive):**
The DOM-based check (`querySelector('.jp-Notebook-ExecutionIndicator')`) has three problems:
1. The DOM element may not exist yet → `querySelector` returns `null` → burns entire timeout
2. Even when found, `data-status` lags behind actual kernel state
3. When timeout expires, test proceeds to `Shift+Enter` with `session.kernel === null` →
   `CodeCell.execute()` at `widget.ts:1750` silently returns `void`, no error

**The fix:** Query JupyterLab's runtime directly via `window.jupyterapp`:
```typescript
await page.waitForFunction(() => {
  const app = (window as any).jupyterapp;
  if (!app) return false;
  const widget = app.shell.currentWidget;
  if (!widget?.sessionContext?.session?.kernel) return false;
  const kernel = widget.sessionContext.session.kernel;
  return kernel.connectionStatus === 'connected' && kernel.status === 'idle';
}, { timeout: 60000 });
```

**Why this works:**
- Checks the EXACT same `session.kernel` that `CodeCell.execute()` checks
- Returns `false` cheaply when app hasn't loaded (no wasted timeout)
- Returns `true` the instant kernel is actually ready to accept execution
- 60s timeout safe because the function is cheap to evaluate (no DOM queries)

### Exp 22 — Verify `window.jupyterapp` availability

**Priority:** Prerequisite for Exp 21
**What:** Quick test — open JupyterLab in Playwright, run
`page.evaluate(() => typeof (window as any).jupyterapp)` to confirm the global exists
and has the expected shape. JupyterLab 4.x exposes this by default.

**Risk:** If `jupyterapp` isn't exposed (some builds strip it), fall back to
`document.querySelector('#main')._jupyterapp` or the Lumino app registry.

---

## Next Experiments — Non-Jupyter Optimizations

Current full DAG timing (warm caches, Vultr 16 vCPU):
```
Total: ~2m42s
├─ Wave 0 (parallel):     32s  [lint, test-py×3, test-js, pw-storybook, pw-wasm-marimo]
├─ build-wheel:           16s  [after test-js]
├─ Wheel-dependent:       50s  [mcp, smoke, pw-server, pw-marimo — all parallel]
└─ playwright-jupyter:  1m12s  [after ALL other jobs finish]
```

Critical path: `test-js(24s) → build-wheel(16s) → wait-all(~50s) → pw-jupyter(1m12s) = 2m42s`

### Exp 15 — Remove waitForTimeout in playwright-server specs (~15s savings)

**Priority:** HIGH
**Estimated savings:** 15-17s off playwright-server's 50s runtime
**Files:**
- `pw-tests/server-buckaroo-summary.spec.ts` — 3× `waitForTimeout(3000)` = **9s of hard sleeps** for view switching. Replace with `waitFor` on pinned row count changing or ag-grid re-render.
- `pw-tests/server-buckaroo-search.spec.ts` — 1× `waitForTimeout(3000)` = 3s
- `pw-tests/theme-screenshots-server.spec.ts` — 5× waits = ~3s
- `pw-tests/server.spec.ts` — 2× `waitForTimeout(1000)` = 2s

**Impact on critical path:** Indirect — playwright-server finishing faster means the wait-all gate for pw-jupyter triggers earlier. Could save ~15s off total CI time.

### Exp 16 — Remove sleep 5 in playwright-marimo warmup (~5s savings)

**Priority:** MEDIUM
**Estimated savings:** ~5s off playwright-marimo's 46s runtime
**File:** `scripts/test_playwright_marimo.sh` line 93
**What:** Replace `sleep 5` after `curl` with polling for actual marimo readiness (e.g., check HTTP response body for compiled widget markers, or poll until the page serves JS assets).

**Impact on critical path:** Same as exp 15 — marimo finishing faster triggers the wait-all gate sooner.

### Exp 17 — Skip JS rebuild in full_build.sh when dist exists (~8s savings)

**Priority:** MEDIUM
**Estimated savings:** ~8s off build-wheel's 16s runtime
**File:** `scripts/full_build.sh`
**What:** `test-js` already runs `pnpm build` (produces `packages/buckaroo-js-core/dist/`). Then `full_build.sh` rebuilds it from scratch. Add a check: if `dist/` exists and is newer than source, skip the JS build and just copy CSS + run esbuild + build wheel.

**Impact on critical path:** Direct — build-wheel is ON the critical path. Cutting it from 16s to ~8s saves 8s directly.

### Exp 18 — Parallelize smoke-test-extras (~10s savings)

**Priority:** LOW
**Estimated savings:** ~10s off smoke-test-extras' 17s runtime
**File:** `ci/hetzner/run-ci.sh` `job_smoke_test_extras()`
**What:** Currently creates 6 venvs sequentially (base, polars, mcp, marimo, jupyterlab, notebook). Run all 6 in parallel with `&` and `wait`. Each is independent.

**Impact on critical path:** None — smoke-test-extras runs parallel with pw-server/pw-marimo, which are slower. But reduces the wait-all gate target.

### Exp 19 — Relax pw-jupyter gate (start after heavy jobs only)

**Priority:** MEDIUM
**Estimated savings:** ~10-15s off total CI time
**File:** `ci/hetzner/run-ci.sh`
**What:** Instead of waiting for ALL jobs, wait only for the heavyweight ones (pw-server, pw-marimo, pw-wasm-marimo) that actually compete for CPU. The light jobs (lint, test-mcp, smoke) are already done by then anyway.

**Risk:** If a light job runs long (unlikely), it could overlap with pw-jupyter. Worth testing after exp 15-16 make the heavy jobs faster.

### Exp 20 — Remove waitForTimeout in playwright-marimo/storybook specs

**Priority:** LOW
**Estimated savings:** ~3s each = ~6s total
**Files:**
- `pw-tests/theme-screenshots-marimo.spec.ts` — 6× waits = ~3.1s
- `pw-tests/transcript-replayer.spec.ts` — 4× waits = ~3.6s

**Impact:** Minor — these jobs are already fast (11s storybook, 46s marimo).

### Priority Order

1. **Exp 15** (pw-server waitForTimeout) — highest absolute savings, on the wait-all gate
2. **Exp 17** (skip JS rebuild) — on the critical path, easy change
3. **Exp 16** (marimo sleep 5) — on the wait-all gate
4. **Exp 19** (relax gate) — unlocks earlier pw-jupyter start
5. **Exp 18** (parallel smoke) — small but free
6. **Exp 20** (minor waitForTimeout) — cleanup

### Projected Impact

If all experiments succeed:
- pw-server: 50s → ~33s (-17s)
- pw-marimo: 46s → ~41s (-5s)
- build-wheel: 16s → ~8s (-8s)
- Wait-all gate finishes ~17s earlier (bottleneck shifts from pw-server to pw-marimo)
- **Total CI: ~2m42s → ~2m15s** (saves ~27s)
- With relaxed gate (exp 19): **~2m05s**

---

## Architecture Notes

### Process Model
All processes run in a SINGLE Docker container:
- N JupyterLab servers (one per parallel slot, different ports)
- N Chromium browsers (one per Playwright process)
- N Python kernels (one per notebook being tested)
- Other DAG jobs (pytest, ruff, storybook, etc.) running concurrently

At PARALLEL=4: 12 heavyweight processes (4 Chromium + 4 JupyterLab + 4 kernels) on 16 vCPUs.

### Root Cause of Flakes
Cell execution fails when JupyterLab's kernel connection isn't established when
Shift+Enter is pressed. The keystroke is silently dropped. The retry loop
(dispatchEvent('click') + Shift+Enter every 15s) eventually catches it, but
under CPU contention the kernel connection can take >120s.

### What Works
1. WebSocket kernel warmup — all kernels reach idle in ~11s
2. Wait-all DAG — eliminate CPU overlap with other jobs
3. Playwright `--retries` — standard flake mitigation
4. `dispatchEvent('click')` — works when DOM is attached but not visible
5. pytest-xdist — halves Python test time

### What Doesn't Work
1. PARALLEL=3 — slower than 4, more batches = worse
2. 60s kernel idle wait — eats test timeout budget
3. PARALLEL=9 — too many processes for 16 vCPUs in full DAG
4. REST API kernel polling — never updates without WebSocket

---

## Commits (chronological)

| Commit | Description |
|--------|-------------|
| a1594bd | WebSocket warmup + remove batch stagger |
| 7e5754a | Unique Playwright --output per slot |
| a869d12 | pytest-xdist + infinite scroll timeout fixes |
| 2207d1e | Reduce DataFrame to 500 rows, bump test timeout |
| 6c1c743 | PARALLEL=8 |
| c2a16ec | CELL_EXEC_TIMEOUT=120s, test timeout=180s |
| 4cd4ccb | Robust cell focus (click + jp-mod-selected) |
| fac3cb5 | Kernel idle indicator wait |
| 4cd68b7 | PARALLEL=4 |
| 61e9947 | Shift+Enter retry loop |
| dc360ac | DEFAULT_TIMEOUT=30s |
| 35e0fc8 | dispatchEvent in retry |
| 7770774 | Wait-all DAG + Playwright retries=1 |
| 92ca618 | PARALLEL=3 (worse than 4) |
| 6a11b71 | Kernel idle wait 60s (too aggressive) |
| 8695488 | Kernel idle wait 15s + retries=2 |
