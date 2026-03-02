#!/bin/bash
# CI orchestrator — runs inside the buckaroo-ci Docker container.
#
# Called by webhook.py via:
#   docker exec -e GITHUB_TOKEN=... -e GITHUB_REPO=... buckaroo-ci \
#     bash /repo/ci/hetzner/run-ci.sh <sha> <branch>
#
# Phases (each captures stdout/stderr to $RESULTS_DIR/<job>.log):
#   1. Parallel:   lint-python, test-js, test-python-3.13
#   2. Sequential: build-wheel  (must follow test-js to avoid JS build conflict)
#   3. Parallel:   test-python-3.11, 3.12, 3.14  (separate venvs, no conflicts)
#   4. Parallel:   test-mcp-wheel, smoke-test-extras
#   5. Parallel:   playwright-storybook, playwright-server, playwright-marimo,
#                  playwright-wasm-marimo, playwright-jupyter  (distinct ports)

set -uo pipefail

SHA=${1:?usage: run-ci.sh SHA BRANCH}
BRANCH=${2:?usage: run-ci.sh SHA BRANCH}

REPO_DIR=/repo
RESULTS_DIR=/opt/ci/logs/$SHA
LOG_URL="http://${HETZNER_SERVER_IP:-localhost}:9000/logs/$SHA"
OVERALL=0

mkdir -p "$RESULTS_DIR"

# Source lib from the image-baked path — survives git checkout of any SHA.
CI_RUNNER_DIR=${CI_RUNNER_DIR:-/opt/ci-runner}
source "$CI_RUNNER_DIR/status.sh"
source "$CI_RUNNER_DIR/lockcheck.sh"

log() { echo "[$(date +'%H:%M:%S')] $*" | tee -a "$RESULTS_DIR/ci.log"; }

# Run a job: captures output, returns exit code.
# run_job <name> <cmd> [args...]
run_job() {
    local name=$1; shift
    local logfile="$RESULTS_DIR/$name.log"
    log "START $name"
    if "$@" >"$logfile" 2>&1; then
        log "PASS  $name"
        return 0
    else
        log "FAIL  $name  (see $LOG_URL/$name.log)"
        return 1
    fi
}

# ── Setup ────────────────────────────────────────────────────────────────────

status_pending "$SHA" "ci/hetzner" "Running CI..." "$LOG_URL"

RUNNER_VERSION=$(cat "$CI_RUNNER_DIR/VERSION" 2>/dev/null || echo "unknown")
log "CI runner: $RUNNER_VERSION"
log "Checkout $SHA (branch: $BRANCH)"
cd "$REPO_DIR"
git fetch origin
git checkout -f "$SHA"
# Clean untracked/ignored files; preserve warm caches in node_modules.
git clean -fdx \
    --exclude='packages/buckaroo-js-core/node_modules' \
    --exclude='packages/js/node_modules' \
    --exclude='packages/node_modules'

# Lockfile check — rebuild deps only when lockfiles changed (~5% of pushes).
if lockcheck_valid; then
    log "Lockfiles unchanged — using warm caches"
else
    log "Lockfiles changed — rebuilding deps"
    rebuild_deps
    lockcheck_update
fi

# Create empty static files so Python unit tests can import buckaroo before
# BuildWheel runs. BuildWheel overwrites these with real artifacts.
mkdir -p buckaroo/static
touch buckaroo/static/compiled.css buckaroo/static/widget.js buckaroo/static/widget.css

# ── Job definitions ──────────────────────────────────────────────────────────

job_lint_python() {
    cd /repo
    # ruff is already in the 3.13 venv from the image build.
    # Do NOT run uv sync here — it would strip --all-extras packages (e.g.
    # pl-series-hash) from the shared venv, racing with job_test_python_3.13.
    /opt/venvs/3.13/bin/ruff check
}

job_test_js() {
    cd /repo/packages
    pnpm install --frozen-lockfile --store-dir /opt/pnpm-store
    cd buckaroo-js-core
    pnpm run build
    pnpm run test
}

job_test_python() {
    local v=$1
    cd /repo
    # Quick sync installs buckaroo in editable mode (deps already in venv).
    UV_PROJECT_ENVIRONMENT=/opt/venvs/$v \
        uv sync --locked --dev --all-extras

    # 3.14 is still alpha — segfaults on pytest startup; skip for now.
    if [[ "$v" == "3.14" ]]; then
        echo "[skip] Python 3.14 alpha known to segfault — skipping pytest"
        return 0
    fi

    # Ignored in Docker — require forkserver/spawn multiprocessing which behaves
    # differently inside container PID namespaces and takes >1s to spawn.
    # mp_timeout_decorator_test.py: entire file ignored (new tests added regularly).
    # multiprocessing_executor_test.py: test_multiprocessing_executor_success fails
    # with "module '__main__' has no attribute '__spec__'" in Docker.
    # test_server_killed_on_parent_death: SIGKILL propagation differs in containers.
    /opt/venvs/$v/bin/python -m pytest tests/unit -m "not slow" --color=yes \
        --ignore=tests/unit/file_cache/mp_timeout_decorator_test.py \
        --deselect tests/unit/file_cache/multiprocessing_executor_test.py::test_multiprocessing_executor_success \
        --deselect "tests/unit/server/test_mcp_tool_cleanup.py::TestServerMonitor::test_server_killed_on_parent_death"
}

job_build_wheel() {
    cd /repo
    PNPM_STORE_DIR=/opt/pnpm-store bash scripts/full_build.sh
}

job_test_mcp_wheel() {
    cd /repo
    local venv=/tmp/ci-mcp-$$
    rm -rf "$venv"
    uv venv "$venv" -q
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "${wheel}[mcp]" pytest -q
    local rc=0
    # test_uvx_no_stdout_pollution: flushes subprocess stdin which Docker closes
    # unexpectedly (non-TTY pipe), causing ValueError: flush of closed file.
    # Passes on GitHub Actions where stdin behaves differently.
    BUCKAROO_MCP_CMD="$venv/bin/buckaroo-table" \
        "$venv/bin/pytest" \
            tests/unit/server/test_mcp_uvx_install.py \
            tests/unit/server/test_mcp_server_integration.py \
            --deselect tests/unit/server/test_mcp_uvx_install.py::TestMcpInstall::test_uvx_no_stdout_pollution \
            -v --color=yes -m slow || rc=$?
    "$venv/bin/pytest" \
        tests/unit/server/test_mcp_uvx_install.py::TestUvxFailureModes \
        -v --color=yes -m slow || rc=$?
    rm -rf "$venv"
    return $rc
}

job_smoke_test_extras() {
    cd /repo
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    for extra in base polars mcp marimo jupyterlab notebook; do
        local venv=/tmp/ci-smoke-${extra}-$$
        rm -rf "$venv"
        uv venv "$venv" -q
        if [[ "$extra" == "base" ]]; then
            uv pip install --python "$venv/bin/python" "$wheel" -q
        else
            uv pip install --python "$venv/bin/python" "${wheel}[${extra}]" -q
        fi
        "$venv/bin/python" scripts/smoke_test.py "$extra"
        rm -rf "$venv"
    done
}

job_playwright_storybook() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-storybook-$$ \
        bash scripts/test_playwright_storybook.sh
}

job_playwright_server() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-server-$$ \
        bash scripts/test_playwright_server.sh
}

job_playwright_marimo() {
    cd /repo
    # UV_PROJECT_ENVIRONMENT: reuse the pre-synced 3.13 venv so `uv run marimo`
    # doesn't race with other jobs creating /repo/.venv from scratch.
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
        bash scripts/test_playwright_marimo.sh
}

job_playwright_wasm_marimo() {
    cd /repo
    # Same rationale as job_playwright_marimo.
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-wasm-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
        bash scripts/test_playwright_wasm_marimo.sh
}

job_playwright_jupyter() {
    cd /repo
    # Isolated venv — avoids pip-reinstalling into the shared 3.13 venv while
    # marimo/wasm-marimo jobs are reading from it in parallel.
    local venv=/tmp/ci-jupyter-$$
    uv venv "$venv" --python 3.13 -q
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "$wheel" polars jupyterlab -q
    local rc=0
    ROOT_DIR=/repo \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
    PARALLEL=2 \
        bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" --venv-location="$venv" || rc=$?
    rm -rf "$venv"
    return $rc
}

export -f job_lint_python job_test_js job_test_python job_build_wheel \
           job_test_mcp_wheel job_smoke_test_extras \
           job_playwright_storybook job_playwright_server job_playwright_marimo \
           job_playwright_wasm_marimo job_playwright_jupyter

# ── Phase 1: LintPython + TestJS + TestPython-3.13 (parallel) ────────────────
log "=== Phase 1: lint-python, test-js, test-python-3.13 (parallel) ==="

run_job lint-python         job_lint_python              & P1=$!
run_job test-js             job_test_js                  & P2=$!
run_job test-python-3.13   bash -c "job_test_python 3.13" & P3=$!

wait $P1 || OVERALL=1
wait $P2 || OVERALL=1
wait $P3 || OVERALL=1

# ── Phase 2: BuildWheel (after test-js to avoid JS build conflict) ────────────
log "=== Phase 2: build-wheel ==="
run_job build-wheel job_build_wheel || OVERALL=1

# ── Phase 3: TestPython 3.11/3.12/3.14 (parallel — separate venvs, no conflicts) ──
log "=== Phase 3: test-python 3.11/3.12/3.14 (parallel) ==="

run_job "test-python-3.11" bash -c "job_test_python 3.11" & P_311=$!
run_job "test-python-3.12" bash -c "job_test_python 3.12" & P_312=$!
run_job "test-python-3.14" bash -c "job_test_python 3.14" & P_314=$!

wait $P_311 || OVERALL=1
wait $P_312 || OVERALL=1
wait $P_314 || OVERALL=1

# ── Phase 4: TestMCPWheel + SmokeTestExtras (parallel, no port conflicts) ────
log "=== Phase 4: test-mcp-wheel + smoke-test-extras (parallel) ==="

run_job test-mcp-wheel      job_test_mcp_wheel     & P4=$!
run_job smoke-test-extras   job_smoke_test_extras  & P5=$!

wait $P4 || OVERALL=1
wait $P5 || OVERALL=1

# ── Phase 5a: Playwright (parallel — each binds to a distinct port) ──────────
# Ports: storybook=6006, server=8701, marimo=2718, wasm-marimo=8765
log "=== Phase 5a: Playwright storybook/server/marimo/wasm-marimo (parallel) ==="

run_job playwright-storybook    job_playwright_storybook    & P_sb=$!
run_job playwright-server       job_playwright_server       & P_srv=$!
run_job playwright-marimo       job_playwright_marimo       & P_mar=$!
run_job playwright-wasm-marimo  job_playwright_wasm_marimo  & P_wmar=$!

wait $P_sb   || OVERALL=1
wait $P_srv  || OVERALL=1
wait $P_mar  || OVERALL=1
wait $P_wmar || OVERALL=1

# ── Phase 5b: Jupyter (after 5a — PARALLEL=2 to balance speed vs JupyterLab stability) ─
log "=== Phase 5b: playwright-jupyter (port 8889, PARALLEL=2) ==="
run_job playwright-jupyter job_playwright_jupyter || OVERALL=1

# ── Final status ─────────────────────────────────────────────────────────────

if [[ $OVERALL -eq 0 ]]; then
    log "=== ALL JOBS PASSED ==="
    status_success "$SHA" "ci/hetzner" "All checks passed" "$LOG_URL"
    touch /opt/ci/last-success
else
    log "=== SOME JOBS FAILED — see $LOG_URL ==="
    status_failure "$SHA" "ci/hetzner" "CI failed — see logs" "$LOG_URL"
fi

exit $OVERALL
