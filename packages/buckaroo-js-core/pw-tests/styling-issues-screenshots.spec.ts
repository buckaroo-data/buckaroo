/**
 * Playwright screenshot capture for styling-issue stories.
 * Follows the theme-screenshots.spec.ts pattern (light-only).
 *
 * SCREENSHOT_DIR env var controls output directory (default: screenshots/after).
 * Run once on each commit to produce "before" and "after" sets:
 *
 *   SCREENSHOT_DIR=screenshots/before npx playwright test pw-tests/styling-issues-screenshots.spec.ts
 *   SCREENSHOT_DIR=screenshots/after  npx playwright test pw-tests/styling-issues-screenshots.spec.ts
 */
import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const STORYBOOK_BASE = 'http://localhost:6006/iframe.html?viewMode=story&id=';

// Output directory — overridable via env var
const screenshotsDir = path.resolve(
  __dirname,
  '..',
  process.env.SCREENSHOT_DIR ?? 'screenshots/after',
);

/**
 * All 16 styling-issue stories.
 * Story IDs follow Storybook's slug rules:
 *   title "Buckaroo/DFViewer/StylingIssues" → "buckaroo-dfviewer-stylingissues"
 *   export name e.g. FewCols_ShortHdr_ShortData → "fewcols-shorthdr-shortdata"
 */
const STORIES = [
  // Section A – width/contention (#595, #596, #599, #600)
  { id: 'buckaroo-dfviewer-stylingissues--fewcols-shorthdr-shortdata',  name: 'A1_FewCols_ShortHdr_ShortData',  issues: '#599' },
  { id: 'buckaroo-dfviewer-stylingissues--fewcols-shorthdr-longdata',   name: 'A2_FewCols_ShortHdr_LongData',   issues: '' },
  { id: 'buckaroo-dfviewer-stylingissues--fewcols-longhdr-shortdata',   name: 'A3_FewCols_LongHdr_ShortData',   issues: '' },
  { id: 'buckaroo-dfviewer-stylingissues--fewcols-longhdr-longdata',    name: 'A4_FewCols_LongHdr_LongData',    issues: '' },
  { id: 'buckaroo-dfviewer-stylingissues--manycols-shorthdr-shortdata', name: 'A5_ManyCols_ShortHdr_ShortData', issues: '#595 #599' },
  { id: 'buckaroo-dfviewer-stylingissues--manycols-shorthdr-longdata',  name: 'A6_ManyCols_ShortHdr_LongData',  issues: '#596' },
  { id: 'buckaroo-dfviewer-stylingissues--manycols-longhdr-shortdata',  name: 'A7_ManyCols_LongHdr_ShortData',  issues: '#596' },
  { id: 'buckaroo-dfviewer-stylingissues--manycols-longhdr-longdata',   name: 'A8_ManyCols_LongHdr_LongData',   issues: '#596 worst-case' },

  // Section B – large numbers / compact_number (#597, #602)
  // Note: compact_number stories may render raw values on pre-#597 commits.
  { id: 'buckaroo-dfviewer-stylingissues--largenumbers-float',          name: 'B9_LargeNumbers_Float',          issues: '#597 before' },
  { id: 'buckaroo-dfviewer-stylingissues--largenumbers-compact',        name: 'B10_LargeNumbers_Compact',        issues: '#597 after' },
  { id: 'buckaroo-dfviewer-stylingissues--clusteredbillions-float',     name: 'B11_ClusteredBillions_Float',     issues: '#602 baseline' },
  { id: 'buckaroo-dfviewer-stylingissues--clusteredbillions-compact',   name: 'B12_ClusteredBillions_Compact',   issues: '#602 precision' },

  // Section C – pinned row / index alignment (#587)
  { id: 'buckaroo-dfviewer-stylingissues--pinnedindex-fewcols',         name: 'C13_PinnedIndex_FewCols',         issues: '#587' },
  { id: 'buckaroo-dfviewer-stylingissues--pinnedindex-manycols',        name: 'C14_PinnedIndex_ManyCols',        issues: '#587' },

  // Section D – mixed cross-issue scenarios
  { id: 'buckaroo-dfviewer-stylingissues--mixed-manynarrow-withpinned', name: 'D15_Mixed_ManyNarrow_WithPinned', issues: '#595 #587 #599' },
  { id: 'buckaroo-dfviewer-stylingissues--mixed-fewwide-withpinned',    name: 'D16_Mixed_FewWide_WithPinned',    issues: '#587 baseline' },
];

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

for (const story of STORIES) {
  test(`screenshot ${story.name}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto(`${STORYBOOK_BASE}${story.id}`);

    // Wait for AG-Grid cells or any visible content
    const cell        = page.locator('.ag-cell');
    const cellWrapper = page.locator('.ag-cell-wrapper');
    const noRows      = page.locator('.ag-overlay-no-rows-center');
    const fullWidth   = page.locator('.ag-full-width-row');
    const sbContent   = page.locator('#storybook-root');

    await cell
      .or(cellWrapper)
      .or(noRows)
      .or(fullWidth)
      .or(sbContent)
      .first()
      .waitFor({ state: 'visible', timeout: 15000 });

    // Settle time for animations / lazy column-width calculation
    await page.waitForTimeout(800);

    await page.screenshot({
      path: path.join(screenshotsDir, `${story.name}.png`),
      fullPage: true,
    });
  });
}
