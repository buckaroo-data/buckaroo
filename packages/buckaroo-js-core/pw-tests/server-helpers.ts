import { APIRequestContext, Page } from '@playwright/test';

const PORT = 8701;
const BASE = `http://localhost:${PORT}`;

/**
 * POST /load to create a session with the given file.
 * Returns the parsed JSON response body.
 */
export async function loadSession(
  request: APIRequestContext,
  sessionId: string,
  filePath: string,
) {
  const resp = await request.post(`${BASE}/load`, {
    data: { session: sessionId, path: filePath },
  });
  if (!resp.ok()) {
    throw new Error(`/load failed (${resp.status()}): ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * Wait for ag-grid to finish loading: overlay hidden, cells visible.
 */
export async function waitForGrid(page: Page) {
  await page.locator('.ag-overlay').first().waitFor({ state: 'hidden', timeout: 15_000 });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
}

/**
 * Get the data row count from the grid's aria-rowcount (minus header rows).
 */
export async function getRowCount(page: Page): Promise<number> {
  const headers = await page
    .locator('.ag-header-viewport .ag-header-row')
    .and(page.getByRole('row'))
    .all();
  const grid = page.getByRole('treegrid').or(page.getByRole('grid'));
  const total = await grid.first().getAttribute('aria-rowcount');
  return Number(total) - headers.length;
}

/**
 * Get the text content of a cell by col-id and row-index.
 */
export async function getCellText(
  page: Page,
  colId: string,
  rowIndex: number,
): Promise<string> {
  const cell = page.locator(`[row-index="${rowIndex}"] [col-id="${colId}"]`);
  return (await cell.innerText()).trim();
}
