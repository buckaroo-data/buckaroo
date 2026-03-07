# CI Pre-Warming: Implementation Plans

Each technique below is a standalone implementation with files to change, code sketches,
validation steps, and known risks. Ordered by recommended priority (Phase 1 first).

**Baseline:** 49s total. Critical path: warmup (11s) → pw-jupyter (37s).

---

## Tech 1+5a: Speculative Pre-Start Servers + Warm Kernels

**Goal:** Eliminate the 11s warmup job by having servers + kernels already running when
CI starts. Combined estimated savings: **8-11s**.

### What changes

#### 1. New file: `ci/hetzner/lib/jupyter-pool.sh`

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

#### 2. Modify: `ci/hetzner/run-ci.sh`

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

#### 3. Modify: `ci/hetzner/update-runner.sh`

Add `jupyter-pool.sh` to the list of files copied from repo to runner dir.

### Validation

1. Run CI normally (cold start — no pool). Verify warmup runs as before.
2. Run CI again immediately. Verify pool check passes and warmup is skipped.
3. Check timing: second run should show ~8-11s savings on total.
4. Kill servers manually, run CI. Verify fallback to full warmup.

### Risks

- Servers OOM-killed between runs → health-check handles this (falls back)
- Rapid successive runs → new run starts while post-run hook is still starting servers.
  Mitigation: pool_check waits up to 5s for pool.json to appear, else falls back.
- Kernel state from warmup may have stale module versions if deps changed between runs.
  Mitigation: only pre-import packages that don't change (pandas/polars/numpy/pyarrow).

---

## Tech 2: Pre-Start Chromium Instances

**Goal:** Save ~2-3s of Chromium launch time from pw-jupyter. Fold into Tech 1's
post-run hook so Chromium is already running when pw-jupyter starts.

### What changes

#### 1. New file: `ci/hetzner/browser-server.js`

```javascript
const { chromium } = require('playwright');
(async () => {
    const server = await chromium.launchServer({
        port: parseInt(process.env.PW_PORT || '3001'),
        headless: true,
        args: ['--disable-dev-shm-usage', '--no-sandbox'],
    });
    console.log(`Browser server: ${server.wsEndpoint()}`);
    // Write WS endpoint to file for Playwright config to read
    const fs = require('fs');
    fs.writeFileSync(`/opt/ci/chromium-pool/ws-${process.env.PW_PORT}.txt`, server.wsEndpoint());
})();
```

#### 2. Add to post-run hook in `jupyter-pool.sh`

```bash
pool_start_chromium() {
    mkdir -p /opt/ci/chromium-pool
    # One Chromium per pw-jupyter — shared browser, separate contexts
    # Actually: single Chromium with multiple contexts is fine
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PW_PORT=3001 node /opt/ci-runner/browser-server.js &
    echo $! > /opt/ci/chromium-pool/pid
}

pool_check_chromium() {
    [[ ! -f /opt/ci/chromium-pool/ws-3001.txt ]] && return 1
    local ws_url
    ws_url=$(cat /opt/ci/chromium-pool/ws-3001.txt)
    # Health check: try CDP /json/version
    curl -sf "http://localhost:3001/json/version" >/dev/null 2>&1 || return 1
    return 0
}
```

#### 3. Playwright config: CI variant

Add to `packages/buckaroo-js-core/playwright-jupyter.config.ts` (or create CI overlay):

```typescript
// Only connect to pre-started browser when env var is set
const connectOptions = process.env.PW_BROWSER_WS
    ? { wsEndpoint: process.env.PW_BROWSER_WS }
    : undefined;

export default defineConfig({
    use: {
        ...connectOptions,
        // ...existing config...
    },
});
```

**Open question:** Playwright's `connectOptions` applies to all workers — they all share
one Chromium. Each worker gets its own `BrowserContext` (isolated). This is fine for test
isolation but means all 9 workers share one Chromium process. If test isolation requires
separate browser *processes*, we'd need 9 Chromium servers on 9 ports.

For now: start with 1 shared Chromium (simpler, lower memory). If tests flake due to
shared process, split to 9.

#### 4. Wire into `test_playwright_jupyter_parallel.sh`

When pool has Chromium ready, set `PW_BROWSER_WS` env var before calling Playwright:
```bash
if [[ -f /opt/ci/chromium-pool/ws-3001.txt ]]; then
    export PW_BROWSER_WS=$(cat /opt/ci/chromium-pool/ws-3001.txt)
fi
```

### Validation

1. Run with pre-started Chromium. Compare pw-jupyter timing vs baseline.
2. Kill Chromium between runs. Verify fallback to local launch.
3. Check test isolation: ensure no state leaks between workers.

### Risks

- Chromium process crash → one test failure cascades to all 9 workers.
  Mitigation: health check; fallback to local launch.
- Playwright version mismatch between pre-started Chromium and test runner.
  Mitigation: version check in pool_check_chromium.

---

## Tech 5a (standalone): Keep Kernels Alive from Warmup

**Goal:** When servers are NOT pre-started (cold start), keep the warmup kernels alive
instead of deleting them. Saves ~4-6s of import burst during pw-jupyter.

This is the cold-start fallback for Tech 1+5a. When Tech 1 is working (servers
pre-started), this is already handled. This section covers the modification needed
when warmup runs during the CI run itself.

### What changes

#### 1. Modify `job_jupyter_warmup()` in `run-ci.sh`

The kernel warmup currently DELETEs the kernel after reaching idle (line 629-634).
Change: DON'T delete. Save kernel ID to a state file for pw-jupyter.

```python
# REMOVE this block (lines 629-634):
# try:
#     req = urllib.request.Request(
#         f'{base}/api/kernels/{kid}?token={token}', method='DELETE')
#     urllib.request.urlopen(req)
# except Exception:
#     pass

# ADD: save kernel ID for pw-jupyter
with open(f'/tmp/ci-jupyter-warmup-kernel-{port}', 'w') as f:
    f.write(kid)
```

#### 2. Modify `test_playwright_jupyter_parallel.sh`

When connecting to a JupyterLab server, check for pre-warmed kernel:
```bash
# For each slot, if a warm kernel exists, pass its ID to the notebook
KERNEL_ID_FILE="/tmp/ci-jupyter-warmup-kernel-${port}"
if [[ -f "$KERNEL_ID_FILE" ]]; then
    export JUPYTER_WARM_KERNEL_ID=$(cat "$KERNEL_ID_FILE")
fi
```

**Critical question:** How does Playwright open a notebook on a *specific* kernel?
- JupyterLab URL: `?kernel_id=...` is not standard
- Jupyter Sessions API: `POST /api/sessions` with `kernel.id` — opens a notebook
  session attached to an existing kernel
- Need to modify the Playwright test to use the Sessions API before navigating

This is the hardest part of 5a. The Playwright test currently just opens a notebook URL
and lets JupyterLab auto-create a kernel. To reuse a warm kernel, the test (or a
pre-step) needs to create a session via REST API binding the notebook to the existing
kernel.

**Alternative approach:** Don't try to reuse kernel IDs. Instead, just don't delete
kernels — the heavy imports (pandas/polars) populate the OS page cache + Python's
bytecode cache. Even if pw-jupyter creates NEW kernels, their imports will be faster
because the .pyc files are warm and the shared libraries are in page cache. This gives
~2-3s instead of ~4-6s but with zero wiring complexity.

### Validation

1. Run with kernel deletion removed. Compare pw-jupyter timing.
2. Verify no stale kernel issues (OOM from 18 kernels alive simultaneously).

### Risks

- 9 warm kernels + 9 new kernels = 18 kernels = high memory. Each kernel ~150MB.
  18 × 150MB = 2.7GB. On 64GB machine, fine. On 32GB, tight.
- If the warm kernels' Python processes are OOM-killed, the server may behave oddly.

---

## Tech 5c: cpuset Isolation

**Goal:** Pin pw-jupyter processes to dedicated cores, eliminating CPU contention from
other jobs. Estimated savings: **3-6s** (unmeasured).

### What changes

#### 1. Modify `docker-compose.yml`

Add `--privileged` or `SYS_ADMIN` capability:
```yaml
services:
  buckaroo-ci:
    privileged: true  # needed for cgroup writes
    # OR:
    # cap_add:
    #   - SYS_ADMIN
```

#### 2. New file: `ci/hetzner/lib/cpuset.sh`

```bash
setup_cpuset() {
    local ncpus
    ncpus=$(nproc)
    if (( ncpus < 12 )); then
        echo "Not enough CPUs for cpuset isolation ($ncpus < 12)" >&2
        return 1
    fi

    # pw-jupyter gets cores 0-11 (12 cores for 9 Chromium + 9 kernels)
    mkdir -p /sys/fs/cgroup/pw-jupyter
    echo "0-11" > /sys/fs/cgroup/pw-jupyter/cpuset.cpus
    echo "0" > /sys/fs/cgroup/pw-jupyter/cpuset.mems

    # everything-else gets cores 12-15
    mkdir -p /sys/fs/cgroup/ci-other
    echo "12-$((ncpus-1))" > /sys/fs/cgroup/ci-other/cpuset.cpus
    echo "0" > /sys/fs/cgroup/ci-other/cpuset.mems
}

run_in_cpuset() {
    local cgroup=$1; shift
    echo $$ > "/sys/fs/cgroup/$cgroup/cgroup.procs"
    "$@"
}
```

#### 3. Modify `run_dag()` in `run-ci.sh`

```bash
# Before starting pw-jupyter:
if setup_cpuset 2>/dev/null; then
    # Run pw-jupyter in dedicated cpuset
    run_in_cpuset pw-jupyter run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
    # Move other running jobs to ci-other cpuset
    for pid in $PID_PY312 $PID_PY314 $PID_SMOKE; do
        echo "$pid" > /sys/fs/cgroup/ci-other/cgroup.procs 2>/dev/null || true
    done
else
    # Fallback: no cpuset, run as before
    run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
fi
```

### Validation

1. Run with cpuset. Compare pw-jupyter timing + flakiness vs baseline.
2. Run stress test (5 consecutive runs). Compare timing variance.
3. Verify cgroup v2 is available in container with --privileged.

### Risks

- `--privileged` is a security concern for shared hosts (our CI is single-tenant, so OK).
- cgroup v2 may not be available in all Docker configurations.
- 4 cores for all other jobs may slow them down — monitor tail latency.

---

## Tech 6: Speculative Pre-Build on Push Webhook

**Goal:** Move `git fetch` + `git checkout` + (optionally) JS build before `run-ci.sh`
is formally called. Saves **2-3s** on every run, up to **15s** on JS-cache-miss runs.

### What changes

#### 1. Modify `ci/hetzner/webhook.py`

Currently webhook.py receives the push event and calls `run-ci.sh`. Add a pre-build
step between receiving the webhook and calling run-ci:

```python
# In webhook handler, before launching run-ci.sh:
def on_push(sha, branch):
    # Speculative pre-build (runs before run-ci.sh)
    subprocess.run([
        'docker', 'exec', 'buckaroo-ci', 'bash', '-c',
        f'cd /repo && git fetch origin && git checkout -f {sha} && '
        f'git clean -fdx --exclude=packages/*/node_modules && '
        f'echo {sha} > /opt/ci/prewarm-ready'
    ], timeout=30)

    # Now run CI (which checks for prewarm-ready)
    subprocess.Popen([
        'docker', 'exec', '-e', f'GITHUB_TOKEN={token}',
        'buckaroo-ci', 'bash', '/opt/ci-runner/run-ci.sh', sha, branch
    ])
```

#### 2. Modify `run-ci.sh` — check for pre-warmed checkout

After the checkout section (~line 278):
```bash
# Check if webhook already did the checkout
if [[ -f /opt/ci/prewarm-ready ]] && [[ "$(cat /opt/ci/prewarm-ready)" == "$SHA" ]]; then
    log "Using pre-warmed checkout for $SHA"
    rm -f /opt/ci/prewarm-ready
else
    git fetch origin
    git checkout -f "$SHA"
    git clean -fdx \
        --exclude='packages/buckaroo-js-core/node_modules' \
        --exclude='packages/js/node_modules' \
        --exclude='packages/node_modules'
fi
```

### Validation

1. Trigger via webhook. Verify git fetch happens before run-ci.sh.
2. Verify SHA mismatch (rapid pushes) falls back to full checkout.
3. Time savings: compare total CI time with/without pre-warm.

### Risks

- Rapid successive pushes: SHA X pre-build, then SHA Y arrives before X's CI starts.
  Pre-build for X is wasted, Y does a full checkout. Harmless but no savings.
- Pre-build failure (network, disk): run-ci.sh falls back to full checkout. Safe.

---

## Tech 7: Synthetic Test Split (Transcript Oracle + Layer B)

**Goal:** Skip pw-jupyter entirely when Python output + JS code haven't changed
(cache hit → ~2s). On cache miss, Layer B gives fast signal (~10s) while full
pw-jupyter runs in parallel (~37s). Weighted average: **~16s** vs current 37s.

This is the most complex technique. Break into sub-tasks.

### Sub-task 7A: Transcript hash computation

#### New file: `ci/hetzner/compute-transcript-hash.sh`

```bash
#!/bin/bash
# Compute content-addressed transcript hash for pw-jupyter oracle.
# Runs at t=0 alongside lint/build jobs.
set -euo pipefail

CACHE_DIR=/opt/ci/transcript-result-cache
HASH_FILE=/opt/ci/transcript-hashes.json
mkdir -p "$CACHE_DIR"

# JS hash: tree hash of packages/*/src/
JS_HASH=$(git ls-tree -r HEAD \
    packages/buckaroo-js-core/src/ \
    packages/buckaroo-js-core/pw-tests/ \
    2>/dev/null | sha256sum | cut -c1-16)

# Python transcript hash: instantiate widgets, hash their output
python3 - <<'PYEOF'
import json, hashlib, sys
sys.path.insert(0, '.')

from buckaroo import BuckarooWidget
import pandas as pd
try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False

datasets = {
    "test_buckaroo_widget": pd.DataFrame({"a": [1,2,3], "b": ["x","y","z"]}),
    "test_dfviewer": pd.DataFrame({"a": [1,2,3], "b": [4.0,5.0,6.0]}),
    # ... add all 9 notebook datasets ...
}
if HAS_POLARS:
    datasets["test_polars_dfviewer"] = pl.DataFrame({"a": [1,2,3], "b": ["x","y","z"]})

hashes = {}
for name, df in datasets.items():
    try:
        w = BuckarooWidget(df)
        blob = json.dumps(w.df_display_args, sort_keys=True, default=str)
        hashes[name] = hashlib.sha256(blob.encode()).hexdigest()[:16]
    except Exception as e:
        hashes[name] = f"ERROR:{e}"

combined = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
result = {"per_notebook": hashes, "combined": combined}
json.dump(result, open("/opt/ci/transcript-hashes.json", "w"), indent=2)
print(f"Transcript hash: {combined}")
PYEOF

echo "$JS_HASH" > /opt/ci/js-hash.txt
```

#### New file: `ci/hetzner/check-transcript-cache.sh`

```bash
#!/bin/bash
# Check if (transcript_hash, js_hash) pair has a cached PASS result.
set -euo pipefail

CACHE_DIR=/opt/ci/transcript-result-cache

T_HASH=$(python3 -c "import json; print(json.load(open('/opt/ci/transcript-hashes.json'))['combined'])")
J_HASH=$(cat /opt/ci/js-hash.txt)
CACHE_KEY="${T_HASH}-${J_HASH}"

if [[ -f "$CACHE_DIR/$CACHE_KEY.result" ]]; then
    RESULT=$(cat "$CACHE_DIR/$CACHE_KEY.result")
    echo "CACHE HIT: ($T_HASH, $J_HASH) → $RESULT"
    exit 0  # cache hit
else
    echo "CACHE MISS: ($T_HASH, $J_HASH)"
    exit 1  # cache miss
fi
```

#### Modify `run_dag()` in `run-ci.sh`

Add transcript hash computation at t=0, and cache check before pw-jupyter:

```bash
# At t=0 (Wave 0), alongside lint/build:
run_job transcript-hash bash "$CI_RUNNER_DIR/compute-transcript-hash.sh" & PID_THASH=$!

# Before starting pw-jupyter:
wait $PID_THASH || true  # transcript hash needed for cache check

local pw_skip=0
if bash "$CI_RUNNER_DIR/check-transcript-cache.sh"; then
    log "SKIP playwright-jupyter (transcript+JS cache hit)"
    pw_skip=1
fi

if [[ $pw_skip -eq 0 ]]; then
    run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
else
    PID_PW_JP=""
fi

# After pw-jupyter completes (if it ran):
if [[ -n "$PID_PW_JP" ]]; then
    wait $PID_PW_JP || OVERALL=1
    # Store result in cache
    T_HASH=$(python3 -c "import json; print(json.load(open('/opt/ci/transcript-hashes.json'))['combined'])")
    J_HASH=$(cat /opt/ci/js-hash.txt)
    if [[ $OVERALL -eq 0 ]]; then
        echo "PASS" > "/opt/ci/transcript-result-cache/${T_HASH}-${J_HASH}.result"
    else
        echo "FAIL" > "/opt/ci/transcript-result-cache/${T_HASH}-${J_HASH}.result"
    fi
fi
```

### Sub-task 7B: Layer A — Python transcript snapshot tests

#### New file: `tests/unit/test_transcript_snapshots.py`

```python
"""Capture widget transcripts and compare against golden snapshots.

These tests verify that Python produces the correct output for each notebook
dataset, without a browser. Runs in ~1s total.
"""
import json
import hashlib
import pytest
from unittest.mock import patch
from buckaroo import BuckarooWidget
import pandas as pd

DATASETS = {
    "test_buckaroo_widget": lambda: pd.DataFrame({"a": [1,2,3], "b": ["x","y","z"]}),
    "test_dfviewer": lambda: pd.DataFrame({"a": [1,2,3], "b": [4.0,5.0,6.0]}),
    # ... fill in all 9 notebook datasets ...
}

def capture_transcript(df, **kwargs):
    sent_messages = []
    with patch.object(BuckarooWidget, 'send',
                      lambda self, msg, buffers=None:
                      sent_messages.append({"msg": msg, "has_buffers": buffers is not None})):
        widget = BuckarooWidget(df, **kwargs)
    return {
        "df_display_args": widget.df_display_args,
        "buckaroo_state": widget.buckaroo_state,
        "sent_count": len(sent_messages),
    }

@pytest.mark.parametrize("name,df_factory", list(DATASETS.items()))
def test_transcript_snapshot(name, df_factory, snapshot):
    transcript = capture_transcript(df_factory())
    # Use syrupy or pytest-snapshot for golden comparison
    assert transcript == snapshot
```

### Sub-task 7C: Layer B — Storybook transcript replay

#### New Playwright spec: `packages/buckaroo-js-core/pw-tests/transcript-replay-from-snapshot.spec.ts`

```typescript
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { waitForCells } from './ag-pw-utils';

const SNAPSHOT_DIR = path.resolve(__dirname, '../../../tests/unit/snapshots/transcripts');

// Only run if snapshot dir exists
const snapshotFiles = fs.existsSync(SNAPSHOT_DIR)
    ? fs.readdirSync(SNAPSHOT_DIR).filter(f => f.endsWith('.json'))
    : [];

for (const file of snapshotFiles) {
    const transcript = JSON.parse(fs.readFileSync(path.join(SNAPSHOT_DIR, file), 'utf-8'));

    test(`replay: ${file}`, async ({ page }) => {
        await page.addInitScript((t) => {
            (window as any)._buckarooTranscript = t;
        }, transcript.js_events);

        await page.goto(
            'http://localhost:6006/iframe.html?id=buckaroo-dfviewer-pinnedrowstranscriptreplayer--primary'
        );
        await waitForCells(page);

        const startButton = page.getByRole('button', { name: 'Start Replay' });
        await startButton.click();
        await page.waitForTimeout(500);

        const rowCount = await page.locator('.ag-row').count();
        expect(rowCount).toBeGreaterThan(0);
    });
}
```

### Validation

1. **7A:** Run transcript hash computation. Verify it produces consistent hashes
   for same code. Verify hash changes when widget logic changes.
2. **7B:** Run `pytest tests/unit/test_transcript_snapshots.py`. Generate golden
   snapshots. Modify widget code, verify test fails.
3. **7C:** Run replay tests against Storybook. Verify cells render.
4. **End-to-end:** Run CI twice with no widget/JS changes. Second run should skip
   pw-jupyter (cache hit).

### Risks

- **Transcript format drift:** Internal refactors silently invalidate all snapshots.
  Mitigation: version the snapshot format.
- **Dataset mismatch:** The CI transcript hash uses simplified test datasets that may
  not match the actual notebook datasets. Must use identical data.
- **False cache hit:** If transcript hash doesn't capture all relevant state (e.g.,
  missing `send()` payloads), a change could slip through. Start conservative —
  hash everything.

---

## Implementation Order

| Priority | Technique | Savings | Effort | Dependencies |
|----------|-----------|---------|--------|--------------|
| 1 | Tech 1+5a (server pool + warm kernels) | 8-11s | 1-2 days | None |
| 2 | Tech 2 (Chromium pre-start) | 2-3s | 0.5 day | Fold into Tech 1 post-run hook |
| 3 | Tech 7A (transcript oracle cache) | 0-37s (cache hit) | 1 day | None |
| 4 | Tech 7B+7C (Layer A+B fast signal) | ~10s fast answer | 2-3 days | Snapshot infra |
| 5 | Tech 5c (cpuset) | 3-6s (unmeasured) | 0.5 day | --privileged flag |
| 6 | Tech 6 (webhook pre-build) | 2-3s | 0.5 day | webhook.py changes |

**Skip:** Tech 3 (Node pre-start), Tech 4 (.pyc cache), Tech 5b (reschedule jobs),
Tech 5d (pytest pre-fork).

### First question to resolve

Before implementing Tech 1, verify the critical path claim from CI logs:

```bash
# On CI server, check recent log:
grep -E 'START|PASS|FAIL' /opt/ci/logs/<recent-sha>/ci.log
```

If build path (build-js + build-wheel + wheel-install = 16s) finishes AFTER warmup (11s),
then warmup is NOT the true bottleneck. Tech 1 would save only `16s - 11s = 5s` because
the build path would become the new gate. Verify timing before committing to Tech 1's
full implementation.
