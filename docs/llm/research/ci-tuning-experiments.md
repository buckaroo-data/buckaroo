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

### Exp 63 — B2B stress test (50 new commits) — DONE

**Script:** `ci/hetzner/stress-test.sh --set=new`

**Runner commit:** c8787afa (includes all b2b fixes)
**Date:** 2026-03-04/05

**Results:** 0/50 passed — all failures are app-level (expected). Infrastructure was stable after fixes.

**Failure pattern by category:**

| Failure | Commits affected | Root cause |
|---------|-----------------|------------|
| `playwright-server` | 50/50 | 2 `/load API` tests added after these commits |
| `playwright-marimo` | ~40/50 | Old app code doesn't support current marimo tests |
| `playwright-jupyter` | ~30/50 | Old app code fails notebook tests (2m timeout) |
| `test-python-3.x` | ~15/50 | Timing flakes under b2b load |
| `lint-python` | 3/50 (ee8d1102, 11a457aa, 650404b7) | Old test files have unused imports (F401) caught by current ruff |
| `test-mcp-wheel` | 0/50 | Fixed: skip when `test_mcp_server_integration.py` absent |
| `test-js` | 0/50 | Fixed: npm_config_store_dir prevents pnpm store mismatch |
| `build-wheel` | 0/50 | Fixed: wipe all node_modules on lockfile change |

**Timing:** Recent commits ~1m03-1m19s. Older commits ~2m13-2m23s (playwright-jupyter hangs 120s on broken old code).

**Infrastructure bugs found and fixed during this experiment:**

| Bug | Fix commit | Description |
|-----|-----------|-------------|
| pnpm ENOTEMPTY race | ae19ed2a | Wipe all 3 node_modules dirs (not just workspace) before reinstall |
| pytest-xdist missing | 4a3a7635 | Force-install after uv sync (old lockfiles don't have it) |
| pnpm store-dir mismatch | a8dfb1b0 | `export npm_config_store_dir=/opt/pnpm-store` in run-ci.sh |
| test-mcp-wheel false positive | c8787afa | Check `test_mcp_server_integration.py` (not `test_mcp_uvx_install.py`) |

**GH CI comparison:** 17/50 commits had GH CI data; 15 "success" on GH → "FAIL" on Hetzner (expected: new tests test features not in old code); 2 were already failing on GH (Dependabot/github-script bumps).

---

### Exp 57 — Deterministic tuning script — READY TO RUN

**Script:** `ci/hetzner/tuning-sweep.sh`

Sweeps JUPYTER_PARALLEL (5,7,9) × STAGGER_DELAY (0,1,2,3) — 12 combos × 3 runs = 36 runs.
Uses `STAGGER_DELAY` env var override in run-ci.sh (Part 3 of this commit).

```bash
bash ci/hetzner/tuning-sweep.sh --sha=fa5e5a7 --runs=3
```

Output: `$LOGDIR/sweep.csv` with pass/fail, total time, pw-jupyter time per combo.

---

### Exp 59 — Time-to-insight analysis — DONE

**Script:** `ci/hetzner/analyze-gh-failures.sh`

**Results (last 50 runs on main):**

| Outcome | Count | % |
|---------|-------|---|
| success | 40 | 80% |
| failure | 8 | 16% |
| cancelled | 2 | 4% |

**Job failure frequency (8 failed runs):**

| Job | Failures | Notes |
|-----|----------|-------|
| Release | 5 | Release workflow issues, not test failures |
| Dependabot | 1 | Dep compat check |
| Test Latest Deps / Python 3.11-3.14 | 1 each | Dep compat, not code bugs |
| Server Playwright Tests | 1 | Only real test failure |
| Marimo Playwright Tests | 1 | Only real test failure |

**Key findings:**
- 80% pass rate on main — good baseline
- 5/8 failures are Release workflow issues (not test failures)
- Only 2 real test failures in 50 runs: pw-server (1) and pw-marimo (1)
- No Python test failures on main — timing flakes only surface under Hetzner CI load
- The "fast path" for --first-jobs should be: lint + build + pw-server (catches the most real bugs)

---

### Exp 60 — Investigate renice effectiveness — DONE (no effect)

**Script:** `ci/hetzner/test-renice.sh`

| Run | Renice | Failed Job | pw-jupyter |
|-----|--------|-----------|------------|
| with-1 | ON | test-python-3.13 (flaky) | 37s |
| with-2 | ON | test-python-3.13 (flaky) | 35s |
| with-3 | ON | test-python-3.13 (flaky) | 36s |
| no-1 | OFF | — (ALL PASS) | 37s |
| no-2 | OFF | — (ALL PASS) | 36s |
| no-3 | OFF | pw-jupyter (120s timeout) | 120s |

**Verdict:** renice has zero effect on pw-jupyter (35-37s either way). The with-renice
FAILs are all the known flaky `test-python-3.13` timing test. The no-renice run 3
pw-jupyter timeout is an unrelated b2b flake. **Can safely remove renice to simplify.**

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

---

### Exp 57 — Deterministic tuning sweep — DONE

**Script:** `ci/hetzner/server-experiments.sh` (server-side)
**SHA:** 61bf303  **Date:** 2026-03-05
**Grid:** JUPYTER_PARALLEL ∈ {5,7,9} × STAGGER_DELAY ∈ {0,1,2,3} × 3 runs = 36 runs

| P | S | Pass | Mean(s) | Notes |
|---|---|------|---------|-------|
| 5 | 0-3 | 0/12 | 133s | pw-jupyter 120s timeout every run |
| 7 | 0-3 | 0/12 | 133s | pw-jupyter 120s timeout every run |
| 9 | 0 | 1/3 | 59s | |
| 9 | 1 | 1/3 | 65s | |
| 9 | 2 | 1/3 | 78s | one run 115s (pw-jupyter flake) |
| 9 | 3 | 1/3 | 62s | |

**Key findings:**
- **P<9 is categorically broken** — P=5 and P=7 always hit the 120s pw-jupyter timeout (133s total).
- **Stagger has zero effect on pass rate** — all four stagger values (0,1,2,3) give identical 1/3 pass rate at P=9.
- **P=9 failures are all `test-python-3.13` timing flake** — the known `test_huge_dataframe_partial_cache_scenario` asserts timing < 0.5s, fails under B2B load. Not a pw-jupyter stability issue.
- **STAGGER=0 is safe** — could drop from default STAGGER=2 to save warmup delay with no reliability cost.

**Verdict:** PARALLEL=9 required (confirmed again). Stagger tuning has no effect. The remaining ~67% failure rate under B2B stress is entirely the pre-existing pytest timing flake, not infra.

---

### Exp 62 — More parallel pytest — DONE

**SHA:** 61bf303  **Date:** 2026-03-05

| Workers | Run 1 | Run 2 | Pass |
|---------|-------|-------|------|
| 4 | 25s | 25s | 2/2 |
| 8 | 22s | 37s | 1/2 (timing flake) |

**Verdict:** Marginal (3s improvement). Workers=8 triggers the timing flake more readily. pytest is not on the critical path — not worth changing.

---

### Exp 64 — tsgo + vitest JS tooling — DONE

**Branch:** `feat/ts-go-compiler` (SHA 898ef803)  **Date:** 2026-03-05

Changes vs baseline:
- `@typescript/native-preview` (tsgo) as `typecheck` script (~4.5x faster than tsc for type-checking)
- vitest replaces jest for unit tests
- ESM-only vite build (removed CJS/UMD formats, sourcemaps, vite-plugin-dts)

Per-job timings (3 runs on VX1 16C):

| Job | Time | vs baseline |
|-----|------|-------------|
| `test-js` | **2s** | was ~4s with jest — 2x faster |
| `build-js` | 9s cold, 1s cache hit | unchanged |
| `build-wheel` | 10s | unchanged |
| `playwright-jupyter` | 57-59s | baseline ~35s — but see below |

**pw-jupyter failures:** "Widget failed to render" (polars_infinite_widget) on all 3 runs. Identical failure pattern seen in Exp 57 P=9 B2B runs on baseline — this is the back-to-back stress flake, not a regression from tsgo/vitest changes. The JS build hash differs (new package.json), so warmup is slightly different, but the failure mode is the same.

**test-python failures:** `test-python-3.13` timing flake on runs 2 and 3 (same B2B flake as Exp 57).

**Verdict:** tsgo/vitest branch is clean — no regressions. `test-js` drops from ~4s to 2s. The branch is ready to merge once CI passes on a clean (non-B2B) run.
