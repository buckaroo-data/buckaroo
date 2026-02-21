import { test, expect } from '@playwright/test';

/**
 * Single smoke test for Buckaroo rendering in marimo WASM (Pyodide).
 *
 * The WASM page is generated from docs/example-notebooks/marimo-wasm/buckaroo_simple.py
 * using: bash scripts/marimo_wasm_output.sh buckaroo_simple.py run
 *
 * Full test suite saved in https://github.com/buckaroo-data/buckaroo/issues/513
 * for re-enabling once WASM test infrastructure is more stable.
 */

test('Buckaroo WASM marimo - page loads and widgets render', async ({ page }) => {
  // Pyodide init + micropip install buckaroo + cell execution can take 2-3 min
  test.setTimeout(300_000);

  // Capture console messages for debugging failures
  const consoleLogs: string[] = [];
  page.on('console', (msg) => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
  });
  page.on('pageerror', (err) => {
    consoleLogs.push(`[PAGE_ERROR] ${err.message}`);
  });

  await page.goto('/');

  // Wait for marimo cells to render - poll for visible notebook content.
  // The "Buckaroo in Marimo WASM" heading appears once cells execute.
  const pollInterval = 5_000;
  const maxWait = 240_000;
  let elapsed = 0;
  let contentRendered = false;

  while (elapsed < maxWait) {
    await page.waitForTimeout(pollInterval);
    elapsed += pollInterval;

    const pageText = await page.evaluate(() => document.body.innerText);
    if (pageText.includes('Buckaroo in Marimo WASM')) {
      contentRendered = true;
      break;
    }
  }

  if (!contentRendered) {
    // Dump console logs to help diagnose CI failures
    console.log('=== Console logs (last 80) ===');
    for (const log of consoleLogs.slice(-80)) {
      console.log(log);
    }
    console.log('=== End console logs ===');
  }

  expect(contentRendered, 'Marimo notebook content should have rendered').toBe(true);

  // Wait for buckaroo widgets to appear after cell execution.
  // The widget renders after micropip installs buckaroo and cells run.
  const widgetMaxWait = 60_000;
  let widgetElapsed = 0;
  let widgetFound = false;

  while (widgetElapsed < widgetMaxWait) {
    await page.waitForTimeout(5_000);
    widgetElapsed += 5_000;

    // Check in main page
    if ((await page.locator('.buckaroo_anywidget').count()) > 0) {
      widgetFound = true;
      break;
    }

    // Also check inside iframes (anywidget may render in iframes)
    for (const frame of page.frames()) {
      if (frame === page.mainFrame()) continue;
      try {
        if ((await frame.locator('.buckaroo_anywidget').count()) > 0) {
          widgetFound = true;
          break;
        }
      } catch (_e) {
        // frame may be detached
      }
    }
    if (widgetFound) break;
  }

  if (!widgetFound) {
    // Dump console logs to help diagnose CI failures
    console.log('=== Console logs (last 80) ===');
    for (const log of consoleLogs.slice(-80)) {
      console.log(log);
    }
    console.log('=== End console logs ===');
  }

  // Check for buckaroo widget and AG-Grid content in main page and frames
  let agCellFound = false;
  let headerFound = false;

  const mainBuckaroo = await page.locator('.buckaroo_anywidget').count();
  const mainAgCell = await page.locator('.ag-cell').count();
  const mainHeaders = await page.locator('.ag-header-cell-text').count();

  if (mainBuckaroo > 0) widgetFound = true;
  if (mainAgCell > 0) agCellFound = true;
  if (mainHeaders > 0) headerFound = true;

  // Check all frames as fallback
  for (const frame of page.frames()) {
    if (frame === page.mainFrame()) continue;
    try {
      if (!widgetFound && (await frame.locator('.buckaroo_anywidget').count()) > 0) widgetFound = true;
      if (!agCellFound && (await frame.locator('.ag-cell').count()) > 0) agCellFound = true;
      if (!headerFound && (await frame.locator('.ag-header-cell-text').count()) > 0) headerFound = true;
    } catch (_e) {
      // frame may be detached
    }
  }

  expect(widgetFound, 'At least one .buckaroo_anywidget should be present').toBe(true);
  expect(agCellFound, 'AG-Grid cells should be visible (data rendered)').toBe(true);
  expect(headerFound, 'AG-Grid column headers should be visible').toBe(true);
});
