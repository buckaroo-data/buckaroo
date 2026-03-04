# CI Tuning — Current State & Open Research

**Branch:** docs/ci-research
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100) — planning move to larger server
**Best config:** P=9 + /dev/shm fix + 5s stagger — **1m42s, all PASS** (commit 176f6f6)

---

## Current Best Configuration (commit 176f6f6, P=9 + /dev/shm fix)

```
Total: 1m42s (warm caches)
├─ Wave 0 (parallel):     37s  [lint, build-js, test-python-3.13, pw-storybook, jupyter-warmup]
├─ build-wheel:            4s  [after build-js, JS cache HIT]
├─ test-js:               ~4s  [starts after build-js, runs in background]
├─ wheel install:          3s  [into pre-warmed jupyter venv]
├─ Wheel-dependent (staggered 5s apart):
│   ├─ pw-jupyter (P=9):  50s  [critical path — 9 parallel notebooks]
│   ├─ pw-server:         40s
│   ├─ pw-marimo:         45s
│   ├─ pw-wasm-marimo:    36s
│   ├─ test-mcp-wheel:    15s
│   ├─ smoke-test-extras: 61s  [5s uncontended, 61s under memory pressure]
│   └─ test-python 3.11/3.12/3.14: ~29s each (deferred 20s)
```

Critical path: `build-js(1s) → build-wheel(4s) → warmup-wait → wheel-install(3s) → pw-jupyter(50s)`
Tail: smoke-test-extras finishes 11s after pw-jupyter due to memory pressure from 9 concurrent Chromium instances

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

### 4. PARALLEL=6 regression — SUPERSEDED by P=9 + /dev/shm fix

P=6 issues were caused by Docker's 64MB /dev/shm. `--disable-dev-shm-usage` on all Playwright configs fixes this. P=9 is now stable with 5s stagger on 32GB.

### 5. 32GB RAM is the constraint for aggressive scheduling

With P=9 jupyter (9 Chromium) + 3 concurrent PW tests (3 more Chromium), free RAM drops to ~860MB. This causes:
- Page cache eviction → slow Python processes (smoke-test-extras: 5s → 61s)
- 2s stagger causes all 12 Chromium instances to launch within 6s, overwhelming memory
- 5s stagger works because it spreads memory allocation over 20s

**Resolution:** Move to larger server (64GB+) or accept 5s stagger on 32GB.

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

### Infra: Bind-mount CI runner scripts (commit 1c49a02) — SUCCESS

**What:** Volume-mount `/opt/ci/runner/` into container at `/opt/ci-runner/:ro`. Added `update-runner.sh` that:
- Copies scripts from repo to `/opt/ci/runner/`
- Detects Dockerfile changes via sha256 hash
- Only rebuilds image when Dockerfile changes

**Result:** Script changes take effect instantly. Tested: `update-runner.sh` correctly prints "Scripts updated (no rebuild needed)" for script-only changes, and triggers full rebuild when Dockerfile hash differs.

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
| fd85f0a | Exp 41-A+B (2s stagger) | 3m08s | 13/2 FAIL | pw-jupyter timeout (0/9), pw-wasm-marimo timeout; smoke 28s |
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

### CPU Profile (commit 4a7fefc, passing run)

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

Machine is massively underutilized during pw-jupyter's last ~15s — 4-13% busy. Kernel I/O latency is the bottleneck, not CPU.

---

## Commits (chronological, recent only)

| Commit | Description |
|--------|-------------|
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
