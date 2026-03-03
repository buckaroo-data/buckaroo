# CI Tuning Experiments — Historical Archive

Completed experiments from the CI optimization effort. For current state and open issues, see `ci-tuning-experiments.md`.

**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Baseline:** 3m16s (full DAG, PARALLEL=3 jupyter)

---

## Summary Table

| Exp | Commit | Config | Pass Rate | Jupyter Time | Total Time |
|-----|--------|--------|----------|-------------|-----------|
| 10 | 7e5754a | P=9 WebSocket phase5b | 8/9 notebooks | ~2m01s | N/A (5b only) |
| 11 | 7e5754a | P=9 full DAG | 0/1 | N/A | N/A |
| 12 | a869d12 | pytest-xdist -n 4 | N/A (python only) | N/A | ~30s/ver (was ~63s) |
| 13 | 2207d1e | infinite_scroll fix | N/A | N/A | N/A |
| 14a | 35e0fc8 | P=4 old DAG | 2/7 = 29% | ~1m12s | ~2m40s |
| 14b | 7770774 | P=4 wait-all DAG | 4/5 = 80% | ~3m20s | ~3m30s |
| 14c | 92ca618 | P=3 wait-all DAG | 3/5 = 60% | ~5m18s | ~7m |
| 14d | 6a11b71 | P=4 wait-all + kernel-idle-60s | 3/5 = 60% | varies | varies |
| 14e | 8695488 | P=4 wait-all + idle-15s + retry=2 | 4/5 = 80% | ~1m12s | ~2m42s |
| **15-21** | **5994612** | **jupyterapp + waitFor removal** | **10/10 jupyter** | **~1m36s** | **~2m59s** |
| 23 | 200bac6 | JS build cache | N/A | N/A | saves 17s critical path |
| 24 | 5c1e58f | Fix full_build.sh skip check | N/A | N/A | build-wheel 17s→3s |
| **18+19+20** | **60618ce** | **parallel smoke + relaxed gate** | **pw-jupyter 1/1** | **1m38s** | **2m31s** |
| **28** | **172158b** | **early kernel warmup** | **3/3 pw-jupyter** | **1m14s** | **2m25s** |
| **30** | **d369894** | **remove heavyweight PW gate** | **7/7 pw-jupyter** | **1m15s** | **1m43s** |
| 31 | b2398d5 | PARALLEL=9 revisited | ABANDONED | 4m+ | N/A |
| 32 | b2398d5 | lean Wave 0 + defer pytest | 3/3 pw-jupyter | 80s | 1m51s |
| **33** | **076f40f** | **P=6 batched + re-warmup** | **9/9 jupyter** | **66s** | **1m44s** |
| 33 | 0e98e13+ | P=9 (various stagger/port combos) | 1-3/9 jupyter | 120s timeout | ~2m45s |
| **34+36** | **2ba10e7** | **SKIP_INSTALL + renice + pw-server fix** | **pw-server 3/3** | **76s** | **2m00s** |

---

## Experiment Details

### Exp 10 — PARALLEL=9 WebSocket warmup baseline (7e5754a)

Mode: `--phase=5b` (isolated, no DAG contention). PARALLEL=9.

**Key discovery:** REST API (GET /api/kernels/{id}) NEVER updates execution_state from "starting" to "idle" without a WebSocket client. The fix: connect to `/api/kernels/{id}/channels` via WebSocket, triggering the "nudge" mechanism. All 9 kernels reached idle in 11s.

Results: 8/9 PASS. `test_infinite_scroll_transcript` fails (2000-row widget too heavy).

Bugs fixed: ENOENT race (unique `--output` per slot), REST warmup replaced with WebSocket.

---

### Exp 11 — PARALLEL=9 full DAG (7e5754a)

All 9 notebooks FAILED. playwright-server overlap causes CPU contention with 9 Chromium + 9 JupyterLab + 9 kernels.

**Finding:** Phase 5b passes (isolated) but full DAG fails at P=9. CPU contention is the bottleneck.

---

### Exp 12 — pytest-xdist (a869d12)

Added `pytest-xdist>=3`, run with `-n 4 --dist load`. Python test time: ~63s → ~30s per version.

---

### Exp 13 — infinite_scroll_transcript fix (2207d1e)

Reduced DataFrame 2000→500 rows, scroll target 1500→400, bumped timeouts, added Shift+Enter retry loop. Passes alone, fails under concurrency.

---

### Exp 14a-e — PARALLEL=4 reliability series

| Variant | Change | Pass Rate |
|---------|--------|-----------|
| 14a (35e0fc8) | P=4 old DAG | 29% (2/7) |
| 14b (7770774) | Wait-all DAG + retries=1 | **80%** (4/5) |
| 14c (92ca618) | P=3 wait-all | 60% (3/5) — worse |
| 14d (6a11b71) | Kernel idle wait 60s | 60% (3/5) — worse |
| 14e (8695488) | Kernel idle 15s + retries=2 | 80% (4/5) |

**Key findings:**
- Wait-all DAG is the single biggest reliability improvement (29%→80%)
- PARALLEL=3 is worse than 4 (more batches = more overhead)
- 60s kernel idle wait burns timeout budget
- 80% is the ceiling with DOM-based kernel checks

---

### Exp 15+16+17+21 — jupyterapp + timing fixes (5994612)

10-run stability test. All in one commit:
1. **Exp 15:** `waitForTimeout(3000)` → `expect().toPass()` in server specs. pw-server 50s→37s.
2. **Exp 16:** `sleep 5` → curl polling in marimo warmup. pw-marimo 46s→42s.
3. **Exp 17:** Skip JS rebuild in full_build.sh — no-op (git checkout clears dist).
4. **Exp 21:** `window.jupyterapp` kernel check. **pw-jupyter 80%→100%.**

Results: pw-jupyter 10/10. Overall 9/10 (1 pw-server flake). Median total: 2m59s.

Bimodal pattern: 7/10 at ~1m36s, 3/10 at ~4m11s (retries used).

---

### Exp 23 — JS Build Cache (200bac6)

Cache `dist/` at `/opt/ci/js-cache/<tree-hash>`. Keyed by sha256 of `git ls-tree` for src/, package.json, tsconfig.json, vite.config.ts.

| Metric | Cache MISS | Cache HIT | Savings |
|--------|-----------|-----------|---------|
| test-js | 21s | 5s | -16s |
| build-wheel starts at | +23s | +7s | -16s |
| wheel-dependent starts at | +40s | +25s | -15s on critical path |

CPU profile showed machine massively underutilized during pw-jupyter (5-10% busy). Bottleneck is kernel I/O latency, not CPU.

---

### Exp 24 — Fix build-wheel skip check (5c1e58f)

`full_build.sh` checked `dist/index.js` but vite outputs `dist/index.es.js`. Fixed. Combined with JS cache: build-wheel 17s→3s.

---

### Exp 18+19+20 — parallel smoke, relaxed gate (60618ce)

1. Parallel smoke-test-extras: 20s→8s
2. Relax pw-jupyter gate: wait only for heavyweight PW jobs
3. Reduce waitForTimeout in marimo screenshots: ~3.4s

Total: 2m59s→**2m31s** (-28s). Critical path now dominated by pw-jupyter (65%).

---

### Exp 28 — Early Kernel Warmup (172158b)

New `job_jupyter_warmup()` in Wave 0: venv, deps, 4 JupyterLab servers, WebSocket warmup, notebook trust. Overlaps with Wave 0 (free).

pw-jupyter 3/3 = 100%. Total: 2m31s→**2m25s** (-6s net). pw-jupyter itself: 1m38s→1m14s (-24s).

---

### Exp 30 — Remove Heavyweight PW Gate (d369894)

pw-jupyter starts alongside all wheel-dependent jobs. No more waiting for pw-server/marimo.

pw-jupyter 7/7 = 100% under 40-75% CPU contention. Total: 2m25s→**1m43s** (-42s).

CPU profile (vmstat): Wave 0 80-97% busy → wheel-dependent 40-75% → pw-jupyter alone 6-20%.

---

### Exp 31 — PARALLEL=9 revisited (b2398d5)

ABANDONED. pw-jupyter 4+ minutes (vs 75s at P=4). Too many processes for 16 vCPU.

---

### Exp 32 — Lean Wave 0 + defer pytest (b2398d5)

Fewer Wave 0 jobs, defer pytest 3.11/3.12/3.14. pw-jupyter 3/3 but total 1m51s (+8s vs Exp 30). Just shifts contention. No benefit.

---

### Exp 33 — PARALLEL=6 batched (076f40f)

PARALLEL=6 with 6+3 batching, between-batch kernel re-warmup. P=9 conclusively dead.

P=6 results: pw-jupyter 66s (9/9), total 1m44s, 13/14 overall (1 pw-server flake).

P=9 results (4 runs, all failed): 1-3/9 notebooks, 120s timeout. Root cause: 27+ processes on 16 vCPU = CPU starvation.

Bug fixes: batch-2 hang (new kernels need WebSocket nudge), `local` outside function.

---

### Exp 34+36 — SKIP_INSTALL + renice + pw-server fix (2ba10e7)

**SKIP_INSTALL:** All PW scripts check `SKIP_INSTALL=1` and skip redundant pnpm install in CI.

**renice:** `renice -n -10` for critical-path (test-js), `renice -n 10` for background. Initial attempt with `nice` failed (external command can't run shell functions).

**pw-server fix:** `getCellText()` + `expect().toBe()` → `cellLocator()` + `toHaveText()`. Auto-retrying assertions eliminate AG-Grid render race.

Results: pw-server 3/3 PASS (flake fixed). pw-jupyter 1/3 — regression from zombie accumulation (see current doc for details).

---

## Architecture Notes

### Process Model
All processes run in a SINGLE Docker container:
- N JupyterLab servers (one per parallel slot, different ports)
- N Chromium browsers (one per Playwright process)
- N Python kernels (one per notebook being tested)
- Other DAG jobs (pytest, ruff, storybook, etc.) running concurrently

At PARALLEL=6: 18 heavyweight processes (6 Chromium + 6 JupyterLab + 6 kernels) on 16 vCPUs.

### Root Cause of Jupyter Flakes (solved)
Cell execution fails when JupyterLab's kernel connection isn't established when Shift+Enter is pressed. The keystroke is silently dropped. Fixed by `window.jupyterapp` kernel check (Exp 21) which queries the exact same `session.kernel` that `CodeCell.execute()` uses.

---

## All Commits (chronological)

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
| 5994612 | jupyterapp kernel check + waitForTimeout removal |
| 200bac6 | JS build cache + ci-queue |
| e7fff5b | Mount js-cache volume for persistence |
| 5c1e58f | Fix full_build.sh index.es.js check |
| 60618ce | Exp 18+19+20: parallel smoke, relaxed gate → 2m31s |
| 172158b | Exp 28: early kernel warmup → 2m25s |
| d369894 | Exp 30: remove heavyweight PW gate → 1m43s |
| d020744 | Exp 29: marimo auto-retry assertions |
| b2398d5 | Exp 31+32: P=9 abandoned, lean Wave 0 → 1m51s |
| 076f40f | Exp 33: P=6 batched + re-warmup → 1m44s |
| 9dcc5e0 | Pre-run cleanup |
| 630cf60 | Exp 34+36: SKIP_INSTALL, renice, pw-server auto-retry |
| da3a7ad | Fix: renice instead of nice for shell functions |
| 2ba10e7 | Fix: don't renice jupyter-warmup, SKIP_INSTALL in pw-jupyter |
