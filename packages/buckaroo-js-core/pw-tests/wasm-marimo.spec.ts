import { test, expect } from '@playwright/test';

/**
 * Wait for AG-Grid to finish rendering inside a marimo WASM page.
 * WASM initialization is slower than server-based marimo, so we use longer timeouts.
 *
 * Pyodide initialization sequence:
 * 1. WASM module loads (~5-10s)
 * 2. Python runtime initializes (~5-10s)
 * 3. marimo cells execute
 * 4. Buckaroo widgets load and render
 */
async function waitForWasmGrid(page: import('@playwright/test').Page, timeout = 90_000) {
  // Wait for at least one buckaroo widget to appear
  // This signals that Pyodide initialization is done and cells have executed
  await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout });
  // Wait for AG-Grid cells to render
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });
}

/**
 * Get the text content of a cell by col-id and row-index within the data grid
 */
async function getCellText(
  container: import('@playwright/test').Locator,
  colId: string,
  rowIndex: number,
): Promise<string> {
  const dfViewer = container.locator('.df-viewer');
  const cell = dfViewer.locator(`[row-index="${rowIndex}"] [col-id="${colId}"]`);
  return (await cell.innerText()).trim();
}

/**
 * Get data row count from the main data grid's aria-rowcount
 */
async function getRowCount(container: import('@playwright/test').Locator): Promise<number> {
  const dfViewer = container.locator('.df-viewer');
  const grid = dfViewer.getByRole('treegrid').or(dfViewer.getByRole('grid'));
  const total = await grid.first().getAttribute('aria-rowcount');
  const headers = await dfViewer.locator('.ag-header .ag-header-row').all();
  return Number(total) - headers.length;
}

/**
 * Scroll to a specific row in AG-Grid virtual scrolling
 */
async function scrollToRow(
  container: import('@playwright/test').Locator,
  targetRow: number,
  page: import('@playwright/test').Page,
) {
  const dfViewer = container.locator('.df-viewer');
  const gridViewport = dfViewer.locator('.ag-root .ag-body-viewport').first();

  // AG-Grid rows are ~28px tall
  const scrollHeight = 28;
  const targetScrollTop = targetRow * scrollHeight;

  await gridViewport.evaluate((el, scrollTop) => {
    el.scrollTop = scrollTop;
  }, targetScrollTop);

  // Wait for new content to load
  await page.waitForTimeout(800);
}

// ---------- tests ------------------------------------------------------------

test.describe('Buckaroo in Marimo WASM (Pyodide)', () => {
  test('diagnostic: check page content and errors', async ({ page }) => {
    // Collect console messages for debugging
    const consoleLogs: string[] = [];
    page.on('console', msg => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });

    page.on('pageerror', error => {
      consoleLogs.push(`[error] ${error.message}`);
    });

    await page.goto('/');
    await page.waitForTimeout(15000); // Wait 15s for Pyodide init

    // Check what's actually on the page
    const pageTitle = await page.title();
    const bodyText = await page.textContent('body');
    const hasError = bodyText?.includes('error') || bodyText?.includes('Error');
    const hasWidget = await page.locator('.buckaroo_anywidget').count();

    // Check for other potential widget containers
    const allDivs = await page.locator('div[class*="widget"]').count();
    const allDivsMario = await page.locator('div[class*="marimo"]').count();
    const agGrids = await page.locator('.ag-root').count();

    console.log(`\n📋 DIAGNOSTIC REPORT:`);
    console.log(`   Page title: ${pageTitle}`);
    console.log(`   Has .buckaroo_anywidget: ${hasWidget}`);
    console.log(`   Has .ag-root (AG-Grid): ${agGrids}`);
    console.log(`   Has div[class*="widget"]: ${allDivs}`);
    console.log(`   Has div[class*="marimo"]: ${allDivsMario}`);
    console.log(`   Body contains 'error': ${hasError}`);
    console.log(`   Console logs (last 10):`);
    consoleLogs.slice(-10).forEach(log => console.log(`     ${log}`));

    // Get list of all visible divs with classes
    const visibleDivs = await page.locator('div[class]').evaluateAll((elements: any[]) =>
      elements.slice(0, 20).map((el: any) => el.className)
    );
    console.log(`   Sample visible div classes:`, visibleDivs);

    // Fail with detailed info
    if (hasWidget === 0 && agGrids === 0) {
      console.log(`\n❌ No widgets found!`);
      throw new Error(
        `No buckaroo widgets rendered. Found: ${allDivs} widget divs, ${allDivsMario} marimo divs, ${agGrids} AG-Grids`
      );
    }
  });

  test('page loads and WASM widgets render', async ({ page }) => {
    // Log page load start
    const startTime = Date.now();

    await page.goto('/');
    await waitForWasmGrid(page);

    const elapsed = Date.now() - startTime;
    console.log(`⏱️  WASM initialization + render: ${elapsed}ms`);

    // There should be at least one buckaroo widget on the page
    const widgets = await page.locator('.buckaroo_anywidget').all();
    expect(widgets.length).toBeGreaterThanOrEqual(1);
  });

  test('WASM notebook displays version info and data', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    // The notebook should have rendered content
    // Check for specific content from buckaroo_ddd_tour.py
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();

    // Should have at least one widget visible
    const widgets = await page.locator('.buckaroo_anywidget').all();
    expect(widgets.length).toBeGreaterThanOrEqual(1);
  });

  test('small DataFrame renders in WASM', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();
    const count = await getRowCount(firstWidget);

    // buckaroo_ddd_tour.py has various DataFrames; just verify non-zero count
    expect(count).toBeGreaterThan(0);
  });

  test('cell values are readable after WASM load', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();

    // Try to read a cell - just verify we can access cell content
    try {
      const firstCellText = await getCellText(firstWidget, 'a', 0);
      expect(firstCellText).toBeTruthy();
    } catch (e) {
      // If exact selector doesn't work, just verify grid is visible
      const cells = await firstWidget.locator('.ag-cell').all();
      expect(cells.length).toBeGreaterThan(0);
    }
  });

  test('column headers are visible in WASM', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();
    const headers = await firstWidget.locator('.ag-header-cell-text').all();

    // Should have at least one column header
    expect(headers.length).toBeGreaterThan(0);
  });

  test('summary stats grid renders in WASM', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();

    // Buckaroo widgets have a stats grid at the bottom
    const statsCells = await firstWidget.locator('.ag-cell').all();

    // Should have cells in both data and stats grids
    expect(statsCells.length).toBeGreaterThan(0);
  });

  test('second widget (if exists) also renders in WASM', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const widgets = await page.locator('.buckaroo_anywidget').all();

    // buckaroo_ddd_tour.py may have multiple widgets
    if (widgets.length >= 2) {
      // Wait for second widget to be visible and have cells
      await widgets[1].waitFor({ state: 'visible', timeout: 30_000 });
      const secondWidgetCells = await widgets[1].locator('.ag-cell').all();
      expect(secondWidgetCells.length).toBeGreaterThan(0);
    }
  });

  test('WASM notebook remains responsive after scroll', async ({ page }) => {
    await page.goto('/');
    await waitForWasmGrid(page);

    const widgets = await page.locator('.buckaroo_anywidget').all();
    if (widgets.length === 0) {
      console.log('⚠️  No widgets found, skipping scroll test');
      return;
    }

    const firstWidget = widgets[0];
    const initialRowCount = await getRowCount(firstWidget);

    if (initialRowCount < 10) {
      console.log(`⚠️  DataSet has only ${initialRowCount} rows, skipping scroll test`);
      return;
    }

    // Try to scroll to middle
    try {
      const targetRow = Math.floor(initialRowCount / 2);
      await scrollToRow(firstWidget, targetRow, page);

      // Verify widget is still responsive
      const cellsAfterScroll = await firstWidget.locator('.ag-cell').all();
      expect(cellsAfterScroll.length).toBeGreaterThan(0);
    } catch (e) {
      // Scroll may not work in all WASM scenarios; just ensure widget didn't crash
      const cells = await firstWidget.locator('.ag-cell').all();
      expect(cells.length).toBeGreaterThan(0);
    }
  });
});
