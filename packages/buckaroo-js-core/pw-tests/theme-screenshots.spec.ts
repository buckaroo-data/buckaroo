import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const STORYBOOK_BASE = 'http://localhost:6006/iframe.html?viewMode=story&id=';

// Representative stories covering the main UI surfaces
const STORIES = [
  // Main data viewer
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--primary', name: 'InfiniteShadow-Primary' },
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--large', name: 'InfiniteShadow-Large' },
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--pinned-rows', name: 'InfiniteShadow-PinnedRows' },
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--color-map-example', name: 'InfiniteShadow-ColorMap' },
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--multi-index', name: 'InfiniteShadow-MultiIndex' },
  { id: 'buckaroo-dfviewer-dfviewerinfiniteshadow--three-level-column-index', name: 'InfiniteShadow-ThreeLevelCol' },

  // Non-infinite DFViewer
  { id: 'buckaroo-dfviewer-dfviewer--primary', name: 'DFViewer-Primary' },
  { id: 'buckaroo-dfviewer-dfviewer--color-from-col', name: 'DFViewer-ColorFromCol' },
  { id: 'buckaroo-dfviewer-dfviewer--chart', name: 'DFViewer-Chart' },

  // Raw infinite viewer
  { id: 'buckaroo-dfviewer-dfviewerinfiniteraw--primary', name: 'InfiniteRaw-Primary' },

  // Full widget
  { id: 'buckaroo-buckaroowidgettest--primary', name: 'BuckarooWidget-Primary' },

  // Chrome / controls
  { id: 'buckaroo-statusbar--primary', name: 'StatusBar-Primary' },
  { id: 'buckaroo-columnseditor--default', name: 'ColumnsEditor-Default' },
  { id: 'buckaroo-chrome-operationviewer-in-stories-dir--default', name: 'OperationViewer-Default' },

  // Cell renderers
  { id: 'buckaroo-dfviewer-renderers-histogram--primary', name: 'Histogram-Primary' },
  { id: 'buckaroo-dfviewer-renderers-chartcell--primary', name: 'ChartCell-Primary' },
  { id: 'buckaroo-dfviewer-renderers-chartcell--composed', name: 'ChartCell-Composed' },

  // MessageBox
  { id: 'buckaroo-messagebox--mixed-messages', name: 'MessageBox-Mixed' },
];

const SCHEMES = ['light', 'dark'] as const;

// Ensure screenshots directory exists
const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

for (const story of STORIES) {
  for (const scheme of SCHEMES) {
    test(`screenshot ${story.name} [${scheme}]`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(`${STORYBOOK_BASE}${story.id}`);

      // Wait for AG-Grid cells or any visible content to render
      const cell = page.locator('.ag-cell');
      const cellWrapper = page.locator('.ag-cell-wrapper');
      const noRows = page.locator('.ag-overlay-no-rows-center');
      const fullWidth = page.locator('.ag-full-width-row');
      const sbContent = page.locator('#storybook-root');

      await cell
        .or(cellWrapper)
        .or(noRows)
        .or(fullWidth)
        .or(sbContent)
        .first()
        .waitFor({ state: 'visible', timeout: 15000 });

      // Small settle time for animations / lazy rendering
      await page.waitForTimeout(500);

      await page.screenshot({
        path: path.join(screenshotsDir, `${story.name}--${scheme}.png`),
        fullPage: true,
      });
    });
  }
}
