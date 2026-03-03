# Galata Pattern Adoption in Buckaroo Playwright Tests

**Date:** 2026-03-03
**Context:** Audit of which JupyterLab Galata testing patterns Buckaroo has adopted, which it hasn't, and whether the gaps matter given current CI reliability (Exp 30: 7/7 pw-jupyter, 1m43s total).

---

## What Is Galata?

Galata is JupyterLab's official end-to-end testing framework, built on Playwright. It lives at `jupyterlab/jupyterlab/galata/` in the monorepo. Named after the Galata Tower in Istanbul, it was originally developed at Bloomberg by Mehmet Bektas before being transferred to the JupyterLab organization.

Galata provides:
- **Playwright fixtures** for JupyterLab state isolation (`kernels`, `sessions`, `tmpPath`)
- **High-level API** — `page.notebook.createNew()`, `page.notebook.runCell()`, `page.notebook.waitForRun()`
- **`window.galata` browser global** for event listening (dialogs, notifications)
- **Visual regression testing** with built-in screenshot comparison
- **Server lifecycle management** — starts/stops JupyterLab for tests

Buckaroo doesn't import Galata directly — it tests a *widget inside* JupyterLab, not JupyterLab itself. But the testing problems are identical (kernel readiness, render completion, cell execution verification), and Galata's battle-tested solutions apply.

Key source files in JupyterLab:
- `galata/src/jupyterlabpage.ts` — app startup, `window.jupyterapp.started`
- `galata/src/helpers/notebook.ts` — `waitForRun()`, execution count verification
- `galata/src/utils.ts` — `waitForCondition()` polling utility

---

## Pattern Scorecard

| # | Pattern | Galata | Buckaroo | Where | Impact |
|---|---------|--------|----------|-------|--------|
| 1 | Internal kernel state check | Yes | **Yes** | `integration.spec.ts:116-123` | Critical — 80% → 100% pass rate |
| 2 | `expect().toPass()` polling | Yes | **Yes** | `server.spec.ts:163`, `server-buckaroo-summary.spec.ts:80,104` | 13s saved, eliminated view-switch flakes |
| 3 | Auto-retrying `toHaveText()` | Yes | **Yes** | `marimo.spec.ts:76-80, 120-122` | Eliminated AG-Grid data loading race |
| 4 | Grid readiness helpers | Yes | **Yes** | `server-helpers.ts:27-30`, `marimo.spec.ts:8-13` | Consistent wait pattern across suites |
| 5 | Kernel shutdown between tests | Yes | **Yes** | `test_playwright_jupyter.sh:298-316` | Prevents kernel state leakage |
| 6 | `jupyterapp.started` wait | Yes | **No** | — | Low risk (see analysis) |
| 7 | Execution count verification | Yes | **No** | — | Covered by retry loop |
| 8 | Animation frame stability | Yes | **No** | — | No reported AG-Grid flakes |
| 9 | `waitForCondition` utility | Yes | **No** | — | Ad-hoc alternatives work |

**Score: 5/9 adopted.** The 5 adopted patterns are the high-impact ones. The 4 missing are refinements with diminishing returns at current reliability levels.

---

## Adopted Patterns — Detail

### 1. Internal Kernel State Check (Critical)

**Galata's approach** (`galata/src/jupyterlabpage.ts:715-724`):
```typescript
await page.evaluate(async () => {
  if (typeof window.jupyterapp === 'object') {
    await window.jupyterapp.started;
    return true;
  }
  return false;
});
```

**Buckaroo's implementation** (`integration.spec.ts:116-123`, `infinite-scroll-transcript.spec.ts:43-49`):
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

This was the single most impactful change in the entire CI optimization effort (Exp 21). It checks the exact same `session.kernel` that `CodeCell.execute()` checks at `widget.ts:1750`. Before this, DOM-based checks (`ExecutionIndicator[data-status="idle"]`) burned timeout budgets when the element didn't exist yet, then proceeded with `session.kernel === null` — causing silent execution drops.

**Impact:** Pass rate jumped from 80% to 100% (10/10 runs at commit 5994612). Still 100% at Exp 30 (7/7) even without the heavyweight Playwright gate.

Used in: `integration.spec.ts`, `infinite-scroll-transcript.spec.ts` (both tests in the Jupyter suite).

### 2. `expect().toPass()` Polling

**Galata's equivalent:** `waitForCondition()` in `galata/src/utils.ts:174-203` — polls a function every 50ms until true or timeout.

**Buckaroo's implementation** (`server.spec.ts:160-163`):
```typescript
await expect(async () => {
  const val = await getCellText(page, COL.name, 0);
  expect(val).not.toBe('Alice');
}).toPass({ timeout: 5000 });
```

Also used in `server-buckaroo-summary.spec.ts:77-80` for waiting on pinned row count changes after view switching:
```typescript
await expect(async () => {
  const count = await getPinnedRowCount(page);
  expect(count).toBeGreaterThan(mainPinnedCount);
}).toPass({ timeout: 10000 });
```

**Impact:** Replaced `waitForTimeout(3000)` calls in server specs, saving 13s total (Exp 15). The `toPass()` pattern returns as soon as the condition is met rather than always waiting the full duration.

Used in: `server.spec.ts` (1 instance), `server-buckaroo-summary.spec.ts` (2 instances), `server-buckaroo-search.spec.ts` (1 instance). Total: 4 call sites.

### 3. Auto-Retrying `toHaveText()`

**Galata's equivalent:** Galata's `waitForRun()` verifies execution count is set — a form of "retry until the expected value appears."

**Buckaroo's implementation** (`marimo.spec.ts:76-80`):
```typescript
// Return locators so callers can use Playwright's auto-retrying toHaveText()
await expect(cellLocator(firstWidget, 'a', 0)).toHaveText('Alice');
await expect(cellLocator(firstWidget, 'a', 1)).toHaveText('Bob');
```

This replaced one-shot `innerText()` calls that had a race condition: AG-Grid renders the cell DOM element before the kernel sends actual data. `innerText()` catches the cell in a loading state and fails immediately. `toHaveText()` retries automatically until the expected value appears or timeout expires.

**Impact:** Implemented in Exp 29. Eliminates the AG-Grid data loading race in marimo tests (Category B flakes from `marimo-playwright-flakiness.md`).

Used in: `marimo.spec.ts` (8 call sites).

### 4. Grid Readiness Helpers

**Galata's equivalent:** Galata provides `page.notebook.waitForCellOutput()` and similar scoped helpers.

**Buckaroo has three variants** for different contexts:

Server context (`server-helpers.ts:27-30`):
```typescript
export async function waitForGrid(page: Page) {
  await page.locator('.ag-overlay').first().waitFor({ state: 'hidden', timeout: 15_000 });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
}
```

Jupyter context (`integration.spec.ts:10-14`):
```typescript
async function waitForAgGrid(outputArea: any, timeout = DEFAULT_TIMEOUT) {
  await outputArea.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await outputArea.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });
}
```

Marimo context (`marimo.spec.ts:8-13`):
```typescript
async function waitForGrid(page: Page) {
  await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 60_000 });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 60_000 });
}
```

Each is tuned to its environment: server waits for overlay to hide, Jupyter scopes to an output area and uses `attached` (cells may be offscreen), marimo waits for the anywidget container first.

### 5. Kernel Shutdown Between Tests

**Galata's approach:** Fixtures automatically manage kernel lifecycle — `kernels` fixture cleans up after each test.

**Buckaroo's implementation** (`test_playwright_jupyter.sh`):
```bash
KERNELS=$(curl -s "http://localhost:$port/api/kernels?token=$JUPYTER_TOKEN")
echo "$KERNELS" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-...-[0-9a-f]{12}' | while read kid; do
  curl -s -X DELETE "http://localhost:$port/api/kernels/$kid?token=$JUPYTER_TOKEN"
done
```

Also clears workspace state (`rm -rf ~/.jupyter/lab/workspaces`) to prevent JupyterLab from restoring previous notebook sessions.

---

## Not Adopted — Analysis

### 6. `jupyterapp.started` Wait

**What Galata does** (`galata/src/jupyterlabpage.ts:715-724`):
```typescript
await page.evaluate(async () => {
  await window.jupyterapp.started;  // Waits for ALL plugins to load
});
```

`jupyterapp.started` is a Promise that resolves when all JupyterLab extensions (including anywidget) have finished their `activate()` calls.

**Why Buckaroo skips it:** The existing kernel state check (`pattern 1`) implicitly waits for the app to be loaded — `window.jupyterapp` is undefined until the app initializes, and the kernel check returns `false` until the full session→kernel chain is established. Adding an explicit `started` wait would be belt-and-suspenders.

**Risk of not having it:** If anywidget's plugin loads after the kernel becomes idle (theoretically possible if extension activation is slow), the kernel check would pass but widget rendering could fail. In practice this hasn't been observed — anywidget is a lightweight extension and activates quickly.

**Recommendation:** Add it as a cheap insurance line before the kernel check. One additional `waitForFunction` call, ~0s cost:
```typescript
await page.waitForFunction(() =>
  typeof (window as any).jupyterapp === 'object',
  { timeout: 30000 }
);
```

### 7. Execution Count Verification

**What Galata does** (`galata/src/helpers/notebook.ts:468-480`):
```typescript
async waitForRun(cellIndex?: number): Promise<void> {
  // Stage 1: Wait for status bar to show "Idle"
  await this.page.locator('#jp-main-statusbar >> text=Idle').waitFor();
  // Stage 2: Verify execution count is set
  done = await this.page.evaluate(cellIdx => {
    return window.galata.haveBeenExecuted(cellIdx);
  }, cellIndex);
}
```

This two-stage check confirms the kernel actually processed the cell (execution count changes from `[ ]:` or `[*]:` to `[1]:`).

**What Buckaroo does instead:** Waits for output to appear in `.jp-OutputArea-output`, with a retry loop that re-sends `Shift+Enter` every 15s if no output arrives. This is cruder but effective — if output appears, the cell definitely executed.

**Risk of not having it:** If a cell produces no visible output (e.g., `import buckaroo` with no display call), the output check would time out even though execution succeeded. Currently all test notebooks produce widget output, so this isn't an issue.

**Recommendation:** Not needed unless test notebooks are added that don't produce visible output.

### 8. Animation Frame Stability

**What Galata does** (`galata/src/helpers/notebook.ts:1290-1331`):
```typescript
// Wait until content is unchanged for 10 consecutive animation frames
let framesWithoutChange = 0;
let previousContent = element.innerHTML;
const check = () => {
  requestAnimationFrame(() => {
    const newContent = element.innerHTML;
    if (previousContent === newContent) framesWithoutChange++;
    else framesWithoutChange = 0;
    previousContent = newContent;
    (framesWithoutChange < 10) ? check() : resolve();
  });
};
```

This catches progressive rendering — content exists but is still changing.

**Why Buckaroo doesn't need it (yet):** AG-Grid's rendering is fast once data arrives. The `waitFor({ state: 'visible' })` on `.ag-cell` catches the point where cells exist. The `toHaveText()` pattern (marimo tests) auto-retries until the correct data appears. No test failures have been traced to partial AG-Grid renders.

**When it would matter:** If Buckaroo adds screenshot comparison tests (visual regression), partial renders would produce flaky diffs. The animation frame check would stabilize screenshots.

**Recommendation:** Not needed for functional tests. Add if visual regression testing is introduced.

### 9. `waitForCondition` Utility

**What Galata does** (`galata/src/utils.ts:174-203`):
```typescript
async function waitForCondition(
  fn: () => boolean | Promise<boolean>,
  timeout: number = 15000
): Promise<void> { /* 50ms polling loop */ }
```

**What Buckaroo uses instead:** A mix of Playwright's built-in `waitForFunction()`, `waitFor()` on locators, `expect().toPass()`, and ad-hoc retry loops. These are more verbose but each is tuned to its specific context.

**Recommendation:** Not worth extracting — Playwright's built-in primitives cover all current use cases.

---

## Remaining `waitForTimeout` Usage

Despite the Galata-inspired improvements, **66 `waitForTimeout` calls** remain across the test suite:

| File | Count | Context |
|------|-------|---------|
| `theme-screenshots-jupyter.spec.ts` | 10 | Screenshot stabilization waits |
| `record-one-second-gap-transcript.spec.ts` | 9 | Intentional timing delays for transcript recording |
| `small-df-scroll.spec.ts` | 7 | Scroll stabilization waits |
| `message-box-streaming.spec.ts` | 7 | Streaming message timing |
| `integration-batch.spec.ts` | 6 | Cell execution delays |
| `theme-screenshots-marimo.spec.ts` | 4 | Screenshot stabilization |
| `transcript-replayer.spec.ts` | 4 | Replay timing |
| `theme-screenshots-server.spec.ts` | 5 | Screenshot stabilization |
| `infinite-scroll-transcript.spec.ts` | 3 | Retry loop + scroll delay |
| Other files | 11 | Various |

**Which ones matter for CI speed:**
- `theme-screenshots-*.spec.ts` — screenshot tests need visual stability; fixed waits are appropriate here
- `record-one-second-gap-transcript.spec.ts` — intentional timing delays to test transcript recording at specific intervals; fixed waits are the point
- `integration-batch.spec.ts` — the 200-800ms waits between cell executions could be replaced with output detection, but this file tests batch execution patterns where timing matters
- `small-df-scroll.spec.ts` — 1500-3000ms waits after scrolling could be replaced with `waitForFunction` checking visible row indices

The CI-critical specs (`integration.spec.ts`, `server.spec.ts`, `marimo.spec.ts`) have already been cleaned up. The remaining `waitForTimeout` calls are in Storybook specs (not on the critical path) or serve intentional timing purposes.

---

## Connections to CI Experiments

| Experiment | Galata Pattern Applied | Result |
|------------|----------------------|--------|
| Exp 15 | `expect().toPass()` replaced `waitForTimeout(3000)` in server specs | pw-server 50s → 37s |
| Exp 21 | `window.jupyterapp` kernel state check | pw-jupyter 80% → 100% pass rate |
| Exp 29 | `toHaveText()` auto-retrying assertions in marimo specs | Eliminated data loading race |
| Exp 30 | Combined effect: no heavyweight gate needed | 7/7 pw-jupyter, total 1m43s |

The Galata-inspired changes account for approximately:
- **100% of the pw-jupyter reliability improvement** (Exp 21 kernel check)
- **13s of pw-server time savings** (Exp 15 `toPass()` polling)
- **Elimination of the heavyweight Playwright gate** (Exp 30 — reliable kernel check means pw-jupyter can run concurrently with other Playwright jobs)

---

## Recommendations

### Worth doing (cheap, low-risk)

1. **Add `jupyterapp.started` wait** before the kernel check in `integration.spec.ts` and `infinite-scroll-transcript.spec.ts`. One line, ensures all extensions are activated. Cost: ~0s (app is already loaded by the time the kernel check runs).

### Not worth doing (current reliability is sufficient)

2. **Execution count verification** — retry loop already handles silent drops. Would only matter for notebooks with no visible output (none exist).

3. **Animation frame stability** — AG-Grid renders quickly, no reported flakes from partial renders. Add if visual regression testing is introduced.

4. **Centralized `waitForCondition` utility** — Playwright's built-in primitives are sufficient. Extracting a utility would add abstraction without fixing any current problem.

5. **Replace remaining `waitForTimeout` calls** — the 66 remaining calls are in Storybook/screenshot specs (not on critical path) or serve intentional timing purposes. The CI-critical specs are already clean.
