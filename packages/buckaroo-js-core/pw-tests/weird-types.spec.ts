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
    // Row 0: categorical=red, timedelta=1d 2h 3m 4s, period=2021-01, interval=(0, 1], int=10
    const row0 = await getRowContents(page, 0);
    expect(row0).toContain('red');
    expect(row0).toContain('2021-01');
    expect(row0).toContain('(0, 1]');
    expect(row0).toContain('10 ');  // float formatter with 0 decimals adds trailing space
  });

  test('duration column formats ISO 8601 as human-readable', async ({ page }) => {
    // "P1DT2H3M4S" → "1d 2h 3m 4s"
    const cell0 = getCellLocator(page, 'b', 0);
    await expect(cell0).toHaveText('1d 2h 3m 4s');

    // "P0DT0H0M1S" → "1s"
    const cell1 = getCellLocator(page, 'b', 1);
    await expect(cell1).toHaveText('1s');

    // "P365DT0H0M0S" → "365d"
    const cell2 = getCellLocator(page, 'b', 2);
    await expect(cell2).toHaveText('365d');

    // "P0DT0H0M0.001S" → "1ms"
    const cell3 = getCellLocator(page, 'b', 3);
    await expect(cell3).toHaveText('1ms');

    // "P0DT0H0M0.0001S" → "100µs"
    const cell4 = getCellLocator(page, 'b', 4);
    await expect(cell4).toHaveText('100µs');
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
});

test.describe('Polars weird types rendering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(
      'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-weirdtypes--polars-weird-types&globals=&args='
    );
    await waitForCells(page);
  });

  test('duration column formats various magnitudes', async ({ page }) => {
    // "P0DT0H0M0.1S" → "100ms"
    await expect(getCellLocator(page, 'a', 0)).toHaveText('100ms');

    // "P0DT1H2M3S" → "1h 2m 3s"
    await expect(getCellLocator(page, 'a', 1)).toHaveText('1h 2m 3s');

    // "P1DT0H0M0S" → "1d"
    await expect(getCellLocator(page, 'a', 2)).toHaveText('1d');

    // "P0DT0H0M0.0000005S" → "1µs" (rounds to nearest)
    await expect(getCellLocator(page, 'a', 3)).toHaveText('1µs');

    // "P0DT0H1M0S" → "1m"
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

  test('binary column shows string repr', async ({ page }) => {
    await expect(getCellLocator(page, 'e', 0)).toHaveText('hello');
    await expect(getCellLocator(page, 'e', 1)).toHaveText('world');
  });
});
