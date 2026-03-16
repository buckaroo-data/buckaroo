# JupyterLab Kernel Connection Deep Dive — CI Cell Execution Flakes

**Date:** 2026-03-03
**Context:** Parallel CI running 4 JupyterLab + 4 Chromium + 4 kernels on 16 vCPU.
Exp 14b (wait-all DAG + P=4 + retries=1) achieves 80% pass rate. This research
explains the remaining 20% failures and provides the fix.

---

## Executive Summary

Cell execution flakes in parallel CI stem from **three architectural layers**:

1. **Server-side:** Kernels never transition from "starting" → "idle" without a WebSocket client (the "nudge" mechanism). Already fixed by WebSocket warmup.
2. **Client-side:** JupyterLab silently drops `Shift+Enter` when `session.kernel` is `null` — returns `void`, no error, no notification. This is the primary remaining failure mode.
3. **Connection layer:** Under CPU contention, WebSocket reconnection exhausts 7 attempts (exponential backoff up to ~120s total) and permanently disconnects.

**The fix:** Replace DOM-based kernel readiness check with `page.waitForFunction` querying JupyterLab's internal kernel state (`session.kernel.connectionStatus === 'connected' && status === 'idle'`).

---

## Layer 1: The "Nudge" Mechanism (Server-Side)

Already documented in `jupyter-kernel-rest-api-execution-state.md`. Summary:

- REST API `GET /api/kernels/{id}` never updates `execution_state` because no ZMQ messages flow
- WebSocket connection triggers server-side `nudge()` which sends `kernel_info_request` repeatedly
- Nudge forces kernel to emit IOPub status messages → server updates `execution_state`
- **Status:** Fixed by WebSocket warmup in Exp 10

### Upstream Issues

| Issue | Description |
|-------|-------------|
| `jupyter-server/jupyter_server#989` | "Inaccurate kernel state" — no reliable way to determine kernel state via REST |
| `jupyter-server/jupyter_server#305` | "idle" means "done with computation" NOT "ready for computation" |
| `jupyter-server/jupyter_server#900` | Proposal for new kernels REST API with event-based state tracking |
| `jupyter/jupyter_client#763` | Proposal to add state machine to KernelManager |
| `jupyter/jupyter_client#926` | jupyter_client 8.x regression: first connection takes ~60s |
| `jupyter-server/jupyter_server#1506` | Nudge retry loop leaks FDs → kills all kernels under pathological load |
| `jupyter-server/jupyter_server#1560` | `_kernel_info_future` stuck forever when restart hits latency |
| `jupyter/jupyter_client#838` | Dual shell+control `kernel_info_request` during nudge reports incorrect idle for busy kernels |

### Upstream Fixes

- **`pending_kernels`** (merged jupyter_client 7.1+ / jupyter_server 1.11+): Adds `KernelManager.ready` promise; surfaces startup errors as `execution_state: "dead"` with `reason` field
- **@Zsailer's `nextgen-kernels-api`**: Proposed complete rewrite eliminating nudge entirely
- **`jupyter-server/jupyter_server#361`**: PR that added the nudge mechanism — WebSocket-only fix

---

## Layer 2: Silent Cell Execution Drops (Client-Side) — THE MAIN ISSUE

### The Full Code Path: Shift+Enter → Kernel

```
Keybinding: "Shift Enter" → "notebook:run-cell-and-select-next"
  (schema: packages/notebook-extension/schema/tracker.json:612-615)
  (selector: .jp-Notebook.jp-mod-editMode — only fires in edit mode)
     ↓
Command handler (packages/notebook-extension/src/index.ts:2525-2576)
     ↓
NotebookActions.runAndAdvance (packages/notebook/src/actions.tsx:677-730)
     ↓
Private.runSelected → Private.runCells (packages/notebook/src/actions.tsx:2533-2618)
     ↓ ← FIRST CHECK: kernelDisplayStatus === 'initializing'
runCell (packages/notebook/src/cellexecutor.ts:24-142)
     ↓ ← SECOND CHECK: isTerminating, pendingInput, hasNoKernel
CodeCell.execute (packages/cells/src/widget.ts:1743-1857)
     ↓ ← THIRD CHECK: !sessionContext.session?.kernel → SILENT VOID RETURN
OutputArea.execute → kernel.requestExecute (packages/outputarea/src/widget.ts:939-966)
     ↓
KernelConnection._sendMessage (packages/services/src/kernel/default.ts:464-508)
     ↓ ← Messages queued in _pendingMessages[] if not connected
```

### All Silent Drop Scenarios

| # | Check Location | Condition | Behavior |
|---|---------------|-----------|----------|
| 1 | `actions.tsx:2546-2563` | `kernelDisplayStatus === 'initializing'` AND `enableKernelInitNotification === true` | Shows notification, returns `false`. **Default: OFF** (`tracker.json:689`) |
| 2 | `cellexecutor.ts:54-60` | `sessionContext.isTerminating` | Shows dialog, silently drops |
| 3 | `cellexecutor.ts:62-68` | `sessionContext.pendingInput` | Shows dialog, returns `false` |
| 4 | `cellexecutor.ts:74-79` | `sessionContext.hasNoKernel` (after start attempt fails) | Clears execution, returns `true` (!), no error |
| 5 | **`widget.ts:1750`** | **`!sessionContext.session?.kernel`** | **Clears execution, returns `void`. NO ERROR.** |
| 6 | Keybinding selector | Notebook not in `.jp-mod-editMode` | Keystroke not captured |

**Scenario #5 is the primary CI failure mode.** When Playwright fires `Shift+Enter` before the session has established a kernel connection, `session?.kernel` evaluates to `null/undefined`, and `CodeCell.execute()` silently returns with no error, no notification, nothing.

### The `kernelDisplayStatus` State Machine

From `packages/apputils/src/sessioncontext.tsx:606-639`:

```typescript
get kernelDisplayStatus(): ISessionContext.KernelDisplayStatus {
  if (this._isTerminating) return 'terminating';
  if (this._isRestarting) return 'restarting';
  if (this._pendingKernelName === this.noKernelName) return 'unknown';
  if (!kernel && this._pendingKernelName) return 'initializing';  // kernel starting
  if (!kernel && !this.isReady && canStart && shouldStart) return 'initializing';
  return (kernel?.connectionStatus === 'connected'
    ? kernel?.status           // 'idle', 'busy', 'starting', etc.
    : kernel?.connectionStatus // 'connecting', 'disconnected'
  ) ?? 'unknown';
}
```

**Important:** `SessionContext.ready` resolves when the SESSION is established, NOT when the kernel is ready. The kernel can still be in `starting` or `connecting` state when `ready` resolves.

---

## Layer 3: WebSocket Connection Under CPU Contention

### Message Queueing and Loss

From `packages/services/src/kernel/default.ts:489-507`:

```typescript
// Send if the ws allows it, otherwise queue the message.
if (this.connectionStatus === 'connected' &&
    this._kernelSession !== RESTARTING_KERNEL_SESSION) {
  this._ws!.send(serialize(msg));
} else if (queue) {
  this._pendingMessages.push(msg);  // ← QUEUED
} else {
  throw new Error('Could not send message');
}
```

Messages ARE queued when not connected. **However, `_clearKernelState()` (line 1302-1304) empties the queue:**

```typescript
private _clearKernelState(): void {
  this._kernelSession = '';
  this._pendingMessages = [];  // ← ALL QUEUED MESSAGES SILENTLY LOST
  this._futures.forEach(future => { future.dispose(); });
  // ...
}
```

`_clearKernelState()` is called during kernel restarts and when `autorestarting` status is received. Under contention, if the connection drops and `_clearKernelState` fires, any queued `execute_request` messages are silently discarded.

### The 3-Second Failsafe

```typescript
const KERNEL_INFO_TIMEOUT = 3000;  // line 33
```

When WebSocket connects, JupyterLab sends `kernel_info_request` and waits up to 3s for a reply. If no reply arrives (kernel slow under contention), it fires a failsafe that sends all pending messages anyway — potentially before the kernel is ready. The code has a FIXME acknowledging this:

```typescript
// FIXME: if sent while zmq subscriptions are not established,
// kernelInfo may not resolve, so use a timeout to ensure we don't hang forever.
// It may be preferable to retry kernelInfo rather than give up after one timeout.
```

### Reconnection Limits

From `default.ts:1696-1732`:

| Attempt | Max delay | Cumulative max |
|---------|-----------|----------------|
| 1 | 0s (immediate) | 0s |
| 2 | 1s | 1s |
| 3 | 3s | 4s |
| 4 | 7s | 11s |
| 5 | 15s | 26s |
| 6 | 31s | 57s |
| 7 | 63s | 120s |
| 8+ | **gives up** | **`connectionStatus = 'disconnected'`** |

After 7 failed attempts (~120s), the kernel is permanently disconnected. Under heavy contention with 12+ heavyweight processes, this can happen.

### Kernel Info Request Special Handling

During startup/restart, `kernel_info_request` bypasses the message queue and is sent immediately — it's the only message type with this privilege:

```typescript
if ((this._kernelSession === STARTING_KERNEL_SESSION ||
     this._kernelSession === RESTARTING_KERNEL_SESSION) &&
    KernelMessage.isInfoRequestMsg(msg)) {
  if (this.connectionStatus === 'connected') {
    this._ws!.send(serialize(msg));  // ← BYPASS QUEUE
    return;
  } else {
    throw new Error('Could not send message: status is not connected');
  }
}
```

This is the client-side "nudge" — ensures the first message to the kernel is always `kernel_info_request` to establish the session and get status back.

---

## The Timing Race in CI

```
T=0s     Playwright opens notebook URL
T=0.5s   JupyterLab JS starts loading
T=2-3s   Notebook DOM rendered (.jp-Notebook attached)
T=2-3s   SessionContext.initialize() starts
T=3-5s   REST API creates kernel (POST /api/kernels)
T=3-5s   WebSocket connection begins
         ⟵ Under contention: 10-30s+ ⟶
T=5-35s  kernel_info_request sent (client-side nudge)
         ⟵ Under contention: kernel may not respond for 10-60s ⟶
T=15-95s kernel_info_reply → kernel.status = "idle"
```

**Current test code (integration.spec.ts:112-127):**
```typescript
await page.waitForFunction(() => {
  const indicator = document.querySelector('.jp-Notebook-ExecutionIndicator');
  if (indicator) {
    const status = indicator.getAttribute('data-status');
    return status === 'idle';
  }
  const kernelStatus = document.querySelector('.jp-Notebook-KernelStatus');
  return kernelStatus?.textContent?.includes('Idle') || false;
}, { timeout: 15000 });
```

**Problems with DOM-based check:**
1. `ExecutionIndicator` may not be in DOM yet → `querySelector` returns `null` → function returns `false` → burns 15s timeout doing nothing useful
2. Even when found, `data-status` attribute lags behind internal kernel state
3. 15s timeout is too short under contention (kernel startup can take 30-60s)
4. When timeout fires, code proceeds to `Shift+Enter` with `session.kernel === null` → silent void return

---

## The Fix

Replace DOM-based kernel readiness check with direct JupyterLab internal state query:

```typescript
// Replace lines 112-127 of integration.spec.ts with:
console.log('⏳ Waiting for kernel to be ready...');
try {
  await page.waitForFunction(() => {
    const app = (window as any).jupyterapp;
    if (!app) return false;
    const widget = app.shell.currentWidget;
    if (!widget?.sessionContext?.session?.kernel) return false;
    const kernel = widget.sessionContext.session.kernel;
    return kernel.connectionStatus === 'connected' && kernel.status === 'idle';
  }, { timeout: 60000 });
  console.log('✅ Kernel is idle');
} catch {
  console.log('⚠️ Kernel idle wait timed out — proceeding with retry loop');
}
```

**Why this works:**
- `window.jupyterapp` is the global JupyterLab Application instance
- `session.kernel` being non-null means WebSocket connection exists (the exact check that `CodeCell.execute()` uses at `widget.ts:1750`)
- `connectionStatus === 'connected'` means WebSocket is open
- `status === 'idle'` means nudge completed and kernel responded
- Returns `false` cheaply when app hasn't loaded → no wasted timeout
- Returns `true` the instant kernel is actually ready
- 60s timeout is safe — doesn't waste budget on missing DOM elements

**Expected impact:** 80% → ~98%+ pass rate (eliminates the `session.kernel === null` silent drop).

---

## Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| `KERNEL_INFO_TIMEOUT` | 3000ms | `services/kernel/default.ts:33` |
| `STARTING_KERNEL_SESSION` | `''` (empty string) | `services/kernel/default.ts` |
| `RESTARTING_KERNEL_SESSION` | `'_RESTARTING_'` | `services/kernel/default.ts` |
| `_reconnectLimit` | 7 | `services/kernel/default.ts:1840` |
| `enableKernelInitNotification` | `false` (default) | `notebook-extension/schema/tracker.json:689` |

## Key Files in JupyterLab Codebase

| Component | File |
|-----------|------|
| Kernel connection + WebSocket + queueing | `packages/services/src/kernel/default.ts` |
| Kernel interfaces + ConnectionStatus type | `packages/services/src/kernel/kernel.ts` |
| Kernel REST API client | `packages/services/src/kernel/restapi.ts` |
| Kernel manager + polling | `packages/services/src/kernel/manager.ts` |
| SessionContext (kernel readiness tracking) | `packages/apputils/src/sessioncontext.tsx` |
| Cell execution flow | `packages/notebook/src/cellexecutor.ts` |
| NotebookActions (runCells, runAndAdvance) | `packages/notebook/src/actions.tsx` |
| CodeCell.execute (silent null kernel drop) | `packages/cells/src/widget.ts` |
| OutputArea.execute (kernel.requestExecute) | `packages/outputarea/src/widget.ts` |
| ExecutionIndicator (DOM status display) | `packages/notebook/src/executionindicator.tsx` |
| Shift+Enter keybinding | `packages/notebook-extension/schema/tracker.json` |
| Command registration | `packages/notebook-extension/src/index.ts` |

---

## Architecture Notes

### Two Independent State Dimensions

JupyterLab tracks kernel state on two axes:

1. **Connection status** (WebSocket layer): `'connecting' | 'connected' | 'disconnected'`
2. **Kernel status** (execution state from IOPub): `'unknown' | 'starting' | 'idle' | 'busy' | 'restarting' | 'autorestarting' | 'terminating' | 'dead'`

The combined display status (`kernelDisplayStatus`) merges these:
- If `connectionStatus !== 'connected'` → show connection status
- If `connectionStatus === 'connected'` → show kernel status

### Design Intent

The Jupyter kernel protocol assumes:
- Kernels start quickly (< 5s)
- WebSocket connections are always present (browser tab open)
- The nudge mechanism bridges the gap at connection time

None of these assumptions hold in parallel CI with CPU contention. The `pending_kernels` feature and proposed `nextgen-kernels-api` are upstream efforts to address this, but neither is complete enough to rely on today.
