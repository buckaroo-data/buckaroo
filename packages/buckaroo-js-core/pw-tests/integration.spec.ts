import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';

const JUPYTER_BASE_URL = process.env.JUPYTER_BASE_URL || 'http://localhost:8889';
const JUPYTER_TOKEN = process.env.JUPYTER_TOKEN || 'test-token-12345';
const DEFAULT_TIMEOUT = 8000; // 8 seconds for most operations
const CELL_EXEC_TIMEOUT = 120000; // kernel startup can be slow when 8 run concurrently
const NAVIGATION_TIMEOUT = 10000; // 10 seconds max for navigation

async function waitForAgGrid(outputArea: any, timeout = DEFAULT_TIMEOUT) {
  // Wait for ag-grid to be present and rendered; 'visible' ensures column layout is done
  await outputArea.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await outputArea.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });
}

// Helper function to get cell content by row and column
async function getCellContent(page: Page, rowIndex: number, colId: string): Promise<string> {
  const cellSelector = `[row-index="${rowIndex}"] [col-id="${colId}"]`;
  const cell = page.locator(cellSelector);
  return await cell.textContent() || '';
}

test.describe('JupyterLab Connection Tests', () => {
  test('✅ JupyterLab server is running and accessible', async ({ page, request }) => {
    console.log('🔍 Checking JupyterLab server status...');
    
    // Test 1: Check if JupyterLab responds to HTTP requests
    const response = await request.get(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`);
    expect(response.status()).toBe(200);
    console.log('✅ JupyterLab HTTP endpoint responds with status 200');
    
    // Test 2: Navigate to JupyterLab and verify it loads
    console.log('🌐 Navigating to JupyterLab...');
    await page.goto(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });
    
    // Test 3: Check that page title indicates JupyterLab
    const title = await page.title();
    expect(title.toLowerCase()).toContain('jupyter');
    console.log(`✅ Page title: "${title}"`);
    
    // Test 4: Verify JupyterLab interface elements are present
    console.log('⏳ Waiting for JupyterLab UI to load...');
    // Wait for JupyterLab to be loaded - use domcontentloaded instead of networkidle
    // networkidle can timeout if JupyterLab keeps making background requests
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    // Wait for a specific JupyterLab element to ensure UI is ready
    await page.locator('[class*="jp-"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    
    // Check for JupyterLab-specific elements
    const jupyterElements = await page.locator('[class*="jp-"], [id*="jupyter"]').count();
    expect(jupyterElements).toBeGreaterThan(0);
    console.log(`✅ Found ${jupyterElements} JupyterLab UI elements`);
    
    // Test 5: Verify we can access the JupyterLab API
    const apiResponse = await request.get(`${JUPYTER_BASE_URL}/api/contents?token=${JUPYTER_TOKEN}`);
    expect(apiResponse.status()).toBe(200);
    const apiData = await apiResponse.json();
    expect(apiData).toHaveProperty('content');
    console.log('✅ JupyterLab API is accessible');
    
    console.log('🎉 SUCCESS: JupyterLab is running and Playwright can connect successfully!');
  });

  test('✅ Can access test notebook file via API', async ({ request }) => {
    console.log('🔍 Checking if test notebook exists...');
    
    const notebookName = process.env.TEST_NOTEBOOK || 'test_polars_widget.ipynb';
    const notebookResponse = await request.get(`${JUPYTER_BASE_URL}/api/contents/${notebookName}?token=${JUPYTER_TOKEN}`);
    expect(notebookResponse.status()).toBe(200);
    
    const notebookData = await notebookResponse.json();
    expect(notebookData).toHaveProperty('content');
    expect(notebookData.type).toBe('notebook');
    console.log(`✅ Test notebook file is accessible via API: ${notebookName}`);
  });
});

test.describe('Buckaroo Widget JupyterLab Integration', () => {
  test('🎯 Buckaroo widget renders ag-grid in JupyterLab', async ({ page }) => {
    // Capture console errors and warnings
    const consoleMessages: Array<{ type: string; text: string }> = [];
    page.on('console', (msg) => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error' || type === 'warning') {
        consoleMessages.push({ type, text });
        console.log(`🔴 Browser ${type}:`, text);
      }
    });
    
    // Capture page errors
    page.on('pageerror', (error) => {
      console.log('🔴 Page error:', error.message);
      consoleMessages.push({ type: 'pageerror', text: error.message });
    });
    
    // Navigate directly to the test notebook
    const notebookName = process.env.TEST_NOTEBOOK || 'test_polars_widget.ipynb';
    console.log(`📓 Opening test notebook: ${notebookName}...`);
    await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });

    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    // Use 'attached' instead of 'visible' as JupyterLab notebooks may have complex visibility states
    await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Find and run the first code cell
    console.log(`▶️ Executing widget code from ${notebookName}...`);
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });

    // Execute with retry — under concurrent load, the first Shift+Enter can be
    // silently dropped if the kernel isn't connected yet. Retry every 10s.
    const outputArea = page.locator('.jp-OutputArea').first();
    const outputLocator = outputArea.locator('.jp-OutputArea-output').first();
    const deadline = Date.now() + CELL_EXEC_TIMEOUT;

    for (let attempt = 1; Date.now() < deadline; attempt++) {
      console.log(`⏳ Shift+Enter attempt ${attempt}...`);
      const firstCell = page.locator('.jp-Cell').first();
      await firstCell.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
      await firstCell.click({ timeout: DEFAULT_TIMEOUT });
      await page.locator('.jp-Cell.jp-mod-selected').first().waitFor({ state: 'attached', timeout: 5000 }).catch(() => {});
      await page.keyboard.press('Shift+Enter');

      // Wait up to 10s for output to appear — if it does, we're done
      try {
        await outputLocator.waitFor({ state: 'attached', timeout: 10000 });
        console.log('✅ Cell executed');
        break;
      } catch {
        if (Date.now() >= deadline) throw new Error(`Cell execution timed out after ${CELL_EXEC_TIMEOUT}ms`);
        console.log(`⚠️ No output after attempt ${attempt}, retrying...`);
      }
    }

    // Check for any error messages in the output
    // Target only stdout text output, not widget output (which also has .jp-OutputArea-output class)
    const stdoutOutputLocator = outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stdout"]').first();
    const outputText = await stdoutOutputLocator.textContent().catch(() => '');
    console.log('📄 Cell output:', outputText);

    if (outputText?.includes('❌') || outputText?.includes('ImportError') || outputText?.includes('ModuleNotFoundError')) {
        throw new Error(`Cell execution failed with error: ${outputText}`);
    }

    // Wait for the buckaroo widget to appear — deterministic wait instead of fixed delay
    console.log('⏳ Waiting for buckaroo widget...');
    await page.locator('[class*="buckaroo"], .ag-root-wrapper').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    const buckarooElements = await page.locator('[class*="buckaroo"]').count();
    const agGridElements = await page.locator('.ag-root-wrapper, .ag-row').count();
    console.log(`✅ Found ${buckarooElements} buckaroo elements, ${agGridElements} ag-grid elements on page`);

    // Wait for ag-grid to render
    console.log('⏳ Waiting for ag-grid to render...');
    await waitForAgGrid(outputArea);
    console.log('✅ ag-grid rendered successfully');

    // Verify the grid structure on the page
    const rows = page.locator('.ag-row');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    const headers = page.locator('.ag-header-cell-text');
    const headerCount = await headers.count();
    expect(headerCount).toBeGreaterThan(0);

    const cells = page.locator('.ag-cell');
    const cellCount = await cells.count();
    expect(cellCount).toBeGreaterThan(0);

    // Verify expected column headers appear
    const headerTexts = await headers.allTextContents();
    expect(headerTexts).toContain('name');
    expect(headerTexts).toContain('age');
    expect(headerTexts).toContain('score');

    // Verify data appears in cells
    const nameCell = page.locator('.ag-cell').filter({ hasText: 'Alice' });
    const ageCell = page.locator('.ag-cell').filter({ hasText: '25' });
    const scoreCell = page.locator('.ag-cell').filter({ hasText: '85.5' });

    await expect(nameCell).toBeVisible();
    await expect(ageCell).toBeVisible();
    await expect(scoreCell).toBeVisible();

    console.log(`🎉 SUCCESS: Widget from ${notebookName} rendered ag-grid with ${rowCount} rows, ${headerCount} columns, and ${cellCount} cells`);
    console.log('📊 Verified data: Alice (age 25, score 85.5)');
  });
});
