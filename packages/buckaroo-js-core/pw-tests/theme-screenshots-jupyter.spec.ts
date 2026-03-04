import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';

const SCHEMES = ['light', 'dark'] as const;

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

// Tall viewport to show code cells above and below the widget output
test.use({ viewport: { width: 1280, height: 900 } });

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

/**
 * Open a notebook in JupyterLab and run all cells.
 * Returns when the first ag-grid widget is visible.
 */
async function openAndRunNotebook(page: import('@playwright/test').Page, notebookName: string) {
  await page.goto(
    `${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`,
    { timeout: 15_000 },
  );
  await page.waitForLoadState('domcontentloaded', { timeout: 10_000 });
  await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: 10_000 });

  // Run all cells: Ctrl+Shift+Enter or the "Run All" menu
  // Focus notebook first
  await page.locator('.jp-Notebook').first().dispatchEvent('click');
  await page.waitForTimeout(300);

  // Use the menu: Run > Run All Cells
  await page.locator('text=Run').first().click();
  await page.waitForTimeout(300);
  const runAll = page.locator('text=Run All Cells');
  if (await runAll.isVisible()) {
    await runAll.click();
  } else {
    // Fallback: Shift+Enter through cells
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Shift+Enter');
      await page.waitForTimeout(500);
    }
  }

  // Wait for ag-grid to render
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout: 15_000 });
  await page.waitForTimeout(1000);
}

const notebookName = process.env.TEST_NOTEBOOK || 'test_buckaroo_widget.ipynb';

for (const scheme of SCHEMES) {
  test(`jupyter notebook in context [${scheme}]`, async ({ page }) => {
    // JupyterLab has its own theme system; emulateMedia sets the browser
    // preference which JupyterLab may or may not follow.  We also try to
    // toggle JupyterLab's built-in theme via the settings menu.
    await page.emulateMedia({ colorScheme: scheme });

    await openAndRunNotebook(page, notebookName);

    // Try to set JupyterLab theme via Settings menu
    if (scheme === 'dark') {
      const settingsMenu = page.locator('text=Settings');
      if (await settingsMenu.isVisible()) {
        await settingsMenu.click();
        await page.waitForTimeout(200);
        const darkTheme = page.locator('text=JupyterLab Dark');
        if (await darkTheme.isVisible()) {
          await darkTheme.click();
          await page.waitForTimeout(1000);
        } else {
          // Close menu if dark theme not found
          await page.keyboard.press('Escape');
        }
      }
    }

    // Scroll to the widget output so code cells above are visible
    const widgetOutput = page.locator('.ag-root-wrapper').first();
    await widgetOutput.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);

    // Viewport screenshot captures surrounding code cells
    await page.screenshot({
      path: path.join(screenshotsDir, `jupyter-notebook-context--${scheme}.png`),
    });
  });

  test(`jupyter full notebook [${scheme}]`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });

    await openAndRunNotebook(page, notebookName);

    if (scheme === 'dark') {
      const settingsMenu = page.locator('text=Settings');
      if (await settingsMenu.isVisible()) {
        await settingsMenu.click();
        await page.waitForTimeout(200);
        const darkTheme = page.locator('text=JupyterLab Dark');
        if (await darkTheme.isVisible()) {
          await darkTheme.click();
          await page.waitForTimeout(1000);
        } else {
          await page.keyboard.press('Escape');
        }
      }
    }

    // Full-page screenshot shows the entire notebook
    await page.screenshot({
      path: path.join(screenshotsDir, `jupyter-full-notebook--${scheme}.png`),
      fullPage: true,
    });
  });
}
