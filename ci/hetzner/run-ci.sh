#!/bin/bash
# CI orchestrator — runs inside the buckaroo-ci Docker container.
#
# Called by webhook.py via:
#   docker exec -e GITHUB_TOKEN=... -e GITHUB_REPO=... buckaroo-ci \
#     bash /repo/ci/hetzner/run-ci.sh <sha> <branch> [--phase=PHASE] [--wheel-from=SHA]
#
# --phase=all          Run all jobs (default, DAG-scheduled)
# --phase=5b           Skip to playwright-jupyter only, using cached wheel.
# --wheel-from=SHA     Use wheel cached from a different commit (for iterating
#                      on test code without rebuilding). Falls back to $SHA.
# --fast-fail          Abort after build-js or build-wheel failure.
# --only-jobs=JOB,JOB  Run only listed jobs (comma-separated). Dependencies
#                      not auto-resolved — include build-js,build-wheel,etc.
# --skip-jobs=JOB,JOB  Skip listed jobs. Safer than --only for ad-hoc filtering.
# --only=JOB,JOB       Alias for --only-jobs (backward compat).
# --skip=JOB,JOB       Alias for --skip-jobs (backward compat).
# --only-testcases=PAT  Run ONLY matching test cases within jobs. Comma-separated.
#                       pytest: -k "pat1 or pat2"; Playwright: --grep "pat1|pat2"
# --first-jobs=JOB,JOB  Run these jobs FIRST (Phase A), then all remaining (Phase B).
#                       With --fast-fail, stops after Phase A failure.
# --first-testcases=PAT Run matching testcases first, then full suite per job.
#                       With --fast-fail, skip full suite if filtered run fails.
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
FAST_FAIL=0
ONLY_JOBS=""
SKIP_JOBS=""
ONLY_TESTCASES=""
FIRST_JOBS=""
FIRST_TESTCASES=""
for arg in "${@:3}"; do
    case "$arg" in
        --phase=*) PHASE="${arg#*=}" ;;
        --wheel-from=*) WHEEL_FROM="${arg#*=}" ;;
        --fast-fail) FAST_FAIL=1 ;;
        --only-jobs=*|--only=*) ONLY_JOBS="${arg#*=}" ;;
        --skip-jobs=*|--skip=*) SKIP_JOBS="${arg#*=}" ;;
        --only-testcases=*) ONLY_TESTCASES="${arg#*=}" ;;
        --first-jobs=*) FIRST_JOBS="${arg#*=}" ;;
        --first-testcases=*) FIRST_TESTCASES="${arg#*=}" ;;
    esac
done

# Mutual exclusion checks
if [[ -n "$FIRST_JOBS" && -n "$ONLY_JOBS" ]]; then
    echo "ERROR: --first-jobs and --only-jobs are mutually exclusive" >&2; exit 1
fi
if [[ -n "$FIRST_TESTCASES" && -n "$ONLY_TESTCASES" ]]; then
    echo "ERROR: --first-testcases and --only-testcases are mutually exclusive" >&2; exit 1
fi

# Ensure all pnpm commands in this run use the same store dir, preventing
# node_modules re-linking when pnpm detects a storeDir mismatch between
# build-js (--store-dir /opt/pnpm-store) and full_build.sh (no flag).
export npm_config_store_dir=/opt/pnpm-store

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

# Capture exact package versions for reproducibility debugging.
if [[ -x "$CI_RUNNER_DIR/capture-versions.sh" ]]; then
    bash "$CI_RUNNER_DIR/capture-versions.sh" > "$RESULTS_DIR/versions.txt" 2>&1
fi

# Job filtering: --only-jobs / --skip-jobs / --first-jobs (phase-aware).
# Dependencies are NOT auto-resolved — include build-js,build-wheel,jupyter-warmup
# manually if you --only-jobs a job that depends on them.
# FIRST_JOBS_PHASE: set to "A" or "B" by run_dag() for --first-jobs support.
FIRST_JOBS_PHASE=""
should_run() {
    local name=$1
    if [[ -n "$ONLY_JOBS" ]]; then
        [[ ",$ONLY_JOBS," == *",$name,"* ]] && return 0 || return 1
    fi
    if [[ -n "$SKIP_JOBS" ]]; then
        [[ ",$SKIP_JOBS," == *",$name,"* ]] && return 1 || return 0
    fi
    if [[ -n "$FIRST_JOBS" ]]; then
        local is_first=0
        [[ ",$FIRST_JOBS," == *",$name,"* ]] && is_first=1
        if [[ "$FIRST_JOBS_PHASE" == "A" ]]; then
            # Phase A: only first-jobs run
            [[ $is_first -eq 1 ]] && return 0 || return 1
        elif [[ "$FIRST_JOBS_PHASE" == "B" ]]; then
            # Phase B: only non-first-jobs run (first-jobs already ran)
            [[ $is_first -eq 0 ]] && return 0 || return 1
        fi
    fi
    return 0
}

# Testcase filter helpers: convert comma-separated patterns to pytest -k / PW --grep.
pytest_k_expr() { [[ -z "${1:-}" ]] && return; echo "${1//,/ or }"; }
pw_grep_expr()  { [[ -z "${1:-}" ]] && return; echo "${1//,/|}"; }

# maybe_renice: wraps renice; skipped when DISABLE_RENICE=1 (Exp 60).
maybe_renice() { [[ "${DISABLE_RENICE:-0}" == "1" ]] && return 0; renice "$@" >/dev/null 2>&1 || true; }

# Run a job: captures output, returns exit code. Skips if filtered out.
# run_job <name> <cmd> [args...]
run_job() {
    local name=$1; shift
    if ! should_run "$name"; then
        log "SKIP  $name (filtered)"
        return 0
    fi
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

# ── Container state snapshot (for b2b contamination debugging) ────────────────
snapshot_container_state() {
    local label=$1 outfile=$2
    {
        echo "=== Container snapshot: $label at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
        echo ""
        echo "--- Processes (ps aux --sort=-rss) ---"
        ps aux --sort=-rss 2>/dev/null || true
        echo ""
        echo "--- /tmp listing ---"
        ls -la /tmp/ 2>/dev/null || true
        echo ""
        echo "--- /dev/shm ---"
        ls -la /dev/shm/ 2>/dev/null || true
        echo ""
        echo "--- TCP sockets ---"
        cat /proc/net/tcp 2>/dev/null | awk 'NR>1 {
            cmd="printf \"%d\" 0x" substr($2, index($2,":")+1)
            cmd | getline port; close(cmd)
            if($4=="01") st="ESTABLISHED"; else if($4=="06") st="TIME_WAIT"; else st=$4
            printf "%s port=%d\n", st, port
        }' | sort | uniq -c | sort -rn || true
        echo ""
        echo "--- Jupyter runtime ---"
        ls -la ~/.local/share/jupyter/runtime/ 2>/dev/null || echo "(empty)"
        echo ""
        echo "--- Jupyter workspaces ---"
        ls -la ~/.jupyter/lab/workspaces/ 2>/dev/null || echo "(none)"
        cat ~/.jupyter/lab/workspaces/*.jupyterlab-workspace 2>/dev/null || true
        echo ""
        echo "--- Memory ---"
        free -m 2>/dev/null || cat /proc/meminfo | head -5
        echo ""
    } > "$outfile" 2>&1
}

# ── Setup ────────────────────────────────────────────────────────────────────

# Snapshot BEFORE cleanup — see what the previous run left behind.
snapshot_container_state "before-cleanup" "$RESULTS_DIR/container-before.txt"

# ── Pre-run cleanup — kill stale processes, remove temp files from prior runs ─
# This ensures each CI run starts from a clean state regardless of how the
# previous run ended (timeout, crash, manual kill, etc.).
# ci_pkill: pkill -f excluding our own PID. Without this, patterns like 'marimo'
# match our args (e.g. --skip=playwright-wasm-marimo) and kill the CI script.
ci_pkill() {
    local pids
    pids=$(pgrep -f "$1" | grep -v "^$$\$") || true
    [[ -n "$pids" ]] && echo "$pids" | xargs kill -9 2>/dev/null || true
}
ci_pkill 'chromium|chrome'
ci_pkill 'jupyter'
ci_pkill 'node.*playwright'
ci_pkill 'marimo'
ci_pkill jupyter-lab
ci_pkill ipykernel
ci_pkill "node.*storybook"
ci_pkill "npm exec serve"
ci_pkill esbuild
ci_pkill 'buckaroo.server'
# Kill anything on known service ports (jupyter 8889-8897, marimo 2718, storybook 6006, buckaroo-server 8701)
for port in 8889 8890 8891 8892 8893 8894 8895 8896 8897 2718 6006 8701; do
    fuser -k $port/tcp 2>/dev/null || true
done
sleep 1  # let processes die before cleaning their files
# Clean temp files from CI jobs
rm -rf /tmp/ci-jupyter-* /tmp/pw-* /tmp/.org.chromium.* 2>/dev/null || true
rm -f /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids 2>/dev/null || true
# Clean ALL JupyterLab log files (accumulate across runs with PID suffixes)
rm -f /tmp/jupyter-port*.log 2>/dev/null || true
# Clean per-port workspace temp dirs
rm -rf /tmp/jlab-ws-* 2>/dev/null || true
# Clean small temp files left by pytest/jupyter
rm -f /tmp/tmp*.txt 2>/dev/null || true
# Clean Playwright artifact directories
rm -rf /tmp/playwright-artifacts-* /tmp/playwright_chromiumdev_profile-* 2>/dev/null || true
# Clean JupyterLab workspace + kernel state — stale workspace files from previous
# runs cause JupyterLab to try reconnecting dead kernels, hanging Shift+Enter.
rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/kernel-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.html 2>/dev/null || true
# Clean any IPython/Jupyter caches that might affect kernel startup
rm -rf ~/.ipython/profile_default/db 2>/dev/null || true
rm -rf ~/.local/share/jupyter/nbsignatures.db 2>/dev/null || true

# Snapshot AFTER cleanup — verify we're starting clean.
snapshot_container_state "after-cleanup" "$RESULTS_DIR/container-after.txt"

status_pending "$SHA" "ci/hetzner" "Running CI (phase=$PHASE)..." "$LOG_URL"

# ── CPU monitoring ────────────────────────────────────────────────────────────
# Sample CPU every 0.1s for fine-grain contention analysis.
vmstat -n 1 > "$RESULTS_DIR/cpu.log" 2>&1 &
CPU_MONITOR_PID=$!
# Fine-grain /proc/stat sampling at 100ms for sub-second resolution.
# Appends with a RUN marker so multiple runs of the same SHA are preserved.
echo "# RUN $(date +%s)" >> "$RESULTS_DIR/cpu-fine.log"
(
while true; do
    ts=$(date +%s.%N)
    read -r _ user nice system idle iowait irq softirq steal _ _ < /proc/stat
    total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    busy=$((total - idle - iowait))
    echo "$ts $busy $total $iowait"
    sleep 0.1
done
) >> "$RESULTS_DIR/cpu-fine.log" 2>&1 &
CPU_FINE_PID=$!

# CI timeout watchdog — kill everything if CI exceeds time limit.
CI_TIMEOUT=${CI_TIMEOUT:-180}
( sleep "$CI_TIMEOUT"; echo "[$(date +'%H:%M:%S')] TIMEOUT: CI exceeded ${CI_TIMEOUT}s" >> "$RESULTS_DIR/ci.log"; kill -TERM 0 ) 2>/dev/null &
WATCHDOG_PID=$!

RUNNER_VERSION=$(cat "$CI_RUNNER_DIR/VERSION" 2>/dev/null || echo "unknown")
log "CI runner: $RUNNER_VERSION  phase=$PHASE${ONLY_JOBS:+  only-jobs=$ONLY_JOBS}${SKIP_JOBS:+  skip-jobs=$SKIP_JOBS}${FIRST_JOBS:+  first-jobs=$FIRST_JOBS}${ONLY_TESTCASES:+  only-tc=$ONLY_TESTCASES}${FIRST_TESTCASES:+  first-tc=$FIRST_TESTCASES}"
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

job_build_js() {
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
    # pytest-xdist may not be in older commits' lockfiles — force-install it
    # so -n 4 --dist load always works.
    uv pip install --python "/opt/venvs/$v/bin/python" pytest-xdist -q 2>/dev/null || true

    # 3.14 is still alpha — segfaults on pytest startup; skip for now.
    if [[ "$v" == "3.14" ]]; then
        echo "[skip] Python 3.14 alpha known to segfault — skipping pytest"
        return 0
    fi

    # Ignored in Docker — require forkserver/spawn multiprocessing which behaves
    # differently inside container PID namespaces and takes >1s to spawn.
    local common_ignores=(
        --ignore=tests/unit/file_cache/mp_timeout_decorator_test.py
        --ignore=tests/unit/file_cache/multiprocessing_executor_test.py
        --ignore=tests/unit/server/test_mcp_server_integration.py
        --deselect "tests/unit/server/test_mcp_tool_cleanup.py::TestServerMonitor::test_server_killed_on_parent_death"
    )
    local k_expr
    k_expr=$(pytest_k_expr "${PYTEST_K_FILTER:-}")

    # ── timing_dependent: high priority, single worker ───────────────────────
    local timing_args=(
        tests/unit -m "timing_dependent" --color=yes
        --dist no
        "${common_ignores[@]}"
    )
    [[ -n "$k_expr" ]] && timing_args+=(-k "$k_expr")

    # ── regular: low priority, parallel workers ──────────────────────────────
    local regular_args=(
        tests/unit -m "not slow and not timing_dependent" --color=yes
        -n "${PYTEST_WORKERS:-4}" --dist load
        "${common_ignores[@]}"
    )
    [[ -n "$k_expr" ]] && regular_args+=(-k "$k_expr")

    # Run both in parallel; timing tests get high CPU priority
    nice -n -15 /opt/venvs/$v/bin/python -m pytest "${timing_args[@]}" &
    local pid_timing=$!
    nice -n 19  /opt/venvs/$v/bin/python -m pytest "${regular_args[@]}" &
    local pid_regular=$!

    wait "$pid_timing";  local rc_timing=$?
    wait "$pid_regular"; local rc_regular=$?

    return $(( rc_timing != 0 || rc_regular != 0 ))
}

job_build_wheel() {
    cd /repo
    PNPM_STORE_DIR=/opt/pnpm-store bash scripts/full_build.sh
}

job_test_mcp_wheel() {
    cd /repo
    # Skip entirely if MCP integration tests aren't present (old commits predate MCP).
    if [[ ! -f tests/unit/server/test_mcp_server_integration.py ]]; then
        echo "[skip] MCP tests not present in this commit"
        return 0
    fi
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
    PW_GREP="${PW_GREP_FILTER:-}" \
        bash scripts/test_playwright_storybook.sh
}

job_playwright_server() {
    cd /repo
    SKIP_INSTALL=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-server-$$ \
    PW_GREP="${PW_GREP_FILTER:-}" \
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
    PW_GREP="${PW_GREP_FILTER:-}" \
        bash scripts/test_playwright_marimo.sh
}

job_playwright_wasm_marimo() {
    cd /repo
    # Same rationale as job_playwright_marimo.
    SKIP_INSTALL=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-wasm-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
    PW_GREP="${PW_GREP_FILTER:-}" \
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
    PARALLEL=9 \
    PW_GREP="${PW_GREP_FILTER:-}" \
        bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" --venv-location="$venv" || rc=$?
    rm -rf "$venv"
    return $rc
}

job_jupyter_warmup() {
    cd /repo
    # Reuse the Docker-built venv (already has jupyterlab, anywidget, polars).
    # Just ensure websocket-client is there (for kernel warmup).
    local venv=/opt/venvs/3.13
    uv pip install --python "$venv/bin/python" websocket-client -q 2>/dev/null || true
    source "$venv/bin/activate"

    # Save venv path for later phases
    echo "$venv" > /tmp/ci-jupyter-warmup-venv

    export JUPYTER_TOKEN="test-token-12345"
    local BASE_PORT=8889 PARALLEL=${JUPYTER_PARALLEL:-9}

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

    # Start all $PARALLEL JupyterLab servers in parallel, then wait for all to be HTTP-ready
    local pids=()
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        jupyter lab --no-browser --port="$port" \
            --ServerApp.token="$JUPYTER_TOKEN" \
            --ServerApp.allow_origin='*' \
            --ServerApp.disable_check_xsrf=True \
            --LabApp.workspaces_dir="/tmp/jlab-ws-$$-$port" \
            --allow-root \
            >/tmp/jupyter-port${port}.log 2>&1 &
        pids+=($!)
    done

    # Poll all servers in parallel until each responds (up to 30s)
    local poll_pids=()
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        (
            for i in $(seq 1 60); do
                curl -sf "http://localhost:${port}/api?token=${JUPYTER_TOKEN}" >/dev/null 2>&1 && {
                    echo "JupyterLab ready on port $port (slot $slot)"
                    exit 0
                }
                sleep 0.5
            done
            echo "JupyterLab on port $port failed to start"
            cat "/tmp/jupyter-port${port}.log" 2>/dev/null || true
            exit 1
        ) &
        poll_pids+=($!)
    done
    for pid in "${poll_pids[@]}"; do
        if ! wait "$pid"; then return 1; fi
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

export JS_CACHE_DIR JS_TREE_HASH PYTEST_WORKERS DISABLE_RENICE PW_GREP_FILTER PYTEST_K_FILTER
export -f job_lint_python job_build_js job_test_js job_test_python job_build_wheel \
           job_test_mcp_wheel job_smoke_test_extras \
           job_playwright_storybook job_playwright_server job_playwright_marimo \
           job_playwright_wasm_marimo job_playwright_jupyter job_jupyter_warmup \
           pytest_k_expr pw_grep_expr maybe_renice

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

    # ── run_dag: Execute the full CI DAG ─────────────────────────────────────
    # Extracted to a function so --first-jobs can call it twice (Phase A then B).
    run_dag() {
        local stagger=${STAGGER_DELAY:-2}

        # ── Wave 0: Minimal jobs — only what's needed on the critical path ──
        log "=== Starting Wave 0 ==="

        run_job lint-python            job_lint_python                & PID_LINT=$!
        maybe_renice -n 10 -p $PID_LINT
        run_job build-js               job_build_js                   & PID_BUILDJS=$!
        maybe_renice -n -10 -p $PID_BUILDJS
        run_job test-python-3.13       bash -c "job_test_python 3.13" & PID_PY313=$!
        maybe_renice -n 10 -p $PID_PY313
        run_job jupyter-warmup         job_jupyter_warmup             & PID_WARMUP=$!

        # ── Wait for build-js, then build wheel + test-js + storybook ────────
        wait $PID_BUILDJS || OVERALL=1
        if [[ $FAST_FAIL -eq 1 && $OVERALL -ne 0 ]]; then
            log "FAST-FAIL: build-js failed — skipping remaining jobs"
            wait $PID_LINT $PID_PY313 $PID_WARMUP 2>/dev/null || true
            log "=== FAST-FAIL EXIT ==="
            return 1
        fi
        log "=== build-js done — starting build-wheel + test-js + storybook ==="

        run_job build-wheel job_build_wheel & PID_WHEEL=$!
        maybe_renice -n -10 -p $PID_WHEEL
        run_job test-js     job_test_js     & PID_TESTJS=$!
        maybe_renice -n 10 -p $PID_TESTJS
        run_job playwright-storybook   job_playwright_storybook       & PID_PW_SB=$!
        maybe_renice -n 10 -p $PID_PW_SB

        # Wait for build-wheel + warmup (both needed before pw-jupyter)
        wait $PID_WHEEL  || OVERALL=1
        if [[ $FAST_FAIL -eq 1 && $OVERALL -ne 0 ]]; then
            log "FAST-FAIL: build-wheel failed — skipping remaining jobs"
            wait $PID_LINT $PID_PY313 $PID_WARMUP $PID_TESTJS $PID_PW_SB 2>/dev/null || true
            log "=== FAST-FAIL EXIT ==="
            return 1
        fi

        # Cache wheel by current SHA so --phase=5b / --wheel-from can reuse it.
        mkdir -p "/opt/ci/wheel-cache/$SHA"
        cp dist/buckaroo-*.whl "/opt/ci/wheel-cache/$SHA/" 2>/dev/null || true
        log "Cached wheel → /opt/ci/wheel-cache/$SHA"

        # ── Install wheel into warm jupyter venv ─────────────────────────────
        wait $PID_WARMUP || OVERALL=1
        log "=== jupyter-warmup done — installing wheel into warm venv ==="
        JUPYTER_VENV=$(cat /tmp/ci-jupyter-warmup-venv)
        wheel=$(ls dist/buckaroo-*.whl | head -1)
        uv pip install --python "$JUPYTER_VENV/bin/python" "$wheel" -q
        "$JUPYTER_VENV/bin/python" -c "import buckaroo; import pandas; import polars" 2>/dev/null || true

        # ── Wheel-dependent jobs — staggered sub-waves ───────────────────────
        JUPYTER_PARALLEL=${JUPYTER_PARALLEL:-9}
        log "=== build-wheel done — starting staggered wheel-dependent jobs (PARALLEL=$JUPYTER_PARALLEL, stagger=${stagger}s) ==="

        # t+0: pw-jupyter (critical path — uses pre-warmed servers)
        job_playwright_jupyter_warm() {
            cd /repo
            local venv
            venv=$(cat /tmp/ci-jupyter-warmup-venv)
            local rc=0
            ROOT_DIR=/repo \
            SKIP_INSTALL=1 \
            PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
            PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
            PARALLEL=$JUPYTER_PARALLEL \
            BASE_PORT=8889 \
            PW_GREP="${PW_GREP_FILTER:-}" \
                timeout 120 bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" \
                    --venv-location="$venv" --servers-running || rc=$?
            for pid in $(cat /tmp/ci-jupyter-warmup-pids 2>/dev/null); do
                kill "$pid" 2>/dev/null || true
            done
            rm -f /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids
            return $rc
        }
        export -f job_playwright_jupyter_warm
        run_job playwright-jupyter   job_playwright_jupyter_warm & PID_PW_JP=$!

        run_job test-mcp-wheel         job_test_mcp_wheel         & PID_MCP=$!
        maybe_renice -n 10 -p $PID_MCP

        # pw-marimo + pw-server start together (no stagger between them)
        [[ $stagger -gt 0 ]] && sleep "$stagger"
        run_job playwright-marimo      job_playwright_marimo       & PID_PW_MA=$!
        run_job playwright-server      job_playwright_server       & PID_PW_SV=$!

        # t+2*stagger: smoke + pw-wasm-marimo
        [[ $stagger -gt 0 ]] && sleep "$stagger"
        run_job smoke-test-extras      job_smoke_test_extras       & PID_SMOKE=$!
        run_job playwright-wasm-marimo job_playwright_wasm_marimo  & PID_PW_WM=$!

        # t+4*stagger: deferred pytest (low priority, not on critical path)
        [[ $stagger -gt 0 ]] && sleep "$stagger"
        run_job test-python-3.11       bash -c "job_test_python 3.11" & PID_PY311=$!
        run_job test-python-3.12       bash -c "job_test_python 3.12" & PID_PY312=$!
        run_job test-python-3.14       bash -c "job_test_python 3.14" & PID_PY314=$!
        maybe_renice -n 10 -p $PID_PY311 $PID_PY312 $PID_PY314

        # ── Wait for all jobs ────────────────────────────────────────────────
        wait $PID_LINT    || OVERALL=1
        wait $PID_TESTJS  || OVERALL=1
        wait $PID_PY313   || OVERALL=1
        wait $PID_PW_JP   || OVERALL=1
        wait $PID_PY311   || OVERALL=1
        wait $PID_PY312   || OVERALL=1
        wait $PID_PY314   || OVERALL=1
        wait $PID_PW_SB   || OVERALL=1
        wait $PID_PW_WM   || OVERALL=1
        wait $PID_MCP     || OVERALL=1
        wait $PID_SMOKE   || OVERALL=1
        wait $PID_PW_SV   || OVERALL=1
        wait $PID_PW_MA   || OVERALL=1
    }

    # ── Execute DAG (with --first-jobs / --first-testcases support) ──────────

    if [[ -n "$FIRST_TESTCASES" ]]; then
        # Phase 1: run with testcase filter
        log "=== FIRST-TESTCASES Phase 1: filtered run ==="
        PYTEST_K_FILTER=$(pytest_k_expr "$FIRST_TESTCASES")
        PW_GREP_FILTER=$(pw_grep_expr "$FIRST_TESTCASES")
        export PYTEST_K_FILTER PW_GREP_FILTER
        run_dag
        PHASE1_RESULT=$OVERALL
        if [[ $FAST_FAIL -eq 1 && $PHASE1_RESULT -ne 0 ]]; then
            log "FAST-FAIL: filtered testcases failed — skipping full suite"
        else
            # Phase 2: full unfiltered run
            log "=== FIRST-TESTCASES Phase 2: full suite ==="
            PYTEST_K_FILTER=""
            PW_GREP_FILTER=""
            export PYTEST_K_FILTER PW_GREP_FILTER
            run_dag
        fi
    elif [[ -n "$FIRST_JOBS" ]]; then
        # Phase A: only first-jobs
        log "=== FIRST-JOBS Phase A: ${FIRST_JOBS} ==="
        FIRST_JOBS_PHASE="A"
        run_dag
        PHASE_A_RESULT=$OVERALL
        if [[ $FAST_FAIL -eq 1 && $PHASE_A_RESULT -ne 0 ]]; then
            log "FAST-FAIL: first-jobs failed — skipping Phase B"
        else
            # Phase B: remaining jobs
            log "=== FIRST-JOBS Phase B: remaining jobs ==="
            FIRST_JOBS_PHASE="B"
            run_dag
        fi
    elif [[ -n "$ONLY_TESTCASES" ]]; then
        # Single run with testcase filter
        PYTEST_K_FILTER=$(pytest_k_expr "$ONLY_TESTCASES")
        PW_GREP_FILTER=$(pw_grep_expr "$ONLY_TESTCASES")
        export PYTEST_K_FILTER PW_GREP_FILTER
        run_dag
    else
        # Normal: single full run
        run_dag
    fi

fi

# ── Stop monitors ────────────────────────────────────────────────────────────
kill $WATCHDOG_PID 2>/dev/null || true
kill $CPU_MONITOR_PID 2>/dev/null || true
kill $CPU_FINE_PID 2>/dev/null || true

# ── End-of-run snapshot — capture what this run left behind ──────────────────
snapshot_container_state "end-of-run" "$RESULTS_DIR/container-end.txt"

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
