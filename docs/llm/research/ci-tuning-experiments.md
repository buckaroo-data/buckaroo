# CI Tuning — Current State & Open Research

**Branch:** docs/ci-research
**Server:** Vultr 32 vCPU / 64 GB (45.76.18.207) — voc-c-32c-64gb-500s-amd
**Best config:** P=9 + /dev/shm fix + 2s stagger — **1m42s, all PASS** (commit 09c6faa)

---

## Current Best Configuration (commit 09c6faa, P=9, 2s stagger, 64GB)

```
Total: 1m42s (warm caches, 32 vCPU / 64 GB)
├─ Wave 0 (parallel):     44s  [lint, build-js, test-python-3.13, pw-storybook, jupyter-warmup]
├─ build-wheel:            3s  [after build-js, JS cache HIT]
├─ test-js:               ~5s  [starts after build-js, runs in background]
├─ wheel install:          3s  [into pre-warmed jupyter venv]
├─ Wheel-dependent (staggered 2s apart):
│   ├─ pw-jupyter (P=9):  52s  [critical path — 9 parallel notebooks]
│   ├─ pw-server:         44s
│   ├─ pw-marimo:         53s
│   ├─ pw-wasm-marimo:    39s
│   ├─ test-mcp-wheel:    14s
│   ├─ smoke-test-extras:  6s  [no memory pressure on 64GB]
│   └─ test-python 3.11/3.12/3.14: ~24s each (deferred 8s)
```

Critical path: `build-js(2s) → build-wheel(3s) → warmup-wait → wheel-install(3s) → pw-jupyter(52s)`

### Key Techniques (all proven)

| Technique | Exp | Impact |
|-----------|-----|--------|
| `window.jupyterapp` kernel check | 21 | pw-jupyter 80% → **100%** pass rate |
| WebSocket kernel warmup in Wave 0 | 28 | -24s off pw-jupyter |
| No heavyweight PW gate | 30 | -42s off total (1m43s vs 2m25s) |
| tini ENTRYPOINT in Dockerfile | 37 | Zero zombies (was 100+ per run) |
| JS build cache (tree-hash keyed) | 23 | -16s off critical path |
| `full_build.sh` skip check fix | 24 | build-wheel 17s → 3s |
| `expect().toPass()` polling | 15 | pw-server 50s → 37s |
| `cellLocator()` + `toHaveText()` | 34+36 | pw-server flake fixed (3/3 PASS) |
| SKIP_INSTALL in PW scripts | 34 | Skips redundant pnpm/playwright install in CI |
| `renice` after fork | 36 | -10 for critical-path, +10 for background |
| Parallel smoke-test-extras | 18 | 20s → 8s |
| pytest-xdist `-n 4` | 12 | ~63s → ~30s per Python version |
| Staggered sub-waves (5s) | 33 | Reduces CPU burst at wheel-dependent launch |
| Between-batch kernel re-warmup | 33 | Fixes batch-2 hang |
| Pre-run cleanup (pkill, rm temps) | 33 | Clean state between CI runs |
| Workspace cleanup in pre-run | 38 | Prevents stale kernel reconnection |
| Split build-js / test-js | 35 | ~3s off critical path (test runs in background) |
| Lockfile hash on bind mount | 39 | No dep rebuild on container restart |
| 120s pw-jupyter timeout + 210s watchdog | 33 | Prevents runaway CI |
| `--disable-dev-shm-usage` on all PW configs | 40 | P=9 stable (Docker 64MB /dev/shm was root cause) |
| P=9 parallel jupyter (settle=0) | 40 | 50s pw-jupyter (down from 96s at P=4) |
| Bind-mount CI runner scripts | 41 | No rebuild needed for script changes |
| 2s stagger (on 64GB) | 42 | 5s→2s, saves ~6s off total vs 5s stagger |
| Port cleanup 8889-8897 | 42 | Fix: was only cleaning 8889-8894 (6 of 9) |
| esbuild + pw-results cleanup | 42 | Prevents ~400MB leak + /tmp accumulation |
| CI watchdog 360s | 42 | Handles cold-start (uv cache miss = +2min) |

### What Doesn't Work

| Approach | Exp | Why |
|----------|-----|-----|
| PARALLEL=3 | 14c | More batches = more overhead, worse than P=4 |
| PARALLEL=6 | 33, 38 | Worked on old image, fails on current (3-6/6 kernel timeouts) |
| PARALLEL=9 | 11, 31, 33 | CPU starvation (27+ processes on 16 vCPU) |
| DOM kernel idle check | 14d | Burns timeout when DOM not rendered |
| REST kernel polling | 10 | Never updates without WebSocket |
| Lean Wave 0 (shift work to later) | 32 | Just moves contention, +8s total |
| `nice` on shell functions | 34+36 | `nice` is external cmd, can't run bash functions |
| `init: true` in docker-compose | 37 | Tini wraps at host level; docker exec'd processes still parent to `sleep` PID 1 |
| 2s stagger (on 32GB) | 41-B | Too aggressive — 12 Chromium instances in 6s exhausts RAM, pw-jupyter hangs |
| 0s stagger (on 64GB) | 42 | All jobs simultaneous → 8/9 pw-jupyter notebooks hang. Kernel provisioner or ZMQ contention |

---

## Open Issues

### 1. Back-to-back run degradation — LARGELY FIXED

**Discovered in:** Exp 34+36, confirmed with tini
**Root causes found:**
- Docker 64MB `/dev/shm` exhaustion (fixed with `--disable-dev-shm-usage`)
- Stale storybook/esbuild processes leaking ~400MB between runs (fixed: `pkill esbuild` in pre-run cleanup)
- Stale JupyterLab on ports 8895-8897 not cleaned (fixed: port range 8889-8897)
- `/tmp/pw-results-*` accumulating across runs (fixed: cleanup added)
**Status:** b2b run 1→2 passes on 64GB with all fixes. Needs more testing for run 3+.

### 2. pw-server flake — FIXED (Exp 34+36)

**Was:** 1/14 failure rate — `sort via header click` test used one-shot `getCellText()` which races with AG-Grid rendering.
**Fix:** `cellLocator()` + `toHaveText()` auto-retrying assertions in `server.spec.ts` and `server-helpers.ts`.
**Result:** 3/3 pw-server PASS after fix.

### 3. Lockfile hash persistence across container restarts — FIXED (commit 4a7fefc)

**Was:** Every container restart triggered "Lockfiles changed — rebuilding deps" because the hash store (`/var/ci/hashes/`) was inside the container.
**Fix:** Moved to `/opt/ci/logs/.lockcheck-hashes/` which is bind-mounted to the host. Hashes now persist across container restarts.

### 4. PARALLEL=6 regression — SUPERSEDED by P=9 + /dev/shm fix

P=6 issues were caused by Docker's 64MB /dev/shm. `--disable-dev-shm-usage` on all Playwright configs fixes this. P=9 is now stable with 5s stagger on 32GB.

### 5. 32GB RAM constraint — RESOLVED (moved to 64GB)

Moved from Vultr 16 vCPU / 32GB (45.76.230.100, destroyed) to 32 vCPU / 64GB (45.76.18.207).
On 64GB: smoke-test-extras runs in 6s (was 61s on 32GB). 2s stagger works. 0s stagger does NOT work (kernel contention, not RAM).

### 6. Container detritus between runs

After each CI run, these processes/files leak and must be cleaned by the next run's pre-run cleanup:
- **Storybook node process** (~400MB RSS) — stays running after playwright-storybook completes
- **3 esbuild processes** (~100MB total) — child processes of storybook/build
- **Watchdog sleep** — `sleep 360` from CI timeout, harmless
- **/tmp/pw-results-*** — Playwright test result dirs, ~15MB per run
- **/tmp/pw-html-*** — Playwright HTML report dirs
- **~/.jupyter/lab/workspaces/** — JupyterLab workspace files
- **~/.local/share/jupyter/runtime/jupyter_cookie_secret** — harmless, persists

The pre-run cleanup in run-ci.sh handles all of these. Verified: after cleanup runs, old storybook/esbuild PIDs are gone, /tmp dirs are removed, ports are freed.

---

## Recent Experiments (Exp 40-41)

### Exp 40 — /dev/shm fix + P=9 (commits e6ea620, 176f6f6) — SUCCESS

**What:** Add `--disable-dev-shm-usage` to all Playwright configs (storybook, server, marimo, wasm-marimo, jupyter). Docker default /dev/shm is 64MB which causes Chromium crashes at P=5+.
**Result:** P=9 stable, settle=0 works, all jobs PASS. Total 1m42s — best ever.
**Key insight:** Back-to-back degradation was also caused by /dev/shm exhaustion, not zombie accumulation.

### Exp 41-A — Defer smoke-test-extras (commit fd85f0a) — WORKS (needs larger server)

**What:** Launch smoke-test-extras after `wait $PID_PW_JP` instead of at t+0. Event-driven, not sleep-based.
**Result on 32GB:** smoke-test-extras 28s (down from 61s). Still not the ideal 5s because pw-wasm-marimo was still running, keeping memory pressure elevated.
**Expected on 64GB+:** should hit the 5s uncontended target.

### Exp 41-B — Tighten stagger 5s→2s (commit fd85f0a) — FAILED on 32GB

**What:** Reduce gaps between pw-marimo/wasm/server from 5s to 2s.
**Result:** pw-jupyter hangs consistently (0/9 or 1/9 notebooks complete in 120s timeout). All 12 Chromium instances launching within 6s overwhelms 32GB RAM.
**Conclusion:** 5s stagger is necessary on 32GB. Re-test on larger server.

### Exp 41-C — MCP timing instrumentation (commit fd85f0a) — IN PLACE

**What:** Added `[mcp-timing]` lines to `job_test_mcp_wheel` — times venv creation, wheel install, each pytest run.
**Note:** Uses `awk` not `bc` (bc not installed in container).
**Result (from fd85f0a run):** test-mcp-wheel total 11s. Detailed breakdown needs green run to read.

### Exp 41-D — pw-server timing instrumentation (commit fd85f0a) — IN PLACE

**What:** Added `--reporter=list` to pw-server in CI for per-test timing. Plus `[pw-server-timing]` total elapsed.
**Result (from fd85f0a run):** pw-server total 41s. Per-test breakdown in pw-server.log.

### Exp 42 — Server upgrade + stagger tuning (commits 6c8590d, 7626c67, 09c6faa) — SUCCESS

**What:** Moved to 32 vCPU / 64GB server. Tested stagger values:
- **0s stagger:** FAILS — 8/9 pw-jupyter notebooks hang at "Shift+Enter attempt 7". Port 8889 works, 8890-8897 don't. Reproducible on both 176f6f6 and 37aed6b. Root cause: kernel provisioner or ZMQ contention when 12 Chromium + 9 JupyterLab kernel starts all race simultaneously. NOT a RAM issue (64GB plenty, free stays >40GB).
- **2s stagger:** WORKS — all pass consistently. 1m42-1m49s total.
- **5s stagger:** WORKS — baseline from 176f6f6, 1m42s on old 32GB server.

**Also fixed:**
- Port cleanup range: was 8889-8894 (6 ports), now 8889-8897 (9 ports for P=9)
- esbuild cleanup: `pkill -9 -f esbuild` added to pre-run cleanup
- /tmp/pw-results-* cleanup: added to pre-run rm
- CI watchdog: 210s → 360s (cold-start on fresh image needs ~3.5min for uv cache miss)

**Key insight:** The 0s stagger failure was initially misattributed to SHA-specific differences (37aed6b vs 176f6f6). In reality, both SHAs fail with 0s stagger when using the bind-mounted runner. The earlier apparent SHA-specificity was because the bind-mounted runner was updated between test runs.

### Infra: Bind-mount CI runner scripts (commit 1c49a02) — SUCCESS

**What:** Volume-mount `/opt/ci/runner/` into container at `/opt/ci-runner/:ro`. Added `update-runner.sh` that:
- Copies scripts from repo to `/opt/ci/runner/`
- Detects Dockerfile changes via sha256 hash
- Only rebuilds image when Dockerfile changes

**Result:** Script changes take effect instantly. Tested: `update-runner.sh` correctly prints "Scripts updated (no rebuild needed)" for script-only changes, and triggers full rebuild when Dockerfile hash differs.

---

## Queued Experiments

### Exp 29 — Marimo auto-retry assertions — VALIDATED

**Status:** Validated in CI — pw-marimo passes consistently on 64GB server.

### Exp 43 — New box deployment checklist

**Priority:** HIGH — needed before spinning up another server
**What:** Codify the full deployment procedure:
1. Provision server (cloud-init or manual)
2. Clone repo, build Docker image
3. Set up bind mounts (`/opt/ci/runner/`, `/opt/ci/logs/`, `/opt/ci/js-cache/`)
4. `docker compose up -d`
5. Run CI with known-good SHA — must ALL PASS
6. Run CI again (b2b) — must ALL PASS
7. Check detritus between runs
**Status:** Procedure documented informally; needs a script or checklist.

### Exp 44 — Post-run cleanup (kill storybook/esbuild at end of CI)

**Priority:** LOW — pre-run cleanup handles it, but cleaner to not leak
**What:** After all jobs complete and results are reported, kill storybook and esbuild processes. Currently they leak ~400MB until the next run's pre-run cleanup kills them.
**Risk:** Low — these processes are only needed during playwright-storybook job.

### Exp 26 — Wheel cache across SHAs

**Priority:** LOWEST — CI-dev-only edge case, not useful for real CI
**What:** Cache wheel keyed by Python+JS source hash. Skip build-wheel entirely on cache hit.

---

## Operational Reference

### Trigger a CI run
```bash
ssh root@45.76.18.207
docker exec -d buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> <BRANCH>
tail -f /opt/ci/logs/<SHA>/ci.log
```

### Update CI scripts (no rebuild needed)
```bash
ssh root@<server-ip>
cd /opt/ci/repo && git fetch origin
git checkout origin/<branch> -- ci/hetzner/ scripts/
bash ci/hetzner/update-runner.sh
```
The `update-runner.sh` script:
- Copies scripts to `/opt/ci/runner/` (bind-mounted into container)
- Detects Dockerfile changes via sha256 hash — only rebuilds when needed
- Script changes take effect instantly, no container restart required

### Manual rebuild (only for Dockerfile changes)
```bash
ssh root@<server-ip>
cd /opt/ci/repo && git fetch origin && git checkout <SHA>
docker build -t buckaroo-ci -f ci/hetzner/Dockerfile .
cd ci/hetzner && docker compose down && docker compose up -d
```

### Parse results from ci.log
Lines: `[HH:MM:SS] START/PASS/FAIL <job>`
Report: wallclock total, per-phase timing, pass/fail per job.

---

## Recent Run History

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
| d369894 | Exp 30 (no PW gate) | 1m25s | 14/0 PASS | Best ever total |
| 076f40f | Exp 33 (P=6 batched) | 1m44s | 14/1 | Best config on old image |
| 2ba10e7 | Exp 34+36 (fixed) | 2m38s | 14/1 | First run post-restart |
| 20fb931 | Exp 37 (`init: true`) | 2m59s | pw-jupyter FAIL | 101 zombies |

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

Note: This profile is from the old 16 vCPU server. On the new 32 vCPU server, CPU is no longer a constraint — the bottleneck is kernel I/O latency and (with 0s stagger) ZMQ/kernel provisioner contention.

---

## Commits (chronological, recent only)

| Commit | Description |
|--------|-------------|
| 09c6faa | Exp 42: bump watchdog 210→360s for cold starts |
| 7626c67 | Exp 42: cleanup esbuild, pw-results, port range 8889-8897 |
| 6c8590d | Exp 42: restore 2s stagger (0s stagger proven broken) |
| 37aed6b | Remove all stagger (BROKEN — do not use) |
| c26897f | Fix: clean all 9 jupyter ports (8889-8897) |
| 676161f | Docs update |
| fd85f0a | Exp 41: fix awk timing (bc not in container) |
| 1c49a02 | Bind-mount CI scripts + update-runner.sh |
| 29b19fa | Exp 41: delay smoke-test, tighten stagger 5→2s, MCP/server timing |
| 176f6f6 | Integrate /dev/shm fix — P=9, settle=0, --disable-dev-shm-usage |
| e6ea620 | Add --disable-dev-shm-usage for Docker P=5+ |
| 5994612 | jupyterapp kernel check + waitForTimeout removal |
| 200bac6 | JS build cache + ci-queue |
| 5c1e58f | Fix full_build.sh index.es.js check |
| 60618ce | Exp 18+19+20: parallel smoke, relaxed gate → **2m31s** |
| 172158b | Exp 28: early kernel warmup → **2m25s** |
| d369894 | Exp 30: remove heavyweight PW gate → **1m43s** |
| d020744 | Exp 29: marimo auto-retry assertions |
| b2398d5 | Exp 31+32: P=9 abandoned, lean Wave 0 → **1m51s** |
| 076f40f | Exp 33: P=6 batched + re-warmup → **1m44s** |
| 9dcc5e0 | Pre-run cleanup |
| 630cf60 | Exp 34+36: SKIP_INSTALL, renice, pw-server auto-retry |
| da3a7ad | Fix: renice instead of nice for shell functions |
| 2ba10e7 | Fix: don't renice jupyter-warmup, SKIP_INSTALL in pw-jupyter |
| 20fb931 | Exp 37: `init: true` in docker-compose (failed) |
| 46c165c | Exp 37: tini ENTRYPOINT in Dockerfile (**working** — 0 zombies) |
| ef53834 | Revert P=6→6, timeout→120, watchdog→210 (P=6 still broken) |
| fff99fa | Revert P=6→4 (stable baseline) |
| c5a0498 | Research docs committed |
| 4a7fefc | Exp 35: split build-js/test-js + lockfile hash persistence fix |
