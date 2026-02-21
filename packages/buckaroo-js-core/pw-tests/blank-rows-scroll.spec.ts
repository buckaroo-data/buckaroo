import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
const DEFAULT_TIMEOUT = 10000;
const NAVIGATION_TIMEOUT = 12000;

async function waitForAgGrid(page: Page, timeout = 5000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'attached', timeout });
}

async function openNotebookAndExecute(page: Page, notebookName: string) {
  await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });
  await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
  await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });

  // Execute the cell
  await page.locator('.jp-Notebook').first().dispatchEvent('click');
  await page.waitForTimeout(200);
  await page.keyboard.press('Shift+Enter');

  // Wait for widget
  const outputArea = page.locator('.jp-OutputArea').first();
  await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
  await page.waitForTimeout(2000);
  await waitForAgGrid(page);
  await page.waitForTimeout(1000);
}

/**
 * Find the main scrollable viewport in the ag-grid (the one with the largest scrollHeight).
 */
async function getMainViewportInfo(page: Page) {
  return page.evaluate(() => {
    const viewports = [
      ...document.querySelectorAll('.ag-body-viewport'),
      ...document.querySelectorAll('.ag-center-cols-viewport'),
    ];
    let mainViewport: Element | null = null;
    let maxScrollHeight = 0;
    for (const vp of viewports) {
      if (vp.scrollHeight > maxScrollHeight) {
        maxScrollHeight = vp.scrollHeight;
        mainViewport = vp;
      }
    }
    if (!mainViewport) return null;
    return {
      scrollHeight: mainViewport.scrollHeight,
      clientHeight: mainViewport.clientHeight,
      scrollTop: mainViewport.scrollTop,
    };
  });
}

/**
 * Scroll the main ag-grid viewport to a specific scrollTop position.
 */
async function scrollTo(page: Page, scrollTop: number) {
  await page.evaluate((targetScrollTop) => {
    const viewports = [
      ...document.querySelectorAll('.ag-body-viewport'),
      ...document.querySelectorAll('.ag-center-cols-viewport'),
    ];
    let mainViewport: Element | null = null;
    let maxScrollHeight = 0;
    for (const vp of viewports) {
      if (vp.scrollHeight > maxScrollHeight) {
        maxScrollHeight = vp.scrollHeight;
        mainViewport = vp;
      }
    }
    if (mainViewport) {
      mainViewport.scrollTop = targetScrollTop;
    }
  }, scrollTop);
}

/**
 * Get all visible rows and check which have data vs blank/None cells.
 * Returns an object with row indices and whether they have real data.
 */
async function getVisibleRowsInfo(page: Page) {
  return page.evaluate(() => {
    const rows = document.querySelectorAll('.ag-row:not(.ag-row-pinned)');
    const rowInfos: Array<{
      rowIndex: number;
      indexCellText: string | null;
      hasData: boolean;
      isBlank: boolean;
      isNone: boolean;
      cellTexts: string[];
    }> = [];

    for (const row of rows) {
      const rowIndex = parseInt(row.getAttribute('row-index') || '-1', 10);
      if (rowIndex < 0) continue;

      const cells = row.querySelectorAll('.ag-cell');
      const cellTexts: string[] = [];
      let indexCellText: string | null = null;

      for (const cell of cells) {
        const colId = cell.getAttribute('col-id');
        const text = (cell.textContent || '').trim();
        cellTexts.push(text);
        if (colId === 'index') {
          indexCellText = text;
        }
      }

      const nonIndexTexts = cellTexts.filter((_, i) => {
        const cell = cells[i];
        return cell?.getAttribute('col-id') !== 'index';
      });

      const isNone = indexCellText === 'None' || indexCellText === 'null';
      const isBlank = nonIndexTexts.every(t => t === '' || t === 'None' || t === 'null');
      const hasData = !isNone && !isBlank && nonIndexTexts.some(t => t !== '');

      rowInfos.push({ rowIndex, indexCellText, hasData, isBlank, isNone, cellTexts });
    }

    return rowInfos.sort((a, b) => a.rowIndex - b.rowIndex);
  });
}


test.describe('Blank Rows Scroll Bug (200-row DataFrame)', () => {

  test('should not show blank/None rows after scrolling to bottom', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    page.on('pageerror', (error) => {
      consoleErrors.push(error.message);
    });

    await openNotebookAndExecute(page, 'test_blank_rows_200.ipynb');

    // Get viewport info
    const vpInfo = await getMainViewportInfo(page);
    console.log('Viewport info:', vpInfo);
    expect(vpInfo).not.toBeNull();

    // Check initial state - rows at top should have data
    const initialRows = await getVisibleRowsInfo(page);
    console.log(`Initial: ${initialRows.length} visible rows`);
    const initialBlank = initialRows.filter(r => r.isBlank || r.isNone);
    console.log(`Initial blank/None rows: ${initialBlank.length}`);

    // All initially visible rows should have data
    for (const row of initialRows) {
      expect(row.hasData).toBe(true);
    }
    console.log('PASS: All initial rows have data');

    // Scroll to the bottom
    const scrollHeight = vpInfo!.scrollHeight;
    console.log(`Scrolling to bottom (scrollTop=${scrollHeight})...`);
    await scrollTo(page, scrollHeight);
    await page.waitForTimeout(2000); // Wait for data to load

    const bottomRows = await getVisibleRowsInfo(page);
    console.log(`After scroll to bottom: ${bottomRows.length} visible rows`);

    const bottomBlank = bottomRows.filter(r => r.isBlank || r.isNone);
    if (bottomBlank.length > 0) {
      console.log(`FAIL: Found ${bottomBlank.length} blank/None rows at bottom:`);
      for (const r of bottomBlank) {
        console.log(`  row ${r.rowIndex}: index="${r.indexCellText}" cells=[${r.cellTexts.join(', ')}]`);
      }
    }

    // This is the assertion that will fail if the bug is present
    expect(bottomBlank.length).toBe(0);

    // Also verify no JS errors related to missing rows
    const rowErrors = consoleErrors.filter(e => e.includes('Missing rows') || e.includes('getRows'));
    if (rowErrors.length > 0) {
      console.log('JS errors related to rows:', rowErrors);
    }
  });

  test('should not show blank rows after fast scroll to middle', async ({ page }) => {
    await openNotebookAndExecute(page, 'test_blank_rows_200.ipynb');

    const vpInfo = await getMainViewportInfo(page);
    expect(vpInfo).not.toBeNull();

    // Scroll quickly to middle
    const middleScroll = Math.floor(vpInfo!.scrollHeight / 2);
    console.log(`Fast scrolling to middle (scrollTop=${middleScroll})...`);
    await scrollTo(page, middleScroll);
    await page.waitForTimeout(2000);

    const midRows = await getVisibleRowsInfo(page);
    console.log(`After scroll to middle: ${midRows.length} visible rows`);

    const midBlank = midRows.filter(r => r.isBlank || r.isNone);
    if (midBlank.length > 0) {
      console.log(`FAIL: Found ${midBlank.length} blank/None rows at middle:`);
      for (const r of midBlank) {
        console.log(`  row ${r.rowIndex}: index="${r.indexCellText}" cells=[${r.cellTexts.join(', ')}]`);
      }
    }

    expect(midBlank.length).toBe(0);
  });

  test('should not show blank rows after incremental scrolling', async ({ page }) => {
    await openNotebookAndExecute(page, 'test_blank_rows_200.ipynb');

    const vpInfo = await getMainViewportInfo(page);
    expect(vpInfo).not.toBeNull();

    // Scroll incrementally (simulates real user scrolling)
    const steps = 10;
    const stepSize = Math.floor(vpInfo!.scrollHeight / steps);

    for (let i = 1; i <= steps; i++) {
      const target = stepSize * i;
      console.log(`Incremental scroll step ${i}/${steps}: scrollTop=${target}`);
      await scrollTo(page, target);
      // Short delay between steps to simulate real scrolling speed
      await page.waitForTimeout(300);
    }

    // Wait for all data to settle
    await page.waitForTimeout(2000);

    const finalRows = await getVisibleRowsInfo(page);
    console.log(`After incremental scroll: ${finalRows.length} visible rows`);

    const finalBlank = finalRows.filter(r => r.isBlank || r.isNone);
    if (finalBlank.length > 0) {
      console.log(`FAIL: Found ${finalBlank.length} blank/None rows after incremental scroll:`);
      for (const r of finalBlank) {
        console.log(`  row ${r.rowIndex}: index="${r.indexCellText}" cells=[${r.cellTexts.join(', ')}]`);
      }
    }

    expect(finalBlank.length).toBe(0);
  });

  test('should not show blank rows after rapid back-and-forth scrolling', async ({ page }) => {
    await openNotebookAndExecute(page, 'test_blank_rows_200.ipynb');

    const vpInfo = await getMainViewportInfo(page);
    expect(vpInfo).not.toBeNull();
    const maxScroll = vpInfo!.scrollHeight;

    // Rapid back and forth - most likely to trigger the race condition
    const positions = [
      maxScroll * 0.8,
      maxScroll * 0.2,
      maxScroll * 0.9,
      maxScroll * 0.1,
      maxScroll,         // bottom
      0,                 // top
      maxScroll * 0.5,   // middle
      maxScroll,         // bottom again
    ];

    for (let i = 0; i < positions.length; i++) {
      const target = Math.floor(positions[i]);
      console.log(`Rapid scroll ${i + 1}/${positions.length}: scrollTop=${target}`);
      await scrollTo(page, target);
      await page.waitForTimeout(200); // Very short delay to stress the cache
    }

    // Wait for data to settle
    await page.waitForTimeout(3000);

    const finalRows = await getVisibleRowsInfo(page);
    console.log(`After rapid scroll: ${finalRows.length} visible rows`);

    const finalBlank = finalRows.filter(r => r.isBlank || r.isNone);
    if (finalBlank.length > 0) {
      console.log(`FAIL: Found ${finalBlank.length} blank/None rows after rapid scroll:`);
      for (const r of finalBlank.slice(0, 5)) {
        console.log(`  row ${r.rowIndex}: index="${r.indexCellText}" cells=[${r.cellTexts.join(', ')}]`);
      }
      if (finalBlank.length > 5) {
        console.log(`  ... and ${finalBlank.length - 5} more`);
      }
    }

    expect(finalBlank.length).toBe(0);
  });

  test('transcript recording captures the blank rows scenario', async ({ page }) => {
    // Same as the first test but with transcript recording enabled
    // This requires a notebook that enables record_transcript=True
    const consoleMessages: string[] = [];
    page.on('console', (msg) => {
      const text = msg.text();
      if (text.includes('[SmartRowCache') || text.includes('[KeyAware') ||
          text.includes('[getRows]') || text.includes('successWrapper') ||
          text.includes('Missing rows')) {
        consoleMessages.push(`[${msg.type()}] ${text}`);
      }
    });

    await openNotebookAndExecute(page, 'test_blank_rows_200.ipynb');

    // Scroll to bottom
    const vpInfo = await getMainViewportInfo(page);
    await scrollTo(page, vpInfo!.scrollHeight);
    await page.waitForTimeout(2000);

    // Log all SmartRowCache-related console messages
    console.log(`\nSmartRowCache/getRows console messages (${consoleMessages.length}):`);
    for (const msg of consoleMessages) {
      console.log(`  ${msg}`);
    }

    // Check for rows
    const rows = await getVisibleRowsInfo(page);
    const blankRows = rows.filter(r => r.isBlank || r.isNone);

    if (blankRows.length > 0) {
      console.log(`\nBug reproduced! ${blankRows.length} blank rows found.`);
      console.log('These SmartRowCache messages show the cache state leading to the bug.');
    } else {
      console.log('\nNo blank rows found in this run (bug may be timing-dependent).');
    }

    // This test is informational - log results but don't fail
    // The actual assertions are in the other tests
  });
});
