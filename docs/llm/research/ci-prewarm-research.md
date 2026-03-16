# CI Pre-Warming Research Plan

**Goal:** Reduce latency from commit push to test answer. Total work done does not
matter — expensive speculative preparation is fine if it shrinks wall-clock time.

**Baseline (VX1 16C, JS cache hit):**
- Total: ~49s
- Critical path: `jupyter-warmup` (11s) → `playwright-jupyter` (37s)
- Build path: `build-js` (3s cache hit) → `build-wheel` (~8s) → `wheel-install` (~5s) = 16s
  — runs in parallel with warmup, so warmup is the true bottleneck leading into pw-jupyter

---

## Technique 1: Speculative Pre-Start of JupyterLab Servers

**What it does:** As soon as a CI run finishes, immediately start 9 fresh JupyterLab
servers for the next run. Each server handles exactly one Playwright test, then is killed
(no server reuse — the known constraint "never reuse a JupyterLab server after running a
Playwright test on it" is preserved). The servers may be at the wrong package version if
buckaroo changes — that's fine, we detect and fix it when the next run actually starts.

**Current cost being eliminated:** ~8–10s of server startup + 2s kernel warmup = 11s total.

**How it works:**

```bash
# Post-run hook: called at the end of run-ci.sh, after all jobs complete
speculative_prestart() {
    # Kill old servers from the run that just finished
    ci_pkill jupyter
    # Clean workspaces
    rm -rf ~/.jupyter/lab/workspaces

    # Start 9 fresh servers speculatively for the next run
    for port in $(seq 8889 8897); do
        jupyter lab --port=$port --no-browser --ServerApp.token='' &
    done

    # Record state so the next run-ci.sh knows servers are ready
    echo '{"ports": [8889..8897], "started_at": "'$(date -Iseconds)'"}' \
        > /opt/ci/jupyter-pool.json
}
```

When the next `run-ci.sh` starts:
```bash
job_jupyter_warmup() {
    if [[ -f /opt/ci/jupyter-pool.json ]]; then
        # Servers already running — just install the new wheel and trust notebooks
        install_wheel_into_jupyter_venv
        copy_and_trust_notebooks
        log "Using pre-started JupyterLab servers (skipping startup)"
        return 0
    fi
    # No pre-started servers — fall back to full warmup
    start_jupyter_servers_and_warmup
}
```

**Buckaroo reinstall:** The JupyterLab server doesn't import buckaroo — only the kernel
does. When the next run starts, it installs the new wheel into the jupyter venv. Fresh
kernels created by pw-jupyter will `import buckaroo` against the new wheel. No server
restart needed for buckaroo changes. If jupyterlab itself changes (rare), the pre-started
servers are at the wrong version — detect via version check and fall back to full warmup.

**Estimated speedup:** **8–11s** off critical path (eliminates entire warmup job).
Total: 49s → ~38s. This speedup is available immediately on any run that follows a
previous run — no webhook needed. The only "cold start" is the very first run after
container boot.

**Complexity:** Medium. Post-run hook, state file, version check, fallback path.

**Risk:** If the gap between runs is long (hours), servers may have drifted (OOM-killed,
port conflicts from other processes). Health-check each server before trusting the pool.
Also need to handle rapid successive runs — if a new run starts while the previous run's
post-run hook is still starting servers, the new run should wait for them or fall back.

---

## Technique 2: Persist Chromium Instances (Playwright Browser Server)

**What it does:** Instead of Playwright launching a fresh Chromium process for each
worker, pre-start Chromium instances and have Playwright connect to them via WebSocket.

**Current cost:** Chromium launch ~1.5–2s per worker. With 9 workers spawning in parallel,
this is ~2–3s of actual wall time. Chromium also compiles JIT on first JS execution.

**How to implement:**

Playwright has two mechanisms:

**Option A: CDP (Chrome DevTools Protocol)**
```bash
# Pre-start Chromium with remote debugging
chromium --remote-debugging-port=9222 --headless --disable-dev-shm-usage &
# ...wait for port to open...
```
```typescript
// playwright.config.ts (jupyter variant)
use: {
  browserURL: 'http://localhost:9222',  // connect instead of launch
}
```
`connectOverCDP` reconnects to a running Chromium. Fast but CDP-based connection has
some quirks with context isolation.

**Option B: Playwright Browser Server**

> **Note:** `npx playwright run-server` does not exist as a CLI command. Playwright exposes
> `browserType.launchServer()` as a Node.js API only. A small wrapper script is needed:
>
> ```javascript
> // ci/hetzner/browser-server.js
> const { chromium } = require('playwright');
> (async () => {
>   const server = await chromium.launchServer({
>     port: parseInt(process.env.PW_PORT || '3001'),
>   });
>   console.log(server.wsEndpoint());
> })();
> ```
> Start with: `PW_PORT=3001 node ci/hetzner/browser-server.js &`

```typescript
use: {
  browserWSEndpoint: process.env.PW_BROWSER_WS ?? undefined,
  // Falls back to local launch if env not set
}
```
This is cleaner: full context isolation per test, but Chromium process persists.

For 9 parallel workers, we'd need 9 Chromium instances (one per worker slot) or one
instance with 9 contexts (if the test isolation allows it). Playwright context isolation
means one Chromium + many contexts is fine for most tests.

**Invalidation triggers:**
- Playwright version change (version check on startup)
- Container restart
- Chromium crash (health check via CDP `/json/version`)

**Estimated speedup:** **2–4s** off playwright-jupyter (saves Chromium launch time).
Total after Technique 1: 38s → **34–36s**.

**Complexity:** Medium. Config change in `playwright.config.ts` (or a CI-specific config
variant), pre-start script, health check.

**Risk:** Context leakage between tests if browser isn't fully reset. Playwright context
isolation handles this, but page crashes in one test could affect others sharing a process.

---

## Technique 3: Pre-Start Playwright Node Process (Test Suite Pre-Import)

**What it does:** When `pnpm exec playwright test` runs, Node startup + module loading
+ test file discovery + config parsing takes 1–3s before any test executes. Pre-loading
would have Node already past this point, waiting for an "execute now" signal.

**Current cost:** ~1.5s Node startup + 1s test discovery + 0.5s config parsing = ~3s.
Not huge, but every second matters.

**Implementation options:**

**Option A: Playwright Component Testing Mode (not applicable here)**

**Option B: Playwright UI Mode / Watch Mode**
```bash
# Run playwright in watch mode — never exits, re-runs on signal
npx playwright test --ui &  # Not practical for CI
```

**Option C: Custom pre-fork (complex)**
Create a thin Node.js "runner daemon" that imports `@playwright/test` internals, loads
the config and test files, and waits on a Unix socket for a "run" command. Essentially
reimplementing Playwright's test runner interface — very invasive.

**Option D: Module pre-warming via Node's `--require`**
```bash
# Pre-load Playwright test runner and freeze it in a snapshot
# Node.js v18+ has --experimental-vm-modules
# Node.js v22 has --experimental-snapshot
node --experimental-snapshot capture --require @playwright/test ./snapshot.bin
```
Node compile snapshots are experimental but would allow loading from frozen state.

**Estimated speedup:** **1–2s** — the smallest gain here. Node startup is not the bottleneck.

**Complexity:** HIGH. Options A/B/C are either inapplicable or require invasive changes.
Option D depends on experimental Node features.

**Recommendation:** Defer. Not worth the complexity for 1–2s savings.

---

## Technique 4: Global .pyc Cache Across Venvs

**What it does:** When a fresh venv is created and packages installed, Python lazily
compiles `.py` files to `.pyc` on first import. A global cache would share compiled
bytecode across venvs so fresh venvs don't pay recompilation cost.

**Current state:** uv has `--compile-bytecode` / `UV_COMPILE_BYTECODE=1`, which runs
`compileall` after install. However:

- **uv does NOT cache .pyc files across venvs.** It hardlinks `.py` source files from
  its archive cache but recompiles bytecode fresh every time. Empirically measured:
  `uv pip install pandas` takes 80ms without `--compile-bytecode`, 1.2s with it.
- **uv recompiles the entire venv**, not just newly installed packages. Installing one
  small package triggers recompilation of pandas, numpy, and everything else. This is
  tracked as [astral-sh/uv#2637](https://github.com/astral-sh/uv/issues/2637) and
  [#12202](https://github.com/astral-sh/uv/issues/12202).
- A PR to fix targeted compilation (only compile newly installed packages, using RECORD
  files) is in progress: see `~/code/uv/PR_PLAN.md`.

**Why this doesn't matter much for our CI:**

- The pre-warmed kernel approach (Technique 5a) pre-imports pandas/polars/numpy, which
  triggers lazy `.pyc` compilation as a side effect. Once kernels are warm, the bytecode
  is compiled.
- `python -m compileall` on the entire buckaroo module takes **300ms** — not worth
  optimizing.
- Smoke test venvs (6 parallel) each pay ~1s of lazy compilation, but they run in parallel
  and are not on the critical path.

**Verdict:** Not worth building a custom `.pyc` cache. Set `UV_COMPILE_BYTECODE=1` in the
container environment if you want eager compilation, and wait for the uv fix to make it
incremental. The real compilation cost is already absorbed by kernel warmup (Tech 5a).

---

## Technique 5b: Pytest-as-a-Service (Cloudpickle Test Functions)

### The idea

Instead of "run pytest on this codebase", treat test execution as a service that accepts
test functions sent over a socket — either as paths to existing test cases or as
cloudpickled callables defined inline in CI scripts.

**Why not use `os.fork()`:** A pre-warmed server that forks to run tests has a fatal
conflict with the existing test suite:

1. **`test_server_killed_on_parent_death`**: kills its own parent PID to test that
   buckaroo's server shuts down. If running inside a fork from a pytest-server, it kills
   the pytest-server process itself.

2. **`mp_timeout_decorator_test.py` / `multiprocessing_executor_test.py`**: already
   `--ignore`d in CI because they use `forkserver`/`spawn` start methods that break in
   Docker PID namespaces. Inside a fork-child, these tests would attempt to attach to or
   create a forkserver that doesn't know about the fork's context.

3. **Forking a multithreaded process is unsafe**: importing pandas, polars, numpy, pyarrow
   all spawn internal thread pools (OpenBLAS, polars rayon, Arrow memory management).
   `os.fork()` clones only the calling thread. Mutexes held by those threads at fork time
   are permanently locked in the child with no thread to release them. This causes deadlocks
   in memory allocators and numpy's internal state — exactly the kind of subtle, hard-to-
   reproduce failure that makes CI unreliable.

**The cloud pickle model (without fork):** A server that accepts test functions as
cloudpickled callables and runs them in a **fresh subprocess** (not a fork). The server
handles dispatch; each test function runs in a clean Python process. The subprocess pays
the full import cost — the value is NOT startup speed, it's the ability to:
- Define tests inline in CI scripts without needing test files
- Send the transcript comparison logic directly from `run-ci.sh`
- Run ad-hoc checks that mix Python and CI state

```python
# ci/hetzner/pytest-server.py (no fork, fresh subprocess per request)
import subprocess, cloudpickle, socket, json, tempfile, os

def handle(req: dict) -> dict:
    if req['mode'] == 'pickle':
        fn = cloudpickle.loads(req['payload'])
        # Write cloudpickled function to temp file, run in fresh Python
        with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as f:
            f.write(req['payload'])
            pkl_path = f.name
        runner = f"""
import cloudpickle, sys
with open({repr(pkl_path)}, 'rb') as f:
    fn = cloudpickle.load(f)
try:
    fn()
    sys.exit(0)
except Exception as e:
    print(f'FAIL: {{e}}')
    sys.exit(1)
"""
        result = subprocess.run(['python3', '-c', runner], capture_output=True)
        os.unlink(pkl_path)
        return {"exit_code": result.returncode, "stdout": result.stdout.decode()}
```

### What this actually gives you

The subprocess approach pays full Python startup + import cost. It's not faster than
running `python3 -c ...` directly. The value is **the dispatch model**:

- CI scripts can define tests as Python functions and send them to the server, which
  routes them to the right Python version's worker
- The transcript oracle computation can be written once as a Python function and sent
  to all 4 Python version servers simultaneously
- The test runner (bash) doesn't need to know how to set up venvs, nice levels, etc.

### The transcript oracle use case (without fork)

The transcript hash computation doesn't need a server at all. It's a simple Python
script that runs once and exits:

```bash
# At t=0 in CI, start this immediately alongside other jobs:
python3 - <<'EOF'
import json, hashlib
from buckaroo import BuckarooWidget
import pandas as pd, polars as pl

datasets = {
    "test_buckaroo_widget":      pd.DataFrame(...),
    "test_polars_dfviewer":      pl.DataFrame(...),
    # ... all 9
}
hashes = {}
for name, df in datasets.items():
    w = BuckarooWidget(df)
    h = hashlib.sha256(json.dumps(w.df_display_args, sort_keys=True).encode()).hexdigest()
    hashes[name] = h

json.dump(hashes, open('/opt/ci/transcript-hashes.json', 'w'))
EOF
```

This takes ~2s (buckaroo + widget instantiation × 9, no browser). No server, no fork,
no multiprocessing. The transcript oracle cache lookup then reads that file in <1ms.

If 2s is too slow, the right solution is the **speculative pre-computation** from
Technique 6: start this script immediately on push webhook arrival, before `run-ci.sh`
is even called. By the time CI starts, the transcript hashes are already computed.

### Estimated value

The cloudpickle dispatch model is useful for **developer ergonomics** (inline test
functions in CI scripts) but provides no speed benefit over running `python3` directly.
The transcript oracle is better served by the push-webhook pre-computation (Technique 6).

**Verdict:** The fork-based pytest-server is not viable due to the multiprocessing test
conflicts and the unsafe-fork-after-threads problem. The cloudpickle dispatch model is
useful as an API layer but doesn't change CI timing. Focus instead on the push-webhook
pre-computation for transcript oracle speed.

---

## Technique 5: Reduce CPU Contention During playwright-jupyter

**The problem:** playwright-jupyter is the critical path at 37s. It runs 9 Chromium
instances + 9 JupyterLab servers + 9 Python kernels simultaneously. At the same time,
these other jobs are running:
- `test-python-3.12` and `test-python-3.14` (each: 4 pytest workers + imports)
- `smoke-test-extras` (6 parallel venvs with `uv pip install` + import compilation)
- `playwright-marimo`, `playwright-wasm-marimo`, `playwright-server`, `playwright-storybook`

That's potentially 50–60 Python/Chromium processes competing for 16 cores. Cache thrashing
and scheduler preemption create timing jitter that makes kernel execution unpredictable.
This is why the timing-sensitive test (`test_huge_dataframe_partial_cache_scenario`)
flakes under load.

### 5a: Keep Kernels Alive from Warmup (Biggest Win)

Currently `job_jupyter_warmup` creates kernels, waits for them to reach `idle` (meaning
all imports done: `import ipykernel, anywidget, buckaroo, pandas, polars`), then **deletes**
them. pw-jupyter then creates **new** kernels, triggering another round of heavy imports.

The CPU burst from 9 kernels simultaneously importing pandas+polars is the worst possible
time to add load — right when Chromium is rendering JupyterLab.

**Critical: do NOT pre-import buckaroo.** The warmup kernel should only import third-party
packages that don't change between runs: `pandas, polars, numpy, pyarrow, anywidget,
ipykernel`. Buckaroo itself imports in <100ms and MUST be imported fresh from the newly
installed wheel — otherwise the kernel has stale module state from the previous run's
wheel. The notebook cell does `import buckaroo` against the current wheel; everything
else is already in `sys.modules` from warmup.

**Fix:** Don't delete kernels after warmup. Store their IDs in a state file. pw-jupyter
connects to the pre-warmed idle kernel instead of creating a new one.

```bash
# In warmup: after kernel reaches idle, DON'T delete it
# Instead:
echo "$kid" >> "/tmp/ci-jupyter-warmup-kernels-${port}"

# In pw-jupyter test script: look up the pre-warmed kernel ID for this slot
PREWARM_KERNEL=$(cat "/tmp/ci-jupyter-warmup-kernels-${port}" 2>/dev/null | head -1)
if [[ -n "$PREWARM_KERNEL" ]]; then
    export JUPYTER_KERNEL_ID="$PREWARM_KERNEL"
fi
```

This requires the Playwright test itself to be able to specify a kernel ID (open the
notebook on a specific existing kernel rather than creating a new one). JupyterLab's URL
supports `?kernel_id=...` but it's not a standard parameter — would need a custom startup
path or API call.

**Alternative:** Use the Jupyter REST API to "reuse" a kernel: open a notebook session
against a specific kernel ID rather than auto-creating. The Sessions API (`POST /api/sessions`)
allows specifying `kernel.id`.

**Estimated speedup:** **4–6s** off pw-jupyter duration. The 9-kernel CPU burst shifts
from t=0 of pw-jupyter (worst time) to t=−warmup (before pw-jupyter starts, CPU is idle).
Also reduces flakiness of timing-dependent tests.

**Relationship to Tech 1:** When servers are speculatively pre-started (Tech 1), the
post-run hook can also pre-warm kernels as part of the same process — making 5a's savings
part of Tech 1's estimate. Tech 5a provides independent value on cold starts (no
pre-started servers) where warmup runs during the CI run and keeping kernels alive avoids
a second import burst when pw-jupyter starts.

### 5b: Schedule Non-Critical CPU-Hungry Jobs After pw-jupyter

Smoke-test-extras and test-python-3.12/3.14 are not on the critical path — pw-jupyter
(37s) runs longer. Move them to START after pw-jupyter completes rather than during it.

```bash
# In run_dag(), instead of:
run_job smoke-test-extras ... & PID_SMOKE=$!
( sleep 10; run_job test-python-3.12 ... ) & PID_PY312=$!

# Do:
wait $PID_PW_JP || OVERALL=1    # wait for pw-jupyter first
run_job smoke-test-extras ... & PID_SMOKE=$!
run_job test-python-3.12 ... &  PID_PY312=$!
run_job test-python-3.14 ... &  PID_PY314=$!
wait $PID_SMOKE $PID_PY312 $PID_PY314 || OVERALL=1
```

**Wall-time impact:** These jobs (smoke ~20s, py3.12 ~10s) finish within pw-jupyter's
37s window anyway. Moving them after pw-jupyter adds ~10s if they're the new bottleneck.
But they run in ~20s after pw-jupyter's 37s, so total becomes max(37, later) + 20 = 57s.

This is a regression in wall time but a reliability improvement. **Tradeoff: not a pure win.**

Better compromise: delay their START by 20s (not 10s as now) — let pw-jupyter's heaviest
kernel-startup phase (first 15s) finish before adding load.

### 5c: cpuset Isolation (Pin pw-jupyter to Dedicated Cores)

Reserve cores 0–11 exclusively for pw-jupyter (9 Chromium + 9 kernels) and cores 12–15
for everything else. The kernel import bursts and Chromium rendering get uncontested cores.

```bash
# Requires cgroup v2 (available in Docker with --privileged or specific caps)
# Create cpuset cgroup for pw-jupyter
mkdir -p /sys/fs/cgroup/pw-jupyter
echo "0-11" > /sys/fs/cgroup/pw-jupyter/cpuset.cpus
echo "0"    > /sys/fs/cgroup/pw-jupyter/cpuset.mems

# Run pw-jupyter inside the cgroup
echo $$ > /sys/fs/cgroup/pw-jupyter/cgroup.procs
bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" ...
```

**Feasibility concern:** Docker containers by default don't have write access to
`/sys/fs/cgroup/`. Requires `--privileged` flag or `--cap-add SYS_ADMIN`. Our current
container setup would need to be updated in `docker-compose.yml`.

**Estimated speedup:** Hard to measure without data. Eliminates the ~30% CPU overhead
from scheduling 50+ processes on 16 cores. Estimate: **3–6s** off pw-jupyter, fewer
timing-test flakes.

### 5d: Pre-Warmed pytest-xdist Workers via Socket Transport

**The idea:** Pre-start N Python processes with pandas/polars/pyarrow already imported.
When `pytest -n4` runs, connect to these idle workers via xdist's socket transport instead
of spawning fresh ones. The import CPU burst shifts from the CI run to before it starts.

**Why this helps:** test-python-3.11 and 3.13 start at t=0, competing with jupyter-warmup
for 16 cores. Their first 2–3s is importing heavy packages (pandas, polars, pyarrow) —
this spikes CPU exactly when warmup needs it. Pre-warmed workers eliminate this burst.

For test-python-3.12/3.14 (which start during pw-jupyter), the benefit is even larger:
these jobs' import burst currently overlaps with playwright-jupyter's heaviest phase.

**Implementation:**

pytest-xdist supports `--tx socket=host:port` via `execnet`. A pre-warmed worker is an
execnet socket server that has already done the heavy imports:

```bash
# Start pre-warmed xdist socket workers for a given Python version
start_xdist_workers() {
    local python="$1"
    local port_base="$2"
    local n="${3:-4}"
    for i in $(seq 0 $((n-1))); do
        port=$((port_base + i))
        # Worker pre-imports heavy packages, then serves as execnet socket gateway
        $python - <<'EOF' &
import pandas, polars, pyarrow, numpy  # pre-import; buckaroo NOT pre-imported (see below)
import sys
sys.argv = ['execnet.script.serve', '--port', '$port']
from execnet.script import serve
serve.main()
EOF
    done
}

# In test job, connect to pre-warmed workers:
pytest -n4 --dist=load \
    --tx "socket=localhost:9001" --tx "socket=localhost:9002" \
    --tx "socket=localhost:9003" --tx "socket=localhost:9004" \
    tests/unit/
```

**Why NOT pre-import buckaroo:** After `uv sync` + editable install, `buckaroo` source
files may have changed. A pre-warmed worker's `sys.modules['buckaroo']` would have the
OLD version. Only pre-import packages that don't change between runs: pandas, polars,
pyarrow, numpy. These are stable across CI runs for a given venv hash.

**Invalidation:** If the venv's package hash changes (polars upgraded, etc.), kill and
restart workers. Hash check: `uv pip freeze | sha256sum`.

**Is fork-after-numpy a concern here?**

**No.** The pre-warmed worker is a standalone process (not forked from the test runner).
The worker imports pandas/polars, then serves test requests sent over the socket. No
`os.fork()` is involved after the imports.

Additionally: `mp_timeout_decorator.py` line 149 uses `multiprocessing.get_context("forkserver")`.
The **forkserver** is a clean Python process spawned before any user imports. All subsequent
`ctx.Process()` calls ask the forkserver to fork from its own clean state — NOT from the
pandas-loaded parent. The `lazy_infinite_polars_widget` / `MultiprocessingExecutor` path
does NOT do fork-after-numpy. The forkserver design specifically exists to avoid this hazard.

**Estimated speedup:** 2–4s reduction in CPU contention during warmup + pw-jupyter phases.
Benefit is greatest for test-python-3.12/3.14 (which start during pw-jupyter).

**Complexity:** Medium. Standard xdist socket transport is documented; the pre-import
wrapper script and worker lifecycle management (~30 lines of bash) are the main work.

**Practical conclusion:** For pytest, the value is **reduced CPU burst during
warmup+kernel startup**. The cpuset approach (5c) gives equivalent contention reduction
with less code. Use xdist socket workers if cpuset requires --privileged (a constraint).

**Estimated combined speedup from Technique 5 (without Tech 1):** On a cold start where
servers are not pre-started, 5a alone saves 4–6s off pw-jupyter by keeping kernels alive
from warmup. 5c (cpuset) may provide additional contention reduction but its value is
unmeasured. 5b and 5d are not recommended.

---

## Technique 6: Speculative Pre-Build on Push (Before CI Is Triggered)

**What it does:** The latency window from `git push` to "CI shows pass/fail" includes:
1. GitHub webhook → our CI server: ~0.5–2s
2. `git fetch` + `git checkout`: ~2–3s (network + disk)
3. JS build or cache check: 0–15s
4. Everything else on the critical path

If we intercept the push event (via webhook) and speculatively start `git fetch`,
`git checkout`, JS build, and even `build-wheel` before the CI job is formally
triggered, those steps disappear from the measured latency.

**Implementation:**

```bash
# Pre-warmer webhook handler (separate from run-ci.sh)
# Triggered by GitHub push event
on_push(sha, branch):
    git fetch origin
    git checkout -f $sha
    # Try to build JS speculatively
    compute_js_hash && check_js_cache || run_build_js
    # Try to build wheel speculatively (takes ~8s)
    run_build_wheel
    # Start JupyterLab server pool warm (if jupyterlab version unchanged)
    ensure_jupyter_pool_ready
    # Write "pre-warm complete" marker for $sha
    echo $sha > /opt/ci/prewarm-ready
```

When `run-ci.sh $SHA ...` is called, it checks for `prewarm-ready` and skips
build-js, build-wheel, jupyter-warmup if already done.

**What this eliminates from measured time:**

The current critical path is: `warmup (11s)` → `pw-jupyter (37s)` = 48s. The build path
(`build-js 3s` → `build-wheel 8s` → `wheel-install 5s` = 16s) runs in parallel and finishes
within the warmup window, so it's not on the critical path for JS-cache-hit runs.

- `jupyter-warmup`: **11s saved** — this is the critical-path win. The build path and
  warmup overlap, so warmup is the gate. Pre-starting servers (Tech 1) achieves this
  without a webhook.
- `git fetch` + `git checkout`: 2–3s — saved only if webhook triggers before `run-ci.sh`.
- `build-js` (cache miss): up to 15s — relevant only on JS changes. On cache hit (3s),
  this finishes well within the warmup window and saves nothing off the critical path.
- `build-wheel`: 8s — parallel with warmup, not on critical path.

**Estimated speedup (over baseline 49s):** **~11s** from pre-starting servers (same as
Tech 1, which can be done without a webhook). The webhook adds **2–3s** more (git fetch)
and enables cache-miss JS builds to happen speculatively. Total: **11–14s** on typical
runs, up to **~25s** on JS-cache-miss runs where build-js (15s) would otherwise become
the new critical path after warmup is eliminated.

**Complexity:** Medium–High. Need a webhook handler separate from the CI runner,
careful SHA-matching (speculative build for SHA X must not contaminate run for SHA Y),
and fallback to full build if pre-warm missed or failed.

**Relationship to Technique 1:** Tech 1 (post-run pre-start) gives most of the speedup
without a webhook — servers are ready because the previous run started them. Tech 6 adds
value in two cases: (a) git fetch + checkout can happen before `run-ci.sh` is called
(~2-3s), and (b) JS cache-miss builds can happen speculatively (up to 15s, but only when
JS changes). For JS-cache-hit runs, Tech 6 adds only the git-fetch savings over Tech 1.

---

## Summary Table

| Technique | Speedup | Complexity | Mechanism |
|-----------|---------|------------|-----------|
| 1+5a. Pre-start servers + warm kernels | **8–11s** | Medium | Eliminates warmup; kernels pre-import deps (not buckaroo) |
| 2. Pre-start Chromium instances | **2–3s** | Medium | Saves Chromium launch in pw-jupyter |
| 3. Pre-start Node/Playwright | 1–2s | High | Minimal; skip |
| 4. Global .pyc cache | — | — | Not worth it; wait for uv fix |
| 5a. Keep kernels alive from warmup | **4–6s** | Medium | Eliminate 9× import burst during pw-jupyter |
| 5b. Schedule heavy jobs after pw-jupyter | 0s net | Low | Reduces contention, may add tail latency |
| 5c. cpuset isolation for pw-jupyter | **?** | Med (needs --privileged) | Unmeasured; theoretical basis is weak |
| 5d. Pre-fork pytest workers | 2–4s | High | Marginal; cpuset is better |
| 6. Speculative pre-build on push | **2–3s** incremental | Med-High | Git fetch + JS cache-miss builds |
| **7. Synthetic test split (fast path)** | **27s to first answer** | Med-High | Python snapshot + Storybook replay |

**Note on additivity:** Tech 1 and 5a overlap — both target the warmup phase. Tech 1
eliminates server startup (8-11s). Tech 5a eliminates the kernel import burst that happens
*during* pw-jupyter. If servers are pre-started (Tech 1), the warmup kernels can also be
pre-warmed as part of the same speculative pre-start, so **5a's savings are included in
Tech 1's estimate** for the post-first-run case. Tech 5a provides independent value only
when servers are NOT pre-started (cold start, or pre-start failed).

### Recommended order

**Phase 1 (high value, reasonable complexity):**
1. **Tech 1 + 5a combined** — post-run hook pre-starts 9 servers AND pre-warms kernels
   (importing pandas/polars/numpy/pyarrow/anywidget, but NOT buckaroo). Next run skips
   warmup entirely, pw-jupyter gets pre-warmed kernels. Combined: **8–11s** off critical
   path. On cold start (no pre-started servers), falls back to current warmup behavior
   but with 5a's improvement (don't delete kernels after warmup).

**Phase 2 (medium value):**
2. **Tech 2** — pre-warm Chromium. 2–3s saved from pw-jupyter launch.
3. **Tech 5c** — cpuset isolation (if --privileged is available in container). Needs
   docker-compose change + cgroup setup. Value is uncertain — measure before committing.

**Phase 3 (incremental, architectural):**
4. **Tech 6** — webhook for speculative git fetch + JS build. Adds 2–3s on top of
   Tech 1 (git fetch time), more on JS-cache-miss runs.

**Skip:**
- Tech 3 (Node pre-start): 1–2s, high complexity.
- Tech 4 (.pyc cache): not worth it, wait for uv#2637 fix.
- Tech 5d (pytest pre-fork): cpuset is simpler and more effective.

### Theoretical minimum with all techniques applied

The critical path today is: `warmup (11s)` → `pw-jupyter (37s)` = **48s**.
pw-jupyter's 37s breaks down as: Chromium launch (~2s) + kernel import burst (~4s) +
actual test execution (~31s).

| State | Critical path | What changes |
|-------|--------------|--------------|
| Baseline | 48s | warmup (11s) → pw-jupyter (37s) |
| + Tech 1+5a (pre-start servers+kernels) | ~37s | warmup eliminated; pw-jupyter starts immediately with warm kernels, saving ~4s of import burst → **~33s** pw-jupyter |
| + Tech 2 (pre-start Chromium) | ~31s | Chromium launch (~2s) eliminated from pw-jupyter |
| + Tech 6 (webhook pre-build) | ~29s | git fetch (2s) moved before run-ci.sh |

**Floor:** The actual test execution within pw-jupyter (9 notebooks, parallelized across
9 workers) takes ~31s. Individual notebook runs are ~4s each, 37s / 9 = 4.1s average.
The overhead above 31s is Chromium + kernel startup. With all techniques applied, we
approach the test-execution floor of **~31s**.

The 31s test-execution floor cannot be shortened without:
- Running fewer notebooks (remove test coverage)
- Speeding up individual notebook execution (widget rendering, Python execution speed)
- Faster Chromium rendering (not under our control)

---

## Technique 7: Synthetic Test Split — Python Transcript + JS Replay

### The core idea

The playwright-jupyter tests verify two things simultaneously:
1. Python produces the correct output (column config, row data, infinite scroll responses)
2. JS renders that output correctly in the browser DOM

These can be tested independently, at much lower cost:
- **Layer A** — Python side: Does the widget emit the correct trait state and `send()` payloads?
  No browser needed. Pure pytest. ~2–5s for all notebooks' worth of data.
- **Layer B** — JS side: Given a known-good transcript, does the browser render correctly?
  No Python kernel needed. Storybook + Playwright. ~5–10s.

Together they run in ~10s. Deliver a "likely pass" answer 40s before the full playwright-jupyter
confirms it. Also: if only Python changed, Layer A catches the regression. If only JS changed,
Layer B catches it.

### What already exists

This infrastructure is **already partially built**:

- `record_transcript = Bool(False).tag(sync=True)` — Python trait that tells JS to start
  recording all widget messages to `window._buckarooTranscript`
- `window._buckarooTranscript` — JS global capturing the live event stream
  (`dfi_cols_fields`, `all_stats_update`, `pinned_rows_config`, `infinite_resp_parsed`,
  `custom_msg`)
- `PinnedRowsTranscriptReplayer` Storybook story — takes a transcript (via
  `window._buckarooTranscript` or `page.addInitScript()` injection) and replays it
  against the real widget, verifying DOM output
- `transcript-replayer.spec.ts` — Playwright tests against the Storybook replayer.
  Already verifies column headers, row data, multi-batch scroll.
- `infinite-scroll-transcript.spec.ts` — Records live transcripts from real JupyterLab runs
- `self.send({"type": "infinite_resp", ...})` — Python side sends data as parquet buffers

**The missing piece: Python-side transcript capture without a browser.**

Currently, recording happens in the browser JS (`window._buckarooTranscript`). To test the
Python side independently, we need to intercept what Python SENDS before the comm layer.

### Layer A: Python transcript capture (no browser)

**What to capture from Python:**
1. Trait state after initialization: `widget.df_display_args`, `widget.buckaroo_state`,
   `widget.column_config` — all traitlets with `tag(sync=True)` that would be sent to JS
2. `self.send()` payloads — the `infinite_resp` parquet responses, which are custom comm
   messages not captured by traitlet sync

**How to mock `self.send()`:**

```python
# tests/unit/transcript_capture_test.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from buckaroo import BuckarooWidget

def capture_widget_transcript(df, **kwargs):
    """Instantiate a widget, intercept all sends, return transcript."""
    sent_messages = []

    with patch.object(BuckarooWidget, 'send', lambda self, msg, buffers=None:
                      sent_messages.append({"msg": msg, "has_buffers": buffers is not None})):
        widget = BuckarooWidget(df, **kwargs)
        # Simulate the initial data request (browser would normally send this)
        widget._handle_custom_msg({"type": "get_data", "key": {"offset": 0, "length": 100}}, [])

    return {
        "trait_state": {
            "df_display_args": widget.df_display_args,
            "buckaroo_state": widget.buckaroo_state,
        },
        "sent_messages": sent_messages,
    }

def test_polars_dfviewer_transcript_snapshot(snapshot):
    import polars as pl
    df = pl.DataFrame({"a": [1,2,3], "b": ["x","y","z"]})
    transcript = capture_widget_transcript(df)
    assert transcript == snapshot  # pytest-snapshot or similar
```

This runs in milliseconds per widget. 9 notebooks × ~100ms = ~1s total (parallel).

**Snapshot management:** Use `pytest-snapshot` or `syrupy` to maintain golden JSON files.
On commit: `pytest --snapshot-update` regenerates. In CI: fail if snapshot differs from
golden. The snapshots live in `tests/unit/snapshots/` and are committed to git.

**What it catches:**
- Regression in column detection logic
- Changes in `df_display_args` structure
- Wrong column types, displayer configs, pinned rows
- Incorrect infinite_resp payloads (wrong data, wrong parquet encoding)

**What it misses:**
- Whether the JS actually renders the data correctly (Layer B covers this)
- E2E communication reliability (covered only by full playwright-jupyter)

### Layer B: JS transcript replay via Storybook (no Python, no JupyterLab)

The Storybook `PinnedRowsTranscriptReplayer` story already accepts injected transcripts.
The key gap: currently the stories use hardcoded test data, not actual notebook transcripts.

**Proposed: parameterize Storybook tests with snapshot data**

```typescript
// pw-tests/transcript-replay-from-snapshot.spec.ts
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import { waitForCells } from './ag-pw-utils';

// Load transcripts generated by Python Layer A tests
const SNAPSHOT_DIR = '../../tests/unit/snapshots/transcripts';

for (const snapshotFile of fs.readdirSync(SNAPSHOT_DIR).filter(f => f.endsWith('.json'))) {
    const transcript = JSON.parse(fs.readFileSync(`${SNAPSHOT_DIR}/${snapshotFile}`, 'utf-8'));

    test(`replay: ${snapshotFile}`, async ({ page }) => {
        await page.addInitScript((t) => { (window as any)._buckarooTranscript = t; }, transcript.js_events);
        await page.goto('http://localhost:6006/iframe.html?id=buckaroo-dfviewer-pinnedrowstranscriptreplayer--primary');
        await waitForCells(page);

        const startButton = page.getByRole('button', { name: 'Start Replay' });
        await startButton.click();
        await page.waitForTimeout(500);

        // Assert on expected row count and column headers from snapshot metadata
        const rowCount = await page.locator('.ag-row').count();
        expect(rowCount).toBeGreaterThan(0);

        // Assert key cells from snapshot expected values
        for (const { selector, value } of transcript.expected_cells) {
            await expect(page.locator(selector)).toContainText(value);
        }
    });
}
```

**Speed:** No Python server, no JupyterLab. Just Storybook (already running for
`playwright-storybook`) + Chromium. Per-test: ~1–2s including replay. 9 notebooks = ~5–10s
total (parallelized).

**What it catches:**
- JS rendering regression (column config not applied, wrong cell values)
- AG-Grid crashes on specific data shapes
- Formatting/displayer bugs

**What it misses:**
- Whether the E2E comm protocol works (covered by playwright-jupyter)
- Infinite scroll triggered by actual user scroll (covered by playwright-jupyter)
- JupyterLab-specific CSS/DOM context: Storybook uses its own stylesheet. Bugs
  from JupyterLab theme, `OutputArea` sizing, or widget container z-index won't
  be caught here.

### Layer B variant: JupyterLab DOM with snapshot shim (higher fidelity, similar speed)

For cases where Storybook's different CSS context is a concern, a middle option:
run against real JupyterLab but replace actual Python execution with a snapshot shim.

The comm channel is established by Python, so Python must run. But instead of doing
real pandas/polars analysis, the kernel executes a trivial shim that loads state from
the snapshot file:

```python
# Notebook shim cell (replaces the real cell)
import json
from buckaroo import BuckarooWidget
snapshot = json.load(open('/opt/ci/snapshots/test_polars_dfviewer.json'))
# Create widget skeleton and inject pre-computed state
bw = object.__new__(BuckarooWidget)
super(BuckarooWidget, bw).__init__()  # initialize comm/widget machinery
bw.df_display_args = snapshot['df_display_args']
bw.buckaroo_state  = snapshot['buckaroo_state']
bw  # display via comm
```

**Time savings over current:** Python analysis (~1-2s/notebook) replaced by JSON load
(~50ms). With 9 parallel slots: **saves ~2s wall time** off the 37s. Marginal.

**Why Storybook Layer B is preferred for the fast path:** Storybook skips JupyterLab
server startup and kernel connection entirely, running in ~5-10s vs 30-35s for the
JupyterLab shim approach. Use the shim only as a targeted supplement when a Storybook
failure needs to be confirmed in the real Jupyter context.

**The comm injection alternative (no Python at all):** You'd need to synthesize a
`comm.open()` message at the Jupyter messaging protocol level and inject it into the
JupyterLab kernel comms registry — requiring deep knowledge of anywidget internals and
the Jupyter comm protocol. Not worth it: the complexity exceeds the 1-2s time saving.

### Transcript equality as a deterministic oracle

```
playwright_jupyter_result = f(transcript, js_code)
```

It's a pure function of both inputs. The skip condition is: **have we already run
f(transcript_hash, js_hash) and gotten PASS?** If yes → result is identical by definition.
Skip playwright-jupyter entirely.

**This is a content-addressed result cache keyed by `(transcript_hash, js_hash)`.**

Not "probably fine" — **certain** (modulo non-determinism in test assertions themselves).

**The decision tree:**

```
t=0: Compute transcript_hash (Python, ~1s) and js_hash (git ls-tree, ~0.1s)

Look up (transcript_hash, js_hash) in result_cache:

  CACHE HIT (PASS):
    → Skip playwright-jupyter entirely. Done in ~2s.
    → Applies whenever this exact (Python output, JS code) pair was previously tested.
      This includes: cosmetic commits, print statement fixes, CI changes, reverts,
      pure refactors that preserve widget output, and any commit where neither
      widget logic nor JS rendering code changed.

  CACHE MISS:
    → This (transcript, JS) combination has never been tested.
    → Must run full playwright-jupyter (37s) to get an authoritative result.
    → Run Layer B in parallel for fast signal at ~10s.
    → Store (transcript_hash, js_hash, result) in cache on completion.
```

**What triggers a cache miss?**
- Transcript changes: any Python change that affects widget output (column detection,
  stats computation, data serialization, displayer config)
- JS changes: any change to `packages/*/src/`
- First run ever for a new dataset or test notebook
- A revert that brings hashes back to a previously cached pair → cache HIT

**What "compute transcript" costs:**
Instantiate `BuckarooWidget(df)` for each test dataset in pure Python, capture
`df_display_args` + `send()` payloads, SHA-256 the normalized JSON. ~100ms per notebook
× 9 = ~1s. This runs at t=0 alongside lint/build/test jobs.

**Common case: skip.**
Any commit that doesn't touch widget logic or JS src triggers a cache hit. This
includes all documentation, test files, CI scripts, non-widget Python, and
behaviorally-equivalent refactors. In typical development this is the majority of commits.

### The CI workflow

```
t=0:    Compute transcript_hash + js_hash (~1s) in parallel with lint/build/test-python

  CACHE HIT:
    t=1:  "Known result for (T, J) → playwright-jupyter SKIPPED"
    t=1:  Report PASS on ci/hetzner/playwright context
    t=10: Other jobs complete → full PASS reported
    [playwright-jupyter never runs]

  CACHE MISS:
    t=1:  Start Layer B (Storybook replay, ~10s) for fast signal
    t=1:  Start playwright-jupyter (37s) for authoritative result + cache population
    t=11: Layer B result → report on ci/hetzner/playwright-fast context
    t=38: playwright-jupyter result → report on ci/hetzner/playwright-full context
          → store (transcript_hash, js_hash, result) in cache
```

GitHub supports multiple commit status contexts. `ci/hetzner/playwright-fast` at ~11s
gives the developer an early answer. `ci/hetzner/playwright-full` at ~38s is the
authoritative gate for merges.

**The cache must persist across runs** — stored at `/opt/ci/transcript-result-cache/`
as `{transcript_hash}-{js_hash}.result` files. Keyed by content, not by SHA or branch.
A revert automatically gets a cache hit if the result was stored when that content was
last tested.

### Layer B's role

Layer B (Storybook replay) runs in parallel with playwright-jupyter on cache misses. Its
job is to deliver a fast signal (~10s), not to replace playwright-jupyter. Over time, if
the false-negative rate of Layer B is measured to be zero across the corpus, it can be
promoted to authoritative — but that trust must be earned from data, not assumed.

**Measuring Layer B reliability:**
```
For each cache-miss commit: record (layer_b_result, full_pw_jupyter_result)
  (pass, pass)  → Layer B gave correct fast signal
  (fail, fail)  → Layer B caught bug early
  (pass, fail)  → FALSE NEGATIVE: Layer B missed something  ← dangerous, measure this
  (fail, pass)  → false positive: Layer B over-strict
```

Until false-negative rate is measured at zero across N commits (N ≥ 50), playwright-jupyter
always runs on cache misses regardless of Layer B result.

### Validation methodology

The cache-hit skip is **deterministic** — same inputs, same function, same output.
No validation needed beyond verifying the cache was populated from a correct run.

Layer B reliability requires empirical validation via the stress test corpus.

### Fragility analysis

**1. Transcript format drift**
The transcript format (`dfi_cols_fields`, `infinite_resp_parsed`, etc.) is an internal detail.
Any refactor of the widget communication protocol silently breaks all snapshots.
Mitigation: version the transcript format; detect format-mismatch (check schema version key
in snapshot header) and auto-invalidate rather than false-passing.

**2. Infinite scroll bidirectionality**
For infinite scroll tests, the transcript is a request→response dialogue. Layer A captures
Python's *responses* to *simulated requests* (hardcoded offset=0, length=100). If the browser
sends different requests (due to viewport size, scroll position), the captured transcript
doesn't match real behavior.
Mitigation: the Layer A simulation uses the same request sequence the notebook uses. The full
playwright-jupyter run is the ground truth for bidirectional behavior.

**3. Snapshot staleness**
When Python output changes intentionally (new feature, data format), all snapshots must be
regenerated. Stale snapshots produce false failures.
Mitigation: `pytest --snapshot-update` as part of the dev workflow. In CI: if `--snapshot-update`
is the only diff, it's a "snapshot refresh commit" — safe to auto-approve.

**4. Storybook story coupling**
The `PinnedRowsTranscriptReplayer` story must stay in sync with the snapshot format. If the
story's mock comm changes event handling, Layer B breaks without Layer A catching it.
Mitigation: keep the story's event schema version-locked to the snapshot format version.

**5. DOM assertion brittleness**
The Layer B assertions (`.ag-cell:has-text("Alice")`) are fragile to column order changes,
cell formatting changes, column renaming. Use structural assertions where possible
(row count, column count) and data assertions only for key sentinel values.

### Estimated impact

| Path | Time | Applies when | Certainty |
|------|------|--------------|-----------|
| Oracle: transcript + JS hash match | ~2s | No widget/JS change | Deterministic |
| Layer A fail: Python output changed | ~2s | Widget logic changed | Deterministic |
| Layer B: Storybook replay | ~10s | Transcript or JS changed | Needs validation |
| Full: playwright-jupyter | ~37s | Both changed, or Layer B fails | Authoritative |

**Frequency estimate for typical development:**
- ~60% of commits: cache hit → skip → ~2s
- ~40% of commits: cache miss → playwright-jupyter runs (37s), Layer B runs in parallel (10s fast signal)

**Weighted average CI time for playwright coverage:**
`0.60 × 2s + 0.40 × 37s = 1.2 + 14.8 = ~16s`

vs current **37s** for every commit. **~2.3× speedup on average.**

The cache hit rate improves over time as more (T, J) combinations are tested and stored.
Reverts, hot-fixes to non-widget code, and repeated test runs against stable widget output
all benefit from the cache immediately. The 37s run only fires when genuinely new
Python-widget or JS-rendering code is being validated for the first time.

---

## Implementation Notes

### Speculative Pre-Start Design

```
/opt/ci/jupyter-pool/
    pool.json          # {pids:[...], ports:[8889..8897], started_at, jupyterlab_version}
```

**Post-run hook** (end of `run-ci.sh`): kill old servers, clean workspaces, start 9 fresh
servers, pre-warm a kernel in each (import pandas/polars/numpy/pyarrow/anywidget — NOT
buckaroo), write `pool.json`.

**Pre-run check** (start of next `run-ci.sh`): read `pool.json`, health-check each server
(HTTP GET `/api/status`), verify jupyterlab version matches. If valid: install new wheel
into jupyter venv, copy+trust notebooks, skip warmup. If invalid: fall back to full warmup.

### Chromium Server Design

> **Note:** `npx playwright run-server` does not exist. Use the `browser-server.js`
> wrapper script described in Technique 2.

```bash
for slot in $(seq 0 8); do
    PW_PORT=$((3001 + slot)) node ci/hetzner/browser-server.js &
done
```

In `playwright.config.ts` (CI variant only):
```typescript
use: {
  browserWSEndpoint: process.env.PW_BROWSER_WS ?? undefined,
  // Falls back to local launch if env not set
}
```

Set `PW_BROWSER_WS=ws://localhost:3001` when connecting to pre-warmed server.
