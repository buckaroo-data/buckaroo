import { test, expect } from '@playwright/test';

/**
 * Wait for AG-Grid to finish rendering inside a marimo page.
 * Marimo wraps anywidget output in its own containers, but the
 * AG-Grid cells are still accessible via standard selectors.
 */
async function waitForGrid(page: import('@playwright/test').Page) {
  // Wait for at least one buckaroo widget to appear
  await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 30_000 });
  // Wait for AG-Grid cells to render
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });
}

/**
 * Get the text content of a cell by col-id and row-index within
 * the main data grid (.df-viewer) of a widget container.
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
 * Get data row count from the main data grid's aria-rowcount.
 * Each BuckarooWidget has two grids (data + summary stats).
 * The data grid lives inside .df-viewer.
 */
async function getRowCount(container: import('@playwright/test').Locator): Promise<number> {
  const dfViewer = container.locator('.df-viewer');
  const grid = dfViewer.getByRole('treegrid').or(dfViewer.getByRole('grid'));
  const total = await grid.first().getAttribute('aria-rowcount');
  const headers = await dfViewer
    .locator('.ag-header .ag-header-row')
    .all();
  return Number(total) - headers.length;
}

/**
 * Scroll to a specific row in the AG-Grid inside a widget container.
 * Uses AG-Grid's virtual scrolling by scrolling the viewport.
 */
async function scrollToRow(
  container: import('@playwright/test').Locator,
  targetRow: number,
  page: import('@playwright/test').Page,
) {
  const dfViewer = container.locator('.df-viewer');
  const gridViewport = dfViewer.locator('.ag-root .ag-body-viewport').first();

  // AG-Grid rows are typically ~25-30px tall; estimate scroll position
  // We scroll to target row's approximate position
  const scrollHeight = 28; // approx row height
  const targetScrollTop = targetRow * scrollHeight;

  await gridViewport.evaluate(
    (el, scrollTop) => {
      el.scrollTop = scrollTop;
    },
    targetScrollTop,
  );

  // Wait for the row to appear
  await page.waitForTimeout(500);
}

/**
 * Wait until a specific cell is visible and has expected content.
 * Useful after scrolling to verify content loaded correctly.
 */
async function waitForCellContent(
  container: import('@playwright/test').Locator,
  colId: string,
  rowIndex: number,
  expectedContent: string,
  timeout = 10_000,
) {
  const dfViewer = container.locator('.df-viewer');
  const cell = dfViewer.locator(`[row-index="${rowIndex}"] [col-id="${colId}"]`);

  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    try {
      const text = (await cell.innerText()).trim();
      if (text === expectedContent) {
        return;
      }
    } catch {
      // Cell not visible yet
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }

  throw new Error(
    `Cell [${rowIndex}:${colId}] did not show "${expectedContent}" within ${timeout}ms`,
  );
}

// ---------- tests ------------------------------------------------------------

test.describe('Buckaroo in marimo', () => {
  test('page loads and renders widgets', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    // There should be at least one buckaroo widget on the page
    const widgets = await page.locator('.buckaroo_anywidget').all();
    expect(widgets.length).toBeGreaterThanOrEqual(1);
  });

  test('small DataFrame renders with correct row count', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    // The first widget is the small BuckarooWidget (5 rows)
    const firstWidget = page.locator('.buckaroo_anywidget').first();

    const count = await getRowCount(firstWidget);
    expect(count).toBe(5);
  });

  test('small DataFrame cell values match source data', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();

    // Column names get mapped to col-ids: name→a, age→b, score→c
    expect(await getCellText(firstWidget, 'a', 0)).toBe('Alice');
    expect(await getCellText(firstWidget, 'a', 1)).toBe('Bob');
    expect(await getCellText(firstWidget, 'a', 2)).toBe('Charlie');
    expect(await getCellText(firstWidget, 'b', 0)).toBe('30');
    expect(await getCellText(firstWidget, 'b', 1)).toBe('25');
  });

  test('column headers are present', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    const firstWidget = page.locator('.buckaroo_anywidget').first();

    for (const name of ['name', 'age', 'score']) {
      await expect(firstWidget.getByRole('columnheader', { name })).toBeVisible();
    }
  });

  test('large DataFrame renders with BuckarooInfiniteWidget', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    // The second widget is the BuckarooInfiniteWidget (200 rows)
    const widgets = page.locator('.buckaroo_anywidget');
    // Wait for the second widget to also render
    await widgets.nth(1).waitFor({ state: 'visible', timeout: 30_000 });
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);
    const count = await getRowCount(secondWidget);
    expect(count).toBe(200);
  });

  test('large DataFrame cell values match source data', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);

    // Columns: id→a, value→b, label→c
    expect(await getCellText(secondWidget, 'a', 0)).toBe('0');
    expect(await getCellText(secondWidget, 'b', 0)).toBe('0');
    expect(await getCellText(secondWidget, 'c', 0)).toBe('row_0');
  });

  test('BuckarooInfiniteWidget scrolls to middle (row 100) without blank cells', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);

    // Scroll to row 100
    await scrollToRow(secondWidget, 100, page);

    // Verify row 100 cell values (id→a, value→b, label→c)
    // After SmartRowCache fix, overshoot should clamp correctly
    await waitForCellContent(secondWidget, 'a', 100, '100');
    await waitForCellContent(secondWidget, 'b', 100, '1000'); // 100 * 10
    await waitForCellContent(secondWidget, 'c', 100, 'row_100');
  });

  test('BuckarooInfiniteWidget scrolls to bottom (row 199) without blank cells', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);

    // Scroll to row 199 (last row, 0-indexed)
    await scrollToRow(secondWidget, 199, page);

    // Verify row 199 cell values
    await waitForCellContent(secondWidget, 'a', 199, '199');
    await waitForCellContent(secondWidget, 'b', 199, '1990'); // 199 * 10
    await waitForCellContent(secondWidget, 'c', 199, 'row_199');
  });

  test('BuckarooInfiniteWidget rapid scroll does not cause blank rows', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);

    // Simulate rapid scrolling: jump to row 50, then 150, then back to 50
    for (let i = 0; i < 3; i++) {
      await scrollToRow(secondWidget, 50, page);
      await waitForCellContent(secondWidget, 'a', 50, '50');

      await scrollToRow(secondWidget, 150, page);
      await waitForCellContent(secondWidget, 'a', 150, '150');
    }

    // Should not crash or show blank cells
    const widgets_after = await page.locator('.buckaroo_anywidget').all();
    expect(widgets_after.length).toBeGreaterThanOrEqual(2);
  });

  test('BuckarooInfiniteWidget scroll to bottom then back to top works correctly', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    const secondWidget = widgets.nth(1);

    // Scroll to bottom
    await scrollToRow(secondWidget, 199, page);
    await waitForCellContent(secondWidget, 'a', 199, '199');

    // Scroll back to top
    await scrollToRow(secondWidget, 0, page);
    await waitForCellContent(secondWidget, 'a', 0, '0');

    // Verify we can still read initial rows correctly
    expect(await getCellText(secondWidget, 'b', 0)).toBe('0');
    expect(await getCellText(secondWidget, 'c', 0)).toBe('row_0');
  });
});
