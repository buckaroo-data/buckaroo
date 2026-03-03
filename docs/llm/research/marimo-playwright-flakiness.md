# Marimo Playwright Flakiness: Root Cause Analysis & Recommendations

**Date:** 2026-03-03
**Repo:** marimo-team/marimo
**Config:** `frontend/playwright.config.ts`

## Current Architecture

The Playwright suite spawns **7 separate marimo server processes** before tests run:

- 1 edit-mode server on port 2718 (shared by ~11 test apps via `?file=` query param)
- 6 run-mode servers on ports 2719-2724 (one per app: components, layout_grid variants, output, shutdown)

All servers start simultaneously via Playwright's `webServer` config with a 30-second timeout. Tests run sequentially on a single Chromium worker with 2 retries on CI.

Key files:
- `frontend/playwright.config.ts` — server config, app routing, timeouts
- `frontend/e2e-tests/global-setup.ts` — pre-test health check (only checks `components.py`)
- `frontend/e2e-tests/global-teardown.ts` — `pkill -f 'marimo.*--headless'`
- `frontend/e2e-tests/test-utils.ts` — `waitForMarimoApp()`, `waitForServerReady()`, retry helpers
- `frontend/e2e-tests/helper.ts` — `createCellBelow()`, `exportAsHTMLAndTakeScreenshot()`, etc.
- `.github/workflows/playwright.yml` — CI workflow, 13-minute timeout

## Failure Categories (by frequency)

### Category A: Web Server Startup Failures (~70%)

The dominant failure mode. All 7 marimo processes start simultaneously, causing a CPU spike on GitHub Actions shared runners. Servers fail to bind within the 30-second `webServer` timeout.

Typical error:
```
Error while checking if http://127.0.0.1:2719/ is available: connect ECONNREFUSED 127.0.0.1:2719
Error: Process from config.webServer was not able to start. Exit code: 1
```

This cascades across all ports (2719-2724), meaning the entire test suite fails before any tests execute. There is no retry at the `webServer` config level — retries only apply to individual test execution.

Contributing factors:
- 7 processes compete for CPU/memory on a shared CI runner
- No sequential startup or health gating between servers
- `global-setup.ts` only validates `components.py` — other servers could be unhealthy
- No detailed logging when a server process exits with code 1

Parallel from Hetzner research: Experiments 14b/14e showed that CPU overlap during server startup drops pass rates from 100% to 29-80%. Sequential startup with polling between servers eliminated this.

### Category B: Test Assertion Races (~20%)

When servers do start, some tests fail due to timing issues:

**kitchen-sink.spec.ts** (most frequent assertion failure):
- Exports notebook as HTML, saves to disk, opens `file://` URL with `waitUntil: "networkidle"`
- The exported HTML loads external resources (CDN scripts, stylesheets) — `networkidle` times out if any resource is slow or unavailable
- Failed on Mar 3, 2026 with `TimeoutError: page.goto: Timeout 10000ms exceeded`

**toggle-cell-language.spec.ts**:
- Converts a cell to markdown, immediately asserts `cellEditor` is hidden
- Race between the conversion completing and the DOM updating the `hide_code=true` state
- Reported as "flaky" — passes on retry

**output.spec.ts**:
- "Loading replaced" test commented out entirely as flaky

### Category C: Session State Contamination (~10%)

Edit-mode tests share a single server on port 2718. State leaks between tests:
- `maybeRestartKernel()` handles reconnection to existing sessions but adds latency and can itself fail
- `resetFile()` does `git checkout` to restore Python files but doesn't reset server-side kernel state
- Test ordering matters — a failed test can leave the server in a bad state for the next test

## Fundamental Architecture Problems

### Problem 1: Too Many Servers Started Simultaneously

7 processes starting at once on a 2-core GitHub Actions runner is the root cause of ~70% of failures. The `webServer` config provides no mechanism for sequential startup or inter-server health gating.

### Problem 2: `networkidle` is Inherently Fragile

Used throughout the test suite:
- `global-setup.ts` line 25: `waitUntil: "networkidle"`
- `test-utils.ts` line 12: `waitForMarimoApp()` starts with `page.waitForLoadState("networkidle")`
- `test-utils.ts` line 41: `waitForServerReady()` uses `networkidle`
- `helper.ts` lines 106, 126, 144: export functions use `networkidle`

Playwright's `networkidle` fires when there are no network requests for 500ms. But marimo apps maintain:
- WebSocket connections to the kernel
- Periodic health check pings
- Lazy-loaded component resources

This means `networkidle` either fires too early (before the app is actually ready) or never fires (because WebSocket traffic never stops).

### Problem 3: No Application-Ready Contract

The tests have no reliable signal for "marimo is ready to accept user interactions." The current `waitForMarimoApp()` checks for DOM elements:

```typescript
document.querySelector("[data-testid='cell-editor']") !== null ||
document.querySelector(".marimo-cell") !== null ||
document.querySelector("[data-testid='marimo-static']") !== null
```

These elements can exist before the kernel is connected and cells are executable. This is the same class of bug found in the Jupyter research (Exp 21) — DOM presence != application readiness.

### Problem 4: Shared Edit Server Creates Ordering Dependencies

All edit-mode tests (title, streams, bad_button, bugs, cells, disabled_cells, kitchen_sink, layout_grid, stdin, slides) route through one server. The `?file=` parameter switches the active file, but server-side state (kernel, variables, execution history) persists across switches.

## Recommended Changes

### 1. Reduce to 2 Servers (Highest Impact)

Instead of 7 servers, run **1 edit server + 1 run server**. marimo edit already supports file switching via query params. For run mode, use `marimo run` with a directory or switch between apps.

```
Before: 7 processes × 30s timeout = fragile on shared CI
After:  2 processes × 60s timeout = robust
```

This eliminates the server startup stampede — the root cause of ~70% of failures.

If run-mode apps need true isolation (different base URLs, etc.), start at most 2-3 run servers, but never 6.

### 2. Add Application-Ready Signal (Replace networkidle)

Add an internal readiness flag to the marimo frontend that reflects actual kernel connection + initial execution state:

```typescript
// In marimo frontend (set after kernel connects and initial cells execute):
window.__MARIMO_READY__ = true;

// In tests (replace all networkidle usage):
await page.waitForFunction(
  () => (window as any).__MARIMO_READY__ === true,
  { timeout: 30_000 }
);
```

This is the exact pattern that took Jupyter Playwright pass rate from 80% to 100% in Experiment 21. The key insight: query the application's internal state, not DOM heuristics or network timing.

Concrete locations to replace:
- `test-utils.ts:waitForMarimoApp()` — replace `networkidle` + DOM check with `__MARIMO_READY__`
- `test-utils.ts:waitForServerReady()` — replace `networkidle` with `__MARIMO_READY__`
- `helper.ts:exportAsHTMLAndTakeScreenshot()` — replace `networkidle` (line 106) with content check
- `global-setup.ts` — replace `networkidle` with `__MARIMO_READY__`

### 3. Increase CI webServer Timeout (Trivial Fix)

30 seconds is too tight for GitHub Actions shared runners. Hetzner research showed servers can take 3-5x longer under contention:

```typescript
// playwright.config.ts line 211
timeout: process.env.CI ? 120 * 1000 : 30 * 1000,
```

This is a one-line change that catches slow CI starts without hurting local dev.

### 4. Fix the Export Test (kitchen-sink.spec.ts)

The export test navigates to a local `file://` URL with `networkidle`, which fails when the exported HTML references external CDN resources. Fix:

```typescript
// helper.ts:exportAsHTMLAndTakeScreenshot() — replace lines 126-128
await exportPage.goto(`file://${fullPath}`, { waitUntil: "load" });
await expect(exportPage.locator('body')).not.toBeEmpty();
```

`waitUntil: "load"` fires when the HTML and its resources are loaded. For a local file, this is immediate. The content check ensures the page actually rendered.

### 5. Use toPass() for Eventually-Consistent Assertions

The `toggle-cell-language` test has a race condition. Playwright's `toPass()` retries the assertion:

```typescript
// toggle-cell-language.spec.ts line 33 — replace:
await expect(cellEditor).toBeHidden();

// with:
await expect(async () => {
  await expect(cellEditor).toBeHidden();
}).toPass({ timeout: 5000 });
```

This handles the delay between "Convert to Markdown" completing and the DOM reflecting `hide_code=true`.

Note: Playwright's built-in `expect(locator).toBeHidden()` already auto-retries for up to the configured `expect.timeout` (5s). If the flake persists, the issue may be that the cell editor element is briefly removed and re-added during the conversion, which confuses the locator. In that case, add a small wait for the conversion to settle:

```typescript
await page.getByText("Convert to Markdown").click();
await expect(page.getByText("Hello Marimo!", { exact: true })).toBeVisible();
// Then check the editor
await expect(cellEditor).toBeHidden();
```

### 6. Sequential Server Startup (If Multi-Server Stays)

If reducing to 2 servers isn't feasible, move server startup from `webServer` config into `globalSetup` with sequential health gating:

```typescript
// global-setup.ts — start servers one at a time
for (const server of servers) {
  const proc = spawn(server.command);
  await pollUntilHealthy(server.url, { timeout: 60_000, interval: 1_000 });
  console.log(`✅ ${server.name} ready on ${server.url}`);
}
```

This prevents the CPU stampede. The tradeoff is slower startup (~10s per server × 7 = ~70s), but that's better than a 30% failure rate.

### 7. Validate All Servers in Global Setup

Currently `global-setup.ts` only checks `components.py`. It should validate every server:

```typescript
const criticalApps: ApplicationNames[] = [
  "components.py",
  "shutdown.py",
  "layout_grid.py//run",
  "layout_grid_max_width.py//run",
  "layout_grid_with_sidebar.py//run",
  "output.py//run",
];
```

This catches unhealthy servers before tests start, preventing cascading failures.

## Priority Matrix

| # | Change | Effort | Impact | Fixes |
|---|--------|--------|--------|-------|
| 1 | Reduce to 2 servers | Medium | Very High | ~70% of failures (server startup) |
| 2 | Add `__MARIMO_READY__` signal | Medium | High | Race conditions, networkidle flakes |
| 3 | Increase CI webServer timeout to 120s | Trivial | Medium | Slow CI starts |
| 4 | Fix export test (`waitUntil: "load"`) | Trivial | Medium | #1 flaky assertion test |
| 5 | `toPass()` for toggle-cell-language | Trivial | Low | Specific flaky test |
| 6 | Sequential startup in globalSetup | Medium | High | Server startup (if multi-server stays) |
| 7 | Validate all servers in globalSetup | Low | Medium | Undetected unhealthy servers |

## Connections to Prior Research

The Hetzner/Jupyter Playwright research identified the same fundamental patterns:

| Hetzner Finding | Marimo Equivalent |
|-----------------|-------------------|
| REST API `starting→idle` never transitions without WebSocket client | `networkidle` fires before marimo kernel is connected |
| `session.kernel === null` causes silent Shift+Enter drops | DOM elements exist before kernel is ready to execute |
| CPU contention at PARALLEL>1 drops pass rate to 29-80% | 7 simultaneous servers on 2-core CI runner |
| Exp 21: internal state check → 100% pass rate | Proposed `__MARIMO_READY__` signal |
| Sequential server startup eliminates CPU overlap | Proposed sequential startup in globalSetup |
| `waitForTimeout()` → `expect().toPass()` saved 13s | Replace fixed waits with polling assertions |

The core lesson is the same: **query internal application state, not DOM/network heuristics.** Every reliability improvement in the Jupyter research came from moving closer to the application's own readiness model.

## GitHub Issues & PRs (Reference)

- **PR #5567** (Jul 2025): Major overhaul — added global-setup/teardown, test-utils, retry helpers
- **PR #5796** (Jul 2025): Added retry logic for a flaky test
- **PR #5810** (Jul 2025): Fixed flaky WASM test
- **PR #8545** (Mar 2026): Fixed plotly snapshot test

Related backend flakiness (shared root causes — race conditions, thread cleanup):
- **PR #8423** (Feb 2026): Flaky resume session watch test
- **PR #8373** (Feb 2026): Thread-safety in WatchdogFileWatcher
- **PR #7880** (Jan 2026): Session TTL test — kernel thread cleanup
- **PR #7842** (Jan 2026): Middleware test — kernel thread not awaited

## Appendix: Current Test Files

| Spec File | App | Mode | Known Issues |
|-----------|-----|------|-------------|
| kitchen-sink.spec.ts | kitchen_sink.py | edit | `networkidle` timeout on HTML export |
| toggle-cell-language.spec.ts | title.py | edit | Race on markdown conversion |
| components.spec.ts | components.py | run | Date picker skipped |
| mode.spec.ts | title.py | edit | 2 tests skipped |
| cells.spec.ts | cells.py | edit | Entire file skipped (testIgnore) |
| disabled.spec.ts | disabled_cells.py | edit | Entire file skipped (testIgnore) |
| output.spec.ts | output.py | run | Loading test commented out |
| kitchen-sink-wasm.spec.ts | — | wasm | Separate WASM config (disabled) |
| bugs.spec.ts | bugs.py | edit | |
| streams.spec.ts | streams.py | edit | |
| stdin.spec.ts | stdin.py | edit | |
| slides.spec.ts | slides.py | edit | |
| layout-grid.spec.ts | layout_grid.py | edit+run | |
| layout-grid-with-sidebar.spec.ts | layout_grid_with_sidebar.py | edit+run | |
| shutdown.spec.ts | shutdown.py | edit | Own port (2719) |
| badButton.spec.ts | bad_button.py | edit | |
