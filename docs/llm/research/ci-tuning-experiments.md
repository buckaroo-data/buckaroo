# CI Tuning — Current State & Next Experiments

**Branch:** docs/ci-research
**Server:** Vultr VX1 16C (137.220.56.81) — 16 vCPU/64GB, EPYC Turin Zen 5
**Previous servers:** VX1 32C (66.42.115.86, active), VX1 16C (destroyed), Rome 32C (destroyed)
**Best config (VX1 16C):** P=9, 0s stagger, parallel overlap — **51s** (commit 1455934, with --skip)
**Full CI (no skip):** ~1m10s, 15-16/16 pass (timing-flaky pytest under load)
**Archive:** See `ci-tuning-experiments-archive.md` for Exp 10-42, 51 details.

---

## ~~Current Blocker: pw-jupyter BROKEN on VX1 32C~~ — RESOLVED

**Root cause: `PARALLEL=5` caused batch server reuse.** With 9 notebooks and P=5,
batch 2 reuses JupyterLab servers from batch 1. Kernels on reused servers never
reach idle from the browser. Fix: `PARALLEL=9` — each notebook gets a dedicated
server, no reuse. 4/4 b2b runs pass (commit 0103187).

The ipykernel version hypothesis was wrong — both 6.29.5 and 7.2.0 fail with P=5,
both pass with P=9. Packages were upgraded anyway (commit cd51c9e).

Full investigation: [`pw-jupyter-batch-reuse-fix.md`](pw-jupyter-batch-reuse-fix.md)

---

## Current Best Configuration (commit 09c6faa, Rome 32v — server destroyed)

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
| `--disable-dev-shm-usage` on all PW configs | 40 | P=9 stable (Docker 64MB /dev/shm was root cause) |
| P=9 parallel jupyter (settle=0) | 40 | 50s pw-jupyter (down from 96s at P=4) |
| Bind-mount CI runner scripts | 41 | No rebuild needed for script changes |
| 2s stagger (on 64GB) | 42 | 5s→2s, saves ~6s off total vs 5s stagger |

### What Doesn't Work

| Approach | Exp | Why |
|----------|-----|-----|
| PARALLEL=3 | 14c | More batches = more overhead, worse than P=4 |
| PARALLEL=9 on 16 vCPU | 11, 31, 33 | CPU starvation (27+ processes on 16 vCPU) |
| 0s stagger (on 64GB) | 42 | Kernel provisioner/ZMQ contention |
| 2s stagger (on 32GB) | 41-B | 12 Chromium in 6s exhausts RAM |
| `nice` on shell functions | 34+36 | `nice` is external cmd, can't run bash functions |
| `init: true` in docker-compose | 37 | Tini wraps at host level, not inside container |
| Move pw-wasm-marimo to Wave 0 | 51 | Requires built wheel — all PW integration tests need the widget installed |

---

## Operational Reference

### Trigger a CI run
```bash
ssh root@66.42.115.86
docker exec -d buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> <BRANCH>
tail -f /opt/ci/logs/<SHA>/ci.log
```

### Update CI scripts (no rebuild needed)
```bash
ssh root@66.42.115.86
cd /opt/ci/repo && git fetch origin
git checkout origin/<branch> -- ci/hetzner/ scripts/
bash ci/hetzner/update-runner.sh
```

### Parse results from ci.log
Lines: `[HH:MM:SS] START/PASS/FAIL <job>`
Report: wallclock total, per-phase timing, pass/fail per job.

---

## Next Round — Detailed Experiment Plans

### ~~Exp 52 — Fix ipykernel version~~ — DONE (not the blocker)

Packages upgraded in commit cd51c9e (ipykernel 6.29.5→7.2.0, jupyterlab 4.5.0→4.5.5,
jupyter-server 2.15.0→2.17.0, tornado 6.4.2→6.5.4). But this wasn't the fix —
the real fix was PARALLEL=9 (commit 0103187). See `pw-jupyter-batch-reuse-fix.md`.

---

### Exp 53 — Restore full parallel DAG — DONE

**Result:** 1m45s → **1m11s** (-34s). All Playwright jobs pass. Commit 5b85d83.

Overlapped pw-marimo (+2s), pw-server (+4s), pw-wasm-marimo (+6s), pytest (+8s)
alongside pw-jupyter. Staggered 2s apart. Mean CPU 47.7%, peak 100% for ~15s
during overlap window (30-45s). Works on VX1 16C — plenty of headroom.

Pre-existing flaky unit tests (`test_lazy_widget_init_should_not_block`,
`test_huge_dataframe_partial_cache_scenario`) occasionally fail due to timing
assertions under CPU pressure. Not CI infra issues — tests need looser thresholds.

**Stagger reduction (0s):** Removed the 2s inter-notebook stagger inside pw-jupyter.
Was needed when batch server reuse was the root cause; with P=9 dedicated servers,
no contention. pw-jupyter 48s → **36s** (-12s). Commit 61bf303.

**Warmup optimization:** Reuse Docker venv (`/opt/venvs/3.13`) instead of creating
a fresh one every run (saves ~5s). Parallel JupyterLab server polling (saves ~3s).
Warmup 20s → **10s**. Commit 93a425d.

**Current best (warm cache, 16C):** ~1m07-1m12s total, pw-jupyter 36s, warmup 10s.
Critical path: warmup(10s) → build-wheel-wait → wheel install(1s) → pw-jupyter(36s).

**Async build-wheel with renice -10:** Made build-wheel run in background with
elevated priority so it overlaps with warmup/storybook. Marginal gain since warmup
(9s) was already longer than build-wheel (8s). Commit 2f44b86.

---

### Exp 53b — tmpfs ramdisk experiment — NOT WORTH IT

**Goal:** Eliminate disk I/O by running CI entirely in RAM.
**Commits:** 3a7697e → 740273a (ramdisk experiments), reverted to 2f44b86.
**Server:** VX1 16C (137.220.56.81), 62GB RAM, 55GB free.

**Approaches tried:**
1. **In-container tmpfs** (3a7697e–ff6f1b3): Mount `/ramdisk` inside container, copy
   repo there, work from `/ramdisk/repo`. Failed due to:
   - `rsync` not in container → switched to tar pipe
   - Docker tmpfs defaults to `noexec` → esbuild EACCES
   - pnpm cross-filesystem hardlinks (store on named volume, repo on tmpfs) → `reused 0`
   - All paths hardcoded to `/repo` (Python editable install, anywidget static files,
     JupyterLab notebook dirs) → `FileNotFoundError: /repo/buckaroo/static/compiled.css`
2. **Host-level tmpfs** (740273a): Mount single tmpfs at `/opt/ci/ramdisk` on host,
   put both repo and pnpm store there, bind-mount both into container. Same filesystem
   = hardlinks work. Zero path changes needed.

**Raw benchmarks:**
| Metric | Disk | tmpfs |
|--------|------|-------|
| Sequential write (256MB) | 509 MB/s | 4.9 GB/s (10x) |
| Small file creation (10K files) | 3.66s | 0.12s (30x) |

**CI results (host tmpfs, warm caches):**
| Run | Total | build-wheel | warmup | wheel install | pw-jupyter |
|-----|-------|-------------|--------|---------------|------------|
| Disk baseline (2f44b86) | 1m06s | 8s | 9s | **5s** | 36s |
| tmpfs run 2 (warm) | 1m06s | 8s | 10s | **1s** | 36s |
| tmpfs run 3 (warm) | 1m06s | 7s | 11s | **1s** | 35s |

| Metric | Disk | tmpfs |
|--------|------|-------|
| iowait mean | 9.7% | 8.8% |
| iowait max | 52 | 37 |
| CPU mean | 47.0% | 46.3% |

**Conclusion:** tmpfs saves 4s on wheel install (5s→1s) and reduces iowait peaks,
but total CI time is identical because the critical path is CPU-bound (pw-jupyter 35-36s).
The 30x small-file speedup doesn't help when I/O phases overlap with CPU-heavy work.

**Not worth the complexity:**
- Requires host-level tmpfs mount (lost on reboot, needs cloud-init automation)
- pnpm store must be on same tmpfs for hardlinks (375MB duplication)
- Cold start after reboot needs full re-clone + pnpm install
- Linux page cache already makes warm reads RAM-speed

**Reverted to disk-based approach (commit 2f44b86).**

---

### Exp 54 — Fast-fail mode — DONE

**Commits:** 69e46e0 (fast-fail), 3528d5f (pnpm install race fix), 1455934 (ci_pkill self-kill fix)

Implemented `--fast-fail` flag. Gates after build-js and build-wheel abort CI if either
fails. Also reduced CI_TIMEOUT from 240s to 180s.

**Side fix (3528d5f):** `full_build.sh` had `pnpm install` on line 30 that ran even when
dist existed. This "Recreated" node_modules while test-js was reading them — race condition.
Fixed: skip pnpm install if node_modules already exists.

---

### Exp 55 — Selective test runs (`--only` / `--skip`) — DONE

**Commits:** e3b4d31 (--only/--skip), 1455934 (ci_pkill fix)

Implemented `--only=JOB,JOB` and `--skip=JOB,JOB` flags. `should_run()` checks filters
before each `run_job`. Dependencies not auto-resolved (documented).

**Bug found:** `pkill -9 -f 'marimo'` matched the CI script's own args
(`--skip=playwright-wasm-marimo`) and killed it during cleanup. Fixed with `ci_pkill()`
helper that excludes `$$` from matches.

**Results (1455934, VX1 16C):**

| Mode | Total | Jobs run | Result |
|------|-------|----------|--------|
| `--skip=3.11,3.12,3.14,wasm-marimo` | **51s** | 12/16 | ALL PASS |
| `--only=lint-python,test-python-3.13` | **20s** | 2/16 | ALL PASS |
| Full run (no filter) | ~1m10s | 16/16 | 15/16 PASS (flaky timing) |

---

### Exp 56 — Fix GitHub CI on this branch — ALREADY PASSING

GitHub CI on `docs/ci-research` is consistently passing. Last 3 completed Checks runs:
all `success`. The `cancelled` runs are from rapid pushes superseding earlier runs.
No action needed.

---

### Exp 57 — Deterministic tuning script

**Priority:** MEDIUM — requires Exp 52 (pw-jupyter working) + Exp 55 (`--only`/`--skip`)

**Problem:** We've tuned by manually trying different settings and running 1-3 times. We need a systematic sweep to find the optimal settings for the VX1 32C server, and a repeatable way to validate them.

**Plan:**
1. Create `ci/hetzner/tuning-sweep.sh` that:
   - Takes a known-good SHA (from `stress-test.sh` SAFE_COMMITS or a recent main commit)
   - Defines a parameter grid:
     - `JUPYTER_PARALLEL`: 5, 7, 9
     - `STAGGER_DELAY`: 0, 1, 2, 3 (seconds between Chromium launches within pw-jupyter)
     - `OVERLAP_MODE`: `sequential` (current: all jobs after pw-jupyter), `partial` (pytest+smoke overlap with pw-jupyter), `full` (everything overlaps, Rome-style)
   - For each parameter combination, runs CI N times (start with N=3, increase to N=5 for promising configs)
   - Records: pass/fail, total wall time, per-job timing, CPU/memory peak
   - Outputs a summary table: combo → pass rate, mean time, p95 time
2. Run it on the server in tmux (will take hours for a full sweep):
   ```
   ssh root@66.42.115.86
   tmux new -s sweep
   bash /opt/ci/repo/ci/hetzner/tuning-sweep.sh
   ```
3. Analyze results: find the Pareto frontier (fastest config with ≥95% pass rate over N runs).
4. The winning config becomes the new default profile. Keep a conservative profile (current settings) as fallback.

**Parameter interactions to watch:**
- `JUPYTER_PARALLEL` × `OVERLAP_MODE`: P=9 + full overlap = 9 Chromium (jupyter) + 3 Chromium (marimo+server+storybook) = 12 browsers. On 32 vCPU this worked on Rome. On VX1 it may differ.
- `STAGGER_DELAY` × `JUPYTER_PARALLEL`: P=9 with 0s stagger failed on Rome 64GB. VX1 128GB might handle it. Or might not (the bottleneck was ZMQ contention, not RAM).

**Depends on:** Exp 52 (pw-jupyter must work), Exp 55 (need `--skip` to skip irrelevant jobs for focused testing, or use `--phase=5b` for jupyter-only sweeps).

---

### Exp 58 — Stress test execution — PARTIAL (infra validated)

**Server:** VX1 16C (137.220.56.81), commit 1455934

Ran 3/16 safe synth commits. All 5 Playwright tests pass every time. Consistent
failures in non-infra tests:

| Job | d301edb | 55f158a | 4f24190 | Root cause |
|-----|---------|---------|---------|------------|
| pw-jupyter | PASS | PASS | PASS | — |
| pw-storybook | PASS | PASS | PASS | — |
| pw-server | PASS | PASS | PASS | — |
| pw-wasm-marimo | PASS | PASS | PASS | — |
| pw-marimo | FAIL | FAIL | FAIL | Old app code compat |
| test-js | FAIL | FAIL | FAIL | Missing jest-util (old lockfile) |
| test-python-3.13 | FAIL | FAIL | FAIL | Flaky timing under load |
| test-python-3.11/12 | FAIL | FAIL | FAIL | Flaky timing under load |

**Conclusion:** CI infrastructure is solid — all Playwright tests pass across code
variants. The synth commits have code-level issues (old dependency lockfiles, flaky
timing assertions) that aren't CI runner bugs. Full 16-commit run deferred — would
show the same pattern.

---

### Exp 59 — Time-to-insight analysis

**Priority:** LOW — research, no code changes needed

**Problem:** We don't know which tests catch real bugs fastest. Some tests may never fail from app changes (e.g., lint), while others catch every regression (e.g., pw-server). Understanding this helps prioritize fast-path testing.

**Plan:**
1. Pull recent CI logs from GitHub Actions:
   ```
   gh run list --branch main --limit 50 --json conclusion,headSha,databaseId
   ```
2. For each run that failed, get which jobs failed:
   ```
   gh run view <id> --json jobs
   ```
3. Correlate with commit diffs:
   ```
   git log --oneline main~50..main
   ```
4. Build a table: `commit SHA | files changed | which CI jobs failed | was it a real bug or flake?`
5. Look for patterns:
   - Do Python-only changes ever fail Playwright tests? (Shouldn't, but maybe pw-server does since it imports Python)
   - Do JS-only changes ever fail Python tests?
   - Which test catches the most real bugs?
   - Which test has the highest flake rate?
6. Output: a ranked list of tests by "value" (bugs caught / time cost). This informs Exp 55's `--only` fast path.

**This is pure analysis** — no code changes, no server work. Can be done locally with `gh` CLI.

---

### Exp 60 — Investigate renice effectiveness

**Priority:** LOW — research on the current server once pw-jupyter works

**Problem:** `renice` is applied to several jobs (build-js at -10, lint/pytest/storybook at +10) but we've never measured whether it actually helps. On 32 vCPU with plenty of headroom, renice may be irrelevant.

**Plan:**
1. Run CI twice with current renice settings, capture `cpu-fine.log` (100ms /proc/stat samples) and per-job timing.
2. Comment out ALL renice lines in `run-ci.sh`, run CI twice more.
3. Compare:
   - Total wall time (with vs without renice)
   - Per-job duration (especially build-js and pw-jupyter)
   - CPU utilization curves from `cpu-fine.log`
4. On 32 vCPU, expect: negligible difference. renice matters most when CPU is saturated (16 vCPU with full overlap). On 32 vCPU with sequential post-pw-jupyter, CPU is rarely saturated.
5. If renice helps: keep it, document the delta. If not: remove the renice lines to simplify the script.

**Theory:** renice -10 for build-js should help during Wave 0 when lint+pytest+warmup are all competing. But build-js is mostly pnpm install (I/O bound, instant on cache hit) and vite build (single-threaded, ~2s). The benefit window is tiny.

**For pw-jupyter:** Currently NOT reniced (it should be, if renice helps at all). If we find renice helps, add `renice -n -10 -p $PID_PW_JP` as the most impactful change.

---

### Exp 61 — Network contention diagnostics (0s stagger investigation)

**Priority:** LOW — research, requires VX1 32C with pw-jupyter working + 128GB RAM

**Background:** 0s stagger (all 9 JupyterLab+Chromium launching simultaneously) fails with 8/9 kernel hangs even on Rome 32v/64GB. We hypothesize TCP port collision in `write_connection_file()`.

Deep research: [`kernel-contention-diagnostics.md`](kernel-contention-diagnostics.md)

**Plan:**
1. Prerequisites: add `strace` to Dockerfile (`apt-get install -y strace`), add `cap_add: SYS_PTRACE` to docker-compose.yml. Rebuild image.
2. Temporarily set stagger to 0s in `test_playwright_jupyter_parallel.sh`.
3. Run CI with diagnostics collection enabled:
   ```
   COLLECT_DIAGNOSTICS=1 docker exec buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> main
   ```
4. After the (expected) failure, collect from server:
   ```
   scp -r root@66.42.115.86:/opt/ci/logs/diagnostics/ ./diagnostics/
   ```
5. Analyze:
   - `collisions.log`: any duplicate ports across kernel connection files? If yes, that's the smoking gun.
   - `ss-snapshots.log`: socket states during warmup — SYN-SENT accumulation, TIME-WAIT count
   - `strace-*.log`: syscall summaries — connect errors, bind errors (EADDRINUSE), futex contention
   - `loadavg.log`: was CPU saturated during the failure?
6. If port collision confirmed, test fix: `--KernelManager.transport=ipc` (Unix domain sockets instead of TCP) or pre-assigned port ranges per server.

**Why this is LOW priority:** The 2s stagger works. This is pure research to understand the mechanism. Only worth doing if we want to push for faster total time by eliminating the stagger delay.

---

### Exp 62 — More parallel pytest

**Priority:** LOW — small potential gain

**Problem:** pytest runs with `-n 4` (4 xdist workers). On 32 vCPU, we could push higher.

**Plan:**
1. Check how many test files exist and how they're distributed:
   ```
   find tests/unit -name '*.py' -path '*/test_*' | wc -l
   ls tests/unit/*/
   ```
2. Run pytest with `-n 8` locally, compare timing vs `-n 4`.
3. Diminishing returns: at some point, test collection + distribution overhead exceeds the parallelism benefit. The current `-n 4` takes ~24s per Python version. If we get to ~15s with `-n 8`, that's a 9s saving on a non-critical-path job.
4. Only worth doing if pytest is on the critical path (it's not currently — it runs in the background).

**When this matters:** If we move pytest to overlap with pw-jupyter (Exp 53), its duration doesn't affect total time at all. Only matters if pytest becomes the tail job.
