# CI Tuning — Current State & Open Research

**Branch:** docs/ci-research
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Best config:** P=4 + tini + SKIP_INSTALL + renice — **~2m01s, 14/14 overall**

---

## Current Best Configuration (commit 4a7fefc)

```
Total: ~2m00s (warm caches) / ~2m21s (first run, lockfile rebuild)
├─ Wave 0 (parallel):     25s  [lint, build-js, test-python-3.13, pw-storybook, jupyter-warmup]
├─ build-wheel:            4s  [after build-js, JS cache HIT]
├─ test-js:               ~4s  [starts after build-js, runs in background]
├─ wheel install:          3s  [into pre-warmed jupyter venv]
├─ Wheel-dependent (staggered 5s apart):
│   ├─ pw-jupyter:        96s  [P=4 batched 4+4+1, critical path]
│   ├─ pw-server:         46s
│   ├─ pw-marimo:         50s
│   ├─ pw-wasm-marimo:    35s
│   ├─ test-mcp-wheel:    14s
│   ├─ smoke-test-extras:  8s  [parallel venv installs]
│   └─ test-python 3.11/3.12/3.14: ~30s each (deferred 20s)
```

Critical path: `build-js(1s) → build-wheel(4s) → warmup-wait → wheel-install(3s) → pw-jupyter(96s)`

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

---

## Open Issues

### 1. Back-to-back run degradation (LOW — workaround: restart container)

**Discovered in:** Exp 34+36, confirmed with tini
**Symptom:** Runs 1-2 after container restart pass. Run 3+ sometimes fails — pw-jupyter kernel connections hang.
**NOT zombies:** tini confirmed 0 zombies. Root cause unknown — something else accumulates across runs.
**Workaround:** Restart container between CI sessions. Single runs always pass.

### 2. pw-server flake — FIXED (Exp 34+36)

**Was:** 1/14 failure rate — `sort via header click` test used one-shot `getCellText()` which races with AG-Grid rendering.
**Fix:** `cellLocator()` + `toHaveText()` auto-retrying assertions in `server.spec.ts` and `server-helpers.ts`.
**Result:** 3/3 pw-server PASS after fix.

### 3. Lockfile hash persistence across container restarts — FIXED (commit 4a7fefc)

**Was:** Every container restart triggered "Lockfiles changed — rebuilding deps" because the hash store (`/var/ci/hashes/`) was inside the container.
**Fix:** Moved to `/opt/ci/logs/.lockcheck-hashes/` which is bind-mounted to the host. Hashes now persist across container restarts.

### 4. PARALLEL=6 regression

P=6 batched (6+3) worked at Exp 33 (076f40f, old image) but fails on current image (tini + SKIP_INSTALL + renice). Kernel connections on later ports (8892-8894) time out. P=4 is stable. Low priority since P=4 only adds ~30s vs P=6.

---

## Queued Experiments

### Exp 29 — Marimo auto-retry assertions (committed, untested on server)

**Status:** Code committed at d020744, not yet validated in CI
**What:** Replace one-shot `getCellText` with `cellLocator` + `toHaveText` in `marimo.spec.ts`. Retries 1→2.
**Verification:** 3+ CI runs, pw-marimo 100%.

### Exp 35 — Split test-js into build-js + test-js — IMPLEMENTED (commit 4a7fefc)

**What:** `build-wheel` now gates only on `build-js` (pnpm install + build). `test-js` (pnpm test) runs in background after build-wheel starts. Saves ~3s off critical path.
**Status:** Pending validation.

### Exp 26 — Wheel cache across SHAs

**Priority:** LOWEST — CI-dev-only edge case, not useful for real CI
**What:** Cache wheel keyed by Python+JS source hash. Skip build-wheel entirely on cache hit.
**Note:** Only helps when iterating on CI harness/Playwright test code without touching Python or JS source. Not relevant for normal development CI runs.

### Exp 25 — Synthetic merge commits for stress testing

**Priority:** LOW
**What:** Merge latest test code onto old SHAs for historical reliability testing.

---

## Operational Reference

### Trigger a CI run
```bash
ssh root@45.76.230.100
docker exec -d buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> <BRANCH>
tail -f /opt/ci/logs/<SHA>/ci.log
```

### Rebuild Docker image (after changing baked files)
```bash
ssh root@45.76.230.100
cd /opt/ci/repo && git fetch origin && git checkout <SHA>
docker build -t buckaroo-ci -f ci/hetzner/Dockerfile .
cd ci/hetzner && docker compose down && docker compose up -d
```

### Parse results from ci.log
Lines: `[HH:MM:SS] START/PASS/FAIL <job>`
Report: wallclock total, per-phase timing, pass/fail per job.

### Baked files
`run-ci.sh` and `test_playwright_jupyter_parallel.sh` are baked into the image at `/opt/ci-runner/`. Changes require image rebuild.

---

## Recent Run History

| SHA | Experiment | Total | Result | Notes |
|-----|-----------|-------|--------|-------|
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

### CPU Profile (Exp 34+36, commit 2ba10e7, passing run)

| Phase | ~Duration | CPU (us+sy) |
|-------|-----------|-------------|
| Wave 0 (lint, test-js, warmup) | 18s | 10→75% ramping |
| Peak (pytest-xdist + PW overlap) | 15s | 70-95% saturated |
| Wheel-dependent (PW concurrent) | 40s | 30-65% |
| pw-jupyter tail (kernel I/O) | 30s | **6-7% idle** |

Machine is massively underutilized during pw-jupyter's tail — bottleneck is kernel I/O latency, not CPU.

---

## Commits (chronological, recent only)

| Commit | Description |
|--------|-------------|
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
