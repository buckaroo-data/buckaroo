import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SCHEMES = ['light', 'dark'] as const;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

for (const scheme of SCHEMES) {
  test(`marimo full page [${scheme}]`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto('/');

    // Wait for buckaroo widgets and AG-Grid cells to render
    await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 30_000 });
    await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    // Wait for the second widget (BuckarooInfiniteWidget) too
    const widgets = page.locator('.buckaroo_anywidget');
    await widgets.nth(1).waitFor({ state: 'visible', timeout: 30_000 });
    await widgets.nth(1).locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    await page.waitForTimeout(1000);

    await page.screenshot({
      path: path.join(screenshotsDir, `marimo-full-page--${scheme}.png`),
      fullPage: true,
    });
  });

  test(`marimo lowcode widget [${scheme}]`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto('/');

    // Wait for the first BuckarooWidget (which has the lowcode/operations UI)
    await page.locator('.buckaroo_anywidget').first().waitFor({ state: 'visible', timeout: 30_000 });
    await page.locator('.buckaroo_anywidget').first().locator('.ag-cell').first()
      .waitFor({ state: 'visible', timeout: 30_000 });

    // Click on Columns tab to open the lowcode UI if available
    const firstWidget = page.locator('.buckaroo_anywidget').first();
    const columnsTab = firstWidget.locator('text=Columns');
    if (await columnsTab.isVisible()) {
      await columnsTab.click();
      await page.waitForTimeout(500);
    }

    await page.waitForTimeout(500);

    // Screenshot just the first widget area
    await firstWidget.screenshot({
      path: path.join(screenshotsDir, `marimo-lowcode-widget--${scheme}.png`),
    });
  });
}
