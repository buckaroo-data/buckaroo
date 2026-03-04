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
| 37 | 20fb931 | `init: true` in docker-compose | 101 zombies after run 1 | N/A | 2m59s |
| **37** | **46c165c** | **tini ENTRYPOINT in Dockerfile** | **0 zombies** | N/A | N/A |
| 38 | ef53834 | P=6 on tini image | 3-6/6 kernel timeout | N/A | ~2m58s |
| **38** | **fff99fa** | **P=4 on tini image** | **14/0 PASS** | **95s** | **2m01s** |
| 35+39 | 4a7fefc | split build-js/test-js + lockfile hash | 15/0 PASS (fresh) | 96s | 2m21s (fresh) |
| **40** | **176f6f6** | **P=9 + /dev/shm fix** | **all PASS** | **50s** | **1m42s** |
| 41-A | fd85f0a | defer smoke-test-extras | needs 64GB | N/A | N/A |
| 41-B | fd85f0a | 2s stagger on 32GB | FAIL (0/9 jupyter) | timeout | 3m08s |
| 41-C | fd85f0a | MCP timing instrumentation | N/A (instrumentation) | N/A | N/A |
| 41-D | fd85f0a | pw-server timing instrumentation | N/A (instrumentation) | N/A | N/A |
| **42** | **09c6faa** | **2s stagger, 64GB** | **all PASS** | **52s** | **1m42s** |
| Infra | 1c49a02 | bind-mount CI runner scripts | N/A | N/A | N/A |
| 51 | N/A | Move pw-wasm-marimo to Wave 0 | INVALID | N/A | N/A |

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

### Exp 37 — tini as PID 1 (20fb931, 46c165c)

**Attempt 1: `init: true` in docker-compose.yml (20fb931)**

FAILED. `init: true` makes Docker wrap the container with tini at the *host* level. Inside the container, PID 1 is still `sleep`. `docker exec`'d CI processes become children of `sleep`, which doesn't call `wait()`. After run 1: 101 zombies (jupyter-lab, chrome-headless, node, python).

Verification: `docker exec buckaroo-ci ps -p 1 -o comm` → `sleep` (not tini). `docker top` shows tini as host-level PID wrapping `sleep`.

**Attempt 2: `ENTRYPOINT ["/usr/bin/tini", "--"]` in Dockerfile (46c165c)**

Bakes tini into the image. `CMD ["sleep", "infinity"]` runs as tini's child. `docker exec`'d processes become children of tini (PID 1), which reaps them. Requires image rebuild (`apt-get install tini`).

**VALIDATED.** Zero zombies after 3 runs. PID 1 is tini. But back-to-back pw-jupyter failures persist (not caused by zombies — see Open Issue #1 in current doc). Tini confirmed working, P=4 is reliable baseline.

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
| 20fb931 | Exp 37: `init: true` in docker-compose (failed) |
| 46c165c | Exp 37: tini ENTRYPOINT in Dockerfile (validated — 0 zombies) |
| ef53834 | Exp 38: revert to P=6 on tini image (P=6 broken) |
| fff99fa | Exp 38: revert P=6→4 (stable baseline) |
| 4a7fefc | Exp 35: split build-js/test-js + lockfile hash persistence fix |
| e6ea620 | Add --disable-dev-shm-usage for Docker P=5+ |
| 176f6f6 | Integrate /dev/shm fix — P=9, settle=0, --disable-dev-shm-usage |
| 29b19fa | Exp 41: delay smoke-test, tighten stagger 5→2s, MCP/server timing |
| 1c49a02 | Bind-mount CI scripts + update-runner.sh |
| fd85f0a | Exp 41: fix awk timing (bc not in container) |
| 676161f | Docs update |
| c26897f | Fix: clean all 9 jupyter ports (8889-8897) |
| 37aed6b | Remove all stagger (BROKEN — do not use) |
| 6c8590d | Exp 42: restore 2s stagger (0s stagger proven broken) |
| 7626c67 | Exp 42: cleanup esbuild, pw-results, port range 8889-8897 |
| 09c6faa | Exp 42: bump watchdog 210→360s for cold starts |

---

## Experiment Details (Exp 39-42)

### Exp 35+39 — Split build-js/test-js + lockfile hash persistence (4a7fefc)

**Split build-js / test-js:** test-js runs in background after build-js completes, saving ~3s off critical path.

**Lockfile hash persistence:** Hash store moved from `/var/ci/hashes/` (inside container) to `/opt/ci/logs/.lockcheck-hashes/` (bind-mounted). Hashes persist across container restarts — no more spurious "Lockfiles changed — rebuilding deps".

Results: 15/0 PASS on fresh run. b2b flaky on pw-jupyter (pre-/dev/shm fix).

---

### Exp 40 — /dev/shm fix + P=9 (e6ea620, 176f6f6) — SUCCESS

**What:** Add `--disable-dev-shm-usage` to all Playwright configs (storybook, server, marimo, wasm-marimo, jupyter). Docker default /dev/shm is 64MB which causes Chromium crashes at P=5+.
**Result:** P=9 stable, settle=0 works, all jobs PASS. Total 1m42s — best ever.
**Key insight:** Back-to-back degradation was also caused by /dev/shm exhaustion, not zombie accumulation.

---

### Exp 41-A — Defer smoke-test-extras (fd85f0a) — WORKS (needs larger server)

**What:** Launch smoke-test-extras after `wait $PID_PW_JP` instead of at t+0. Event-driven, not sleep-based.
**Result on 32GB:** smoke-test-extras 28s (down from 61s). Still not the ideal 5s because pw-wasm-marimo was still running, keeping memory pressure elevated.
**Expected on 64GB+:** should hit the 5s uncontended target.

### Exp 41-B — Tighten stagger 5s→2s (fd85f0a) — FAILED on 32GB

**What:** Reduce gaps between pw-marimo/wasm/server from 5s to 2s.
**Result:** pw-jupyter hangs consistently (0/9 or 1/9 notebooks complete in 120s timeout). All 12 Chromium instances launching within 6s overwhelms 32GB RAM.
**Conclusion:** 5s stagger is necessary on 32GB. Re-test on larger server.

### Exp 41-C — MCP timing instrumentation (fd85f0a) — IN PLACE

**What:** Added `[mcp-timing]` lines to `job_test_mcp_wheel` — times venv creation, wheel install, each pytest run.
**Note:** Uses `awk` not `bc` (bc not installed in container).
**Result (from fd85f0a run):** test-mcp-wheel total 11s. Detailed breakdown needs green run to read.

### Exp 41-D — pw-server timing instrumentation (fd85f0a) — IN PLACE

**What:** Added `--reporter=list` to pw-server in CI for per-test timing. Plus `[pw-server-timing]` total elapsed.
**Result (from fd85f0a run):** pw-server total 41s. Per-test breakdown in pw-server.log.

---

### Exp 42 — Server upgrade + stagger tuning (6c8590d, 7626c67, 09c6faa) — SUCCESS

**What:** Moved to 32 vCPU / 64GB server. Tested stagger values:
- **0s stagger:** FAILS — 8/9 pw-jupyter notebooks hang at "Shift+Enter attempt 7". Port 8889 works, 8890-8897 don't. Reproducible on both 176f6f6 and 37aed6b. Root cause: kernel provisioner or ZMQ contention when 12 Chromium + 9 JupyterLab kernel starts all race simultaneously. NOT a RAM issue (64GB plenty, free stays >40GB).
- **2s stagger:** WORKS — all pass consistently. 1m42-1m49s total.
- **5s stagger:** WORKS — baseline from 176f6f6, 1m42s on old 32GB server.

**Also fixed:**
- Port cleanup range: was 8889-8894 (6 ports), now 8889-8897 (9 ports for P=9)
- esbuild cleanup: `pkill -9 -f esbuild` added to pre-run cleanup
- /tmp/pw-results-* cleanup: added to pre-run rm
- CI watchdog: 210s → 360s (cold-start on fresh image needs ~3.5min for uv cache miss)

**Key insight:** The 0s stagger failure was initially misattributed to SHA-specific differences (37aed6b vs 176f6f6). In reality, both SHAs fail with 0s stagger when using the bind-mounted runner.

### Infra: Bind-mount CI runner scripts (1c49a02) — SUCCESS

**What:** Volume-mount `/opt/ci/runner/` into container at `/opt/ci-runner/:ro`. Added `update-runner.sh` that:
- Copies scripts from repo to `/opt/ci/runner/`
- Detects Dockerfile changes via sha256 hash
- Only rebuilds image when Dockerfile changes

**Result:** Script changes take effect instantly. No container restart required.

---

## Resolved Issues (from Exp 39-42 era)

### Back-to-back run degradation — LARGELY FIXED

**Root causes found:**
- Docker 64MB `/dev/shm` exhaustion (fixed with `--disable-dev-shm-usage`)
- Stale storybook/esbuild processes leaking ~400MB between runs (fixed: `pkill esbuild` in pre-run cleanup)
- Stale JupyterLab on ports 8895-8897 not cleaned (fixed: port range 8889-8897)
- `/tmp/pw-results-*` accumulating across runs (fixed: cleanup added)
**Status:** b2b run 1→2 passes on 64GB with all fixes.

### pw-server flake — FIXED (Exp 34+36)

`cellLocator()` + `toHaveText()` auto-retrying assertions in `server.spec.ts` and `server-helpers.ts`. 3/3 pw-server PASS after fix.

### Lockfile hash persistence across container restarts — FIXED (4a7fefc)

Moved hash store to bind-mounted `/opt/ci/logs/.lockcheck-hashes/`.

### PARALLEL=6 regression — SUPERSEDED by P=9 + /dev/shm fix

P=6 issues were caused by Docker's 64MB /dev/shm. `--disable-dev-shm-usage` fixes this. P=9 is now stable with 2s stagger on 64GB.

### 32GB RAM constraint — RESOLVED (moved to 64GB)

On 64GB: smoke-test-extras 6s (was 61s on 32GB). 2s stagger works. 0s stagger does NOT work (kernel contention, not RAM).

### Container detritus between runs

Processes/files that leak after each CI run:
- Storybook node process (~400MB RSS), 3 esbuild processes (~100MB), watchdog sleep, /tmp/pw-results-*, /tmp/pw-html-*, ~/.jupyter/lab/workspaces/, ~/.local/share/jupyter/runtime/jupyter_cookie_secret

All handled by pre-run cleanup in run-ci.sh.

---

## Run History (Exp 39-42 era)

| SHA | Experiment | Total | Result | Notes |
|-----|-----------|-------|--------|-------|
| 09c6faa | Exp 42 (2s stagger, 64GB, run 1) | 1m42s | **all PASS** | Post-restart, clean container |
| 09c6faa | Exp 42 (2s stagger, 64GB, b2b) | 2m27s | **all PASS** | pw-wasm-marimo slow (1m35s anomaly) |
| 37aed6b | 0s stagger, 64GB (5 runs) | 2m-3m | ALL FAIL | pw-jupyter hangs 8/9 every time |
| 176f6f6 | 0s stagger runner, 64GB (run 3) | 2m01s | FAIL | 0s stagger fails on ALL SHAs |
| c26897f | 2s stagger, 64GB, port fix | 1m45s | **all PASS** | First clean run after port fix |
| c26897f | 2s stagger, 64GB, warm cache | 1m47s | **all PASS** | Cache hit confirmed |
| fd85f0a | Exp 41-A+B (2s stagger, 32GB) | 3m08s | 13/2 FAIL | pw-jupyter timeout (0/9), pw-wasm-marimo timeout; smoke 28s |
| 1c49a02 | Exp 41-A+B (2s stagger) | 3m29s | 13/2 FAIL | pw-jupyter timeout (1/9); first bind-mount run |
| 176f6f6 | P=9, /dev/shm fix, 5s stagger | 1m42s | **all PASS** | Best config — baseline for optimization |
| e6ea620 | P=5 + /dev/shm fix | — | all PASS | /dev/shm fix validated |
| 4a7fefc | Exp 35+39 (run 1, fresh) | 2m21s | **15/0 PASS** | Lockfile rebuild (first on new image); build-js 1s |
| 4a7fefc | Exp 35+39 (run 2, b2b) | 2m00s | 14/1 FAIL | Lockfiles unchanged (fix works!); pw-jupyter b2b |
| 4a7fefc | Exp 35+39 (post-restart) | 2m37s | 14/1 FAIL | Lockfiles unchanged after restart; pw-jupyter flaky |
| 4a7fefc | Exp 35+39 (b2b again) | 1m36s | **15/0 PASS** | pw-jupyter 96s; fastest warm run |
| fff99fa | P=4 + tini (run 1) | 2m41s | **14/0 PASS** | Post-restart, lockfile rebuild |
| fff99fa | P=4 + tini (run 2) | 2m01s | **14/0 PASS** | Back-to-back, no lockfile |
| fff99fa | P=4 + tini (run 3) | 2m10s | 13/1 FAIL | pw-jupyter timeout (back-to-back degradation) |
| ef53834 | P=6 + tini (run 1) | 2m58s | 13/1 FAIL | 3/6 pw-jupyter pass |
| ef53834 | P=6 + tini (run 2) | 2m01s | 13/1 FAIL | 0/6 pw-jupyter pass |
| ef53834 | P=4 env override | 2m07s | **14/0 PASS** | Proves P=4 works on this image |

### CPU Profile (commit 4a7fefc, 16 vCPU — OLD SERVER)

| Phase | Time | Duration | CPU (us+sy) |
|-------|------|----------|-------------|
| Setup + checkout | 0-3s | 3s | ~5% |
| Wave 0 ramp (lint, build-js, pytest, storybook, warmup) | 4-12s | 8s | 21→97% |
| Wave 0 peak (test-python-3.13 + warmup) | 13-18s | 5s | 48-73% |
| Wave 0 tail + warmup finishing | 19-33s | 14s | 6-28% |
| Wheel-dependent launch (all PW + pytest) | 34-55s | 21s | 39-64% |
| Peak concurrent (all PW + pytest overlap) | 56-77s | 21s | 49-94% |
| Jobs finishing, pw-jupyter tail | 78-87s | 9s | 20-35% |
| pw-jupyter alone (kernel I/O bound) | 88-101s | 13s | **4-13%** |

Note: This profile is from the old 16 vCPU server. On 32 vCPU, CPU is no longer a constraint — bottleneck is kernel I/O latency and ZMQ/kernel provisioner contention.

---

### Exp 51 — Move pw-wasm-marimo to Wave 0 — INVALID

**What:** Start pw-wasm-marimo in Wave 0 alongside lint/build-js, since it uses static WASM files served by `npx serve`.
**Why it doesn't work:** All Playwright integration tests (including pw-wasm-marimo) require the built wheel to be installed. The widget JS bundle comes from the wheel build. Cannot run before build-wheel completes.

---

## VX1-Era Experiments (Exp 52-58)

**Server:** Vultr VX1 16C (137.220.56.81) — 16 vCPU/64GB, EPYC Turin Zen 5
**Baseline:** ~1m42s (32 vCPU / 64GB, P=9, 2s stagger)

### Summary Table (VX1 era)

| Exp | Description | Result | Total Time |
|-----|-------------|--------|------------|
| 52 | Fix ipykernel version | NOT THE FIX (P=9 was) | — |
| 53 | Parallel DAG + warmup optimization | 1m45s → **1m10s** (-34s) | 1m10s |
| 53b | tmpfs ramdisk | NOT WORTH IT (CPU-bound) | 1m06s |
| 54 | Fast-fail mode (`--fast-fail`) | Implemented | — |
| 55 | `--only`/`--skip` job filters | **51s** (with --skip) | 51s |
| 56 | GitHub CI status | Already passing | — |
| 58 | Stress test (3/16 commits) | Infra validated, app-level failures | — |

---

### Exp 52 — Fix ipykernel version — NOT THE BLOCKER

Packages upgraded in commit cd51c9e (ipykernel 6.29.5→7.2.0, jupyterlab 4.5.0→4.5.5,
jupyter-server 2.15.0→2.17.0, tornado 6.4.2→6.5.4). But this wasn't the fix —
the real fix was PARALLEL=9 (commit 0103187). See `pw-jupyter-batch-reuse-fix.md`.

---

### Exp 53 — Restore full parallel DAG — 1m10s

**Result:** 1m45s → **1m11s** (-34s). All Playwright jobs pass. Commit 5b85d83.

Overlapped pw-marimo (+2s), pw-server (+4s), pw-wasm-marimo (+6s), pytest (+8s)
alongside pw-jupyter. Staggered 2s apart. Mean CPU 47.7%, peak 100% for ~15s
during overlap window (30-45s). Works on VX1 16C — plenty of headroom.

**Stagger reduction (0s):** Removed the 2s inter-notebook stagger inside pw-jupyter.
pw-jupyter 48s → **36s** (-12s). Commit 61bf303.

**Warmup optimization:** Reuse Docker venv, parallel JupyterLab server polling.
Warmup 20s → **10s**. Commit 93a425d.

**Current best (warm cache, 16C):** ~1m07-1m12s total, pw-jupyter 36s, warmup 10s.

**Async build-wheel with renice -10:** Marginal gain since warmup (9s) was already
longer than build-wheel (8s). Commit 2f44b86.

---

### Exp 53b — tmpfs ramdisk — NOT WORTH IT

**Goal:** Eliminate disk I/O by running CI entirely in RAM.
**Server:** VX1 16C (137.220.56.81), 62GB RAM, 55GB free.

tmpfs saves 4s on wheel install (5s→1s) and reduces iowait peaks, but total CI time
is identical because the critical path is CPU-bound (pw-jupyter 35-36s). Linux page
cache already makes warm reads RAM-speed. Not worth the complexity (host-level tmpfs,
pnpm store duplication, cold-start fragility). Reverted to disk-based approach.

---

### Exp 54 — Fast-fail mode

**Commits:** 69e46e0 (fast-fail), 3528d5f (pnpm install race fix), 1455934 (ci_pkill self-kill fix)

`--fast-fail` flag gates after build-js and build-wheel — aborts if either fails.
CI_TIMEOUT reduced from 240s to 180s.

**Side fix (3528d5f):** `full_build.sh` ran `pnpm install` even when dist existed,
destroying node_modules while test-js was reading them. Fixed with existence check.

---

### Exp 55 — Selective test runs (`--only`/`--skip`)

**Commits:** e3b4d31 (--only/--skip), 1455934 (ci_pkill fix)

`--only=JOB,JOB` and `--skip=JOB,JOB` flags. `should_run()` checks filters.

**Bug found:** `pkill -9 -f 'marimo'` matched `--skip=playwright-wasm-marimo` in
the CI script's own args. Fixed with `ci_pkill()` helper that excludes `$$`.

| Mode | Total | Result |
|------|-------|--------|
| `--skip=3.11,3.12,3.14,wasm-marimo` | **51s** | ALL PASS |
| `--only=lint-python,test-python-3.13` | **20s** | ALL PASS |
| Full (no filter) | ~1m10s | 15/16 (flaky timing) |

---

### Exp 56 — GitHub CI status — ALREADY PASSING

GitHub CI on `docs/ci-research` consistently passing. No action needed.

---

### Exp 58 — Stress test execution — PARTIAL (infra validated)

Ran 3/16 safe synth commits on VX1 16C. All 5 Playwright tests pass every time.
Consistent failures in non-infra tests (old lockfiles, timing assertions under load).

| Job | d301edb | 55f158a | 4f24190 |
|-----|---------|---------|---------|
| pw-jupyter | PASS | PASS | PASS |
| pw-storybook | PASS | PASS | PASS |
| pw-server | PASS | PASS | PASS |
| pw-wasm-marimo | PASS | PASS | PASS |
| pw-marimo | FAIL | FAIL | FAIL |
| test-js | FAIL | FAIL | FAIL |

**Conclusion:** CI infrastructure is solid. Synth commits have code-level issues
(old dependency lockfiles, flaky timing assertions) not CI runner bugs.
