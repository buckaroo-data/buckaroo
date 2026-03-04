import { test, expect } from '@playwright/test';

/**
 * Wait for AG-Grid to finish rendering inside a marimo page.
 * Marimo wraps anywidget output in its own containers, but the
 * AG-Grid cells are still accessible via standard selectors.
 */
async function waitForGrid(page: import('@playwright/test').Page) {
  // Wait for at least one buckaroo widget to appear
  await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 60_000 });
  // Wait for AG-Grid cells to render
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 60_000 });
}

/**
 * Get a cell locator by col-id and row-index within
 * the main data grid (.df-viewer) of a widget container.
 * Returns a locator (not text) so callers can use Playwright's
 * auto-retrying expect(locator).toHaveText() instead of one-shot innerText().
 */
function cellLocator(
  container: import('@playwright/test').Locator,
  colId: string,
  rowIndex: number,
): import('@playwright/test').Locator {
  const dfViewer = container.locator('.df-viewer');
  return dfViewer.locator(`[row-index="${rowIndex}"] [col-id="${colId}"]`);
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
    .locator('.ag-header-viewport .ag-header-row')
    .all();
  return Number(total) - headers.length;
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
    // Use toHaveText() — auto-retries until data loads (handles kernel→grid race)
    await expect(cellLocator(firstWidget, 'a', 0)).toHaveText('Alice');
    await expect(cellLocator(firstWidget, 'a', 1)).toHaveText('Bob');
    await expect(cellLocator(firstWidget, 'a', 2)).toHaveText('Charlie');
    await expect(cellLocator(firstWidget, 'b', 0)).toHaveText('30');
    await expect(cellLocator(firstWidget, 'b', 1)).toHaveText('25');
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
    await widgets.nth(1).waitFor({ state: 'visible', timeout: 60_000 });
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 60_000 });

    const secondWidget = widgets.nth(1);
    const count = await getRowCount(secondWidget);
    expect(count).toBe(200);
  });

  test('large DataFrame cell values match source data', async ({ page }) => {
    await page.goto('/');
    await waitForGrid(page);

    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 60_000 });

    const secondWidget = widgets.nth(1);

    // Columns: id→a, value→b, label→c
    // Auto-retrying assertions handle kernel→grid data loading race
    await expect(cellLocator(secondWidget, 'a', 0)).toHaveText('0');
    await expect(cellLocator(secondWidget, 'b', 0)).toHaveText('0');
    await expect(cellLocator(secondWidget, 'c', 0)).toHaveText('row_0');
  });
});
