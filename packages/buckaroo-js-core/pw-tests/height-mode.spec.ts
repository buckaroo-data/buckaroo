import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const STORYBOOK_BASE = 'http://localhost:6006/iframe.html?viewMode=story&id=';

const screenshotsDir = path.resolve(__dirname, '..', 'screenshots', 'height-mode');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

/**
 * Wait for AG-Grid to render its first data cells.
 */
async function waitForAgGrid(page: any, timeout = 15000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });
}

/**
 * querySelector that pierces open shadow DOMs.
 * Stories use ShadowDomWrapper, so elements live inside a shadow root
 * that native document.querySelector cannot reach.
 */
function deepQuerySelector(selector: string, root: ParentNode = document): Element | null {
  const el = root.querySelector(selector);
  if (el) return el;
  // Walk all elements looking for shadow roots
  const allEls = root.querySelectorAll('*');
  for (const host of allEls) {
    if (host.shadowRoot) {
      const found = deepQuerySelector(selector, host.shadowRoot);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Get the bounding box height of the .theme-hanger element (the AG Grid container).
 * Pierces shadow DOM since stories use ShadowDomWrapper.
 */
async function getThemeHangerHeight(page: any): Promise<number> {
  return page.evaluate(() => {
    const dqs = (sel: string, root: ParentNode = document): Element | null => {
      const el = root.querySelector(sel);
      if (el) return el;
      for (const host of root.querySelectorAll('*')) {
        if (host.shadowRoot) { const f = dqs(sel, host.shadowRoot); if (f) return f; }
      }
      return null;
    };
    const el = dqs('.theme-hanger');
    if (!el) return 0;
    return el.getBoundingClientRect().height;
  });
}

/**
 * Get the bounding box of the .df-viewer element.
 * Pierces shadow DOM since stories use ShadowDomWrapper.
 */
async function getDfViewerBox(page: any): Promise<{ height: number; width: number } | null> {
  return page.evaluate(() => {
    const dqs = (sel: string, root: ParentNode = document): Element | null => {
      const el = root.querySelector(sel);
      if (el) return el;
      for (const host of root.querySelectorAll('*')) {
        if (host.shadowRoot) { const f = dqs(sel, host.shadowRoot); if (f) return f; }
      }
      return null;
    };
    const el = dqs('.df-viewer');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { height: r.height, width: r.width };
  });
}

// --- Height Mode stories ---

const HEIGHT_MODE_STORIES = {
  fractionMode: 'buckaroo-dfviewer-heightmode--fraction-mode',
  fractionModeShort: 'buckaroo-dfviewer-heightmode--fraction-mode-short',
  fixedMode: 'buckaroo-dfviewer-heightmode--fixed-mode',
  fixedModeShort: 'buckaroo-dfviewer-heightmode--fixed-mode-short',
  fillMode: 'buckaroo-dfviewer-heightmode--fill-mode',
  fillModeShort: 'buckaroo-dfviewer-heightmode--fill-mode-short',
  noHeightMode: 'buckaroo-dfviewer-heightmode--no-height-mode',
  noHeightModeShort: 'buckaroo-dfviewer-heightmode--no-height-mode-short',
};

test.describe('HeightMode Storybook integration tests', () => {

  test('fill mode: grid fills container', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fillMode}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    // Container is 600px. In fill mode, the grid should use most of it.
    // Allow tolerance for status bar, headers, borders.
    expect(height).toBeGreaterThan(400);

    // Verify the CSS flex chain is unbroken (pierce shadow DOM)
    const flexDisplay = await page.evaluate(() => {
      const dqs = (sel: string, root: ParentNode = document): Element | null => {
        const el = root.querySelector(sel);
        if (el) return el;
        for (const host of root.querySelectorAll('*')) {
          if (host.shadowRoot) { const f = dqs(sel, host.shadowRoot); if (f) return f; }
        }
        return null;
      };
      const el = dqs('.df-viewer.fill-mode');
      return el ? getComputedStyle(el).display : 'not-found';
    });
    expect(flexDisplay).toBe('flex');

    await page.screenshot({
      path: path.join(screenshotsDir, 'fill-mode-300rows.png'),
      fullPage: true,
    });
  });

  test('fill mode short: grid does NOT stretch to fill', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fillModeShort}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    // 3 rows at ~21px each + header ≈ 100px. Should be well under 200.
    expect(height).toBeLessThan(200);

    await page.screenshot({
      path: path.join(screenshotsDir, 'fill-mode-short.png'),
      fullPage: true,
    });
  });

  test('fraction mode: grid uses approximately half of container', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fractionMode}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    // window.innerHeight / 2 ≈ half the viewport. The story container is 600px
    // but fraction mode uses window.innerHeight, not the container.
    // Just verify it's a reasonable size (not 0, not the full viewport).
    expect(height).toBeGreaterThan(100);
    expect(height).toBeLessThan(800);

    await page.screenshot({
      path: path.join(screenshotsDir, 'fraction-mode-300rows.png'),
      fullPage: true,
    });
  });

  test('fraction mode short: grid auto-sizes to content', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fractionModeShort}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    expect(height).toBeLessThan(200);

    await page.screenshot({
      path: path.join(screenshotsDir, 'fraction-mode-short.png'),
      fullPage: true,
    });
  });

  test('fixed mode: grid uses explicit pixel height', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fixedMode}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    // dfvHeight is 400. Allow some tolerance for borders/padding.
    expect(height).toBeGreaterThan(380);
    expect(height).toBeLessThan(420);

    await page.screenshot({
      path: path.join(screenshotsDir, 'fixed-mode-300rows.png'),
      fullPage: true,
    });
  });

  test('fixed mode short: still uses fixed height (no short mode)', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.fixedModeShort}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    // Fixed mode ignores short — should still be ~400px
    expect(height).toBeGreaterThan(380);
    expect(height).toBeLessThan(420);

    await page.screenshot({
      path: path.join(screenshotsDir, 'fixed-mode-short.png'),
      fullPage: true,
    });
  });

  test('no heightMode: backward compat defaults to fraction', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.noHeightMode}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    expect(height).toBeGreaterThan(100);

    await page.screenshot({
      path: path.join(screenshotsDir, 'no-heightmode-300rows.png'),
      fullPage: true,
    });
  });

  test('no heightMode short: backward compat short mode', async ({ page }) => {
    await page.goto(`${STORYBOOK_BASE}${HEIGHT_MODE_STORIES.noHeightModeShort}`);
    await waitForAgGrid(page);
    await page.waitForTimeout(500);

    const height = await getThemeHangerHeight(page);
    expect(height).toBeLessThan(200);

    await page.screenshot({
      path: path.join(screenshotsDir, 'no-heightmode-short.png'),
      fullPage: true,
    });
  });

  // Screenshot all stories in dark mode for the comparison viewer
  for (const [name, storyId] of Object.entries(HEIGHT_MODE_STORIES)) {
    test(`screenshot ${name} [dark]`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'dark' });
      await page.goto(`${STORYBOOK_BASE}${storyId}`);
      await waitForAgGrid(page);
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(screenshotsDir, `${name}--dark.png`),
        fullPage: true,
      });
    });
  }
});

// After all tests, write a manifest for the comparison viewer.
// Shows "before" (noHeightMode = legacy default) vs "after" (each named mode).
test.afterAll(() => {
  const manifest = {
    generated: new Date().toISOString(),
    pairs: [
      // Before/after: default (legacy) vs fill mode
      {
        name: 'Fill Mode — 300 rows',
        before: 'noHeightMode--dark.png',
        after: 'fillMode--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fill (after)',
      },
      {
        name: 'Fill Mode — short (3 rows)',
        before: 'noHeightModeShort--dark.png',
        after: 'fillModeShort--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fill (after)',
      },
      // Before/after: default (legacy) vs fraction mode
      {
        name: 'Fraction Mode — 300 rows',
        before: 'noHeightMode--dark.png',
        after: 'fractionMode--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fraction (after)',
      },
      {
        name: 'Fraction Mode — short (3 rows)',
        before: 'noHeightModeShort--dark.png',
        after: 'fractionModeShort--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fraction (after)',
      },
      // Before/after: default (legacy) vs fixed mode
      {
        name: 'Fixed Mode — 300 rows',
        before: 'noHeightMode--dark.png',
        after: 'fixedMode--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fixed 400px (after)',
      },
      {
        name: 'Fixed Mode — short (3 rows)',
        before: 'noHeightModeShort--dark.png',
        after: 'fixedModeShort--dark.png',
        beforeLabel: 'Default (before)',
        afterLabel: 'Fixed 400px (after)',
      },
      // Cross-comparison: fill vs fraction (the two non-fixed modes)
      {
        name: 'Fill vs Fraction — 300 rows',
        before: 'fractionMode--dark.png',
        after: 'fillMode--dark.png',
        beforeLabel: 'Fraction',
        afterLabel: 'Fill',
      },
      {
        name: 'Fill vs Fraction — short (3 rows)',
        before: 'fractionModeShort--dark.png',
        after: 'fillModeShort--dark.png',
        beforeLabel: 'Fraction',
        afterLabel: 'Fill',
      },
    ],
  };
  fs.writeFileSync(
    path.join(screenshotsDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2)
  );
});
