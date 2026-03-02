#!/bin/bash
# Parallel Playwright tests against JupyterLab for Buckaroo widgets.
# Drop-in replacement for test_playwright_jupyter.sh — runs notebooks in
# parallel batches against a single JupyterLab server.
#
# Usage:
#   bash scripts/test_playwright_jupyter_parallel.sh --venv-location=/path/to/venv
#   bash scripts/test_playwright_jupyter_parallel.sh --use-local-venv
#   PARALLEL=3 bash scripts/test_playwright_jupyter_parallel.sh  # max 3 concurrent
#
# Each notebook gets its own Playwright process (separate browser window).
# JupyterLab handles multiple notebooks with independent kernels fine.
set -euo pipefail

if [ -z "${ROOT_DIR:-}" ]; then
    cd "$(dirname "$0")/.."
    ROOT_DIR="$(pwd)"
fi
cd "$ROOT_DIR"

# ── Argument parsing (same interface as test_playwright_jupyter.sh) ───────────

USE_LOCAL_VENV=false
VENV_LOCATION=""
NOTEBOOK=""
PARALLEL=${PARALLEL:-4}

while [[ $# -gt 0 ]]; do
    case $1 in
        --use-local-venv|--local-dev) USE_LOCAL_VENV=true; shift ;;
        --venv-location=*) VENV_LOCATION="${1#*=}"; shift ;;
        --venv-location)   VENV_LOCATION="$2"; shift 2 ;;
        --notebook=*)      NOTEBOOK="${1#*=}"; shift ;;
        --notebook)        NOTEBOOK="$2"; shift 2 ;;
        --parallel=*)      PARALLEL="${1#*=}"; shift ;;
        --parallel)        PARALLEL="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# ── Notebooks ────────────────────────────────────────────────────────────────

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

# ── Logging ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
ok()  { echo -e "${GREEN}$1${NC}"; }
err() { echo -e "${RED}$1${NC}"; }

# ── Venv setup (same as original) ───────────────────────────────────────────

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

# ── Dependency check (same as original) ─────────────────────────────────────

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

python -c "import buckaroo; print(f'buckaroo {getattr(buckaroo, \"__version__\", \"?\")}')"

# ── Playwright deps ─────────────────────────────────────────────────────────

cd packages/buckaroo-js-core
pnpm install 2>/dev/null || npm install
pnpm exec playwright install chromium 2>/dev/null || true

# ── JupyterLab ───────────────────────────────────────────────────────────────

JUPYTER_TOKEN="test-token-12345"
JUPYTER_PORT=8889
JUPYTER_PID=""

cleanup() {
    log "Cleaning up..."
    [ -n "$JUPYTER_PID" ] && kill "$JUPYTER_PID" 2>/dev/null; wait "$JUPYTER_PID" 2>/dev/null || true
    # Clean up copied notebooks
    cd "$ROOT_DIR"
    for nb in "${NOTEBOOKS[@]}"; do rm -f "$nb"; done
    # Remove test venv if we created it
    if [ -z "$VENV_LOCATION" ] && [ "$USE_LOCAL_VENV" = false ] && [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi
}
trap cleanup EXIT

cd "$ROOT_DIR"

# Kill stale jupyter on our port
lsof -ti:$JUPYTER_PORT 2>/dev/null | while read pid; do
    ps -p "$pid" -o comm= 2>/dev/null | grep -qE 'jupyter|python' && kill -9 "$pid" 2>/dev/null
done || true

rm -rf .jupyter/lab/workspaces ~/.jupyter/lab/workspaces 2>/dev/null || true

export JUPYTER_TOKEN
python -m jupyter lab --no-browser --port=$JUPYTER_PORT \
    --ServerApp.token=$JUPYTER_TOKEN --ServerApp.allow_origin='*' \
    --ServerApp.disable_check_xsrf=True --allow-root &
JUPYTER_PID=$!
log "JupyterLab PID: $JUPYTER_PID"

# Wait for ready
for i in $(seq 1 30); do
    curl -sf "http://localhost:$JUPYTER_PORT/lab?token=$JUPYTER_TOKEN" >/dev/null 2>&1 && break
    [ "$i" -eq 30 ] && { err "JupyterLab failed to start"; exit 1; }
    sleep 1
done
ok "JupyterLab ready on port $JUPYTER_PORT"

# ── Copy all notebooks up front ─────────────────────────────────────────────

for nb in "${NOTEBOOKS[@]}"; do
    cp "tests/integration_notebooks/$nb" "$nb"
done

# ── Kernel cleanup — delete all running kernels and sessions ─────────────────
# Called after each notebook finishes so stale kernels don't accumulate
# across batches and cause WebSocket comm failures for the next batch.

shutdown_kernels() {
    local kernels
    kernels=$(curl -s "http://localhost:$JUPYTER_PORT/api/kernels?token=$JUPYTER_TOKEN" 2>/dev/null || echo "[]")
    if [ "$kernels" != "[]" ] && [ -n "$kernels" ]; then
        # || true: grep returns exit 1 when no IDs found; don't let pipefail kill script
        echo "$kernels" | grep -o '"id":"[^"]*"' | sed 's/"id":"//;s/"$//' | while read -r kid; do
            curl -s -X DELETE "http://localhost:$JUPYTER_PORT/api/kernels/$kid?token=$JUPYTER_TOKEN" >/dev/null 2>&1 || true
        done || true
    fi
    local sessions
    sessions=$(curl -s "http://localhost:$JUPYTER_PORT/api/sessions?token=$JUPYTER_TOKEN" 2>/dev/null || echo "[]")
    if [ "$sessions" != "[]" ] && [ -n "$sessions" ]; then
        echo "$sessions" | grep -o '"id":"[^"]*"' | sed 's/"id":"//;s/"$//' | while read -r sid; do
            curl -s -X DELETE "http://localhost:$JUPYTER_PORT/api/sessions/$sid?token=$JUPYTER_TOKEN" >/dev/null 2>&1 || true
        done || true
    fi
    sleep 0.5
}

# ── Run one notebook's tests (called in background) ─────────────────────────

run_one() {
    local nb=$1 idx=$2 logfile=$3
    local spec="pw-tests/integration.spec.ts"
    local timeout=30000

    if [[ "$nb" == "test_infinite_scroll_transcript.ipynb" ]]; then
        spec="pw-tests/infinite-scroll-transcript.spec.ts"
        timeout=45000
    fi

    cd "$ROOT_DIR/packages/buckaroo-js-core"
    TEST_NOTEBOOK="$nb" \
        npx playwright test "$spec" \
            --config playwright.config.integration.ts \
            --reporter=line \
            --timeout=$timeout \
        >"$logfile" 2>&1
}
export -f run_one
export ROOT_DIR JUPYTER_TOKEN

# ── Parallel execution with bounded concurrency ─────────────────────────────

log "Running $TOTAL notebooks, $PARALLEL at a time"

OVERALL=0
declare -A PIDS       # pid -> notebook name
declare -A LOGFILES   # notebook name -> logfile
RUNNING=0
QUEUE=("${NOTEBOOKS[@]}")
NEXT=0

TMPDIR=$(mktemp -d -t pw-jupyter-parallelXXXXXX)

# ── Explicit batch execution ─────────────────────────────────────────────────
# Run notebooks in batches of PARALLEL. Wait for the whole batch to finish,
# shut down all kernels, then start the next batch. This prevents stale
# kernels from accumulating and interfering with subsequent batches.

PASSED=0
FAILED_LIST=()
NEXT=0
declare -A BATCH_PIDS

while [ $NEXT -lt $TOTAL ]; do
    # Start up to PARALLEL notebooks
    unset BATCH_PIDS; declare -A BATCH_PIDS
    BATCH_COUNT=0
    while [ $BATCH_COUNT -lt "$PARALLEL" ] && [ $NEXT -lt $TOTAL ]; do
        local_nb="${QUEUE[$NEXT]}"
        local_logfile="$TMPDIR/${local_nb%.ipynb}.log"
        LOGFILES["$local_nb"]="$local_logfile"
        run_one "$local_nb" "$NEXT" "$local_logfile" &
        BATCH_PIDS[$!]="$local_nb"
        log "START [$((NEXT+1))/$TOTAL] $local_nb"
        ((NEXT++)) || true
        ((BATCH_COUNT++)) || true
    done

    # Wait for all jobs in this batch
    for pid in "${!BATCH_PIDS[@]}"; do
        set +e
        wait "$pid"
        rc=$?
        set -e
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
    unset BATCH_PIDS

    # Shut down all kernels before next batch so they don't accumulate
    if [ $NEXT -lt $TOTAL ]; then
        shutdown_kernels
    fi
done

# ── Summary ──────────────────────────────────────────────────────────────────

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $OVERALL -eq 0 ]; then
    ok "ALL $TOTAL JUPYTER TESTS PASSED (parallel=$PARALLEL)"
else
    err "FAILED: ${#FAILED_LIST[@]}/$TOTAL notebooks"
    for nb in "${FAILED_LIST[@]}"; do
        err "  - $nb"
        # Show last 5 lines of the log for quick diagnosis
        tail -5 "${LOGFILES[$nb]}" 2>/dev/null | sed 's/^/    /'
    done
fi
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Dump individual logs on failure
if [ $OVERALL -ne 0 ]; then
    for nb in "${FAILED_LIST[@]}"; do
        log "=== Full log: $nb ==="
        cat "${LOGFILES[$nb]}" 2>/dev/null || true
    done
fi

rm -rf "$TMPDIR"
exit $OVERALL
