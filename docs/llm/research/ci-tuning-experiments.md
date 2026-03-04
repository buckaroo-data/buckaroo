# CI Tuning — Current State & Next Experiments

**Branch:** docs/ci-research
**Server:** Vultr VX1 16C (137.220.56.81) — 16 vCPU/64GB, EPYC Turin Zen 5
**Best config (VX1 16C):** P=9, 0s stagger, parallel overlap — **51s** (commit 1455934, with --skip)
**Full CI (no skip):** ~1m10s, 15-16/16 pass (timing-flaky pytest under load)
**Archive:** See `ci-tuning-experiments-archive.md` for Exp 10-42, 51-56, 58.

---

## Operational Reference

### Trigger a CI run
```bash
ssh root@137.220.56.81
docker exec buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> <BRANCH>
tail -f /opt/ci/logs/<SHA>/ci.log
```

### Update CI scripts (no rebuild needed)
```bash
ssh root@137.220.56.81
cd /opt/ci/repo && git fetch origin
git checkout origin/<branch> -- ci/hetzner/ scripts/
bash ci/hetzner/update-runner.sh
```

### Parse results from ci.log
Lines: `[HH:MM:SS] START/PASS/FAIL <job>`
Report: wallclock total, per-phase timing, pass/fail per job.

---

## Open Experiments

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
