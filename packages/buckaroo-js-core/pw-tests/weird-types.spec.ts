import { test, expect } from '@playwright/test';
import { waitForCells, getRowContents, getCellLocator } from './ag-pw-utils';

test.describe('Pandas weird types rendering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(
      'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-weirdtypes--pandas-weird-types&globals=&args='
    );
    await waitForCells(page);
  });

  test('all 5 rows render with correct values', async ({ page }) => {
    const row0 = await getRowContents(page, 0);
    expect(row0).toContain('red');
    expect(row0).toContain('2021-01');
    expect(row0).toContain('(0, 1]');
    expect(row0).toContain('10 ');  // float formatter with 0 decimals adds trailing space
  });

  test('duration column formats ISO 8601 as human-readable', async ({ page }) => {
    await expect(getCellLocator(page, 'b', 0)).toHaveText('1d 2h 3m 4s');
    await expect(getCellLocator(page, 'b', 1)).toHaveText('1s');
    await expect(getCellLocator(page, 'b', 2)).toHaveText('365d');
    await expect(getCellLocator(page, 'b', 3)).toHaveText('1ms');
    await expect(getCellLocator(page, 'b', 4)).toHaveText('100µs');
  });

  test('categorical column shows string values', async ({ page }) => {
    await expect(getCellLocator(page, 'a', 0)).toHaveText('red');
    await expect(getCellLocator(page, 'a', 1)).toHaveText('green');
    await expect(getCellLocator(page, 'a', 2)).toHaveText('blue');
  });

  test('period column shows period strings', async ({ page }) => {
    await expect(getCellLocator(page, 'c', 0)).toHaveText('2021-01');
    await expect(getCellLocator(page, 'c', 4)).toHaveText('2021-05');
  });

  test('interval column shows interval strings', async ({ page }) => {
    await expect(getCellLocator(page, 'd', 0)).toHaveText('(0, 1]');
    await expect(getCellLocator(page, 'd', 2)).toHaveText('(2, 3]');
  });

  test('integer column formats correctly', async ({ page }) => {
    await expect(getCellLocator(page, 'e', 0)).toHaveText('10');
    await expect(getCellLocator(page, 'e', 4)).toHaveText('50');
  });

  test('histograms render in pinned rows', async ({ page }) => {
    // Pinned rows are rendered with ag-floating-top
    const pinnedArea = page.locator('.ag-floating-top');
    await expect(pinnedArea).toBeVisible();

    // Should have histogram-component divs (recharts BarChart)
    const histogramCells = pinnedArea.locator('.histogram-component');
    const count = await histogramCells.count();
    expect(count).toBeGreaterThanOrEqual(3);  // at least categorical, duration, int columns
  });

  test('dtype pinned row shows column types', async ({ page }) => {
    const pinnedArea = page.locator('.ag-floating-top');
    // The dtype row should contain type strings
    await expect(pinnedArea).toContainText('category');
    await expect(pinnedArea).toContainText('int64');
  });
});

test.describe('Polars weird types rendering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(
      'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-weirdtypes--polars-weird-types&globals=&args='
    );
    await waitForCells(page);
  });

  test('duration column formats various magnitudes', async ({ page }) => {
    await expect(getCellLocator(page, 'a', 0)).toHaveText('100ms');
    await expect(getCellLocator(page, 'a', 1)).toHaveText('1h 2m 3s');
    await expect(getCellLocator(page, 'a', 2)).toHaveText('1d');
    await expect(getCellLocator(page, 'a', 3)).toHaveText('1µs');
    await expect(getCellLocator(page, 'a', 4)).toHaveText('1m');
  });

  test('time column shows time strings', async ({ page }) => {
    await expect(getCellLocator(page, 'b', 0)).toHaveText('14:30:00');
    await expect(getCellLocator(page, 'b', 1)).toHaveText('09:15:30');
  });

  test('categorical column shows values', async ({ page }) => {
    await expect(getCellLocator(page, 'c', 0)).toHaveText('red');
    await expect(getCellLocator(page, 'c', 2)).toHaveText('blue');
  });

  test('decimal column formats as float', async ({ page }) => {
    await expect(getCellLocator(page, 'd', 0)).toHaveText('100.500');
    await expect(getCellLocator(page, 'd', 2)).toHaveText('0.010');
  });

  test('binary column shows hex repr', async ({ page }) => {
    await expect(getCellLocator(page, 'e', 0)).toHaveText('68656c6c6f');
    await expect(getCellLocator(page, 'e', 1)).toHaveText('776f726c64');
  });

  test('histograms render in pinned rows', async ({ page }) => {
    const pinnedArea = page.locator('.ag-floating-top');
    await expect(pinnedArea).toBeVisible();

    const histogramCells = pinnedArea.locator('.histogram-component');
    const count = await histogramCells.count();
    expect(count).toBeGreaterThanOrEqual(4);  // duration, time, categorical, int columns
  });

  test('dtype pinned row shows polars type names', async ({ page }) => {
    const pinnedArea = page.locator('.ag-floating-top');
    await expect(pinnedArea).toContainText('Categorical');
    await expect(pinnedArea).toContainText('Int64');
  });
});
