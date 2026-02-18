import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';

const STORY_URL =
  'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-smalldfscroll--primary&globals=&args=';

/**
 * Wait for AG-Grid to render its first data cells.
 */
async function waitForAgGrid(page: Page, timeout = 10000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });
}

/**
 * Get the main scrollable viewport element info.
 */
async function getViewportInfo(page: Page) {
  return page.evaluate(() => {
    const vp = document.querySelector('.ag-body-viewport');
    if (!vp) return null;
    return {
      scrollHeight: vp.scrollHeight,
      clientHeight: vp.clientHeight,
      scrollTop: vp.scrollTop,
    };
  });
}

/**
 * Scroll the AG-Grid body viewport to a specific scrollTop.
 */
async function scrollTo(page: Page, scrollTop: number) {
  await page.evaluate((target) => {
    const vp = document.querySelector('.ag-body-viewport');
    if (vp) vp.scrollTop = target;
  }, scrollTop);
}

/**
 * Collect visible row data. Returns info about each rendered row including
 * whether it has real data or appears blank/undefined.
 */
async function getVisibleRowsInfo(page: Page) {
  return page.evaluate(() => {
    const rows = document.querySelectorAll('.ag-row:not(.ag-row-pinned)');
    const infos: Array<{
      rowIndex: number;
      cellTexts: string[];
      isBlank: boolean;
    }> = [];

    for (const row of rows) {
      const rowIndex = parseInt(row.getAttribute('row-index') || '-1', 10);
      if (rowIndex < 0) continue;

      const cells = row.querySelectorAll('.ag-cell');
      const cellTexts: string[] = [];
      for (const cell of cells) {
        cellTexts.push((cell.textContent || '').trim());
      }

      // A row is blank if all non-index cells are empty, 'None', 'null', or 'undefined'
      const nonIndexTexts = cellTexts.slice(1); // skip first cell (index)
      const isBlank = nonIndexTexts.length === 0 ||
        nonIndexTexts.every(t => t === '' || t === 'None' || t === 'null' || t === 'undefined');

      infos.push({ rowIndex, cellTexts, isBlank });
    }
    return infos.sort((a, b) => a.rowIndex - b.rowIndex);
  });
}

test.describe('Small DataFrame scroll blank rows (Storybook)', () => {

  test('no blank rows after scrolling to bottom of 200-row DataFrame', async ({ page }) => {
    // Collect console errors for debugging
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    await page.goto(STORY_URL);
    await waitForAgGrid(page);
    // Let initial data settle
    await page.waitForTimeout(1500);

    // Verify initial rows have data
    const initialRows = await getVisibleRowsInfo(page);
    expect(initialRows.length).toBeGreaterThan(0);
    const initialBlank = initialRows.filter(r => r.isBlank);
    expect(initialBlank.length).toBe(0);

    // Scroll to bottom
    const vpInfo = await getViewportInfo(page);
    expect(vpInfo).not.toBeNull();
    await scrollTo(page, vpInfo!.scrollHeight);
    await page.waitForTimeout(2000);

    // Check for blank rows at bottom
    const bottomRows = await getVisibleRowsInfo(page);
    const bottomBlank = bottomRows.filter(r => r.isBlank);

    if (bottomBlank.length > 0) {
      console.log(`Found ${bottomBlank.length} blank rows at bottom:`);
      for (const r of bottomBlank.slice(0, 5)) {
        console.log(`  row ${r.rowIndex}: [${r.cellTexts.join(', ')}]`);
      }
    }
    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors.slice(0, 5));
    }

    expect(bottomBlank.length).toBe(0);
  });

  test('no blank rows after scrolling to middle of 200-row DataFrame', async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForAgGrid(page);
    await page.waitForTimeout(1500);

    const vpInfo = await getViewportInfo(page);
    expect(vpInfo).not.toBeNull();

    // Scroll to middle
    const mid = Math.floor(vpInfo!.scrollHeight / 2);
    await scrollTo(page, mid);
    await page.waitForTimeout(2000);

    const midRows = await getVisibleRowsInfo(page);
    const midBlank = midRows.filter(r => r.isBlank);

    if (midBlank.length > 0) {
      console.log(`Found ${midBlank.length} blank rows at middle:`);
      for (const r of midBlank.slice(0, 5)) {
        console.log(`  row ${r.rowIndex}: [${r.cellTexts.join(', ')}]`);
      }
    }

    expect(midBlank.length).toBe(0);
  });

  test('no blank rows after rapid back-and-forth scrolling', async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForAgGrid(page);
    await page.waitForTimeout(1500);

    const vpInfo = await getViewportInfo(page);
    expect(vpInfo).not.toBeNull();
    const maxScroll = vpInfo!.scrollHeight;

    // Rapid back-and-forth scrolling to stress the cache
    const positions = [
      maxScroll * 0.7,
      maxScroll * 0.2,
      maxScroll * 0.9,
      maxScroll * 0.1,
      maxScroll,
      0,
      maxScroll * 0.5,
      maxScroll,
    ];

    for (const pos of positions) {
      await scrollTo(page, Math.floor(pos));
      await page.waitForTimeout(200);
    }

    // Let everything settle
    await page.waitForTimeout(3000);

    const finalRows = await getVisibleRowsInfo(page);
    const finalBlank = finalRows.filter(r => r.isBlank);

    if (finalBlank.length > 0) {
      console.log(`Found ${finalBlank.length} blank rows after rapid scroll:`);
      for (const r of finalBlank.slice(0, 5)) {
        console.log(`  row ${r.rowIndex}: [${r.cellTexts.join(', ')}]`);
      }
    }

    expect(finalBlank.length).toBe(0);
  });
});
