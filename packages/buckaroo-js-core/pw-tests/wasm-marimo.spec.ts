import { test, expect, Page } from '@playwright/test';

/**
 * Single smoke test for Buckaroo rendering in marimo WASM (Pyodide).
 *
 * Full test suite saved in https://github.com/buckaroo-data/buckaroo/issues/513
 * for re-enabling once WASM test infrastructure is more stable.
 */

let sharedPage: Page;

test.describe('Buckaroo in Marimo WASM (Pyodide)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();
    await sharedPage.goto('/');
    // Wait for Pyodide init + buckaroo widget + AG-Grid render
    await sharedPage.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 60_000 });
    await sharedPage.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
  });

  test.afterAll(async () => {
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
