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

# ── CPU monitoring ────────────────────────────────────────────────────────────
# Sample CPU every 0.1s for fine-grain contention analysis.
vmstat -n 1 > "$RESULTS_DIR/cpu.log" 2>&1 &
CPU_MONITOR_PID=$!
# Fine-grain /proc/stat sampling at 100ms for sub-second resolution
(
while true; do
    ts=$(date +%s.%N)
    read -r _ user nice system idle iowait irq softirq steal _ _ < /proc/stat
    total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    busy=$((total - idle - iowait))
    echo "$ts $busy $total"
    sleep 0.1
done
) > "$RESULTS_DIR/cpu-fine.log" 2>&1 &
CPU_FINE_PID=$!

# CI timeout watchdog — kill everything if CI exceeds time limit.
CI_TIMEOUT=${CI_TIMEOUT:-210}
( sleep "$CI_TIMEOUT"; echo "[$(date +'%H:%M:%S')] TIMEOUT: CI exceeded ${CI_TIMEOUT}s" >> "$RESULTS_DIR/ci.log"; kill -TERM 0 ) 2>/dev/null &
WATCHDOG_PID=$!

# ── Pre-run cleanup — kill stale processes, remove temp files from prior runs ─
# This ensures each CI run starts from a clean state regardless of how the
# previous run ended (timeout, crash, manual kill, etc.).
pkill -f jupyter-lab 2>/dev/null || true
pkill -f playwright 2>/dev/null || true
pkill -f chromium 2>/dev/null || true
pkill -f "node.*storybook" 2>/dev/null || true
pkill -f "npm exec serve" 2>/dev/null || true
rm -rf /tmp/ci-jupyter-warmup* /tmp/pw-jupyter-parallel* /tmp/pw-html-* 2>/dev/null || true
rm -f /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids 2>/dev/null || true

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

# ── JS build cache ──────────────────────────────────────────────────────────
JS_CACHE_DIR=/opt/ci/js-cache
JS_TREE_HASH=$(git ls-tree -r HEAD \
    packages/buckaroo-js-core/src/ \
    packages/buckaroo-js-core/package.json \
    packages/buckaroo-js-core/tsconfig.json \
    packages/buckaroo-js-core/vite.config.ts \
    2>/dev/null | sha256sum | cut -c1-16)

if [[ -d "$JS_CACHE_DIR/$JS_TREE_HASH" ]]; then
    cp -r "$JS_CACHE_DIR/$JS_TREE_HASH" packages/buckaroo-js-core/dist
    log "JS build cache HIT ($JS_TREE_HASH)"
    export JS_DIST_CACHED=1
else
    log "JS build cache MISS ($JS_TREE_HASH)"
    export JS_DIST_CACHED=0
fi

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
    if [[ "${JS_DIST_CACHED:-0}" != "1" ]]; then
        pnpm run build
        # Cache for future runs
        mkdir -p "$JS_CACHE_DIR"
        rm -rf "$JS_CACHE_DIR/$JS_TREE_HASH"
        cp -r dist "$JS_CACHE_DIR/$JS_TREE_HASH"
        log "JS build cached ($JS_TREE_HASH)"
    else
        log "JS build skipped (cache hit)"
    fi
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
    local pids=() names=() rc=0
    for extra in base polars mcp marimo jupyterlab notebook; do
        (
            cd /repo
            venv=/tmp/ci-smoke-${extra}-$$
            rm -rf "$venv"
            uv venv "$venv" -q
            if [[ "$extra" == "base" ]]; then
                uv pip install --python "$venv/bin/python" "$wheel" -q
            else
                uv pip install --python "$venv/bin/python" "${wheel}[${extra}]" -q
            fi
            "$venv/bin/python" scripts/smoke_test.py "$extra"
            rm -rf "$venv"
        ) &
        pids+=($!)
        names+=("$extra")
    done
    for i in "${!pids[@]}"; do
        if ! wait "${pids[$i]}"; then
            echo "FAIL: smoke-${names[$i]}"
            rc=1
        fi
    done
    return $rc
}

job_playwright_storybook() {
    cd /repo
    SKIP_INSTALL=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-storybook-$$ \
        bash scripts/test_playwright_storybook.sh
}

job_playwright_server() {
    cd /repo
    SKIP_INSTALL=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-server-$$ \
        bash scripts/test_playwright_server.sh
}

job_playwright_marimo() {
    cd /repo
    # UV_PROJECT_ENVIRONMENT: reuse the pre-synced 3.13 venv so `uv run marimo`
    # doesn't race with other jobs creating /repo/.venv from scratch.
    SKIP_INSTALL=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
        bash scripts/test_playwright_marimo.sh
}

job_playwright_wasm_marimo() {
    cd /repo
    # Same rationale as job_playwright_marimo.
    SKIP_INSTALL=1 \
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
    PARALLEL=4 \
        bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" --venv-location="$venv" || rc=$?
    rm -rf "$venv"
    return $rc
}

job_jupyter_warmup() {
    cd /repo
    local venv=/tmp/ci-jupyter-warmup
    rm -rf "$venv"
    uv venv "$venv" --python 3.13 -q
    uv pip install --python "$venv/bin/python" \
        jupyterlab anywidget polars websocket-client -q
    source "$venv/bin/activate"

    # Save venv path for later phases
    echo "$venv" > /tmp/ci-jupyter-warmup-venv

    export JUPYTER_TOKEN="test-token-12345"
    local BASE_PORT=8889 PARALLEL=${JUPYTER_PARALLEL:-6}

    # Clean stale state
    rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
    rm -f ~/.local/share/jupyter/runtime/kernel-*.json 2>/dev/null || true
    rm -f ~/.local/share/jupyter/runtime/jpserver-*.json 2>/dev/null || true
    rm -f ~/.local/share/jupyter/runtime/jpserver-*.html 2>/dev/null || true

    # Kill stale processes on target ports
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        fuser -k $port/tcp 2>/dev/null || true
    done

    # Start $PARALLEL JupyterLab servers sequentially
    local pids=()
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        jupyter lab --no-browser --port="$port" \
            --ServerApp.token="$JUPYTER_TOKEN" \
            --ServerApp.allow_origin='*' \
            --ServerApp.disable_check_xsrf=True \
            --allow-root \
            >/tmp/jupyter-port${port}.log 2>&1 &
        pids+=($!)
        local started=false
        for i in $(seq 1 30); do
            curl -sf "http://localhost:${port}/api?token=${JUPYTER_TOKEN}" >/dev/null 2>&1 && { started=true; break; }
            sleep 1
        done
        if [ "$started" = false ]; then
            echo "JupyterLab on port $port failed to start"
            cat "/tmp/jupyter-port${port}.log" || true
            return 1
        fi
        echo "JupyterLab ready on port $port (slot $slot)"
    done

    # Save PIDs for cleanup
    echo "${pids[*]}" > /tmp/ci-jupyter-warmup-pids

    # Pre-warm Python bytecaches
    python3 -c "import buckaroo; import pandas; import polars" 2>/dev/null || \
    python3 -c "import pandas; import polars; print('Pre-warm (no buckaroo yet)')" 2>/dev/null || true

    # WebSocket kernel warmup (all 4 in parallel)
    local warmup_pids=()
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        python3 -c "
import json, sys, time, urllib.request, websocket

port = $port
token = '$JUPYTER_TOKEN'
base = f'http://localhost:{port}'

req = urllib.request.Request(
    f'{base}/api/kernels?token={token}',
    data=b'{}',
    headers={'Content-Type': 'application/json'},
    method='POST',
)
resp = urllib.request.urlopen(req)
kid = json.loads(resp.read())['id']
print(f'  kernel {kid[:8]}... created on port {port}')

ws_url = f'ws://localhost:{port}/api/kernels/{kid}/channels?token={token}'
ws = websocket.create_connection(ws_url, timeout=90)

deadline = time.time() + 90
state = 'unknown'
while time.time() < deadline:
    ws.settimeout(max(1, deadline - time.time()))
    try:
        msg = json.loads(ws.recv())
    except (websocket.WebSocketTimeoutException, TimeoutError):
        break
    if msg.get('msg_type') == 'status':
        state = msg.get('content', {}).get('execution_state', 'unknown')
        if state == 'idle':
            break

ws.close()
print(f'  kernel {kid[:8]}... on port {port} reached state: {state}')

try:
    req = urllib.request.Request(
        f'{base}/api/kernels/{kid}?token={token}', method='DELETE')
    urllib.request.urlopen(req)
except Exception:
    pass

sys.exit(0 if state == 'idle' else 1)
" 2>&1 &
        warmup_pids+=($!)
    done

    local warmup_ok=true
    for pid in "${warmup_pids[@]}"; do
        if ! wait "$pid"; then warmup_ok=false; fi
    done
    if [ "$warmup_ok" = true ]; then
        echo "All $PARALLEL kernel warmups complete"
    else
        echo "WARNING: some kernel warmups failed — continuing anyway"
    fi

    # Copy + trust notebooks
    local notebooks=(test_buckaroo_widget.ipynb test_buckaroo_infinite_widget.ipynb
        test_polars_widget.ipynb test_polars_infinite_widget.ipynb
        test_dfviewer.ipynb test_dfviewer_infinite.ipynb
        test_polars_dfviewer.ipynb test_polars_dfviewer_infinite.ipynb
        test_infinite_scroll_transcript.ipynb)
    for nb in "${notebooks[@]}"; do
        cp "tests/integration_notebooks/$nb" "$nb"
        jupyter trust "$nb" 2>/dev/null || true
    done

    # Clean workspaces after trust
    rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true

    deactivate
}

export JS_CACHE_DIR JS_TREE_HASH
export -f job_lint_python job_test_js job_test_python job_build_wheel \
           job_test_mcp_wheel job_smoke_test_extras \
           job_playwright_storybook job_playwright_server job_playwright_marimo \
           job_playwright_wasm_marimo job_playwright_jupyter job_jupyter_warmup

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

    # ── Wave 0: Minimal jobs — only what's needed on the critical path ──────
    # Run one pytest (3.13) for fast signal. Delay 3.11/3.12/3.14 to reduce
    # CPU contention during Wave 0 — they start 5s after wheel-dependent jobs.
    log "=== Starting Wave 0 ==="

    # renice after fork: -10 = critical path, 10 = background work
    # (nice can't run shell functions; renice changes priority of running PID)
    run_job lint-python            job_lint_python                & PID_LINT=$!
    renice -n 10 -p $PID_LINT >/dev/null 2>&1 || true
    run_job test-js                job_test_js                    & PID_TESTJS=$!
    renice -n -10 -p $PID_TESTJS >/dev/null 2>&1 || true
    run_job test-python-3.13       bash -c "job_test_python 3.13" & PID_PY313=$!
    renice -n 10 -p $PID_PY313 >/dev/null 2>&1 || true
    run_job playwright-storybook   job_playwright_storybook       & PID_PW_SB=$!
    renice -n 10 -p $PID_PW_SB >/dev/null 2>&1 || true
    # Early kernel warmup — venv + 4 JupyterLab servers + kernel warmup while
    # heavyweight jobs are running. Finishes by ~t=20s, long before wheel is ready.
    run_job jupyter-warmup         job_jupyter_warmup             & PID_WARMUP=$!
    renice -n 10 -p $PID_WARMUP >/dev/null 2>&1 || true

    # ── Wait for test-js only, then build wheel ──────────────────────────────
    wait $PID_TESTJS || OVERALL=1
    log "=== test-js done — starting build-wheel ==="

    run_job build-wheel job_build_wheel || OVERALL=1

    # Cache wheel by current SHA so --phase=5b / --wheel-from can reuse it.
    mkdir -p "/opt/ci/wheel-cache/$SHA"
    cp dist/buckaroo-*.whl "/opt/ci/wheel-cache/$SHA/" 2>/dev/null || true
    log "Cached wheel → /opt/ci/wheel-cache/$SHA"

    # ── Install wheel into warm jupyter venv ─────────────────────────────────
    wait $PID_WARMUP || OVERALL=1
    log "=== jupyter-warmup done — installing wheel into warm venv ==="
    JUPYTER_VENV=$(cat /tmp/ci-jupyter-warmup-venv)
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$JUPYTER_VENV/bin/python" "$wheel" -q
    "$JUPYTER_VENV/bin/python" -c "import buckaroo; import pandas; import polars" 2>/dev/null || true

    # ── Wheel-dependent jobs — staggered sub-waves (Exp 33) ──────────────────
    # pw-jupyter is the critical path; start it FIRST with all pre-warmed servers.
    # Then stagger remaining jobs every 5s to let pw-jupyter claim CPU headroom
    # during its initial Chromium launch + first batch of tests.
    JUPYTER_PARALLEL=${JUPYTER_PARALLEL:-6}
    log "=== build-wheel done — starting staggered wheel-dependent jobs (PARALLEL=$JUPYTER_PARALLEL) ==="

    # t+0: pw-jupyter (critical path — uses pre-warmed servers)
    job_playwright_jupyter_warm() {
        cd /repo
        local venv
        venv=$(cat /tmp/ci-jupyter-warmup-venv)
        local rc=0
        ROOT_DIR=/repo \
        PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
        PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
        PARALLEL=$JUPYTER_PARALLEL \
        BASE_PORT=8889 \
            timeout 120 bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" \
                --venv-location="$venv" --servers-running || rc=$?
        # Cleanup servers + venv
        for pid in $(cat /tmp/ci-jupyter-warmup-pids 2>/dev/null); do
            kill "$pid" 2>/dev/null || true
        done
        rm -rf "$venv"
        rm -f /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids
        return $rc
    }
    export -f job_playwright_jupyter_warm
    run_job playwright-jupyter   job_playwright_jupyter_warm & PID_PW_JP=$!

    # Also start lightweight jobs that won't compete much (nice 10 = lower priority)
    run_job test-mcp-wheel       job_test_mcp_wheel       & PID_MCP=$!
    renice -n 10 -p $PID_MCP >/dev/null 2>&1 || true
    run_job smoke-test-extras    job_smoke_test_extras     & PID_SMOKE=$!
    renice -n 10 -p $PID_SMOKE >/dev/null 2>&1 || true

    # t+5s: pw-marimo
    sleep 5
    run_job playwright-marimo    job_playwright_marimo      & PID_PW_MA=$!
    renice -n 10 -p $PID_PW_MA >/dev/null 2>&1 || true

    # t+10s: pw-wasm-marimo
    sleep 5
    run_job playwright-wasm-marimo job_playwright_wasm_marimo & PID_PW_WM=$!
    renice -n 10 -p $PID_PW_WM >/dev/null 2>&1 || true

    # t+15s: pw-server
    sleep 5
    run_job playwright-server    job_playwright_server     & PID_PW_SV=$!
    renice -n 10 -p $PID_PW_SV >/dev/null 2>&1 || true

    # t+20s: pytest 3.11/3.12/3.14 (3.13 already ran in Wave 0)
    sleep 5
    run_job test-python-3.11       bash -c "job_test_python 3.11" & PID_PY311=$!
    renice -n 10 -p $PID_PY311 >/dev/null 2>&1 || true
    run_job test-python-3.12       bash -c "job_test_python 3.12" & PID_PY312=$!
    renice -n 10 -p $PID_PY312 >/dev/null 2>&1 || true
    run_job test-python-3.14       bash -c "job_test_python 3.14" & PID_PY314=$!
    renice -n 10 -p $PID_PY314 >/dev/null 2>&1 || true

    # ── Wait for all jobs ─────────────────────────────────────────────────────
    wait $PID_LINT    || OVERALL=1
    wait $PID_PY313   || OVERALL=1
    wait $PID_PY311   || OVERALL=1
    wait $PID_PY312   || OVERALL=1
    wait $PID_PY314   || OVERALL=1
    wait $PID_PW_SB   || OVERALL=1
    wait $PID_PW_WM   || OVERALL=1
    wait $PID_MCP     || OVERALL=1
    wait $PID_SMOKE   || OVERALL=1
    wait $PID_PW_SV   || OVERALL=1
    wait $PID_PW_MA   || OVERALL=1
    wait $PID_PW_JP   || OVERALL=1

fi

# ── Stop monitors ────────────────────────────────────────────────────────────
kill $WATCHDOG_PID 2>/dev/null || true
kill $CPU_MONITOR_PID 2>/dev/null || true
kill $CPU_FINE_PID 2>/dev/null || true

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
