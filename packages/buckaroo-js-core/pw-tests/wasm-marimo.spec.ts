import { test, expect } from '@playwright/test';

/**
 * Smoke test for marimo WASM (Pyodide) page loading and cell execution.
 *
 * Widget rendering (.buckaroo_anywidget, AG-Grid) is unreliable in Pyodide,
 * so this test only verifies that:
 *   1. The marimo WASM page loads (Pyodide initializes)
 *   2. Cells execute without errors
 *   3. Expected markdown output is produced
 *
 * Full widget-rendering tests tracked in:
 * https://github.com/buckaroo-data/buckaroo/issues/513
 */

test('marimo WASM page loads and cells execute', async ({ page }) => {
  await page.goto('/');

  // 1. Wait for Pyodide to initialize and cells to produce output.
  //    The markdown cell renders "Buckaroo in Marimo WASM" once executed.
  await page.waitForFunction(
    () => document.body.textContent?.includes('Buckaroo in Marimo WASM') ?? false,
    { timeout: 90_000 },
  );

  // 2. At least one marimo cell with output rendered
  const cells = await page.locator('.marimo-cell').all();
  expect(cells.length).toBeGreaterThanOrEqual(1);

  const outputAreas = await page.locator('.output-area').all();
  expect(outputAreas.length).toBeGreaterThanOrEqual(1);

  // 3. No error banners visible
  const errors = await page.locator('[role="alert"]').all();
  expect(errors.length).toBe(0);
});
