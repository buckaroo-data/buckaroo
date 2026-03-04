#!/bin/bash
# Parallel Playwright tests against JupyterLab for Buckaroo widgets.
# Each parallel slot gets its own isolated JupyterLab server on a distinct port,
# eliminating ZMQ socket contention from concurrent kernel startups.
#
# Usage:
#   bash scripts/test_playwright_jupyter_parallel.sh --venv-location=/path/to/venv
#   bash scripts/test_playwright_jupyter_parallel.sh --use-local-venv
#   PARALLEL=3 bash scripts/test_playwright_jupyter_parallel.sh  # 3 isolated servers
#
# Ports used: BASE_PORT to BASE_PORT+PARALLEL-1 (default 8889..8889+N-1)
set -euo pipefail

if [ -z "${ROOT_DIR:-}" ]; then
    cd "$(dirname "$0")/.."
    ROOT_DIR="$(pwd)"
fi
cd "$ROOT_DIR"

# ── Argument parsing (same interface as before) ───────────────────────────────

USE_LOCAL_VENV=false
VENV_LOCATION=""
NOTEBOOK=""
PARALLEL=${PARALLEL:-9}
BASE_PORT=${BASE_PORT:-8889}
SERVERS_RUNNING=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --use-local-venv|--local-dev) USE_LOCAL_VENV=true; shift ;;
        --venv-location=*) VENV_LOCATION="${1#*=}"; shift ;;
        --venv-location)   VENV_LOCATION="$2"; shift 2 ;;
        --notebook=*)      NOTEBOOK="${1#*=}"; shift ;;
        --notebook)        NOTEBOOK="$2"; shift 2 ;;
        --parallel=*)      PARALLEL="${1#*=}"; shift ;;
        --parallel)        PARALLEL="$2"; shift 2 ;;
        --servers-running) SERVERS_RUNNING=true; shift ;;
        *) shift ;;
    esac
done

# ── Notebooks ─────────────────────────────────────────────────────────────────

NOTEBOOKS=(
    "test_buckaroo_widget.ipynb"
    "test_buckaroo_infinite_widget.ipynb"
    "test_polars_widget.ipynb"
    "test_polars_infinite_widget.ipynb"
    "test_dfviewer.ipynb"
    "test_dfviewer_infinite.ipynb"
    "test_polars_dfviewer.ipynb"
    "test_polars_dfviewer_infinite.ipynb"
    "test_infinite_scroll_transcript.ipynb"
)

if [ -n "$NOTEBOOK" ]; then
    IFS=',' read -ra NOTEBOOKS <<< "$NOTEBOOK"
fi

TOTAL=${#NOTEBOOKS[@]}

# ── Logging ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
ok()  { echo -e "${GREEN}$1${NC}"; }
err() { echo -e "${RED}$1${NC}"; }

# ── Venv setup ────────────────────────────────────────────────────────────────

if [ -n "$VENV_LOCATION" ]; then
    VENV_DIR="$VENV_LOCATION"
    [ -d "$VENV_DIR" ] || { err "Venv not found at $VENV_DIR"; exit 1; }
    log "Using venv: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
elif [ "$USE_LOCAL_VENV" = true ]; then
    VENV_DIR=".venv"
    [ -d "$VENV_DIR" ] || { err "Local venv not found at $VENV_DIR"; exit 1; }
    source "$VENV_DIR/bin/activate"
else
    VENV_DIR="./test_venv"
    log "Creating test venv..."
    uv venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
fi

# ── Dependency check ──────────────────────────────────────────────────────────

if [ -z "$VENV_LOCATION" ] && [ "$USE_LOCAL_VENV" = false ]; then
    python3 -c "import polars; import jupyterlab" 2>/dev/null || {
        log "Installing Python deps..."
        uv pip install pandas polars jupyterlab
    }
fi

if [ -n "$VENV_LOCATION" ] || [ "$USE_LOCAL_VENV" = true ]; then
    python -c "import buckaroo" 2>/dev/null || { err "buckaroo not installed in venv"; exit 1; }
else
    log "Running full build..."
    bash scripts/full_build.sh
    uv pip install --force-reinstall dist/*.whl
fi

# websocket-client is needed for WebSocket-based kernel warmup
python -c "import websocket" 2>/dev/null || {
    log "Installing websocket-client..."
    uv pip install websocket-client
}

python -c "import buckaroo; print(f'buckaroo {getattr(buckaroo, \"__version__\", \"?\")}')"

# ── Playwright deps ───────────────────────────────────────────────────────────

cd packages/buckaroo-js-core
if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    pnpm install 2>/dev/null || npm install
    pnpm exec playwright install chromium 2>/dev/null || true
fi

# ── Multiple isolated JupyterLab servers (one per parallel slot) ──────────────

JUPYTER_TOKEN="test-token-12345"
declare -a JUPYTER_PIDS=()

cleanup() {
    log "Cleaning up..."
    # When --servers-running, caller manages server lifecycle
    if [ "$SERVERS_RUNNING" = false ]; then
        for pid in "${JUPYTER_PIDS[@]:-}"; do
            [ -n "$pid" ] && kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
        done
    fi
    cd "$ROOT_DIR"
    for nb in "${NOTEBOOKS[@]}"; do rm -f "$nb"; done
    if [ -z "$VENV_LOCATION" ] && [ "$USE_LOCAL_VENV" = false ] && [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi
}
trap cleanup EXIT

cd "$ROOT_DIR"

export JUPYTER_TOKEN

# ── Kernel warmup function (used for initial warmup and between-batch re-warmup)
# Creates a kernel, connects via WebSocket to trigger the "nudge" mechanism,
# waits for idle state, then deletes the warmup kernel. Without this, kernels
# can get stuck in "starting" state forever (REST API never transitions).
warmup_one_kernel() {
    local port=$1
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
ws = websocket.create_connection(ws_url, timeout=30)

deadline = time.time() + 30
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
" 2>&1
}
export -f warmup_one_kernel

if [ "$SERVERS_RUNNING" = true ]; then
    # Pre-warmed servers from job_jupyter_warmup — load PIDs for cleanup trap
    if [[ -f /tmp/ci-jupyter-warmup-pids ]]; then
        read -ra JUPYTER_PIDS < /tmp/ci-jupyter-warmup-pids
    fi
    log "Using pre-warmed servers (${#JUPYTER_PIDS[@]} PIDs loaded)"
else
    # Kill stale processes on all ports we'll use
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        lsof -ti:$port 2>/dev/null | while read -r pid; do
            ps -p "$pid" -o comm= 2>/dev/null | grep -qE 'jupyter|python' && kill -9 "$pid" 2>/dev/null
        done || true
    done

    rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
    # Remove stale kernel connection files — accumulate across runs, delay startup
    rm -f ~/.local/share/jupyter/runtime/kernel-*.json 2>/dev/null || true
    rm -f ~/.local/share/jupyter/runtime/jpserver-*.json 2>/dev/null || true
    rm -f ~/.local/share/jupyter/runtime/jpserver-*.html 2>/dev/null || true

    # ── Start JupyterLab servers (sequential — one at a time) ────────────────────
    # Starting one at a time prevents CPU competition during initialisation.
    # We do NOT start warmup kernels here: the JupyterLab REST API keeps a kernel
    # in "starting" state until a WebSocket client connects, so REST-only polling
    # never reaches "idle" and the lingering kernel process interferes with
    # batch-1 test kernels. Instead, we sleep once after all servers are HTTP-ready
    # to let the kernel provisioners finish initialising.

    log "Starting $PARALLEL isolated JupyterLab servers (sequential — one at a time)..."
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        jupyter lab --no-browser --port="$port" \
            --ServerApp.token="$JUPYTER_TOKEN" \
            --ServerApp.allow_origin='*' \
            --ServerApp.disable_check_xsrf=True \
            --allow-root \
            >/tmp/jupyter-port${port}-$$.log 2>&1 &
        JUPYTER_PIDS[$slot]=$!
        log "  Waiting for JupyterLab on port $port (pid ${JUPYTER_PIDS[$slot]})..."
        started=false
        for i in $(seq 1 30); do
            curl -sf "http://localhost:${port}/api?token=${JUPYTER_TOKEN}" >/dev/null 2>&1 && { started=true; break; }
            sleep 1
        done
        if [ "$started" = false ]; then
            err "JupyterLab on port $port failed to start"
            cat "/tmp/jupyter-port${port}-$$.log" || true
            exit 1
        fi
        ok "  JupyterLab ready on port $port (slot $slot)"
    done

    log "All $PARALLEL servers HTTP-ready — warming up kernels..."
    # Pre-warm Python bytecaches so kernel imports don't compile .pyc concurrently.
    python3 -c "import buckaroo; import pandas; import polars; print('Pre-warm done')" 2>&1 || \
        python3 -c "import buckaroo; import pandas; print('Pre-warm done (no polars)')" 2>&1 || true

    # Warm up each server via WebSocket nudge (uses warmup_one_kernel defined above).

    declare -a WARMUP_PIDS=()
    for slot in $(seq 0 $((PARALLEL-1))); do
        port=$((BASE_PORT + slot))
        log "  Warming kernel on port $port (background)..."
        warmup_one_kernel "$port" &
        WARMUP_PIDS+=($!)
    done

    warmup_ok=true
    for pid in "${WARMUP_PIDS[@]}"; do
        if ! wait "$pid"; then warmup_ok=false; fi
    done
    if [ "$warmup_ok" = true ]; then
        ok "  All $PARALLEL kernel warmups complete"
    else
        log "  WARNING: some kernel warmups failed — continuing anyway"
    fi

    # ── Copy and trust notebooks ──────────────────────────────────────────────────

    for nb in "${NOTEBOOKS[@]}"; do
        cp "tests/integration_notebooks/$nb" "$nb"
    done
    for nb in "${NOTEBOOKS[@]}"; do
        jupyter trust "$nb" 2>/dev/null || true
    done
    rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
fi

# ── Per-server kernel cleanup (between batches) ───────────────────────────────

shutdown_kernels_on_port() {
    local port=$1
    local kernels
    kernels=$(curl -s "http://localhost:$port/api/kernels?token=$JUPYTER_TOKEN" 2>/dev/null || echo "[]")
    if [ "$kernels" != "[]" ] && [ -n "$kernels" ]; then
        echo "$kernels" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | while read -r kid; do
            curl -s -X DELETE "http://localhost:$port/api/kernels/$kid?token=$JUPYTER_TOKEN" >/dev/null 2>&1 || true
        done || true
    fi
    local sessions
    sessions=$(curl -s "http://localhost:$port/api/sessions?token=$JUPYTER_TOKEN" 2>/dev/null || echo "[]")
    if [ "$sessions" != "[]" ] && [ -n "$sessions" ]; then
        echo "$sessions" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | while read -r sid; do
            curl -s -X DELETE "http://localhost:$port/api/sessions/$sid?token=$JUPYTER_TOKEN" >/dev/null 2>&1 || true
        done || true
    fi
    rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
    sleep 0.5
}

# ── Run one notebook (called in background, targets a specific server port) ───

run_one() {
    local nb=$1 idx=$2 logfile=$3 port=$4
    local spec="pw-tests/integration.spec.ts"
    local timeout=180000

    if [[ "$nb" == "test_infinite_scroll_transcript.ipynb" ]]; then
        spec="pw-tests/infinite-scroll-transcript.spec.ts"
    fi

    cd "$ROOT_DIR/packages/buckaroo-js-core"
    # Each parallel slot needs its own test-results dir to avoid ENOENT races
    # when 9 Playwright processes try to mkdir .playwright-artifacts-0 simultaneously.
    local results_dir="/tmp/pw-results-${nb%.ipynb}-$$"
    TEST_NOTEBOOK="$nb" \
    JUPYTER_BASE_URL="http://localhost:$port" \
    JUPYTER_TOKEN="$JUPYTER_TOKEN" \
    PLAYWRIGHT_HTML_OUTPUT_DIR="/tmp/pw-html-jupyter-${nb%.ipynb}-$$" \
        npx playwright test "$spec" \
            --config playwright.config.integration.ts \
            --reporter=line \
            --timeout=$timeout \
            --retries=2 \
            --output="$results_dir" \
        >"$logfile" 2>&1
}
export -f run_one
export ROOT_DIR JUPYTER_TOKEN

# ── Batch execution ───────────────────────────────────────────────────────────
# Each slot in a batch targets slot's dedicated JupyterLab server.
# No two notebooks ever share a server simultaneously.

log "Running $TOTAL notebooks, $PARALLEL at a time ($PARALLEL isolated JupyterLab servers)"

OVERALL=0
PASSED=0
FAILED_LIST=()
declare -A LOGFILES
QUEUE=("${NOTEBOOKS[@]}")
NEXT=0
BATCH_NUM=0

TMPDIR=$(mktemp -d -t pw-jupyter-parallelXXXXXX)

while [ $NEXT -lt $TOTAL ]; do
    declare -A BATCH_PIDS=()
    declare -A BATCH_PORTS=()
    BATCH_COUNT=0
    BATCH_USED_PORTS=()

    while [ $BATCH_COUNT -lt "$PARALLEL" ] && [ $NEXT -lt $TOTAL ]; do
        # Stagger Chromium launches — 1.5s fails on b2b runs; 2s is minimum reliable
        [ $BATCH_COUNT -gt 0 ] && sleep 2
        local_nb="${QUEUE[$NEXT]}"
        local_logfile="$TMPDIR/${local_nb%.ipynb}.log"
        local_port=$((BASE_PORT + BATCH_COUNT))
        LOGFILES["$local_nb"]="$local_logfile"
        run_one "$local_nb" "$NEXT" "$local_logfile" "$local_port" &
        local_pid=$!
        BATCH_PIDS[$local_pid]="$local_nb"
        BATCH_PORTS[$local_pid]="$local_port"
        BATCH_USED_PORTS+=("$local_port")
        log "START [$((NEXT+1))/$TOTAL] $local_nb (port $local_port)"
        ((NEXT++)) || true
        ((BATCH_COUNT++)) || true
    done

    for pid in "${!BATCH_PIDS[@]}"; do
        set +e; wait "$pid"; rc=$?; set -e
        nb="${BATCH_PIDS[$pid]}"
        if [ $rc -eq 0 ]; then
            ok "  PASS $nb"
            ((PASSED++)) || true
        else
            err "  FAIL $nb (see ${LOGFILES[$nb]})"
            FAILED_LIST+=("$nb")
            OVERALL=1
        fi
    done

    # Clean up each used server's kernel and re-warm before next batch.
    # Without re-warmup, new kernels can get stuck in "starting" state —
    # the REST API never transitions without a WebSocket nudge.
    if [ $NEXT -lt $TOTAL ]; then
        for p in "${BATCH_USED_PORTS[@]:-}"; do
            shutdown_kernels_on_port "$p"
        done
        # Determine how many ports the next batch will use
        remaining=$((TOTAL - NEXT))
        next_batch_size=$((remaining < PARALLEL ? remaining : PARALLEL))
        for slot in $(seq 0 $((next_batch_size - 1))); do
            rwport=$((BASE_PORT + slot))
            # Verify server is responsive
            curl -sf "http://localhost:${rwport}/api?token=${JUPYTER_TOKEN}" >/dev/null 2>&1 || {
                log "WARNING: Server on port $rwport not responding after cleanup"
            }
            # Quick kernel warmup: create → WebSocket nudge → wait idle → delete
            warmup_one_kernel "$rwport" >/dev/null 2>&1 || true
        done
    fi
    ((BATCH_NUM++)) || true
done

# ── Summary ───────────────────────────────────────────────────────────────────

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $OVERALL -eq 0 ]; then
    ok "ALL $TOTAL JUPYTER TESTS PASSED (parallel=$PARALLEL)"
else
    err "FAILED: ${#FAILED_LIST[@]}/$TOTAL notebooks"
    for nb in "${FAILED_LIST[@]}"; do
        err "  - $nb"
        tail -5 "${LOGFILES[$nb]}" 2>/dev/null | sed 's/^/    /'
    done
fi
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $OVERALL -ne 0 ]; then
    for nb in "${FAILED_LIST[@]}"; do
        log "=== Full log: $nb ==="
        cat "${LOGFILES[$nb]}" 2>/dev/null || true
    done
fi

rm -rf "$TMPDIR"
exit $OVERALL
