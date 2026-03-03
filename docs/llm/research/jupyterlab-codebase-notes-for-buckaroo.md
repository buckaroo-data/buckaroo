# JupyterLab Codebase Notes for Buckaroo

**Date:** 2026-03-03
**Source:** Deep dive into `jupyterlab/jupyterlab` codebase + Galata test framework
**Purpose:** Patterns, APIs, and fixes buckaroo should adopt

---

## 1. The Kernel Readiness Fix (Critical — Do This First)

**Problem:** Current DOM-based kernel check (`integration.spec.ts:112-127`) uses
`.jp-Notebook-ExecutionIndicator[data-status="idle"]` which fails when:
- The ExecutionIndicator isn't in DOM yet (JupyterLab still loading) → `querySelector` returns `null` → function returns `false` → burns 15s timeout
- data-status attribute lags behind internal kernel state

**Fix:** Query JupyterLab's internal kernel state directly:

```typescript
await page.waitForFunction(() => {
  const app = (window as any).jupyterapp;
  if (!app) return false;
  const widget = app.shell.currentWidget;
  if (!widget?.sessionContext?.session?.kernel) return false;
  const kernel = widget.sessionContext.session.kernel;
  return kernel.connectionStatus === 'connected' && kernel.status === 'idle';
}, { timeout: 60000 });
```

**Why this works:** This checks the exact same condition JupyterLab checks before
allowing execution. `CodeCell.execute()` at `packages/cells/src/widget.ts:1750`
silently returns void if `!sessionContext.session?.kernel`. Our check ensures the
kernel object exists AND is connected AND is idle before we fire Shift+Enter.

**Expected impact:** 80% → ~98%+ pass rate.

---

## 2. Galata Patterns We Should Adopt

Galata is JupyterLab's official Playwright testing framework (`galata/`). It has
years of battle-tested patterns for the exact problems we're solving.

### 2a. Wait for App Started — Not Just DOM

Galata waits for `window.jupyterapp.started` before doing anything:

```typescript
// From galata/src/jupyterlabpage.ts:715-724
await page.evaluate(async () => {
  if (typeof window.jupyterapp === 'object') {
    await window.jupyterapp.started;  // Waits for ALL plugins to load
    return true;
  }
  return false;
});
```

**We should add this** before our notebook load check. It ensures all extensions
(including anywidget support) are initialized before we interact with the notebook.

### 2b. Double-Check Cell Execution (Status Bar + Execution Count)

Galata's `waitForRun()` uses a two-stage check:

```typescript
// From galata/src/helpers/notebook.ts:468-480
async waitForRun(cellIndex?: number): Promise<void> {
  // Stage 1: Wait for status bar to show "Idle"
  const idleLocator = this.page.locator('#jp-main-statusbar >> text=Idle');
  await idleLocator.waitFor();

  // Stage 2: Verify execution count is set
  let done = false;
  do {
    await this.page.waitForTimeout(20);
    done = await this.page.evaluate(cellIdx => {
      return window.galata.haveBeenExecuted(cellIdx);
    }, cellIndex);
  } while (!done);
}
```

**Key insight:** Status bar showing "Idle" alone isn't enough. Must also verify the
cell's execution count was set (proving the kernel actually processed the request).

### 2c. Animation Frame Stability for Rendering

Galata checks that rendered content is stable across multiple animation frames:

```typescript
// From galata/src/helpers/notebook.ts:1290-1331
// Wait until content is unchanged for 10 consecutive animation frames
let framesWithoutChange = 0;
let previousContent = element.innerHTML;

const check = () => {
  window.requestAnimationFrame(() => {
    const newContent = element.innerHTML;
    if (previousContent === newContent) {
      framesWithoutChange++;
    } else {
      framesWithoutChange = 0;  // Reset on change
    }
    previousContent = newContent;
    if (framesWithoutChange < 10) {
      check();
    } else {
      resolve();  // Stable!
    }
  });
};
```

**We should use this** for AG-Grid rendering. Currently we `waitFor({ state: 'visible' })`
on `.ag-cell` but AG-Grid renders progressively. 10 stable frames would catch the
point where rows are fully populated.

### 2d. `waitForCondition` Utility

Galata's core polling utility (50ms intervals, 15s default):

```typescript
// From galata/src/utils.ts:174-203
async function waitForCondition(
  fn: () => boolean | Promise<boolean>,
  timeout: number = 15000
): Promise<void> {
  return new Promise((resolve, reject) => {
    const check = async () => {
      if (await Promise.resolve(fn())) {
        resolve();
      } else {
        setTimeout(check, 50);
      }
    };
    check();
    setTimeout(() => reject(new Error('Timed out')), timeout);
  });
}
```

This is simpler and more reliable than our retry loops. Consider extracting a
similar utility for buckaroo tests.

---

## 3. How Anywidget Rendering Works in JupyterLab

Understanding this helps diagnose widget rendering failures.

### Output Rendering Pipeline

```
Kernel execute_reply (IOPub)
  ↓
OutputArea._onIOPub()     — packages/outputarea/src/widget.ts:732
  ↓
OutputAreaModel.add()     — adds to model, emits changed signal
  ↓
OutputArea.onModelChanged() — receives signal
  ↓
RenderMimeRegistry.preferredMimeType() — selects best MIME renderer
  ↓
RenderMimeRegistry.createRenderer() — instantiates renderer widget
  ↓
renderer.renderModel(model) — async, fire-and-forget (!)
  ↓
Widget attached to DOM
```

### Fire-and-Forget Render Issue

At `packages/outputarea/src/widget.ts:594-611`, when an output is updated:

```typescript
void renderer.renderModel(model);  // Fire and forget!
```

If multiple updates arrive rapidly, the renderer may render stale data.
Anywidget's React rendering should handle this via state diffing, but it means
our test shouldn't assume the first paint is the final paint.

### Comm Message Handling

Anywidget uses the Jupyter comm protocol, NOT the MIME renderer pipeline, for
ongoing widget-kernel communication. The comm messages flow through:

```
KernelConnection._handleMessage()     — default.ts:1595
  ↓
_handleCommMsg / _handleCommOpen      — handles comm_open, comm_msg, comm_close
  ↓
anywidget model.on('msg:custom')      — frontend receives custom messages
  ↓
SmartRowCache processes infinite_resp  — buckaroo-specific handling
```

This means our `infinite_request`/`infinite_resp` messages go through the same
WebSocket connection as execution. If the WebSocket drops, comm messages are
also lost (they're not queued like execute_request).

---

## 4. Key JupyterLab Constants That Affect CI

| Constant | Value | Impact | Location |
|----------|-------|--------|----------|
| `KERNEL_INFO_TIMEOUT` | 3000ms | Failsafe: sends pending messages even if kernel_info_reply not received. Under contention, kernel may not be ready. | `services/kernel/default.ts:33` |
| `_reconnectLimit` | 7 | After 7 failed WebSocket reconnection attempts (~120s total), kernel is permanently `disconnected` | `services/kernel/default.ts:1840` |
| `enableKernelInitNotification` | `false` | When true, shows notification instead of silently dropping execution during init. Consider enabling in test notebooks. | `notebook-extension/schema/tracker.json:689` |

### Reconnection Backoff Schedule

| Attempt | Max delay | Cumulative |
|---------|-----------|------------|
| 1 | 0s | 0s |
| 2 | 1s | 1s |
| 3 | 3s | 4s |
| 4 | 7s | 11s |
| 5 | 15s | 26s |
| 6 | 31s | 57s |
| 7 | 63s | 120s |
| 8+ | gives up | `disconnected` |

With P=4 on 16 vCPU, if a WebSocket drops during contention, it has ~120s
to reconnect before permanent failure.

---

## 5. Silent Execution Drop Scenarios (Full List)

Every way Shift+Enter can be silently swallowed in JupyterLab:

| # | Check | Condition | Result |
|---|-------|-----------|--------|
| 1 | Keybinding selector | Not in `.jp-mod-editMode` | Keystroke ignored |
| 2 | `actions.tsx:2546` | `kernelDisplayStatus === 'initializing'` AND `enableKernelInitNotification` | Shows notification, `return false` |
| 3 | `cellexecutor.ts:54` | `sessionContext.isTerminating` | Shows dialog, drops |
| 4 | `cellexecutor.ts:62` | `sessionContext.pendingInput` | Shows dialog, `return false` |
| 5 | `cellexecutor.ts:74` | `hasNoKernel` after start attempt | Clears execution, `return true` (!) |
| **6** | **`widget.ts:1750`** | **`!sessionContext.session?.kernel`** | **Returns `void`, NO error** |

**#6 is our primary failure mode.** The kernel object doesn't exist yet when
Shift+Enter fires. The code path returns cleanly with no error, no notification,
and no queuing.

---

## 6. Message Queueing — What's Safe and What's Not

### Safe: Messages queued while WebSocket is down

`packages/services/src/kernel/default.ts:489-507` — if `connectionStatus !== 'connected'`
or kernel is restarting, messages are pushed to `_pendingMessages[]` and sent when
connection recovers.

### Unsafe: `_clearKernelState()` drops the queue

`default.ts:1302-1304`:
```typescript
private _clearKernelState(): void {
  this._kernelSession = '';
  this._pendingMessages = [];  // ALL QUEUED MESSAGES LOST
  this._futures.forEach(future => { future.dispose(); });
}
```

Called during:
- Kernel restarts (autorestarting status received)
- `reconnect()` method
- `dispose()`

**For buckaroo:** If the kernel auto-restarts during a test (OOM, crash), any
pending `execute_request` or `comm_msg` (infinite_request) messages are silently
dropped. Our retry loop handles this for execution, but infinite scroll requests
via SmartRowCache would need their own retry logic.

---

## 7. Notebook Windowing (Virtual Scrolling)

JupyterLab virtualizes cells in large notebooks. Not all cells are in the DOM.

```typescript
// Galata uses data-windowed-list-index to find cells
const firstIndex = parseInt(
  (await cells.first().getAttribute('data-windowed-list-index')) ?? '', 10
);
```

**For buckaroo:** Our test notebooks are small (1-2 cells) so this doesn't matter
today. But if we ever test multi-cell notebooks, we can't assume all cells are in
DOM. Use `data-windowed-list-index` attribute instead of `.jp-Cell:nth-child(n)`.

---

## 8. `window.jupyterapp` API Surface for Tests

Available globals in the browser context during JupyterLab tests:

```typescript
// Application object
window.jupyterapp: JupyterFrontEnd

// Key properties
window.jupyterapp.started              // Promise: resolves when plugins loaded
window.jupyterapp.shell.currentWidget  // Current active widget (NotebookPanel)
window.jupyterapp.serviceManager       // Sessions, kernels, contents APIs

// Kernel state (via currentWidget)
const panel = window.jupyterapp.shell.currentWidget;
panel.sessionContext                   // ISessionContext
panel.sessionContext.session           // Session.ISessionConnection
panel.sessionContext.session.kernel    // Kernel.IKernelConnection
panel.sessionContext.session.kernel.status          // 'idle'|'busy'|'starting'|...
panel.sessionContext.session.kernel.connectionStatus // 'connected'|'connecting'|'disconnected'
panel.sessionContext.session.kernel.info            // Promise<IInfoReply>
panel.sessionContext.kernelDisplayStatus            // Combined display status
panel.sessionContext.isReady                        // Boolean
panel.sessionContext.hasNoKernel                    // Boolean
```

**`kernel.info`** is a Promise that resolves when the kernel_info_reply arrives
(the nudge completed). This is the definitive "kernel is fully ready" signal:

```typescript
// Most reliable way to wait for kernel readiness
await page.evaluate(async () => {
  const panel = window.jupyterapp.shell.currentWidget;
  await panel.sessionContext.session.kernel.info;
});
```

---

## 9. Recommended Test Helper Improvements

### Replace current kernel wait (integration.spec.ts:112-127)

```typescript
// NEW: Wait for app + kernel ready
async function waitForKernelReady(page: Page, timeout = 60000) {
  // Stage 1: Wait for JupyterLab app to finish loading
  await page.waitForFunction(() => {
    return typeof (window as any).jupyterapp === 'object';
  }, { timeout: 30000 });

  // Stage 2: Wait for kernel to be connected and idle
  await page.waitForFunction(() => {
    const app = (window as any).jupyterapp;
    const widget = app.shell.currentWidget;
    if (!widget?.sessionContext?.session?.kernel) return false;
    const kernel = widget.sessionContext.session.kernel;
    return kernel.connectionStatus === 'connected' && kernel.status === 'idle';
  }, { timeout });
}
```

### Add AG-Grid rendering stability check

```typescript
async function waitForGridStable(page: Page, timeout = 15000) {
  await page.locator('.ag-overlay').first().waitFor({ state: 'hidden', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });

  // Wait for AG-Grid to stop re-rendering (10 stable animation frames)
  await page.evaluate(() => new Promise<void>(resolve => {
    const grid = document.querySelector('.ag-root-wrapper')!;
    let stableFrames = 0;
    let prev = grid.innerHTML;
    const check = () => {
      requestAnimationFrame(() => {
        const cur = grid.innerHTML;
        stableFrames = (cur === prev) ? stableFrames + 1 : 0;
        prev = cur;
        (stableFrames >= 10) ? resolve() : check();
      });
    };
    check();
  }));
}
```

### Add execution verification after Shift+Enter

```typescript
async function verifyExecution(page: Page, timeout = 15000) {
  // Check that execution count was set (kernel actually ran the cell)
  await page.waitForFunction(() => {
    const cell = document.querySelector('.jp-CodeCell');
    if (!cell) return false;
    const prompt = cell.querySelector('.jp-InputArea-prompt');
    // Execution count shows "[N]:" not "[*]:" or "[ ]:"
    return prompt?.textContent?.match(/\[\d+\]:/) !== null;
  }, { timeout });
}
```

---

## 10. The `display_id` Pattern — Relevant for Widget Updates

JupyterLab supports `update_display_data` messages that update existing outputs
by `display_id`. From `packages/outputarea/src/widget.ts:774-778`:

```typescript
if (displayId && msgType === 'display_data') {
  targets = this._displayIdMap.get(displayId) || [];
  targets.push(model.length - 1);
  this._displayIdMap.set(displayId, targets);
}
```

Anywidget likely uses this for widget model updates. If multiple updates arrive
for the same display_id, the output is updated in-place rather than appended.
This is relevant if we ever see duplicate widget renders — it could mean
display_id handling failed.

---

## Summary: Priority Actions for Buckaroo CI

1. **Replace DOM kernel check with `window.jupyterapp` state query** (Section 1)
   — Expected: 80% → ~98% pass rate

2. **Add `window.jupyterapp.started` wait before notebook interaction** (Section 2a)
   — Ensures all plugins loaded before we touch the notebook

3. **Add execution count verification after Shift+Enter** (Section 9)
   — Galata pattern: don't trust status bar alone

4. **Consider AG-Grid animation frame stability check** (Section 9)
   — Catches progressive AG-Grid rendering

5. **Consider enabling `enableKernelInitNotification`** (Section 4)
   — Makes silent drops visible as notifications (detectable in tests)
