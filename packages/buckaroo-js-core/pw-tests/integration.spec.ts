import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
const DEFAULT_TIMEOUT = 35000; // 15 seconds for most operations
const NAVIGATION_TIMEOUT = 30000; // 30 seconds max for navigation

async function waitForAgGrid(outputArea: any, timeout = 10000) {
  // Wait for ag-grid to be present and rendered within the output area
  await outputArea.locator('.ag-root-wrapper').first().waitFor({ state: 'visible', timeout });
  // Wait for cells to be present
  await outputArea.locator('.ag-cell').first().waitFor({ state: 'visible', timeout });
  // Wait for no loading overlays
  await outputArea.locator('.ag-overlay-loading-center').waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
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
    await page.locator('.jp-Notebook').first().waitFor({ state: 'visible', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Find and run the first code cell
    console.log(`▶️ Executing widget code from ${notebookName}...`);
    // Wait for notebook to be fully interactive (use domcontentloaded instead of networkidle)
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    // Focus on the notebook and use keyboard shortcut to run cell (Shift+Enter)
    await page.locator('.jp-Notebook').first().click();
    await page.keyboard.press('Shift+Enter');

    // Wait for cell execution to complete
    console.log('⏳ Waiting for cell execution...');
    // Wait for output area to appear (may be hidden but should be attached)
    const outputArea = page.locator('.jp-OutputArea').first();
    await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    // Wait a bit for execution to complete
    await page.waitForTimeout(2000);
    console.log('✅ Cell executed');

    // Check for any error messages in the output
    // Target only stdout text output, not widget output (which also has .jp-OutputArea-output class)
    const stdoutOutputLocator = outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stdout"]').first();
    const outputText = await stdoutOutputLocator.textContent().catch(() => '');
    console.log('📄 Cell output:', outputText);

    if (outputText?.includes('❌') || outputText?.includes('ImportError') || outputText?.includes('ModuleNotFoundError')) {
        throw new Error(`Cell execution failed with error: ${outputText}`);
    }

    // Wait for the buckaroo widget to appear within the output area
    console.log('⏳ Waiting for buckaroo widget...');
    try {
        await outputArea.locator('.buckaroo-widget').waitFor({ state: 'visible', timeout: DEFAULT_TIMEOUT });
        console.log('✅ Buckaroo widget appeared');
    } catch (error) {
        // Comprehensive error diagnostics
        console.log('❌ Widget failed to appear. Gathering diagnostic information...');
        
        // Get the full output area text content
        const fullOutputText = await outputArea.textContent().catch(() => '');
        console.log('📄 Full output area text:', fullOutputText || '(empty)');
        
        // Get the HTML structure of the output area
        const outputAreaHTML = await outputArea.innerHTML().catch(() => '');
        console.log('📄 Output area HTML structure:', outputAreaHTML.substring(0, 2000) || '(empty)');
        
        // Check for stdout output
        const stdoutOutput = outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stdout"]');
        const stdoutCount = await stdoutOutput.count();
        if (stdoutCount > 0) {
            const stdoutText = await stdoutOutput.first().textContent().catch(() => '');
            console.log('📄 stdout output:', stdoutText || '(empty)');
        }
        
        // Check for stderr output
        const stderrOutput = outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.stderr"]');
        const stderrCount = await stderrOutput.count();
        if (stderrCount > 0) {
            const stderrText = await stderrOutput.first().textContent().catch(() => '');
            console.log('📄 stderr output:', stderrText || '(empty)');
        }
        
        // Check for error outputs (multiple types)
        const errorOutputs = outputArea.locator('.jp-OutputArea-error');
        const errorCount = await errorOutputs.count();
        if (errorCount > 0) {
            const errorTexts = await errorOutputs.allTextContents();
            console.log('📄 Error outputs:', errorTexts.join('\n---\n'));
        }
        
        // Check for traceback
        const tracebackOutput = outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.error"]');
        const tracebackCount = await tracebackOutput.count();
        if (tracebackCount > 0) {
            const tracebackText = await tracebackOutput.first().textContent().catch(() => '');
            console.log('📄 Traceback:', tracebackText || '(empty)');
        }
        
        // Check for any buckaroo-related elements
        const buckarooElements = await outputArea.locator('[class*="buckaroo"]').count();
        const anyWidgets = await outputArea.locator('.widget-area').count();
        const widgetOutputs = await outputArea.locator('.jp-OutputArea-output[data-mime-type="application/vnd.jupyter.widget-view+json"]').count();
        console.log(`📊 Found ${buckarooElements} buckaroo elements, ${anyWidgets} widget areas, ${widgetOutputs} widget outputs`);
        
        // Check for all output types
        const allOutputs = await outputArea.locator('.jp-OutputArea-output').all();
        console.log(`📊 Total output elements: ${allOutputs.length}`);
        for (let i = 0; i < allOutputs.length; i++) {
            const mimeType = await allOutputs[i].getAttribute('data-mime-type').catch(() => 'unknown');
            const text = await allOutputs[i].textContent().catch(() => '');
            console.log(`  Output ${i + 1} (${mimeType}): ${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`);
        }
        
        // Log captured console errors
        if (consoleMessages.length > 0) {
            console.log('📄 Browser console errors/warnings:', JSON.stringify(consoleMessages, null, 2));
        }
        
        // Build comprehensive error message
        let errorMessage = 'Widget failed to render. ';
        if (errorCount > 0) {
            const errorTexts = await errorOutputs.allTextContents();
            errorMessage += `Errors: ${errorTexts.join('; ')}. `;
        }
        if (stderrCount > 0) {
            const stderrText = await stderrOutput.first().textContent().catch(() => '');
            errorMessage += `Stderr: ${stderrText}. `;
        }
        if (tracebackCount > 0) {
            const tracebackText = await tracebackOutput.first().textContent().catch(() => '');
            errorMessage += `Traceback: ${tracebackText}. `;
        }
        if (fullOutputText) {
            errorMessage += `Full output: ${fullOutputText.substring(0, 500)}${fullOutputText.length > 500 ? '...' : ''}. `;
        }
        if (consoleMessages.length > 0) {
            errorMessage += `Console errors: ${consoleMessages.map(m => `${m.type}: ${m.text}`).join('; ')}. `;
        }
        errorMessage += `Found ${buckarooElements} buckaroo elements, ${widgetOutputs} widget outputs.`;
        
        throw new Error(errorMessage);
    }

    // Wait for ag-grid to render within the output area
    console.log('⏳ Waiting for ag-grid to render in notebook output...');
    await waitForAgGrid(outputArea);
    console.log('✅ ag-grid rendered successfully');

    // Verify the grid structure within the output area
    const rows = outputArea.locator('.ag-row');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    const headers = outputArea.locator('.ag-header-cell-text');
    const headerCount = await headers.count();
    expect(headerCount).toBeGreaterThan(0);

    const cells = outputArea.locator('.ag-cell');
    const cellCount = await cells.count();
    expect(cellCount).toBeGreaterThan(0);

    // Verify expected column headers appear
    const headerTexts = await headers.allTextContents();
    expect(headerTexts).toContain('name');
    expect(headerTexts).toContain('age');
    expect(headerTexts).toContain('score');

    // Verify data appears in cells within the output area
    const nameCell = outputArea.locator('.ag-cell').filter({ hasText: 'Alice' });
    const ageCell = outputArea.locator('.ag-cell').filter({ hasText: '25' });
    const scoreCell = outputArea.locator('.ag-cell').filter({ hasText: '85.5' });

    await expect(nameCell).toBeVisible();
    await expect(ageCell).toBeVisible();
    await expect(scoreCell).toBeVisible();

    console.log(`🎉 SUCCESS: Widget from ${notebookName} rendered ag-grid with ${rowCount} rows, ${headerCount} columns, and ${cellCount} cells`);
    console.log('📊 Verified data: Alice (age 25, score 85.5)');
  });
});
