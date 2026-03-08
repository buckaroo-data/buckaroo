#!/bin/bash
# Start JupyterLab servers and pre-warm kernels.
# Writes state files for pw-jupyter:
#   /tmp/ci-jupyter-warmup-venv  — venv path
#   /tmp/ci-jupyter-warmup-pids  — server PIDs
set -uo pipefail
cd /repo

venv=/opt/venvs/3.13
uv pip install --python "$venv/bin/python" websocket-client -q 2>/dev/null || true
source "$venv/bin/activate"

echo "$venv" > /tmp/ci-jupyter-warmup-venv

export JUPYTER_TOKEN="test-token-12345"
BASE_PORT=8889
PARALLEL=${JUPYTER_PARALLEL:-9}

# Clean stale state
rm -rf ~/.jupyter/lab/workspaces /repo/.jupyter/lab/workspaces 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/kernel-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.json 2>/dev/null || true
rm -f ~/.local/share/jupyter/runtime/jpserver-*.html 2>/dev/null || true

# Kill stale processes on target ports
kill_port() {
    local port=$1 hex_port inode pid
    printf -v hex_port "%04X" "$port"
    inode=$(awk "/:${hex_port} /{print \$10}" /proc/net/tcp /proc/net/tcp6 2>/dev/null | head -1)
    [[ -z "$inode" ]] && return 0
    for fd in /proc/*/fd/*; do
        [[ "$(readlink "$fd" 2>/dev/null)" == "socket:[$inode]" ]] || continue
        pid=${fd#/proc/}; pid=${pid%%/*}
        kill -9 "$pid" 2>/dev/null || true
        return 0
    done
}
for slot in $(seq 0 $((PARALLEL-1))); do
    kill_port $((BASE_PORT + slot))
done

# Start all servers in parallel
pids=()
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

# Poll all servers until each responds (up to 30s)
poll_pids=()
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
    if ! wait "$pid"; then exit 1; fi
done

echo "${pids[*]}" > /tmp/ci-jupyter-warmup-pids

# Pre-warm Python bytecaches
python3 -c "import buckaroo; import pandas; import polars" 2>/dev/null || \
python3 -c "import pandas; import polars; print('Pre-warm (no buckaroo yet)')" 2>/dev/null || true

# WebSocket kernel warmup (all in parallel)
warmup_pids=()
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

warmup_ok=true
for pid in "${warmup_pids[@]}"; do
    if ! wait "$pid"; then warmup_ok=false; fi
done
if [ "$warmup_ok" = true ]; then
    echo "All $PARALLEL kernel warmups complete"
else
    echo "WARNING: some kernel warmups failed — continuing anyway"
fi

# Copy + trust notebooks
notebooks=(test_buckaroo_widget.ipynb test_buckaroo_infinite_widget.ipynb
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
