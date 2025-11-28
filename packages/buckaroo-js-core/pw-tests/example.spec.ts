import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';
import {waitForCells, getRowContents, getRowCount, getCellLocator } from './ag-pw-utils';
const waitForLog = async (page, expectedLog) => {
  return new Promise<void>((resolve) => {
    const handler = (msg) => {
      if (msg.text().includes(expectedLog)) {
        page.off('console', handler);
        resolve();
      }
    };
    page.on('console', handler);
  });
};

const logCounts = {}
const setupCounter = (page, expectedLog) => {
    logCounts[expectedLog] = 0;
    const handler = (msg) => {
      if (msg.text().includes(expectedLog)) {
	  logCounts[expectedLog] +=1
      }
    };
    page.on('console', handler);
};

 async function waitForGridReady(page: Page) {
    await page.locator('ag-overlay-loading-center').first().waitFor({ state: 'hidden' });
    // Normal cells
    const cellLocator =page.locator('.ag-cell');
    // Grouped cells
    const cellWrapperLocator = page.locator('.ag-cell-wrapper');
    // Full width only cells
    const fullWidthRow = page.locator('.ag-full-width-row');
    // No rows to show
    const noRowsToShowLocator = page.locator('.ag-overlay-no-rows-center');
    await cellLocator.or(cellWrapperLocator).or(noRowsToShowLocator).or(fullWidthRow).first().waitFor({ state: 'visible' });
}

test('DFVIewerInfiniteShadow renders in basic case', async ({ page }) => {
    await page.goto('http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-dfviewerinfiniteshadow--primary&globals=&args=')
    const RenderLogMsg= "[DFViewerInfinite] Total render time:"
    setupCounter(page, RenderLogMsg)
    await waitForGridReady(page);
    const rc = await getRowContents(page, 0);
    expect(rc).toStrictEqual(["", "20.00      ", "  20", "foo", "foo", ]);
    expect(logCounts[RenderLogMsg]).toBe(1);

    await page.getByRole('button', { name: 'Toggle Config' }).click();
    //await page.waitForTimeout(1000);
    expect(logCounts[RenderLogMsg]).toBe(1);
    const rc2 = await getRowContents(page, 0);
    expect(rc2).toStrictEqual(["20.00      ", "  20", "foo", ]);
});

test('DFVIewerInfinite Raw works', async ({ page }) => {
    await page.goto('http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-dfviewerinfiniteraw--primary&globals=&args=')
    const RenderLogMsg= "[DFViewerInfinite] Total render time:"
    setupCounter(page, RenderLogMsg)

    await waitForGridReady(page);
    const rc = await getRowContents(page, 0);
    expect(rc).toStrictEqual(["", "20.00", "20", "foo", ]);
    expect(logCounts[RenderLogMsg]).toBe(1);
});

test('test color_map works', async ({ page }) => {
    /*
      color maps are complex, depending on summary_stats histogram_bins.   and compelx rendering setups.

      

      */
    await page.goto('http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-dfviewerinfiniteshadow--color-map-example&globals=&args=')
    await waitForGridReady(page);
    const el200 = await page.getByText('200');
    const cell = await getCellLocator(page, 'a', 2);
    const innerTexts = await cell.allInnerTexts();
    expect(innerTexts).toStrictEqual(["300"]);
    
  const color = await cell.evaluate((element) =>
    window.getComputedStyle(element).getPropertyValue("background-color")
  );
  expect(color).toBe("rgb(83, 143, 239)")
})
