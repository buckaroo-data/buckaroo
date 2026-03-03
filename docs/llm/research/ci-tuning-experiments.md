# CI Tuning — Current State & Open Research

**Branch:** docs/ci-research
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Best config:** Exp 33 (P=6 batched) — **1m44s, 9/9 jupyter, 13/14 overall**

---

## Current Best Configuration (Exp 33, commit 076f40f)

```
Total: ~1m44s
├─ Wave 0 (parallel):     25s  [lint, test-js, test-python-3.13, pw-storybook, jupyter-warmup]
├─ build-wheel:            3s  [after test-js, JS cache HIT]
├─ wheel install:          3s  [into pre-warmed jupyter venv]
├─ Wheel-dependent (staggered 5s apart):
│   ├─ pw-jupyter:        66s  [P=6 batched 6+3, critical path]
│   ├─ pw-server:         47s
│   ├─ pw-marimo:         50s
│   ├─ pw-wasm-marimo:    35s
│   ├─ test-mcp-wheel:    12s
│   ├─ smoke-test-extras:  8s  [parallel venv installs]
│   └─ test-python 3.11/3.12/3.14: ~30s each (deferred 20s)
```

Critical path: `test-js(7s) → build-wheel(3s) → warmup-wait → wheel-install(2s) → pw-jupyter(66s) = ~1m18s + overhead = ~1m44s`

### Key Techniques (all proven)

| Technique | Exp | Impact |
|-----------|-----|--------|
| `window.jupyterapp` kernel check | 21 | pw-jupyter 80% → **100%** pass rate |
| WebSocket kernel warmup in Wave 0 | 28 | -24s off pw-jupyter |
| No heavyweight PW gate | 30 | -42s off total (1m43s vs 2m25s) |
| PARALLEL=6 batched (6+3) | 33 | 66s pw-jupyter (vs 75s at P=4) |
| JS build cache (tree-hash keyed) | 23 | -16s off critical path |
| `full_build.sh` skip check fix | 24 | build-wheel 17s → 3s |
| `expect().toPass()` polling | 15 | pw-server 50s → 37s |
| Parallel smoke-test-extras | 18 | 20s → 8s |
| pytest-xdist `-n 4` | 12 | ~63s → ~30s per Python version |
| Staggered sub-waves (5s) | 33 | Reduces CPU burst at wheel-dependent launch |
| Between-batch kernel re-warmup | 33 | Fixes batch-2 hang |
| Pre-run cleanup (pkill, rm temps) | 33 | Clean state between CI runs |
| 120s pw-jupyter timeout + 210s watchdog | 33 | Prevents runaway CI |

### What Doesn't Work

| Approach | Exp | Why |
|----------|-----|-----|
| PARALLEL=3 | 14c | More batches = more overhead, worse than P=4 |
| PARALLEL=9 | 11, 31, 33 | CPU starvation (27+ processes on 16 vCPU) |
| DOM kernel idle check | 14d | Burns timeout when DOM not rendered |
| REST kernel polling | 10 | Never updates without WebSocket |
| Lean Wave 0 (shift work to later) | 32 | Just moves contention, +8s total |
| `nice` on shell functions | 34+36 | `nice` is external cmd, can't run bash functions |

---

## Open Issues

### 1. Zombie process accumulation (BLOCKING for back-to-back runs)

**Discovered in:** Exp 34+36
**Symptom:** First CI run after container restart passes. Subsequent runs: pw-jupyter times out (0/6 notebooks complete).
**Root cause:** Docker PID 1 (`sleep infinity`) doesn't reap zombies. After each CI run, ~100+ defunct `jupyter-lab` and `python` processes accumulate. By run 2-3, 326+ zombies exist.
**Ports are free** — zombies don't hold sockets. Warmup succeeds (all kernels reach idle). Notebooks start but never complete.

**Fix options:**
1. **Add `tini` as PID 1** in Dockerfile (`ENTRYPOINT ["/usr/bin/tini", "--"]`) — reaps zombies automatically
2. **Add `init: true`** in docker-compose.yml — same effect, uses Docker's built-in tini
3. Investigate if the real issue is stale JupyterLab workspace state, not zombies

### 2. pw-server flake — FIXED (Exp 34+36)

**Was:** 1/14 failure rate — `sort via header click` test used one-shot `getCellText()` which races with AG-Grid rendering.
**Fix:** `cellLocator()` + `toHaveText()` auto-retrying assertions in `server.spec.ts` and `server-helpers.ts`.
**Result:** 3/3 pw-server PASS after fix.

### 3. Lockfile hash persistence across container restarts

Every container restart triggers "Lockfiles changed — rebuilding deps" because the hash store (`/var/ci/hashes/`) is inside the container. Should be a named volume or stored on the host bind mount.

---

## Queued Experiments

### Exp 37 — tini as PID 1 (zombie fix)

**Priority:** HIGH — blocks reliable back-to-back runs
**Files:** `ci/hetzner/Dockerfile`, `ci/hetzner/docker-compose.yml`
**What:** Add `init: true` to docker-compose.yml (or `ENTRYPOINT ["/usr/bin/tini", "--"]` in Dockerfile). This makes Docker use tini as PID 1, which reaps zombie processes automatically.
**Verification:** 3+ back-to-back CI runs, all pass. Zero zombies between runs.

### Exp 29 — Marimo auto-retry assertions (committed, untested on server)

**Status:** Code committed at d020744, not yet validated in CI
**What:** Replace one-shot `getCellText` with `cellLocator` + `toHaveText` in `marimo.spec.ts`. Retries 1→2.
**Verification:** 3+ CI runs, pw-marimo 100%.

### Exp 36 — renice CPU priority (partially working)

**Status:** Implemented (renice after fork), but untested with clean back-to-back runs due to zombie issue.
**What:** `renice -n -10` for critical-path (test-js), `renice -n 10` for background. jupyter-warmup left at default (servers persist).
**Blocked by:** Exp 37 (zombie fix) — can't get clean back-to-back data.

### Exp 34 — SKIP_INSTALL (working)

**Status:** Implemented and working in single runs.
**What:** `SKIP_INSTALL=1` env var skips `pnpm install` + `playwright install chromium` in PW scripts. Set in CI wrappers.
**Blocked by:** Exp 37 — need clean multi-run data.

### Exp 35 — Split test-js into build-js + test-js

**Priority:** LOW — saves ~2-3s off critical path
**What:** `build-wheel` waits for all of `test-js` (build + test). Split so build-wheel gates only on the build step.

### Exp 26 — Wheel cache across SHAs

**Priority:** LOW — saves ~3s (build-wheel is already 3s)
**What:** Cache wheel keyed by Python+JS source hash. Skip build-wheel entirely on cache hit.

### Exp 25 — Synthetic merge commits for stress testing

**Priority:** LOW
**What:** Merge latest test code onto old SHAs for historical reliability testing.

### PARALLEL=9 (tabled)

**Status:** Conclusively failed at current hardware (16 vCPU), but not permanently dead.
**Ideas for future retry:**
- `renice` the kernel or server processes so they get more CPU
- Single shared JupyterLab server instead of one-per-slot
- Stagger only the last 3-4 starts by 5-10s
- Profile which process uses the most CPU
- Reduced reproduction on the same server

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
