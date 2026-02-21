import { test, expect, Page } from '@playwright/test';

/**
 * Single smoke test for Buckaroo rendering in marimo WASM (Pyodide).
 *
 * Full test suite saved in https://github.com/buckaroo-data/buckaroo/issues/513
 * for re-enabling once WASM test infrastructure is more stable.
 */

let sharedPage: Page;

// Collect all browser console output for CI debugging
const consoleLogs: string[] = [];
const pageErrors: string[] = [];

test.describe('Buckaroo in Marimo WASM (Pyodide)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();

    // Capture all console messages for debugging
    sharedPage.on('console', (msg) => {
      const text = `[${msg.type()}] ${msg.text()}`;
      consoleLogs.push(text);
    });

    sharedPage.on('pageerror', (err) => {
      pageErrors.push(`[PAGE ERROR] ${err.message}`);
    });

    await sharedPage.goto('/');
    // Wait for Pyodide init + buckaroo widget + AG-Grid render
    // Use longer timeout since Pyodide needs to download & compile fastparquet WASM
    await sharedPage.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 120_000 });
    await sharedPage.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });
  });

  test.afterAll(async () => {
    // Print all captured console output for CI debugging
    if (consoleLogs.length > 0) {
      console.log('\n=== Browser Console Output ===');
      for (const log of consoleLogs) {
        console.log(log);
      }
      console.log('=== End Console Output ===\n');
    }
    if (pageErrors.length > 0) {
      console.log('\n=== Page Errors ===');
      for (const err of pageErrors) {
        console.log(err);
      }
      console.log('=== End Page Errors ===\n');
    }
    await sharedPage?.close();
  });

  test('page loads and WASM widgets render with data', async () => {
    // At least one buckaroo widget rendered
    const widgets = await sharedPage.locator('.buckaroo_anywidget').all();
    expect(widgets.length).toBeGreaterThanOrEqual(1);

    // AG-Grid cells are visible (data actually rendered)
    const cells = await sharedPage.locator('.ag-cell').all();
    expect(cells.length).toBeGreaterThan(0);

    // Column headers are present
    const headers = await sharedPage.locator('.ag-header-cell-text').all();
    expect(headers.length).toBeGreaterThan(0);
  });
});
