import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
const DEFAULT_TIMEOUT = 10000;
const NAVIGATION_TIMEOUT = 12000;
const USER_ACTION_DELAY_MS = 1000; // 1 second between user actions

async function waitForAgGrid(page: Page, timeout = 5000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'attached', timeout });
}

test.describe('Record Transcript with 1 Second Gaps', () => {
  test('should record transcript with 1 second gaps between user actions', async ({ page }) => {
    // Use the infinite scroll notebook which triggers data fetches
    const notebookName = 'test_infinite_scroll_transcript.ipynb';
    console.log(`📓 Opening test notebook: ${notebookName}...`);
    await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });

    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Execute the cell
    console.log('▶️ Executing widget code...');
    await page.locator('.jp-Notebook').first().dispatchEvent('click');
    await page.waitForTimeout(200);
    await page.keyboard.press('Shift+Enter');

    // Wait for cell execution and widget to render
    console.log('⏳ Waiting for cell execution...');
    const outputArea = page.locator('.jp-OutputArea').first();
    await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    await page.waitForTimeout(2000);
    console.log('✅ Cell executed');

    // Wait for widget to render
    console.log('⏳ Waiting for buckaroo widget...');
    await waitForAgGrid(page);
    await page.waitForTimeout(1000);
    console.log('✅ Widget rendered');

    // Clear any existing transcript
    await page.evaluate(() => {
      (window as any)._buckarooTranscript = [];
    });

    // Perform user actions with 1-second gaps between them
    console.log('🎬 Starting user actions with 1-second gaps...');

    // Action 1: Scroll down (triggers data fetch)
    console.log('   Action 1: Scrolling down...');
    const grid = page.locator('.ag-root-wrapper').first();
    await grid.evaluate((el) => {
      (el as HTMLElement).scrollTop = 500;
    });
    await page.waitForTimeout(USER_ACTION_DELAY_MS);

    // Action 2: Scroll down more
    console.log('   Action 2: Scrolling down more...');
    await grid.evaluate((el) => {
      (el as HTMLElement).scrollTop = 1000;
    });
    await page.waitForTimeout(USER_ACTION_DELAY_MS);

    // Action 3: Scroll back up
    console.log('   Action 3: Scrolling back up...');
    await grid.evaluate((el) => {
      (el as HTMLElement).scrollTop = 200;
    });
    await page.waitForTimeout(USER_ACTION_DELAY_MS);

    // Action 4: Click on a cell (if available)
    console.log('   Action 4: Clicking on a cell...');
    const firstCell = page.locator('.ag-cell').first();
    if (await firstCell.count() > 0) {
      await firstCell.click();
      await page.waitForTimeout(USER_ACTION_DELAY_MS);
    }

    // Action 5: Scroll to bottom
    console.log('   Action 5: Scrolling to bottom...');
    await grid.evaluate((el) => {
      (el as HTMLElement).scrollTop = (el as HTMLElement).scrollHeight;
    });
    await page.waitForTimeout(USER_ACTION_DELAY_MS);

    // Wait a bit for all responses to come in
    console.log('⏳ Waiting for responses to complete...');
    await page.waitForTimeout(2000);

    // Get the transcript
    const transcript = await page.evaluate(() => {
      return (window as any)._buckarooTranscript || [];
    });

    console.log(`📝 Recorded transcript with ${transcript.length} events`);

    // Log event types
    const eventTypes = transcript.map((e: any) => e.event);
    const uniqueEventTypes = [...new Set(eventTypes)];
    console.log(`📝 Event types: ${uniqueEventTypes.join(', ')}`);

    // Verify we have events
    expect(transcript.length).toBeGreaterThan(0);

    // Save transcript to file
    const transcriptPath = path.join(__dirname, 'one-second-gap-transcript.json');
    fs.writeFileSync(transcriptPath, JSON.stringify(transcript, null, 2));
    console.log(`💾 Saved transcript to ${transcriptPath}`);

    // Also log it to console for easy copy-paste
    console.log('\n📋 Transcript JSON:');
    console.log(JSON.stringify(transcript, null, 2));
  });
});

