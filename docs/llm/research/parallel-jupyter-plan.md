# Parallel Jupyter Playwright Testing — Findings & Plan

## Status: Parked at PARALLEL=1

PARALLEL=1 is shipped and stable (9/9 pass, ~104s). The work below documents 20 experiments attempting PARALLEL=3 and lays out how to resume if the notebook count grows enough to justify it.

---

## What We Learned (20 experiments)

### The three failure modes, in order of discovery

**1. ZMQ socket contention (shared server, any PARALLEL>1)**

Multiple concurrent kernel startups on one JupyterLab server race for ZMQ socket allocation. Manifests as `tornado.websocket.WebSocketClosedError` and `zmq.error.ZMQError: Socket operation on non-socket`. The widget comm channel never establishes — the cell executes but no output arrives. No amount of waiting fixes this.

- Observed: Exp 2 (PARALLEL=3), Exp 4 (PARALLEL=2)
- Fix: **One JupyterLab server per parallel slot** on a distinct port. Eliminates all ZMQ contention.

**2. CPU competition during server startup**

Starting N JupyterLab servers simultaneously on an 8-core box causes all to compete for CPU during their Python import + extension loading phase. Servers on later ports (8890, 8891) take 3-5x longer to reach HTTP-ready. Even after HTTP-ready, their kernel provisioners are sluggish because the JupyterLab process itself is still settling.

- Observed: Exp 6 (3 servers, parallel startup, 72s startup phase, 2/9 fail)
- Fix: **Sequential server startup** — start server N, poll until HTTP 200, then start server N+1.

**3. Batch-1 kernel startup contention**

Even with isolated servers and sequential startup, the first batch of 3 notebooks launching simultaneously causes CPU contention during Python kernel startup (specifically `import polars`, which compiles Rust FFI bindings). The kernel on slot 2 (last to start) exceeds the cell execution timeout because 3 concurrent `import polars` processes saturate CPU.

- Observed: Exp 7-20 (various configurations, 1-3/9 fail, always batch 1, always last-launched slot)
- Partial mitigations tried:
  - 30s sleep after servers HTTP-ready (helps but doesn't eliminate)
  - 20s stagger between batch-1 launches (helps but eats all parallelism savings)
  - Pre-warming `.pyc` bytecaches in the parent process (marginal)
  - REST API warmup kernels (counterproductive — creates ghost processes because JupyterLab REST API never reports `idle` without a WebSocket client)
  - CELL_EXEC_TIMEOUT up to 60s (tolerates slow starts but doesn't fix root cause)

### The timing math problem

PARALLEL=1 takes ~104s (9 notebooks × ~12s each, no overhead).

PARALLEL=3 best case (no stagger, no sleep):
- Sequential server startup: ~45s (3 × 15s)
- 3 batches × ~14s each: ~42s
- **Total: ~87s** (17s savings)

PARALLEL=3 with stagger needed for reliability:
- Sequential server startup: ~45s
- Post-startup sleep: 30s
- Batch 1 with 20s stagger: ~54s
- Batches 2-3: ~28s
- **Total: ~157s** (53s SLOWER)

The overhead required for batch-1 reliability exceeds the parallelism gains. This is why every "passing" PARALLEL=3 config was slower or equal to PARALLEL=1.

### JupyterLab REST API kernel state is misleading

The JupyterLab REST API (`GET /api/kernels/{id}`) reports kernel `execution_state` but only transitions from `starting` to `idle` after a WebSocket client connects to the IOPub channel. A REST-only warmup poll will never see `idle`. Warmup kernels created via REST stay in `starting` forever, accumulate as zombie processes, and make batch-1 worse.

---

## Architecture Built (ready for reuse)

The following infrastructure is complete and working:

### `scripts/test_playwright_jupyter_parallel.sh`
- N isolated JupyterLab servers, one per parallel slot
- Sequential server startup with HTTP polling
- `run_one()` function: runs a single notebook against a specific port
- Batch execution: fills N slots, waits for all, cleans up kernels, next batch
- Per-server kernel cleanup between batches via REST API
- Stale process cleanup (lsof + kill on all ports at start)
- Runtime file cleanup (`~/.local/share/jupyter/runtime/kernel-*.json`)
- Workspace state cleanup (`~/.jupyter/lab/workspaces`)

### Spec changes (already merged)
- `integration.spec.ts`: `JUPYTER_BASE_URL` from env var (was hardcoded `localhost:8889`)
- `infinite-scroll-transcript.spec.ts`: same
- `waitForAgGrid()`: deterministic waits instead of `waitForTimeout()`
- `CELL_EXEC_TIMEOUT`: configurable, currently 60s

### CI infrastructure
- `--phase=5b` flag on `run-ci.sh`: skip phases 1-4, load cached wheel, run only playwright-jupyter
- Wheel cache at `/opt/ci/wheel-cache/$SHA/`: persists across `--phase=5b` re-runs

---

## How To Resume This Work

When the notebook count grows (e.g., 15+ notebooks making PARALLEL=1 take 3+ minutes), here's the path forward:

### Step 1: Fix the root cause (kernel import contention)

The core problem is 3 concurrent `import polars` + `import buckaroo` processes saturating CPU. Two approaches:

**A. Pre-start kernels via WebSocket (not REST)**

The REST API warmup failed because `execution_state` never reaches `idle` without a WebSocket connection. The fix: use a small Python/Node script that:
1. POST `/api/kernels` to create a kernel
2. Connect to its WebSocket channel (`/api/kernels/{id}/channels`)
3. Wait for `execution_state: idle` on the IOPub stream
4. Execute `import polars; import buckaroo` via the shell channel
5. Wait for idle again
6. DELETE the kernel

This ensures the kernel provisioner AND Python bytecaches are fully warm. The key insight missed in Exp 7-9 was that REST polling cannot observe kernel readiness — you must connect via WebSocket.

**B. Increase parallelism to match CPU cores**

The CCX33 has 8 dedicated vCPUs. PARALLEL=3 means 3 JupyterLab servers + 3 Chromium instances + 3 Python kernels = 9 heavy processes. At PARALLEL=4, the contention gets worse. But at PARALLEL=9 (one server per notebook), there are no batches at all — every notebook runs simultaneously, and the total time is `max(individual notebook time)` plus startup overhead. This trades memory for time:
- 9 JupyterLab servers: ~200MB each = 1.8GB
- 9 Chromium instances: ~100MB each = 0.9GB
- Total: ~2.7GB additional (CCX33 has 32GB)

This eliminates batch-2/3 entirely. The only question is whether 9 simultaneous kernel startups (even on isolated servers) can complete within a reasonable timeout.

### Step 2: Validate with 3 consecutive passes

Any PARALLEL>1 config must pass 3/3 consecutive full runs before shipping. The flakiness is non-deterministic and depends on CPU scheduling.

### Step 3: Tighten timeouts

Once stable, reduce `CELL_EXEC_TIMEOUT` from 60s back toward 20s. The 60s value was set to tolerate slow batch-1 starts; if the root cause is fixed, 20s should be plenty.

---

## Experiment Log Reference

Full experiment details (20 experiments with commit SHAs, exact error messages, and timing breakdowns) are in `docs/llm/research/parallel-jupyter-experiments.md`.

### Summary table

| Exp | PARALLEL | Architecture | Result |
|-----|----------|-------------|--------|
| 1-5 | 1-3 | Shared server | ZMQ contention at PARALLEL>1; PARALLEL=1 stable |
| 6 | 3 | Isolated servers, parallel startup | CPU competition during startup |
| 7-9 | 3 | Isolated servers, sequential startup, REST warmup | Ghost kernel processes from REST warmup |
| 10-20 | 3 | Isolated servers, sequential startup, sleep+stagger | Batch-1 flakes; stagger overhead exceeds savings |

### Key commits
- `65d49b2`: `waitForTimeout` → `waitFor` in specs
- `f46971d`: Isolated servers (one per slot)
- `d6bc031`: Sequential server startup
- `92a99aa`: Removed REST warmup, added sleep
- `a719762`: Final state (CELL_EXEC_TIMEOUT=60s, state:visible, 90s runner timeout)
