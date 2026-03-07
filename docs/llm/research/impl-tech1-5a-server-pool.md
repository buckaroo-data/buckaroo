# Tech 1+5a: Speculative Pre-Start Servers + Warm Kernels

**Goal:** Eliminate the 11s warmup job by having servers + kernels already running when
CI starts. Combined estimated savings: **8-11s**.

**Baseline:** 49s total. Critical path: warmup (11s) → pw-jupyter (37s).

---

## What changes

### 1. New file: `ci/hetzner/lib/jupyter-pool.sh`

Functions for managing the speculative server pool:

```bash
POOL_STATE=/opt/ci/jupyter-pool/pool.json
POOL_DIR=/opt/ci/jupyter-pool

# Called at end of run-ci.sh (post-run hook)
pool_speculative_start() {
    local base_port=8889 parallel=9
    local venv=/opt/venvs/3.13
    local jlab_version
    jlab_version=$("$venv/bin/python" -c "import jupyterlab; print(jupyterlab.__version__)")

    mkdir -p "$POOL_DIR"
    rm -f "$POOL_DIR"/*.pid

    # Start 9 fresh JupyterLab servers
    local pids=()
    for slot in $(seq 0 $((parallel-1))); do
        local port=$((base_port + slot))
        "$venv/bin/jupyter" lab --no-browser --port="$port" \
            --ServerApp.token="test-token-12345" \
            --ServerApp.allow_origin='*' \
            --ServerApp.disable_check_xsrf=True \
            --LabApp.workspaces_dir="/tmp/jlab-ws-pool-$port" \
            --allow-root \
            >/tmp/jupyter-port${port}.log 2>&1 &
        pids+=($!)
    done

    # Pre-warm a kernel in each server (import deps, NOT buckaroo)
    # Wait for servers first, then create+warm kernels, DON'T delete them
    for slot in $(seq 0 $((parallel-1))); do
        local port=$((base_port + slot))
        pool_warmup_kernel "$port" &
    done
    wait  # wait for all warmups

    # Write state file
    cat > "$POOL_STATE" <<EOF
{
    "ports": [$(seq -s, $base_port $((base_port + parallel - 1)))],
    "pids": [$(IFS=,; echo "${pids[*]}")],
    "jupyterlab_version": "$jlab_version",
    "venv": "$venv",
    "started_at": "$(date -Iseconds)"
}
EOF
}

pool_warmup_kernel() {
    local port=$1 token="test-token-12345"
    # Wait for server ready
    for i in $(seq 1 60); do
        curl -sf "http://localhost:${port}/api?token=${token}" >/dev/null 2>&1 && break
        sleep 0.5
    done
    # Create kernel, wait for idle (imports pandas/polars/etc), DON'T delete
    python3 -c "
import json, sys, time, urllib.request, websocket
port, token = $port, '$token'
base = f'http://localhost:{port}'
req = urllib.request.Request(f'{base}/api/kernels?token={token}', data=b'{}',
    headers={'Content-Type': 'application/json'}, method='POST')
kid = json.loads(urllib.request.urlopen(req).read())['id']
ws = websocket.create_connection(f'ws://localhost:{port}/api/kernels/{kid}/channels?token={token}', timeout=90)
deadline = time.time() + 90
while time.time() < deadline:
    ws.settimeout(max(1, deadline - time.time()))
    try: msg = json.loads(ws.recv())
    except: break
    if msg.get('msg_type') == 'status' and msg.get('content',{}).get('execution_state') == 'idle':
        break
ws.close()
# DO NOT delete kernel — leave it for pw-jupyter to reuse
print(f'kernel {kid[:8]} warm on port {port}')
" 2>&1
}

# Called at start of run-ci.sh (pre-run check)
pool_check() {
    [[ ! -f "$POOL_STATE" ]] && return 1

    local jlab_version
    jlab_version=$(/opt/venvs/3.13/bin/python -c "import jupyterlab; print(jupyterlab.__version__)")
    local cached_version
    cached_version=$(python3 -c "import json; print(json.load(open('$POOL_STATE'))['jupyterlab_version'])")

    [[ "$jlab_version" != "$cached_version" ]] && return 1

    # Health-check each server
    local token="test-token-12345"
    local ports
    ports=$(python3 -c "import json; print(' '.join(str(p) for p in json.load(open('$POOL_STATE'))['ports']))")
    for port in $ports; do
        curl -sf "http://localhost:${port}/api?token=${token}" >/dev/null 2>&1 || return 1
    done
    return 0
}
```

### 2. Modify: `ci/hetzner/run-ci.sh`

**At the end** (before `exit $OVERALL`, after final status):
```bash
# Post-run: speculatively pre-start servers for the next run
source "$CI_RUNNER_DIR/jupyter-pool.sh"
log "Post-run: starting speculative server pool"
pool_speculative_start &  # fire-and-forget, don't block exit
```

**In `job_jupyter_warmup()`** — add pool check at the top:
```bash
job_jupyter_warmup() {
    source "$CI_RUNNER_DIR/jupyter-pool.sh"
    if pool_check; then
        log "Using pre-started JupyterLab pool (skipping warmup)"
        local venv
        venv=$(python3 -c "import json; print(json.load(open('$POOL_STATE'))['venv'])")
        echo "$venv" > /tmp/ci-jupyter-warmup-venv
        # Install new wheel into venv (buckaroo changed)
        # (wheel install happens separately in run_dag)
        # Copy + trust notebooks
        # ... existing notebook copy logic ...
        return 0
    fi
    # ... existing full warmup logic unchanged ...
}
```

**In pre-run cleanup**: DON'T kill jupyter/chromium if pool is valid:
```bash
# Replace unconditional ci_pkill 'jupyter' with:
source "$CI_RUNNER_DIR/jupyter-pool.sh"
if ! pool_check; then
    ci_pkill 'jupyter'
    ci_pkill jupyter-lab
    ci_pkill ipykernel
    # ... rest of kill_port loop ...
fi
```

### 3. Modify: `ci/hetzner/update-runner.sh`

Add `jupyter-pool.sh` to the list of files copied from repo to runner dir.

---

## Validation

1. Run CI normally (cold start — no pool). Verify warmup runs as before.
2. Run CI again immediately. Verify pool check passes and warmup is skipped.
3. Check timing: second run should show ~8-11s savings on total.
4. Kill servers manually, run CI. Verify fallback to full warmup.

## Risks

- Servers OOM-killed between runs → health-check handles this (falls back)
- Rapid successive runs → new run starts while post-run hook is still starting servers.
  Mitigation: pool_check waits up to 5s for pool.json to appear, else falls back.
- Kernel state from warmup may have stale module versions if deps changed between runs.
  Mitigation: only pre-import packages that don't change (pandas/polars/numpy/pyarrow).

## Pre-implementation check

Before implementing, verify the critical path claim from CI logs:

```bash
grep -E 'START|PASS|FAIL' /opt/ci/logs/<recent-sha>/ci.log
```

If build path (build-js + build-wheel + wheel-install = 16s) finishes AFTER warmup (11s),
then warmup is NOT the true bottleneck. Tech 1 would save only `16s - 11s = 5s` because
the build path would become the new gate.
