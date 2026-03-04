#!/bin/bash
# Fast pw-jupyter iteration script — warmup, settle, test. Nothing else.
#
# Usage:
#   bash /repo/ci/hetzner/run-pw-jupyter.sh <WHEEL_SHA> <TEST_SHA> [SETTLE_TIME]
#
# Args:
#   WHEEL_SHA   — SHA with a cached wheel at /opt/ci/wheel-cache/<SHA>/
#                 No wheel? Run full pipeline first: run-ci.sh <SHA> <BRANCH>
#   TEST_SHA    — SHA to checkout for playwright test code
#   SETTLE_TIME — seconds to wait after warmup before tests (default: 0)
#
# Total timeout: 240s (CI_TIMEOUT env to override). Parallelism: JUPYTER_PARALLEL env or 4.
# Results: /opt/ci/logs/<TEST_SHA>-pwj/

set -uo pipefail

WHEEL_SHA=${1:?usage: run-pw-jupyter.sh WHEEL_SHA TEST_SHA [SETTLE_TIME]}
TEST_SHA=${2:?usage: run-pw-jupyter.sh WHEEL_SHA TEST_SHA [SETTLE_TIME]}
SETTLE_TIME=${3:-0}
PARALLEL=${JUPYTER_PARALLEL:-9}
BASE_PORT=8889

REPO_DIR=/repo
RESULTS_DIR=/opt/ci/logs/${TEST_SHA}-pwj
WHEEL_CACHE_DIR=/opt/ci/wheel-cache/$WHEEL_SHA
CI_RUNNER_DIR=${CI_RUNNER_DIR:-/opt/ci-runner}
OVERALL=0

mkdir -p "$RESULTS_DIR"
: > "$RESULTS_DIR/ci.log"

log() { echo "[$(date +'%H:%M:%S')] $*" | tee -a "$RESULTS_DIR/ci.log"; }

# ── Validate wheel ──────────────────────────────────────────────────────
wheel_path=$(ls "$WHEEL_CACHE_DIR"/buckaroo-*.whl 2>/dev/null | head -1)
if [[ -z "$wheel_path" ]]; then
    log "ERROR: no cached wheel at $WHEEL_CACHE_DIR"
    log "Run full CI first: run-ci.sh $WHEEL_SHA <BRANCH>"
    exit 1
fi
log "wheel=$WHEEL_SHA  test=$TEST_SHA  settle=${SETTLE_TIME}s  P=$PARALLEL"

# ── Watchdog ────────────────────────────────────────────────────────────
CI_TIMEOUT=${CI_TIMEOUT:-240}
( sleep "$CI_TIMEOUT"; log "TIMEOUT: exceeded ${CI_TIMEOUT}s"; kill -TERM 0 ) 2>/dev/null &
WATCHDOG_PID=$!

# ── CPU monitor ─────────────────────────────────────────────────────────
vmstat -n 1 > "$RESULTS_DIR/cpu.log" 2>&1 &
CPU_PID=$!

# ── Pre-run cleanup (same as run-ci.sh) ─────────────────────────────────
pkill -9 -f jupyter-lab 2>/dev/null || true
pkill -9 -f playwright 2>/dev/null || true
pkill -9 -f chromium 2>/dev/null || true
for port in $(seq $BASE_PORT $((BASE_PORT + PARALLEL - 1))); do
    fuser -k $port/tcp 2>/dev/null || true
done
sleep 1
rm -rf /tmp/ci-jupyter-warmup* /tmp/ci-jupyter-pwj* /tmp/pw-jupyter-parallel* /tmp/pw-html-* 2>/dev/null || true
rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/kernel-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.html 2>/dev/null || true
rm -rf ~/.ipython/profile_default/db 2>/dev/null || true
rm -rf ~/.local/share/jupyter/nbsignatures.db 2>/dev/null || true

# ── Checkout test code ──────────────────────────────────────────────────
log "Checkout $TEST_SHA"
cd "$REPO_DIR"
git fetch origin
git checkout -f "$TEST_SHA"
git clean -fdx \
    --exclude='packages/buckaroo-js-core/node_modules' \
    --exclude='packages/js/node_modules' \
    --exclude='packages/node_modules'

# ── Load wheel + extract static files ───────────────────────────────────
mkdir -p dist
cp "$wheel_path" dist/
python3 -c "
import zipfile, glob
wheel = glob.glob('dist/buckaroo-*.whl')[0]
with zipfile.ZipFile(wheel) as z:
    for name in z.namelist():
        if name.startswith('buckaroo/static/'):
            z.extract(name, '.')
print('Static files extracted')
" 2>/dev/null || true

# ── Warmup ──────────────────────────────────────────────────────────────
log "=== Warmup: $PARALLEL servers ==="

VENV=/tmp/ci-jupyter-pwj
rm -rf "$VENV"
uv venv "$VENV" --python 3.13 -q
uv pip install --python "$VENV/bin/python" \
    jupyterlab anywidget polars websocket-client -q
uv pip install --python "$VENV/bin/python" "$wheel_path" -q
source "$VENV/bin/activate"
echo "$VENV" > /tmp/ci-jupyter-warmup-venv

export JUPYTER_TOKEN="test-token-12345"

# Start JupyterLab servers (sequential, one per slot)
SERVER_PIDS=()
for slot in $(seq 0 $((PARALLEL-1))); do
    port=$((BASE_PORT + slot))
    jupyter lab --no-browser --port="$port" \
        --ServerApp.token="$JUPYTER_TOKEN" \
        --ServerApp.allow_origin='*' \
        --ServerApp.disable_check_xsrf=True \
        --allow-root \
        >/tmp/jupyter-port${port}.log 2>&1 &
    SERVER_PIDS+=($!)
    started=false
    for i in $(seq 1 30); do
        curl -sf "http://localhost:${port}/api?token=${JUPYTER_TOKEN}" >/dev/null 2>&1 && { started=true; break; }
        sleep 1
    done
    if [ "$started" = false ]; then
        log "FAIL: JupyterLab on port $port did not start"
        cat "/tmp/jupyter-port${port}.log" || true
        exit 1
    fi
    log "  Server ready on port $port"
done
echo "${SERVER_PIDS[*]}" > /tmp/ci-jupyter-warmup-pids

# Pre-warm bytecaches
python3 -c "import buckaroo; import pandas; import polars" 2>/dev/null || true

# WebSocket kernel warmup (all slots in parallel)
WARMUP_PIDS=()
for slot in $(seq 0 $((PARALLEL-1))); do
    port=$((BASE_PORT + slot))
    python3 -c "
import json, sys, time, urllib.request, websocket
port, token = $port, '$JUPYTER_TOKEN'
base = f'http://localhost:{port}'
req = urllib.request.Request(f'{base}/api/kernels?token={token}',
    data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
kid = json.loads(urllib.request.urlopen(req).read())['id']
ws = websocket.create_connection(
    f'ws://localhost:{port}/api/kernels/{kid}/channels?token={token}', timeout=90)
deadline, state = time.time() + 90, 'unknown'
while time.time() < deadline:
    ws.settimeout(max(1, deadline - time.time()))
    try: msg = json.loads(ws.recv())
    except: break
    if msg.get('msg_type') == 'status':
        state = msg.get('content', {}).get('execution_state', 'unknown')
        if state == 'idle': break
ws.close()
print(f'  port {port}: {state}')
try: urllib.request.urlopen(urllib.request.Request(
    f'{base}/api/kernels/{kid}?token={token}', method='DELETE'))
except: pass
sys.exit(0 if state == 'idle' else 1)
" 2>&1 &
    WARMUP_PIDS+=($!)
done

warmup_ok=true
for pid in "${WARMUP_PIDS[@]}"; do
    if ! wait "$pid"; then warmup_ok=false; fi
done
[ "$warmup_ok" = true ] && log "  All $PARALLEL kernels warmed" || log "  WARNING: some warmups failed"

# Copy + trust notebooks (parallel — serial trust takes ~17s)
TRUST_PIDS=()
for nb in tests/integration_notebooks/test_*.ipynb; do
    cp "$nb" "$(basename "$nb")"
done
for nb in test_*.ipynb; do
    jupyter trust "$nb" 2>/dev/null &
    TRUST_PIDS+=($!)
done
for pid in "${TRUST_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true

deactivate

# ── Settle ──────────────────────────────────────────────────────────────
log "Settling ${SETTLE_TIME}s..."
sleep "$SETTLE_TIME"

# ── Run playwright-jupyter ──────────────────────────────────────────────
log "=== START playwright-jupyter (P=$PARALLEL) ==="

rc=0
ROOT_DIR=/repo \
SKIP_INSTALL=1 \
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
PARALLEL=$PARALLEL \
BASE_PORT=$BASE_PORT \
    timeout 120 bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" \
        --venv-location="$VENV" --servers-running \
    > "$RESULTS_DIR/playwright-jupyter.log" 2>&1 || rc=$?

if [[ $rc -eq 0 ]]; then
    log "PASS  playwright-jupyter"
else
    log "FAIL  playwright-jupyter (rc=$rc)"
    OVERALL=1
fi

# ── Cleanup ─────────────────────────────────────────────────────────────
for pid in $(cat /tmp/ci-jupyter-warmup-pids 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
done
rm -rf "$VENV" /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids

kill $WATCHDOG_PID 2>/dev/null || true
kill $CPU_PID 2>/dev/null || true

if [[ $OVERALL -eq 0 ]]; then
    log "=== PASS (settle=${SETTLE_TIME}s P=$PARALLEL) ==="
else
    log "=== FAIL — see $RESULTS_DIR/playwright-jupyter.log ==="
    tail -20 "$RESULTS_DIR/playwright-jupyter.log" 2>/dev/null || true
fi

exit $OVERALL
