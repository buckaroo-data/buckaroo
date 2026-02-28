import { test, expect } from '@playwright/test';
import { waitForCells } from './ag-pw-utils';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const screenshotsDir = path.join(__dirname, '..', 'screenshots');

const STORYBOOK_BASE = 'http://localhost:6006/iframe.html?viewMode=story&id=';

// Ensure screenshots directory exists
test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test('default story renders without theme overrides', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--default-no-theme`);
  await waitForCells(page);

  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  // Light mode default: white
  expect(bg).toBe('rgb(255, 255, 255)');
});

test('custom accent color applied to selected column', async ({ page }) => {
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--custom-accent`);
  await waitForCells(page);

  // Click column header to select it
  await page.locator('.ag-header-cell').nth(1).click();

  // Assert the accent color is applied to cells
  const cell = page.locator('.ag-cell[col-id="a"]').first();
  await expect(cell).toHaveCSS('background-color', 'rgb(255, 102, 0)'); // #ff6600
});

test('forced dark scheme ignores OS light preference', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' }); // OS says light
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--forced-dark`);
  await waitForCells(page);

  // Grid should use dark background despite OS light mode
  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(26, 26, 46)'); // #1a1a2e
});

test('forced light scheme ignores OS dark preference', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' }); // OS says dark
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--forced-light`);
  await waitForCells(page);

  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(250, 250, 250)'); // #fafafa
});

test('full custom theme applies all properties', async ({ page }) => {
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--full-custom`);
  await waitForCells(page);

  // Background
  const gridBody = page.locator('.ag-body-viewport').first();
  const bg = await gridBody.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(bg).toBe('rgb(26, 26, 46)'); // #1a1a2e

  // Screenshot for visual debugging
  await page.screenshot({
    path: path.join(screenshotsDir, 'theme-full-custom.png'),
    fullPage: true,
  });
});

test('screenshot: default vs custom comparison', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--default-no-theme`);
  await waitForCells(page);
  await page.screenshot({
    path: path.join(screenshotsDir, 'theme-default-light.png'),
    fullPage: true,
  });

  await page.goto(`${STORYBOOK_BASE}buckaroo-theme-themecustomization--forced-dark`);
  await waitForCells(page);
  await page.screenshot({
    path: path.join(screenshotsDir, 'theme-forced-dark.png'),
    fullPage: true,
  });
});
