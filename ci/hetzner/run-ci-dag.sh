#!/bin/bash
# CI orchestrator — DAG-based parallel execution.
#
# Drop-in replacement for run-ci.sh. Each job starts as soon as its specific
# dependencies are met, not when an entire phase completes.
#
# Dependency graph:
#   No dependencies (start immediately):
#     lint-python, build-js, test-python-{3.11,3.12,3.13,3.14},
#     playwright-storybook
#
#   Depends on build-js (needs tsc+vite output in dist/):
#     test-js       (jest, runs in parallel with build-wheel)
#     build-wheel   (esbuild + uv build, skips redundant pnpm install+build)
#
#   Depends on build-wheel (needs .whl):
#     test-mcp-wheel, smoke-test-extras, playwright-server, playwright-jupyter,
#     playwright-marimo, playwright-wasm-marimo
#
# Critical path: build-js (~12s) → build-wheel (~10s) → pw-jupyter (~90s) ≈ 112s

set -uo pipefail

SHA=${1:?usage: run-ci-dag.sh SHA BRANCH}
BRANCH=${2:?usage: run-ci-dag.sh SHA BRANCH}

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

job_build_js() {
    cd /repo/packages
    pnpm install --frozen-lockfile --store-dir /opt/pnpm-store
    cd buckaroo-js-core
    pnpm run build
}

job_test_js() {
    cd /repo/packages/buckaroo-js-core
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

    # mp_timeout tests use forkserver which takes >1s to spawn in Docker.
    # test_server_killed_on_parent_death relies on SIGKILL propagation that
    # behaves differently in container PID namespaces.
    # Both disabled here; tune once baseline timing is known.
    /opt/venvs/$v/bin/python -m pytest tests/unit -m "not slow" --color=yes \
        --deselect tests/unit/file_cache/mp_timeout_decorator_test.py::test_mp_timeout_pass \
        --deselect tests/unit/file_cache/mp_timeout_decorator_test.py::test_mp_fail_then_normal \
        --deselect "tests/unit/server/test_mcp_tool_cleanup.py::TestServerMonitor::test_server_killed_on_parent_death"
}

job_build_wheel() {
    cd /repo
    # build-js already ran pnpm install + pnpm build (tsc+vite).
    # We only need: copy CSS, esbuild anywidget+standalone, uv build.
    mkdir -p buckaroo/static
    cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css
    cd packages
    pnpm --filter buckaroo-widget run build
    pnpm --filter buckaroo-widget run build:standalone
    cd ..
    rm -rf dist || true
    uv build --wheel
}

job_test_mcp_wheel() {
    cd /repo
    local venv=/tmp/ci-mcp-$$
    rm -rf "$venv"
    uv venv "$venv" -q
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "${wheel}[mcp]" pytest -q
    BUCKAROO_MCP_CMD="$venv/bin/buckaroo-table" \
        "$venv/bin/pytest" \
            tests/unit/server/test_mcp_uvx_install.py \
            tests/unit/server/test_mcp_server_integration.py \
            -v --color=yes -m slow
    "$venv/bin/pytest" \
        tests/unit/server/test_mcp_uvx_install.py::TestUvxFailureModes \
        -v --color=yes -m slow
    rm -rf "$venv"
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
    # UV_PROJECT_ENVIRONMENT: reuse pre-synced 3.13 venv so `uv run marimo`
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
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
        bash scripts/test_playwright_jupyter.sh --venv-location="$venv"
    rm -rf "$venv"
}

export -f job_lint_python job_build_js job_test_js job_test_python job_build_wheel \
           job_test_mcp_wheel job_smoke_test_extras \
           job_playwright_storybook job_playwright_server job_playwright_marimo \
           job_playwright_wasm_marimo job_playwright_jupyter

# ── DAG execution ────────────────────────────────────────────────────────────
# build-js starts immediately alongside all other independent jobs.
# Once build-js completes, test-js and build-wheel start in parallel.
# Once build-wheel completes, wheel-dependent jobs start.

log "=== Starting all independent jobs ==="

run_job lint-python           job_lint_python                 & PID_LINT=$!
run_job build-js              job_build_js                    & PID_BUILDJS=$!
run_job test-python-3.11      bash -c "job_test_python 3.11"  & PID_PY311=$!
run_job test-python-3.12      bash -c "job_test_python 3.12"  & PID_PY312=$!
run_job test-python-3.13      bash -c "job_test_python 3.13"  & PID_PY313=$!
run_job test-python-3.14      bash -c "job_test_python 3.14"  & PID_PY314=$!
run_job playwright-storybook  job_playwright_storybook        & PID_PW_SB=$!

# ── Wait for build-js, then fork test-js + build-wheel in parallel ───────────

wait $PID_BUILDJS || OVERALL=1
log "=== build-js done — starting test-js + build-wheel ==="

run_job test-js   job_test_js     & PID_TESTJS=$!
run_job build-wheel job_build_wheel || OVERALL=1

# ── Wheel-dependent jobs ─────────────────────────────────────────────────────

log "=== build-wheel done — starting wheel-dependent jobs ==="

run_job test-mcp-wheel         job_test_mcp_wheel              & PID_MCP=$!
run_job smoke-test-extras      job_smoke_test_extras            & PID_SMOKE=$!
run_job playwright-server      job_playwright_server            & PID_PW_SV=$!
run_job playwright-jupyter     job_playwright_jupyter           & PID_PW_JP=$!
run_job playwright-marimo      job_playwright_marimo            & PID_PW_MA=$!
run_job playwright-wasm-marimo job_playwright_wasm_marimo       & PID_PW_WM=$!

# ── Wait for everything ─────────────────────────────────────────────────────

wait $PID_LINT    || OVERALL=1
wait $PID_TESTJS  || OVERALL=1
wait $PID_PY311   || OVERALL=1
wait $PID_PY312   || OVERALL=1
wait $PID_PY313   || OVERALL=1
wait $PID_PY314   || OVERALL=1
wait $PID_PW_SB   || OVERALL=1
wait $PID_MCP     || OVERALL=1
wait $PID_SMOKE   || OVERALL=1
wait $PID_PW_SV   || OVERALL=1
wait $PID_PW_JP   || OVERALL=1
wait $PID_PW_MA   || OVERALL=1
wait $PID_PW_WM   || OVERALL=1

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
