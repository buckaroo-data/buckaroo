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
| **15-21** | **5994612** | **jupyterapp + waitFor removal** | **10/10 jupyter, 9/10 overall** | **~1m36s** | **~2m59s** |
| 23 | 200bac6 | JS build cache + ci-queue | TBD (stress test running) | N/A | saves 15s critical path |
| 24 | 5c1e58f | Fix full_build.sh skip check | Not yet tested | N/A | saves ~10s more on build-wheel |

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

**Status:** DONE — 5-run stability test
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

### Exp 15+16+17+21 combined — `5994612` ⭐ BEST OVERALL

**Status:** DONE — 10-run stability test
**Changes (all in one commit):**
1. **Exp 15:** Replace `waitForTimeout(3000)` in server specs with `expect().toPass()` polling
2. **Exp 16:** Replace `sleep 5` in test_playwright_marimo.sh with curl polling loop
3. **Exp 17:** Skip JS rebuild in full_build.sh when dist already exists
4. **Exp 21:** Replace DOM kernel idle check with `window.jupyterapp` internal state query

**Results:** pw-jupyter 10/10 = **100% pass rate**. Overall 9/10 (1 pw-server flake).

| Run | pw-server | pw-marimo | pw-jupyter | Result | Total |
|-----|----------|----------|-----------|--------|-------|
| 1 | 37s | 42s | **1m36s** | **PASS** | **2m59s** |
| 2 | 36s | 41s | **1m36s** | **PASS** | **2m59s** |
| 3 | 36s | 42s | **1m35s** | **PASS** | **2m58s** |
| 4 | FAIL | 41s | **1m35s** | FAIL | 2m58s |
| 5 | 37s | 42s | **4m11s** | **PASS** | **5m34s** |
| 6 | 36s | 42s | **4m11s** | **PASS** | **5m33s** |
| 7 | 36s | 41s | **1m36s** | **PASS** | **2m58s** |
| 8 | 36s | 42s | **1m36s** | **PASS** | **2m59s** |
| 9 | 35s | 41s | **4m10s** | **PASS** | **5m32s** |
| 10 | 36s | 42s | **1m35s** | **PASS** | **2m58s** |

**Stage improvements vs baseline (14e):**
- pw-server: 50s → **37s** (-13s, exp 15)
- pw-marimo: 46s → **42s** (-4s, exp 16)
- build-wheel: 17s → 17s (exp 17 no-op — checkout clears dist)
- pw-jupyter pass rate: 80% → **100%** (exp 21)

**Key findings:**
1. `window.jupyterapp` kernel check (exp 21) broke the 80% ceiling completely — 10/10 jupyter passes.
2. pw-server `waitForTimeout` removal saved 13s but introduced a 1/10 flake (needs investigation).
3. pw-jupyter has a bimodal pattern: 7/10 runs at ~1m36s, 3/10 at ~4m11s (retries used).
4. Median total CI time: **2m59s** (vs 2m43s in 14e, +16s from longer jupyter median).
5. Exp 17 (skip JS rebuild) was a no-op — `git checkout` clears dist/ so the skip never triggers.

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

### Priority Order (superseded — exp 15-17 done in 5994612)

1. ~~**Exp 15** (pw-server waitForTimeout)~~ — DONE in 5994612. Saved 13s (50s → 37s)
2. ~~**Exp 17** (skip JS rebuild)~~ — DONE in 5994612 but was a no-op (git checkout clears dist). **Fixed properly in Exp 23** (external JS cache).
3. ~~**Exp 16** (marimo sleep 5)~~ — DONE in 5994612. Saved 4s (46s → 42s)
4. **Exp 19** (relax gate) — still TODO
5. **Exp 18** (parallel smoke) — still TODO
6. **Exp 20** (minor waitForTimeout) — still TODO

### Projected Impact (superseded by actual results)

~~If all experiments succeed:~~
- ~~pw-server: 50s → ~33s (-17s)~~ → **Actual: 50s → 37s (-13s)**
- ~~pw-marimo: 46s → ~41s (-5s)~~ → **Actual: 46s → 42s (-4s)**
- ~~build-wheel: 16s → ~8s (-8s)~~ → **Actual: 17s → 17s (no-op — git checkout clears dist)**
- ~~Total CI: ~2m42s → ~2m15s~~ → **Actual: 2m59s median** (jupyter bimodal: 7/10 at 1m36s, 3/10 at 4m11s)

**Exp 17 root cause:** `full_build.sh` checked for `dist/index.js` but vite outputs `dist/index.es.js`. The skip condition never triggered. Fixed in `5c1e58f` but only helps future SHAs (old SHAs have old full_build.sh). The real fix is Exp 23 (external JS cache).

---

### Exp 23 — JS Build Cache + CI Job Queue (f30da68 → 5c1e58f)

**Status:** IN PROGRESS — stress test running (5/16 complete)
**Changes:**
1. **JS build cache:** Cache `dist/` at `/opt/ci/js-cache/<tree-hash>` keyed by `sha256sum` of `git ls-tree` for `src/`, `package.json`, `tsconfig.json`, `vite.config.ts`. Restore after `git checkout`, save in `job_test_js()`.
2. **CI job queue:** `ci-queue.sh` — directory-based queue with `flock` single-worker enforcement. Commands: push, status, cancel, clear, log, repeat.
3. **full_build.sh fix:** Check `dist/index.es.js` not `dist/index.js` for skip logic.

**JS cache impact (measured):**

| Metric | Cache MISS | Cache HIT | Savings |
|--------|-----------|-----------|---------|
| test-js | 21s | 5s | **-16s** |
| build-wheel starts at | +23s | +7s | **-16s** |
| wheel-dependent starts at | +40s | +25s | **-15s on critical path** |

build-wheel still takes 18s with cache HIT because `full_build.sh` had the wrong filename check — it rebuilt JS from scratch even though dist/ existed. Fixed in `5c1e58f` (`index.js` → `index.es.js`). **Expected build-wheel with both fixes: ~8s** (just esbuild widget + uv build, no tsc+vite).

**CPU utilization during CI (Vultr 16 vCPU):**
```
Phase                  Host CPU    Container CPU    Notes
─────────────────────  ─────────   ──────────────   ──────────────────
Wave 0 (8 parallel)    ~60-90%     ~800-1200%       All 16 cores busy
build-wheel            ~40%        ~400%            tsc+vite
Wheel-dependent        ~40-60%     ~600%            4 jobs parallel
pw-jupyter startup     ~40%        ~800%            4 JupyterLabs + 4 Chromiums launching
pw-jupyter execution   ~5-10%      ~100%            Mostly idle — waiting on kernel I/O
pw-jupyter idle gaps   ~1-3%       ~5-25%           Between batches, near zero
```

**Key finding:** The machine is massively underutilized during playwright-jupyter (the longest phase). 16 vCPUs sit at 5-10% while waiting for kernel I/O. The bottleneck is kernel startup/connection latency, not CPU.

**Stress test results (in progress):**

| SHA | Time | Result | JS Cache | Notes |
|-----|------|--------|----------|-------|
| 7b6a05c | 206s | FAIL | HIT (from prior test) | test-python × 3 fail (old code) |
| fcfe368 | 186s | FAIL | HIT (from prior test) | pw-jupyter fail (old specs) |
| 5ff4d6e | 209s | FAIL | HIT (same hash as 837654e) | pw-jupyter fail (old specs) |
| 837654e | 206s | FAIL | HIT | pw-jupyter fail (old specs) |
| f8a8b94 | ... | running | ... | ... |

All failures are from old test code (no `window.jupyterapp` kernel check). This is exactly what synthetic merges (Part 3) would fix.

---

### Exp 24 — Fix build-wheel with JS cache (5c1e58f)

**Status:** DONE (code deployed, not yet tested with new SHAs)
**What:** `full_build.sh` checked for `dist/index.js` but vite outputs `dist/index.es.js`. Fixed the check.

**Expected impact with both Exp 23 + 24:**
```
                    Before    Cache MISS    Cache HIT + fix
test-js              21s        21s            5s
build-wheel          18s        18s           ~8s (esbuild + uv build only)
Critical path gap    40s        40s           ~13s
```

This saves **27s on the critical path** (from checkout to wheel-dependent jobs starting).

**Projected total CI with Exp 23+24:** `~13s (to wheel) + 42s (pw-marimo) + 96s (pw-jupyter) = ~2m31s`

---

## Future Experiments

### Exp 25 — Synthetic Merge Commits for Stress Testing

**Status:** Code written (`prepare-synth.sh`), not yet tested
**What:** Merge latest test improvements (from `5994612`) onto old SHAs so stress tests use current Playwright specs with old application code. Resolves conflicts by taking "theirs" for test files, "ours" for app code.
**Why:** Current stress test runs old SHAs with old specs that lack `window.jupyterapp` kernel check → all pw-jupyter tests fail. Synthetic merges would give accurate reliability data.

### Exp 19 — Relax pw-jupyter gate

**Priority:** MEDIUM — saves ~10-15s
**What:** Wait only for heavy jobs (pw-server, pw-marimo) not all jobs. Light jobs (lint, smoke, mcp) are always done by then.
**Risk:** If a light job runs long, it overlaps pw-jupyter.

### Exp 18 — Parallelize smoke-test-extras

**Priority:** LOW — saves ~10s off wall time but NOT on critical path
**What:** Run 6 venv installs in parallel (currently sequential).

### Exp 20 — Minor waitForTimeout cleanup

**Priority:** LOW — ~6s total across marimo+storybook specs
**What:** Replace remaining `waitForTimeout` calls in non-server specs.

### Exp 26 — Wheel cache across SHAs

**Priority:** MEDIUM
**What:** If Python source hasn't changed between commits, reuse the wheel from a prior SHA. Key by `git ls-tree -r HEAD buckaroo/ pyproject.toml | sha256sum`. Would eliminate build-wheel entirely for JS-only changes.

### Exp 27 — Persistent pnpm install skip

**Priority:** LOW — saves ~2-3s
**What:** `pnpm install --frozen-lockfile` takes 2-3s even with warm store (just creating hardlinks). Skip if `node_modules/.package-lock.json` matches `pnpm-lock.yaml` hash.

### Exp 28 — Early Kernel Warmup (decouple kernel startup from wheel)

**Priority:** HIGH — saves ~30-40s off critical path
**What:** Start JupyterLab servers and warm kernels at t0 (Wave 0), before the wheel is built. Install buckaroo wheel into the running venv after build-wheel completes. Run Playwright tests against already-warm kernels.

**Why it works:**
- JupyterLab needs `anywidget`/`ipywidgets` extensions loaded at startup (for widget rendering), but NOT `buckaroo` itself
- Pre-install `jupyterlab`, `anywidget`, `ipywidgets`, `polars`, `websocket-client` at t0
- Start 4 JupyterLab servers + WebSocket kernel warmup (overlaps with test-js → build-wheel)
- After wheel built: `uv pip install buckaroo-*.whl` into the running venv — deps already satisfied, so just installs the Python package (~1-2s)
- anywidget loads widget JS dynamically at runtime — no JupyterLab restart needed
- New kernels spawned by Playwright tests will be able to `import buckaroo`

**Current pw-jupyter breakdown (~1m36s):**
1. Create venv + install wheel+polars+jupyterlab: ~10-15s
2. Start 4 JupyterLab servers: ~5-10s
3. WebSocket kernel warmup per server: ~20-30s
4. Run Playwright tests: ~50-60s

Steps 1-3 (~35-55s) can overlap with Wave 0 + build-wheel (~13-40s depending on cache).

**CPU data supports this:** Machine is at 5-10% during pw-jupyter execution — the kernel I/O bottleneck means there's plenty of CPU headroom to warm kernels in Wave 0 alongside other jobs.

**Risk:** If kernel warmup competes with Wave 0 CPU-intensive jobs (pytest-xdist, tsc+vite), it could slow both down. But warmup is mostly I/O-bound (waiting for kernel idle), not CPU-bound.

**Files:** `ci/hetzner/run-ci.sh` (major restructure of DAG), `scripts/test_playwright_jupyter_parallel.sh` (accept pre-warmed servers)

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
| 5994612 | jupyterapp kernel check + waitForTimeout removal + marimo sleep removal |
| 200bac6 | JS build cache + ci-queue + prepare-synth + stress-test --synth |
| e7fff5b | Mount js-cache volume for persistence |
| 5c1e58f | Fix full_build.sh index.es.js check (exp 24) |
