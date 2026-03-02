# Plan: DAG-based CI execution to minimize wall time

## Context

Current Hetzner CI takes ~9 minutes with a 5-phase sequential structure. Depot Linux-only critical path is 3:27. The phase structure is overly conservative — many jobs wait for phases they don't actually depend on.

**Root cause:** The phased approach forces jobs to wait for entire phases to complete, even when they only depend on one specific job. For example, test-python-3.11/3.12/3.14 wait for build-wheel (Phase 2), but they don't need the wheel at all — they use editable install with placeholder static files.

**Goal:** Restructure run-ci.sh from phases to a dependency DAG. Each job starts as soon as its specific dependencies are met, not when an entire phase completes.

## Actual dependency graph

```
No dependencies (start immediately):
  lint-python
  test-python-3.11
  test-python-3.12
  test-python-3.13
  test-python-3.14
  playwright-storybook     (builds its own storybook server, no wheel)
  playwright-marimo        (uses uv run marimo, no wheel)
  playwright-wasm-marimo   (static HTML files, no wheel)

Depends on test-js completing (dist/ write conflict):
  build-wheel

Depends on build-wheel completing (needs dist/buckaroo-*.whl):
  test-mcp-wheel
  smoke-test-extras
  playwright-server        (installs wheel[mcp] into clean venv)
  playwright-jupyter       (installs wheel into 3.13 venv)
```

test-js itself has no dependencies so it also starts immediately.

## Critical path analysis

```
test-js (~20s) → build-wheel (~20s) → playwright-jupyter (~90s) = ~2m10s
```

Everything else finishes within that window:
- All pytest runs: ~51-84s (done before build-wheel even finishes)
- pw-storybook: ~11-20s
- pw-marimo: ~53s
- pw-wasm: ~33s
- pw-server: starts at ~40s, takes ~55s, done at ~95s
- mcp/smoke: start at ~40s, take ~10-23s

**Projected total: ~2m10s** (vs 9min current, vs 3:27 Depot)

## CPU budget (8 vCPU CCX33)

Peak concurrency: ~12 jobs at time zero. But:
- lint-python finishes in ~5s, freeing 1 CPU
- pw-storybook/wasm finish in ~20-35s
- Most pytest runs are single-threaded
- Playwright jobs are I/O bound (waiting on chromium)
- By the time wheel-dependent jobs start (~40s), half the initial burst is done

8 vCPU is sufficient. Some jobs may run ~10-20% slower from contention, but the parallelism gain far outweighs it.

## Implementation

### Changes to `ci/hetzner/run-ci.sh`

Replace the 5-phase structure (lines 199-241) with DAG-based execution:

```bash
# ── Wave 0: Everything with no dependencies (start immediately) ──────────
log "=== Starting all independent jobs ==="

run_job lint-python          job_lint_python                & PID_LINT=$!
run_job test-js              job_test_js                    & PID_TESTJS=$!
run_job test-python-3.11     bash -c "job_test_python 3.11" & PID_PY311=$!
run_job test-python-3.12     bash -c "job_test_python 3.12" & PID_PY312=$!
run_job test-python-3.13     bash -c "job_test_python 3.13" & PID_PY313=$!
run_job test-python-3.14     bash -c "job_test_python 3.14" & PID_PY314=$!
run_job playwright-storybook job_playwright_storybook       & PID_PW_SB=$!
run_job playwright-marimo    job_playwright_marimo           & PID_PW_MA=$!
run_job playwright-wasm-marimo job_playwright_wasm_marimo   & PID_PW_WM=$!

# ── Wait for test-js specifically, then build wheel ──────────────────────
wait $PID_TESTJS || OVERALL=1
log "=== test-js done — starting build-wheel ==="

run_job build-wheel job_build_wheel || OVERALL=1

# ── Wheel-dependent jobs (start as soon as wheel exists) ─────────────────
log "=== build-wheel done — starting wheel-dependent jobs ==="

run_job test-mcp-wheel       job_test_mcp_wheel       & PID_MCP=$!
run_job smoke-test-extras    job_smoke_test_extras     & PID_SMOKE=$!
run_job playwright-server    job_playwright_server     & PID_PW_SV=$!
run_job playwright-jupyter   job_playwright_jupyter    & PID_PW_JP=$!

# ── Wait for everything ─────────────────────────────────────────────────
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

### Conflict: playwright-jupyter vs test-python-3.13 (shared venv)

`job_playwright_jupyter` installs the wheel into `/opt/venvs/3.13` via `pip install --force-reinstall`. `job_test_python 3.13` also uses `/opt/venvs/3.13` via `uv sync`. Running both simultaneously would corrupt the venv.

**Fix:** `playwright-jupyter` should create its own isolated venv instead of mutating the shared 3.13 venv. Change `job_playwright_jupyter` to:

```bash
job_playwright_jupyter() {
    cd /repo
    local venv=/tmp/ci-jupyter-$$
    uv venv "$venv" --python 3.13 -q
    local wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "$wheel" polars jupyterlab -q
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
        bash scripts/test_playwright_jupyter.sh --venv-location="$venv"
    rm -rf "$venv"
}
```

### No other file changes needed

- Job functions stay the same (except playwright-jupyter above)
- `run_job` helper stays the same
- Status reporting stays the same
- Lockfile check stays the same

## What 51 seconds would require

The ~2m10s critical path is bounded by:

```
test-js (20s) → build-wheel (20s) → playwright-jupyter (90s)
```

To get below 60s total, you'd need to eliminate the sequential chain. Options:
1. **Cache the wheel** — skip build-wheel when pyproject.toml + JS source unchanged. Critical path drops to max(pytest ~84s, pw-jupyter ~90s using cached wheel) ≈ ~90s
2. **Speed up playwright-jupyter** — 90s is suspiciously slow (first run was 35s). Investigate why it varies. If it's consistently 35s, critical path with cached wheel = ~84s (longest pytest)
3. **Cache + fast jupyter** — critical path = ~51-84s depending on pytest speed

The wheel cache is the single biggest lever — most pushes don't change JS or pyproject.toml.

## Verification

1. Rebuild the Docker image (since run-ci.sh is baked at `/opt/ci-runner/`):
   ```bash
   ssh root@5.161.210.126
   cd /opt/ci/repo && git pull
   docker build -f ci/hetzner/Dockerfile -t buckaroo-ci .
   docker compose -f ci/hetzner/docker-compose.yml up -d --force-recreate
   ```

2. Run CI manually and compare timing:
   ```bash
   docker exec buckaroo-ci bash /opt/ci-runner/run-ci.sh <SHA> main \
     > /opt/ci/logs/dag-test.log 2>&1 &
   tail -f /opt/ci/logs/dag-test.log
   ```

3. Verify all 14 jobs pass
4. Compare wall time against the 9min baseline and 3:27 Depot baseline

## Files to modify

- `ci/hetzner/run-ci.sh` — replace phases with DAG execution (~lines 199-241), modify `job_playwright_jupyter` (~line 185)
