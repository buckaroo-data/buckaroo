# CI Tuning — Current State & Next Experiments

**Branch:** docs/ci-research
**Server:** Vultr VX1 32C (66.42.115.86) — vx1-g-32c-128g, 32 vCPU/128GB, EPYC Turin Zen 5
**Previous servers:** VX1 16C (destroyed), Rome 32C (destroyed)
**Best config (Rome 32v):** P=9 + /dev/shm fix + 2s stagger — **1m42s, all PASS** (commit 09c6faa)
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

### Exp 53 — Restore full parallel DAG on 32 vCPU

**Priority:** HIGH — once pw-jupyter works, reclaim the parallelism we had on Rome

**Background:** The current `run-ci.sh` serializes everything after pw-jupyter (lines 619-629): pw-marimo, pw-server, pw-wasm-marimo, smoke-test, pytest 3.11/3.12/3.14 all wait for pw-jupyter to finish. This was done because the VX1 16C (only 16 vCPU) couldn't handle the overlap. The VX1 32C has the same core count as Rome, so the old overlap config should work.

**Plan:**
1. After Exp 52 confirms pw-jupyter passes, modify `run-ci.sh` to restore overlapping:
   - Move pw-marimo, pw-server, pw-wasm-marimo, smoke-test-extras back to launch alongside pw-jupyter (staggered 2s apart), same as the Rome config (commit 09c6faa).
   - Keep pytest 3.11/3.12/3.14 deferred 8s (they were always deferred).
2. Push the change, update runner on server:
   ```
   git push origin docs/ci-research
   ssh root@66.42.115.86
   cd /opt/ci/repo && git fetch origin && git checkout origin/docs/ci-research -- ci/hetzner/ scripts/
   bash ci/hetzner/update-runner.sh
   ```
3. Run CI, report timing. Compare against Rome baseline (1m42s).
4. If stable, run b2b (3 consecutive runs) to confirm reliability.

**Expected outcome:** Total time drops from ~3m (sequential) back to ~1m40-1m50s range. VX1 32C has 128GB RAM (vs Rome's 64GB), so if anything it should be more comfortable with overlap.

**What to watch for:** The VX1 is Zen 5, which may have different scheduler/interrupt characteristics. If pw-jupyter starts failing again under overlap, try increasing the stagger from 2s to 3s or 5s.

---

### Exp 54 — Fast-fail mode

**Priority:** HIGH — saves minutes when iterating on fixes

**Problem:** When a job fails early (e.g., lint-python at t+10s), the full ~3 minute run continues. During development, this wastes 2+ minutes per iteration.

**Plan:**
1. Add a `--fast-fail` flag to `run-ci.sh` arg parsing (alongside existing `--phase` and `--wheel-from`).
2. After each `wait $PID_xxx || OVERALL=1` line, check: if `$FAST_FAIL` is set and `$OVERALL` is non-zero, skip launching subsequent waves. Already-running background jobs are left alone (killing them cleanly is complex and not worth it).
3. The key insertion points:
   - After `wait $PID_BUILDJS` (line 553): if build-js fails, don't build-wheel or launch any playwright
   - After `run_job build-wheel` (line 556): if wheel build fails, don't launch wheel-dependent jobs
   - After `wait $PID_PW_JP` (line 620): if pw-jupyter fails, still launch the remaining jobs (they're independent) — OR skip them for maximum speed. Make this configurable or just skip.
4. Test by intentionally introducing a lint failure, verifying CI exits in ~15s instead of ~3m.
5. For the webhook/ci-queue path, fast-fail should be opt-in (default off) since you want full results for real CI.

**Implementation notes:**
- Don't try to `kill` background PIDs — they may have spawned children (JupyterLab, Chromium) that won't get cleaned up. Let them finish naturally; the pre-run cleanup will handle them next run.
- The `wait` calls at the end (lines 632-643) should still run so we collect accurate pass/fail for the jobs that did start.
- Log `SKIP <job> (fast-fail)` so the ci.log is parseable.

---

### Exp 55 — Selective test runs (`--only` / `--skip`)

**Priority:** HIGH — enables fast iteration and is a prerequisite for the tuning script

**Problem:** To iterate on pw-jupyter, you have to run the entire CI. To iterate on a Python test fix, you wait for build-js + build-wheel even though you only need pytest. pw-wasm-marimo takes 2+ minutes and rarely fails from app changes.

**Plan:**
1. Add `--only=JOB1,JOB2` and `--skip=JOB1,JOB2` flags to `run-ci.sh`. Job names match the `run_job` first argument (e.g., `lint-python`, `build-js`, `playwright-jupyter`, `test-python-3.13`).
2. Before each `run_job` call, check if the job is allowed:
   - If `--only` is set: skip jobs not in the list
   - If `--skip` is set: skip jobs in the list
   - Dependency handling: if `--only=playwright-jupyter`, implicitly include `build-js`, `build-wheel`, `jupyter-warmup` (its dependencies). OR, document that the user must include dependencies manually. The simpler approach (manual) is better to start.
3. Skipped jobs should log `SKIP <job> (filtered)` and return 0.
4. Special case: `--only=playwright-jupyter` is essentially `--phase=5b` but starting from scratch. Consider whether `--phase=5b` (which uses cached wheel) is sufficient, or if `--only` adds value.
5. Example usage:
   ```
   run-ci.sh SHA BRANCH --only=lint-python,test-python-3.13    # 15s
   run-ci.sh SHA BRANCH --skip=playwright-wasm-marimo           # saves 2min
   run-ci.sh SHA BRANCH --only=playwright-jupyter,build-js,build-wheel,jupyter-warmup  # just pw-jupyter
   ```
6. Test by running with various `--only`/`--skip` combos, verify correct jobs run.

**Interaction with `--fast-fail`:** These are orthogonal. `--only` controls which jobs start, `--fast-fail` controls whether to abort after a failure. Both can be used together.

---

### Exp 56 — Fix GitHub CI on this branch

**Priority:** MEDIUM — stops the failure notification noise

**Problem:** The `docs/ci-research` branch generates GitHub Actions failure notifications on every push.

**Plan:**
1. Check what's actually failing:
   ```
   gh run list --branch docs/ci-research --limit 5
   gh run view <run-id>
   ```
2. Likely issues:
   - `ci/hetzner/` shell scripts may fail shellcheck or have syntax that triggers lint
   - `packages/.npmrc` with `shamefully-hoist=true` may break pnpm on GH runners
   - Playwright config changes (`--disable-dev-shm-usage`) shouldn't matter on GH
   - `stress-test.sh`, `create-merge-commits.sh` are new files that may not pass lint
3. Options to fix:
   - **Option A:** Add this branch to the GH workflow's `branches-ignore` list in `.github/workflows/checks.yml`. Quick but hides real issues.
   - **Option B:** Fix the actual failures. Better long-term since changes will eventually merge to main.
   - **Option C:** Add a `.github/workflows/` override on this branch that skips the problematic jobs. Middle ground.
4. For Option B, push fixes, check CI passes via `gh run watch`.

**Note:** Don't spend a lot of time on this if the failures are in CI-research-only files (shell scripts, docs). Option A is fine for a research branch.

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

### Exp 58 — Stress test execution

**Priority:** MEDIUM — validates CI reliability across code variation

**Background:** `stress-test.sh` and 42 synthetic merge commits are already built. The infrastructure exists but has never been run.

**Plan:**
1. After Exp 52 + 53 stabilize the server, start with a small run:
   ```
   ssh root@66.42.115.86
   tmux new -s stress
   # From local machine (stress-test.sh SSHes into server):
   bash ci/hetzner/stress-test.sh --limit=3 --set=safe
   ```
2. Check that the synth branches exist on origin (they were pushed from a previous session):
   ```
   git branch -r | grep synth/
   ```
   If missing, re-run `create-merge-commits.sh` and push.
3. Review results:
   ```
   ssh root@66.42.115.86
   cat /opt/ci/logs/stress-run-ci-safe/summary.txt
   ```
4. If 3/3 pass, run full safe set (16 commits).
5. Then failing set (10 commits) — compare which jobs fail vs GitHub Actions failures.
6. Report: pass rates, timing distribution, flake patterns.

**What to watch for:**
- Safe set should be 16/16. Any failure is a runner bug.
- Failing set failures should match the same jobs that failed on GitHub Actions. Different failures = runner issue.
- Timing variance: expect ~1m40s ± 15s. If some commits are much slower, investigate (heavier build, more tests).

**Note:** `stress-test.sh` runs from the local machine and SSHes into the server. If your laptop sleeps, the run dies. For unattended runs, the script needs a refactor to run directly on the server (replace `ssh $SERVER "docker exec ..."` with just `docker exec ...`). Add `--local` flag or detect if already on the server.

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
