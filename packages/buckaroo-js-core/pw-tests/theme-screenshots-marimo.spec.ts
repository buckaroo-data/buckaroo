import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SCHEMES = ['light', 'dark'] as const;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

// Use a tall viewport so the full-page screenshot captures surrounding
// marimo cells (markdown headings, descriptions) above and below widgets.
test.use({ viewport: { width: 1280, height: 900 } });

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

    // fullPage: true captures the entire scrollable area — markdown cells
    // above and below the widgets will be visible in the screenshot.
    await page.screenshot({
      path: path.join(screenshotsDir, `marimo-full-page--${scheme}.png`),
      fullPage: true,
    });
  });

  test(`marimo small widget in context [${scheme}]`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto('/');

    // Wait for the first BuckarooWidget to render
    const firstWidget = page.locator('.buckaroo_anywidget').first();
    await firstWidget.waitFor({ state: 'visible', timeout: 30_000 });
    await firstWidget.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });
    await page.waitForTimeout(500);

    // Scroll so the first widget is roughly centred, showing markdown
    // cells above and the second widget heading below.
    await firstWidget.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);

    // Viewport screenshot (not fullPage) gives a natural "window" view
    // with surrounding notebook cells visible.
    await page.screenshot({
      path: path.join(screenshotsDir, `marimo-small-widget-context--${scheme}.png`),
    });
  });

  test(`marimo lowcode widget [${scheme}]`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto('/');

    // Wait for the first BuckarooWidget (which has the lowcode/operations UI)
    const firstWidget = page.locator('.buckaroo_anywidget').first();
    await firstWidget.waitFor({ state: 'visible', timeout: 30_000 });
    await firstWidget.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 30_000 });

    // Click on Columns tab to open the lowcode UI if available
    const columnsTab = firstWidget.locator('text=Columns');
    if (await columnsTab.isVisible()) {
      await columnsTab.click();
      await page.waitForTimeout(500);
    }

    await page.waitForTimeout(500);

    // Scroll so surrounding cells are visible
    await firstWidget.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);

    // Viewport screenshot shows the lowcode UI with notebook context
    await page.screenshot({
      path: path.join(screenshotsDir, `marimo-lowcode-widget--${scheme}.png`),
    });
  });
}
