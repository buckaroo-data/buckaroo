#!/bin/bash
# CI orchestrator — runs inside the buckaroo-ci Docker container.
#
# Called by webhook.py via:
#   docker exec -e GITHUB_TOKEN=... -e GITHUB_REPO=... buckaroo-ci \
#     bash /repo/ci/hetzner/run-ci.sh <sha> <branch> [--phase=PHASE] [--wheel-from=SHA]
#
# --phase=all        Run all jobs (default, DAG-scheduled)
# --phase=5b         Skip to playwright-jupyter only, using cached wheel.
# --wheel-from=SHA   Use wheel cached from a different commit (for iterating
#                    on test code without rebuilding). Falls back to $SHA.
#
# DAG execution (each captures stdout/stderr to $RESULTS_DIR/<job>.log):
#   Immediate:     lint-python, test-js, test-python-3.{11,12,13,14},
#                  playwright-storybook, playwright-wasm-marimo
#   After test-js: build-wheel  → wheel cached to /opt/ci/wheel-cache/$SHA/
#   After wheel:   test-mcp-wheel, smoke-test-extras, playwright-server,
#                  playwright-marimo (needs real widget.js from build),
#                  playwright-jupyter (PARALLEL=1, isolated JupyterLab)

set -uo pipefail

SHA=${1:?usage: run-ci.sh SHA BRANCH [--phase=PHASE]}
BRANCH=${2:?usage: run-ci.sh SHA BRANCH [--phase=PHASE]}

PHASE=all
WHEEL_FROM=""
for arg in "${@:3}"; do
    case "$arg" in
        --phase=*) PHASE="${arg#*=}" ;;
        --wheel-from=*) WHEEL_FROM="${arg#*=}" ;;
    esac
done

REPO_DIR=/repo
RESULTS_DIR=/opt/ci/logs/$SHA
WHEEL_CACHE_DIR=/opt/ci/wheel-cache/${WHEEL_FROM:-$SHA}
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

status_pending "$SHA" "ci/hetzner" "Running CI (phase=$PHASE)..." "$LOG_URL"

RUNNER_VERSION=$(cat "$CI_RUNNER_DIR/VERSION" 2>/dev/null || echo "unknown")
log "CI runner: $RUNNER_VERSION  phase=$PHASE"
log "Checkout $SHA (branch: $BRANCH)"
cd "$REPO_DIR"
git fetch origin
git checkout -f "$SHA"
# Clean untracked/ignored files; preserve warm caches in node_modules.
git clean -fdx \
    --exclude='packages/buckaroo-js-core/node_modules' \
    --exclude='packages/js/node_modules' \
    --exclude='packages/node_modules'

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
    # Files ignored: multiprocessing and server-subprocess tests fail under
    # DAG concurrency (12 simultaneous jobs). Covered by test-mcp-wheel job
    # which runs server integration tests in isolation with the built wheel.
    /opt/venvs/$v/bin/python -m pytest tests/unit -m "not slow" --color=yes \
        -n 4 --dist load \
        --ignore=tests/unit/file_cache/mp_timeout_decorator_test.py \
        --ignore=tests/unit/file_cache/multiprocessing_executor_test.py \
        --ignore=tests/unit/server/test_mcp_server_integration.py \
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
    PARALLEL=3 \
        bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" --venv-location="$venv" || rc=$?
    rm -rf "$venv"
    return $rc
}

export -f job_lint_python job_test_js job_test_python job_build_wheel \
           job_test_mcp_wheel job_smoke_test_extras \
           job_playwright_storybook job_playwright_server job_playwright_marimo \
           job_playwright_wasm_marimo job_playwright_jupyter

# ── Phase routing ─────────────────────────────────────────────────────────────

if [[ "$PHASE" == "5b" ]]; then

    # ── Standalone Phase 5b — uses cached wheel from a prior full run ─────────
    wheel_path=$(ls "$WHEEL_CACHE_DIR"/buckaroo-*.whl 2>/dev/null | head -1)
    if [[ -z "$wheel_path" ]]; then
        log "ERROR: no cached wheel at $WHEEL_CACHE_DIR"
        log "Run full CI first: run-ci.sh $SHA $BRANCH"
        status_failure "$SHA" "ci/hetzner" "No cached wheel — run full CI first" "$LOG_URL"
        exit 1
    fi
    mkdir -p dist
    cp "$wheel_path" dist/
    log "Loaded cached wheel: $(basename "$wheel_path")"

    # Extract compiled static assets from the wheel so source-path `import
    # buckaroo` works correctly. git clean removed buckaroo/static/; anywidget
    # resolves asset paths relative to __file__ in the source tree.
    python3 -c "
import zipfile, glob
wheel = glob.glob('dist/buckaroo-*.whl')[0]
with zipfile.ZipFile(wheel) as z:
    for name in z.namelist():
        if name.startswith('buckaroo/static/'):
            z.extract(name, '.')
print('Extracted static files from wheel')
" 2>/dev/null || true

    log "=== Phase 5b (standalone): playwright-jupyter ==="
    run_job playwright-jupyter job_playwright_jupyter || OVERALL=1

else

    # ── Full CI (all phases) ──────────────────────────────────────────────────

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

    # ── Wave 0: All independent jobs (no deps — start immediately) ──────────
    log "=== Starting all independent jobs ==="

    run_job lint-python            job_lint_python                & PID_LINT=$!
    run_job test-js                job_test_js                    & PID_TESTJS=$!
    run_job test-python-3.11       bash -c "job_test_python 3.11" & PID_PY311=$!
    run_job test-python-3.12       bash -c "job_test_python 3.12" & PID_PY312=$!
    run_job test-python-3.13       bash -c "job_test_python 3.13" & PID_PY313=$!
    run_job test-python-3.14       bash -c "job_test_python 3.14" & PID_PY314=$!
    run_job playwright-storybook   job_playwright_storybook       & PID_PW_SB=$!
    run_job playwright-wasm-marimo job_playwright_wasm_marimo     & PID_PW_WM=$!

    # ── Wait for test-js only, then build wheel ──────────────────────────────
    wait $PID_TESTJS || OVERALL=1
    log "=== test-js done — starting build-wheel ==="

    run_job build-wheel job_build_wheel || OVERALL=1

    # Cache wheel by current SHA so --phase=5b / --wheel-from can reuse it.
    mkdir -p "/opt/ci/wheel-cache/$SHA"
    cp dist/buckaroo-*.whl "/opt/ci/wheel-cache/$SHA/" 2>/dev/null || true
    log "Cached wheel → /opt/ci/wheel-cache/$SHA"

    # ── Wheel-dependent jobs (start as soon as wheel exists) ─────────────────
    log "=== build-wheel done — starting wheel-dependent jobs ==="

    run_job test-mcp-wheel       job_test_mcp_wheel       & PID_MCP=$!
    run_job smoke-test-extras    job_smoke_test_extras     & PID_SMOKE=$!
    run_job playwright-server    job_playwright_server     & PID_PW_SV=$!
    # playwright-marimo needs the real widget.js produced by build-wheel
    # (the empty stub from `touch` won't render). Runs here, not in Wave 0.
    run_job playwright-marimo    job_playwright_marimo      & PID_PW_MA=$!

    # pw-jupyter needs maximum CPU headroom — wait for ALL other jobs first.
    # playwright-server (58s) used to overlap, causing random 1/9 failures.
    wait $PID_PW_MA  || OVERALL=1
    wait $PID_PW_WM  || OVERALL=1
    wait $PID_LINT    || OVERALL=1
    wait $PID_PY311   || OVERALL=1
    wait $PID_PY312   || OVERALL=1
    wait $PID_PY313   || OVERALL=1
    wait $PID_PY314   || OVERALL=1
    wait $PID_PW_SB   || OVERALL=1
    wait $PID_MCP     || OVERALL=1
    wait $PID_SMOKE   || OVERALL=1
    wait $PID_PW_SV   || OVERALL=1
    log "=== all other jobs done — starting playwright-jupyter ==="
    run_job playwright-jupyter   job_playwright_jupyter    & PID_PW_JP=$!

    # ── Wait for jupyter ──────────────────────────────────────────────────────
    wait $PID_PW_JP   || OVERALL=1

fi

# ── Final status ─────────────────────────────────────────────────────────────

if [[ $OVERALL -eq 0 ]]; then
    log "=== ALL JOBS PASSED (phase=$PHASE) ==="
    status_success "$SHA" "ci/hetzner" "All checks passed" "$LOG_URL"
    touch /opt/ci/last-success
else
    log "=== SOME JOBS FAILED — see $LOG_URL ==="
    status_failure "$SHA" "ci/hetzner" "CI failed — see logs" "$LOG_URL"
fi

exit $OVERALL
