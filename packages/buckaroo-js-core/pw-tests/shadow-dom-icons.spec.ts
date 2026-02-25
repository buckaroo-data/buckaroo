import { test, expect, Page } from '@playwright/test';

const SHADOW_STORY_URL =
  'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-dfviewerinfiniteshadow--primary&globals=&args=';

async function waitForGridReady(page: Page) {
  await page.locator('ag-overlay-loading-center').first().waitFor({ state: 'hidden' });
  await page
    .locator('.ag-cell')
    .or(page.locator('.ag-cell-wrapper'))
    .or(page.locator('.ag-overlay-no-rows-center'))
    .or(page.locator('.ag-full-width-row'))
    .first()
    .waitFor({ state: 'visible' });
}

test('grid content is mounted under a ShadowRoot in storybook', async ({ page }) => {
  await page.goto(SHADOW_STORY_URL);
  await waitForGridReady(page);

  const shadowInfo = await page.evaluate(() => {
    const host = document.querySelector('#storybook-root')?.firstElementChild as HTMLElement | null;
    const shadowRoot = host?.shadowRoot;
    return {
      hasHost: !!host,
      hasShadowRoot: !!shadowRoot,
      rootWrapperCount: shadowRoot?.querySelectorAll('.ag-root-wrapper').length || 0,
      styleTagCount: shadowRoot?.querySelectorAll('style').length || 0,
    };
  });

  expect(shadowInfo.hasHost).toBe(true);
  expect(shadowInfo.hasShadowRoot).toBe(true);
  expect(shadowInfo.rootWrapperCount).toBeGreaterThan(0);
  expect(shadowInfo.styleTagCount).toBeGreaterThan(0);
});

test('sorted header label remains clean (no private-use glyphs)', async ({ page }) => {
  await page.goto(SHADOW_STORY_URL);
  await waitForGridReady(page);

  const header = page.locator('.ag-header-cell[col-id="a"]').first();
  await header.click();

  const headerText = (await header.locator('.ag-header-cell-text').innerText()).trim();
  const rawHeaderText = await header.innerText();

  expect(headerText).toBe('a');
  expect(/[\uE000-\uF8FF]/.test(rawHeaderText)).toBe(false);
  await expect(page.locator('.ag-header-cell-sorted-asc .ag-icon-asc').first()).toBeVisible();
});
