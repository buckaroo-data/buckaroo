# Plan: DAG-based CI execution to minimize wall time

## Context

Current Hetzner CI takes ~5m56s with a 5-phase sequential structure (run 26, commit 1759612). Depot Linux-only critical path is 3:27. The phase structure is overly conservative — many jobs wait for phases they don't actually depend on.

**Root cause:** The phased approach forces jobs to wait for entire phases to complete, even when they only depend on one specific job. For example, test-python-3.11/3.12/3.14 wait for build-wheel (Phase 2), but they don't need the wheel at all — they use editable install with placeholder static files. Similarly, playwright-storybook/marimo/wasm-marimo don't need the wheel but wait until Phase 5a (after phases 1-4 complete).

**Goal:** Restructure run-ci.sh from phases to a dependency DAG. Each job starts as soon as its specific dependencies are met, not when an entire phase completes.

## Current phase structure (run-ci.sh as of aea3201)

```
Phase 1 (parallel):   lint-python, test-js, test-python-3.13
Phase 2 (sequential): build-wheel                              ← waits for ALL of phase 1
Phase 3 (parallel):   test-python-3.11, 3.12, 3.14             ← waits for phase 2 (unnecessary)
Phase 4 (parallel):   test-mcp-wheel, smoke-test-extras         ← waits for phase 3 (unnecessary)
Phase 5a (parallel):  pw-storybook, pw-server, pw-marimo, pw-wasm ← waits for phase 4 (unnecessary)
Phase 5b (sequential): pw-jupyter (PARALLEL=1)                  ← waits for phase 5a (unnecessary)
```

Timing (run 26): Phase 1: 1m15s | Phase 2: 22s | Phase 3: 1m16s | Phase 4: 20s | Phase 5a: 59s | Phase 5b: 1m44s

## Actual dependency graph

```
No dependencies (start immediately):
  lint-python
  test-python-3.11
  test-python-3.12
  test-python-3.13
  test-python-3.14
  playwright-storybook     (builds its own storybook server, no wheel needed)
  playwright-marimo        (uses uv run marimo with pre-synced 3.13 venv, no wheel)
  playwright-wasm-marimo   (static HTML files, no wheel)

Depends on test-js completing (pnpm build writes to packages/buckaroo-js-core/dist/):
  build-wheel              (full_build.sh calls pnpm build, conflicts with test-js pnpm build)

test-js has no deps — starts immediately, build-wheel waits only for it.

Depends on build-wheel completing (needs dist/buckaroo-*.whl):
  test-mcp-wheel           (installs wheel[mcp] into isolated venv)
  smoke-test-extras        (installs wheel with each extra into isolated venvs)
  playwright-server        (installs wheel[mcp] into clean venv — see scripts/test_playwright_server.sh)
  playwright-jupyter       (installs wheel + polars + jupyterlab into isolated venv)
```

### Venv conflicts (already resolved)

- `job_playwright_jupyter` creates `/tmp/ci-jupyter-$$` — no conflict with shared venvs
- `job_playwright_marimo` and `job_playwright_wasm_marimo` use `UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13` read-only — no conflict with `job_test_python 3.13` which runs `uv sync` (both are in Phase 1 currently but `uv sync` is fast and atomic)
- `job_lint_python` does NOT run `uv sync` — avoids racing with test-python-3.13

## Critical path analysis

```
test-js (~24s) → build-wheel (~22s) → playwright-jupyter (~104s) = ~2m30s
```

Everything else finishes within that window:
- All pytest runs: ~63s (start at t=0, done well before build-wheel finishes)
- lint-python: ~5s
- pw-storybook: ~10s (start at t=0)
- pw-marimo: ~56s (start at t=0)
- pw-wasm-marimo: ~35s (start at t=0)
- pw-server: ~58s (starts after build-wheel at ~46s, done at ~104s)
- test-mcp-wheel: ~12s (starts after build-wheel)
- smoke-test-extras: ~20s (starts after build-wheel)

**Projected total: ~2m30s** (vs 5m56s current, vs ~12min Depot)

## Implementation

### Changes to `ci/hetzner/run-ci.sh`

Replace the 5-phase structure (lines 277-334) with DAG-based execution. Keep everything else (job definitions, setup, `--phase=5b`, wheel cache, lockfile check, status reporting).

```bash
# ── Wave 0: Everything with no dependencies (start immediately) ──────────
log "=== Starting all independent jobs ==="

run_job lint-python            job_lint_python                & PID_LINT=$!
run_job test-js                job_test_js                    & PID_TESTJS=$!
run_job test-python-3.11       bash -c "job_test_python 3.11" & PID_PY311=$!
run_job test-python-3.12       bash -c "job_test_python 3.12" & PID_PY312=$!
run_job test-python-3.13       bash -c "job_test_python 3.13" & PID_PY313=$!
run_job test-python-3.14       bash -c "job_test_python 3.14" & PID_PY314=$!
run_job playwright-storybook   job_playwright_storybook       & PID_PW_SB=$!
run_job playwright-marimo      job_playwright_marimo           & PID_PW_MA=$!
run_job playwright-wasm-marimo job_playwright_wasm_marimo     & PID_PW_WM=$!

# ── Wait for test-js only, then build wheel ───────────────────────────────
wait $PID_TESTJS || OVERALL=1
log "=== test-js done — starting build-wheel ==="

run_job build-wheel job_build_wheel || OVERALL=1

# Cache wheel by SHA so --phase=5b can skip the build on re-runs.
mkdir -p "$WHEEL_CACHE_DIR"
cp dist/buckaroo-*.whl "$WHEEL_CACHE_DIR/" 2>/dev/null || true
log "Cached wheel → $WHEEL_CACHE_DIR"

# ── Wheel-dependent jobs (start as soon as wheel exists) ──────────────────
log "=== build-wheel done — starting wheel-dependent jobs ==="

run_job test-mcp-wheel       job_test_mcp_wheel       & PID_MCP=$!
run_job smoke-test-extras    job_smoke_test_extras     & PID_SMOKE=$!
run_job playwright-server    job_playwright_server     & PID_PW_SV=$!
run_job playwright-jupyter   job_playwright_jupyter    & PID_PW_JP=$!

# ── Wait for everything ──────────────────────────────────────────────────
wait $PID_LINT    || OVERALL=1
wait $PID_PY311   || OVERALL=1
wait $PID_PY312   || OVERALL=1
wait $PID_PY313   || OVERALL=1
wait $PID_PY314   || OVERALL=1
wait $PID_PW_SB   || OVERALL=1
wait $PID_PW_MA   || OVERALL=1
wait $PID_PW_WM   || OVERALL=1
wait $PID_MCP     || OVERALL=1
wait $PID_SMOKE   || OVERALL=1
wait $PID_PW_SV   || OVERALL=1
wait $PID_PW_JP   || OVERALL=1
```

### No other changes needed

- Job functions: unchanged (all already handle their own venvs/ports)
- `run_job` helper: unchanged
- `--phase=5b` routing: unchanged
- Lockfile check / status reporting: unchanged
- Wheel cache: unchanged (just moves to after build-wheel instead of after phase 2)

### Timing comparison

```
                    Current (phased)    DAG
lint-python         t=0, done t=5       t=0, done t=5
test-js             t=0, done t=24      t=0, done t=24
test-python-3.13    t=0, done t=75      t=0, done t=63
build-wheel         t=75, done t=97     t=24, done t=46     ← 51s earlier start
test-python-3.11    t=97, done t=160    t=0, done t=63      ← 97s earlier start
test-python-3.12    t=97, done t=160    t=0, done t=63      ← 97s earlier start
test-python-3.14    t=97, done t=160    t=0, done t=5       ← 97s earlier start
test-mcp-wheel      t=160, done t=172   t=46, done t=58
smoke-test-extras   t=160, done t=180   t=46, done t=66
pw-storybook        t=180, done t=190   t=0, done t=10      ← 180s earlier start
pw-server           t=180, done t=238   t=46, done t=104
pw-marimo           t=180, done t=236   t=0, done t=56      ← 180s earlier start
pw-wasm-marimo      t=180, done t=215   t=0, done t=35      ← 180s earlier start
pw-jupyter          t=238, done t=342   t=46, done t=150     ← 192s earlier start
                    ─────────────────   ───────────────
                    TOTAL: ~5m42s       TOTAL: ~2m30s
```

## CPU budget (8 vCPU CCX33)

Peak concurrency at t=0: 9 jobs. But:
- lint-python finishes in ~5s (1 core freed)
- test-python-3.14 skips pytest (finishes in ~5s)
- pw-storybook finishes in ~10s
- pw-wasm-marimo finishes in ~35s
- By the time wheel-dependent jobs start (~46s), only pw-marimo and possibly test-python 3.11/3.12/3.13 are still running

Most jobs are single-threaded or I/O-bound (Playwright waits on Chromium). 8 vCPU is sufficient. Some jobs may run ~10-20% slower from contention in the first 30s, but the parallelism gain far outweighs it.

## Risk: pw-jupyter CPU contention

playwright-jupyter (PARALLEL=1, 104s) is the critical path. At t=46 when it starts, these may still be running:
- test-python-3.13 (usually done by t=63)
- pw-marimo (usually done by t=56)

By t=63, only pw-jupyter and pw-server remain. Minimal contention for the bulk of pw-jupyter's runtime.

If pw-jupyter proves flaky under DAG concurrency, add a `wait` for pw-marimo before starting it:
```bash
wait $PID_PW_MA || OVERALL=1  # ensure marimo done before jupyter starts
```

## Verification

1. Rebuild Docker image (run-ci.sh is baked at `/opt/ci-runner/`):
   ```bash
   ssh root@5.161.210.126
   cd /opt/ci/repo && git pull
   docker build -f ci/hetzner/Dockerfile -t buckaroo-ci .
   docker compose -f ci/hetzner/docker-compose.yml up -d --force-recreate
   ```

2. Run CI and compare timing:
   ```bash
   docker exec buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> main \
     > /opt/ci/logs/dag-test.log 2>&1 &
   tail -f /opt/ci/logs/dag-test.log
   ```

3. Verify all 14 jobs pass
4. Compare wall time against 5m56s (phased) baseline
5. Run 3x to confirm stability

## Files to modify

- `ci/hetzner/run-ci.sh` — replace phases 1-5b (~lines 277-334) with DAG execution block above

## Future: parallel jupyter

playwright-jupyter currently runs PARALLEL=1 (104s). See `docs/llm/research/parallel-jupyter-plan.md` for findings from 20 experiments attempting PARALLEL=3. Summary: the overhead required for batch-1 reliability exceeds parallelism savings at 9 notebooks. Revisit when notebook count grows to 15+, using the pre-started persistent server approach (9 JupyterLab servers running in container, ~16s test time).
