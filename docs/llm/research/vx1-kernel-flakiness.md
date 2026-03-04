# VX1 Kernel Flakiness Investigation

**Date:** 2026-03-04
**Server:** Vultr VX1 32C (66.42.115.86) — AMD EPYC Turin Zen 5, 32 vCPU, 128 GB
**Branch:** docs/ci-research

---

## Problem Statement

pw-jupyter fails on VX1 instances (both 16 vCPU and 32 vCPU) but works reliably on Rome 32 vCPU. The failure mode is identical at all parallelism levels (P=1 through P=9): the Playwright test's `waitForFunction` checking `kernel.connectionStatus === 'connected' && kernel.status === 'idle'` times out at 30-60s. The kernel never appears idle to the browser.

This is NOT a resource/parallelism issue — it reproduces with a single notebook on a 32 vCPU box with 120+ GB free RAM and <5% CPU utilization.

---

## What We've Proven

### 1. The kernel process starts and works correctly

`jupyter_client.KernelManager` (direct ZMQ, no JupyterLab) starts a kernel that reaches ready/idle in **0.5s**:

```
Starting kernel manager...
Kernel process started in 0.136s
Channels started, waiting for ready...
KERNEL READY in 0.516s (total: 0.652s)
```

Cell execution works perfectly via this path. ZMQ is fine.

### 2. The REST API shows "starting" forever (known, expected)

`GET /api/kernels/{id}` via JupyterLab shows `execution_state: "starting"` indefinitely.
This is the known behavior documented in `jupyter-kernel-rest-api-execution-state.md`:
the REST API only updates when ZMQ messages flow, and no messages flow without a
WebSocket connection. The server needs a "nudge" (triggered by WebSocket connect).

### 3. WebSocket connection to an existing kernel immediately sees idle

After starting a kernel via REST API and letting it sit for 30s in "starting" state,
connecting via WebSocket (Python `websockets` library) immediately receives:

```
WS [status]: {'execution_state': 'busy'}
WS [status]: {'execution_state': 'idle'}
-> Kernel is IDLE via WebSocket!
```

This confirms: the kernel IS idle, and the WebSocket nudge mechanism works correctly.
The server's nudge sends `kernel_info_request`, the kernel responds, and status messages
flow to the WebSocket client.

### 4. Direct kernel launch (bypassing JupyterLab) works

`python -m ipykernel_launcher -f connection.json` starts successfully, prints the
ready message, no stderr errors. 12 threads, sleeping state, 71 MB RSS.

### 5. Python imports are fast

```
ipykernel import: 0.077s
zmq import: 0.000s
buckaroo import: 1.337s
```

### 6. System resources are abundant

- /dev/shm: 2.0 GB (0% used)
- RAM: 125 GB (2.5 GB used)
- CPU: 32 vCPU, load average <1
- No swap usage

---

## What We Haven't Proven Yet

### The critical gap: does the BROWSER see kernel idle?

We proved that a Python WebSocket client sees idle immediately. We did NOT
prove that Chromium (via Playwright) opening a notebook sees kernel idle.

The previous session's debug script reported: `Kernel wait TIMEOUT: 31233ms`
from the browser's `page.waitForFunction()` checking
`kernel.connectionStatus === 'connected' && kernel.status === 'idle'`.

**This is the core contradiction:**
- Python WebSocket client → immediate idle ✓
- Browser (Playwright) `waitForFunction` → 30s+ timeout ✗

### Possible explanations for the contradiction

1. **JupyterLab frontend loading is slow on VX1.** The browser must load JupyterLab's JS
   bundle, initialize extensions, open the notebook, create a session, and establish the
   WebSocket connection. If any step is slow, `window.jupyterapp` or the session/kernel
   chain may not exist when `waitForFunction` starts polling.

2. **The kernel starts idle but transitions to busy during widget rendering.** For the
   failing notebooks (DFViewerInfinite, infinite_scroll), the widget initialization
   involves heavier Python computation. The kernel may go idle → busy → stay busy for
   a long time. The `waitForFunction` check requires `status === 'idle'`, which won't
   be true while the cell is executing.

3. **Automatic cell execution.** JupyterLab may auto-execute the first cell on notebook
   open (if the notebook's metadata has `autorun` or if there's a workspace state).
   This would put the kernel into `busy` before the test code even runs.

4. **VX1-specific network/timing.** The EPYC Turin platform may have different interrupt
   coalescing, timer resolution, or scheduler behavior that affects WebSocket message
   delivery timing in ways that don't affect raw ZMQ.

### The notebook-specific failure pattern is telling

From the previous session:
- **Pass:** test_buckaroo_widget, test_polars_widget, test_dfviewer, test_polars_dfviewer,
  test_infinite_scroll_transcript (5/9)
- **Fail:** test_buckaroo_infinite_widget, test_polars_infinite_widget,
  test_dfviewer_infinite, test_polars_dfviewer_infinite (4/9)

All failing notebooks contain "infinite" — they use DFViewerInfinite which renders more
data and has virtual scrolling. This suggests the issue may be widget rendering time, not
kernel startup time.

---

## Relationship to Previous Research

### From `jupyterlab-kernel-connection-deep-dive.md`

The deep dive identified three failure layers:
1. **Server-side nudge** — kernel stays "starting" without WebSocket (proven above)
2. **Client-side silent drop** — `CodeCell.execute()` silently returns void when
   `session.kernel === null` at `widget.ts:1750`
3. **WebSocket reconnection limits** — 7 attempts (~120s), then permanently disconnected

The current fix (`waitForFunction` on kernel state, 60s timeout, retry loop for
Shift+Enter) was designed to handle all three layers. On Rome, it works perfectly.
On VX1, layer 1 is fine, but something in layers 2-3 is different.

### From `galata-pattern-adoption.md`

Galata uses `sessionContext.ready` (a Promise) instead of polling `kernel.status`.
`sessionContext.ready` resolves when the SESSION is established, NOT when the kernel
is ready. But it's a different (potentially faster) signal.

Galata also uses execution count verification (`resetExecutionCount` + `haveBeenExecuted`)
rather than waiting for output DOM elements. This is more reliable than our current
"wait for `.jp-OutputArea-output`" approach.

### From `kernel-contention-diagnostics.md`

The TCP port collision hypothesis (ports allocated then released before kernel binds)
was relevant for the parallel warmup case. Not relevant here since we're seeing failures
at P=1.

---

## Next Steps

### Step 1: Run browser-based kernel check (blocked, needs re-run)

The script `pw-kernel-check.cjs` was prepared but didn't execute due to JupyterLab not
running when the Node.js script launched. The script polls `window.jupyterapp` kernel
state from inside a real Chromium browser. This will definitively show:
- How long until `jupyterapp` is available
- How long until `session.kernel` is non-null
- How long until `connectionStatus === 'connected'`
- How long until `status === 'idle'`
- Whether status ever reaches idle, or if it's stuck at something else

### Step 2: Test with `sessionContext.ready` (Galata pattern)

Replace the kernel status polling with:
```typescript
await page.evaluate(async () => {
  const app = (window as any).jupyterapp;
  const nbPanel = app.shell.currentWidget;
  await nbPanel.sessionContext.ready;
});
```
This is what Galata uses and may behave differently from our current approach.

### Step 3: Increase test timeouts as a quick fix

The "infinite" widgets may simply need more time on VX1's Zen 5 platform for
reasons we don't fully understand (maybe JS JIT compilation is different, maybe
AG-Grid virtual scrolling is slower). Increasing timeouts from 30s to 90s might
just work.

### Step 4: Compare JupyterLab page load timing

Use Playwright's `page.on('requestfinished')` to log every HTTP request during
notebook loading. Compare Rome vs VX1 to see if any resources load significantly
slower.

### ~~Step 5: Check if it's a Python/ipykernel version issue~~ — DEBUNKED

An earlier research doc (`pw-jupyter-exploration-results.md:145-152`) claimed Rome had
ipykernel 7.2.0, jupyterlab 4.5.5, etc. **This was wrong.** The lockfile (`uv.lock`)
has always pinned the same versions. Verified at commits e6ea620 (Rome era) and 2e86252
(VX1):

| Package | Version (all builds, all servers) |
|---------|----------------------------------|
| ipykernel | 6.29.5 |
| jupyterlab | 4.5.0 |
| jupyter_server | 2.15.0 |
| jupyter_client | 8.6.3 |
| ipywidgets | 8.1.5 |
| pyzmq | 27.1.0 |

Both Rome and VX1 use `uv sync --locked` (Dockerfile line 42, run-ci.sh line 193)
and `pnpm install --frozen-lockfile` (Dockerfile line 33). The Dockerfile, uv.lock,
and pyproject.toml are identical between the Rome and VX1 builds.

**The same code, same lockfile, same Docker recipe works on Rome but fails on VX1.**

---

## Package Versions (confirmed identical across all builds)

| Package | Version |
|---------|---------|
| Python | 3.13.2 |
| ipykernel | 6.29.5 |
| jupyterlab | 4.5.0 |
| jupyter_server | 2.15.0 |
| jupyter_client | 8.6.3 |
| ipywidgets | 8.1.5 |
| pyzmq | 27.1.0 |

---

## Hypothesis Ranking (updated after debunking version mismatch)

| # | Hypothesis | Likelihood | Evidence |
|---|-----------|-----------|---------|
| 1 | **VX1 platform-specific** — Zen 5 timer resolution, interrupt coalescing, or scheduler behavior affects ZMQ/WebSocket timing | High | Same code works on Rome, fails on VX1. Only variable is hardware. |
| 2 | **Widget rendering time** — DFViewerInfinite is slow on VX1 | Medium | 5/9 pass (simple), 4/9 fail (infinite). But even single test at P=1 fails. |
| 3 | **Chromium behavior differs** — V8 JIT, WebSocket implementation, or rendering pipeline behaves differently on Zen 5 | Medium | Playwright uses Chromium headless; Chromium may have platform-specific codepaths |
| 4 | **JupyterLab frontend loading** — JS bundle loading or extension init is slower on VX1 | Low-Medium | Not yet measured; could explain why browser doesn't see kernel idle |

**Key fact: this is a hardware-level issue.** The software stack is identical. Something about
the VX1 (EPYC Turin / Zen 5) platform causes the JupyterLab-in-browser kernel readiness
detection to fail, while the same kernel works perfectly via direct ZMQ and raw WebSocket.

**Recommended next steps:**
1. Run the browser-based kernel check (`pw-kernel-check.cjs`) to see what the browser
   actually observes during notebook loading on VX1
2. If browser sees kernel idle but widget rendering is slow, increase timeouts
3. If browser never sees kernel idle, investigate Chromium WebSocket behavior on Zen 5
4. As a control: spin up a Rome box and verify the exact same Docker image passes
