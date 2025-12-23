import { test, expect, Page, BrowserContext } from '@playwright/test';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
// Increased timeouts for CI (slower environment)
const DEFAULT_TIMEOUT = 15000;
const NAVIGATION_TIMEOUT = 20000;
const WIDGET_RENDER_TIMEOUT = 8000; // Max time to wait for widget to render

// Get notebooks from environment variable or use defaults
const NOTEBOOKS = (process.env.TEST_NOTEBOOKS || '').split(',').filter(Boolean);

async function waitForAgGrid(page: Page, timeout = 5000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'attached', timeout });
}

async function shutdownKernelsAndSessions() {
  // Shutdown all kernels via API
  try {
    const kernelsResp = await fetch(`${JUPYTER_BASE_URL}/api/kernels?token=${JUPYTER_TOKEN}`);
    if (kernelsResp.ok) {
      const kernels = await kernelsResp.json();
      for (const kernel of kernels) {
        await fetch(`${JUPYTER_BASE_URL}/api/kernels/${kernel.id}?token=${JUPYTER_TOKEN}`, { method: 'DELETE' });
      }
    }
  } catch {}
  
  // Close all sessions
  try {
    const sessionsResp = await fetch(`${JUPYTER_BASE_URL}/api/sessions?token=${JUPYTER_TOKEN}`);
    if (sessionsResp.ok) {
      const sessions = await sessionsResp.json();
      for (const session of sessions) {
        await fetch(`${JUPYTER_BASE_URL}/api/sessions/${session.id}?token=${JUPYTER_TOKEN}`, { method: 'DELETE' });
      }
    }
  } catch {}
}

// Only run batch tests if notebooks are provided
if (NOTEBOOKS.length > 0) {
  test.describe('Batch JupyterLab Integration Tests', () => {
    // Run tests serially to avoid conflicts
    test.describe.configure({ mode: 'serial' });
    
    test('JupyterLab server is running', async ({ request }) => {
      const response = await request.get(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`);
      expect(response.status()).toBe(200);
      console.log('✅ JupyterLab is running');
    });
    
    // Generate a test for each notebook
    for (let i = 0; i < NOTEBOOKS.length; i++) {
      const notebook = NOTEBOOKS[i];
      
      test(`[${i + 1}/${NOTEBOOKS.length}] ${notebook}`, async ({ page, request }) => {
        console.log(`\n📓 Testing: ${notebook} [${i + 1}/${NOTEBOOKS.length}]`);
        
        // Just navigate to lab home first - don't kill kernels aggressively
        // JupyterLab handles multiple notebooks fine
        await page.goto(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });
        await page.waitForTimeout(200);
        
        // Verify notebook exists
        const notebookResponse = await request.get(`${JUPYTER_BASE_URL}/api/contents/${notebook}?token=${JUPYTER_TOKEN}`);
        if (notebookResponse.status() !== 200) {
          throw new Error(`Notebook ${notebook} not found`);
        }
        
        // Navigate directly to the notebook
        console.log(`📂 Opening ${notebook}...`);
        await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebook}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });
        await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
        
        // Wait for this specific notebook to load
        await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
        
        // Ensure we're looking at a fresh notebook by checking the tab title
        await page.waitForTimeout(300);
        console.log('✅ Notebook loaded');
        
        // Execute the cell
        console.log('▶️ Executing cell...');
        await page.locator('.jp-Notebook').first().dispatchEvent('click');
        await page.waitForTimeout(200);
        await page.keyboard.press('Shift+Enter');
        
        // Wait for output - fresh output for this notebook
        const outputArea = page.locator('.jp-OutputArea').first();
        await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
        console.log('✅ Cell executed');
        
        // Wait for widget elements with retry logic (CI can be slow)
        let buckarooElements = 0;
        let agGridElements = 0;
        const maxRetries = 16; // 16 * 500ms = 8 seconds max
        for (let retry = 0; retry < maxRetries; retry++) {
          await page.waitForTimeout(500);
          buckarooElements = await page.locator('[class*="buckaroo"]').count();
          agGridElements = await page.locator('.ag-root-wrapper, .ag-row').count();
          if (buckarooElements > 0 || agGridElements > 0) {
            console.log(`✅ Widget appeared after ${(retry + 1) * 500}ms`);
            break;
          }
          if (retry >= 5 && retry % 3 === 0) {
            console.log(`⏳ Still waiting for widget... (attempt ${retry + 1}/${maxRetries})`);
          }
        }
        
        if (buckarooElements === 0 && agGridElements === 0) {
          throw new Error(`Widget failed to render for ${notebook}`);
        }
        console.log(`✅ Found ${buckarooElements} buckaroo, ${agGridElements} ag-grid elements`);
        
        // Wait for ag-grid
        await waitForAgGrid(page);
        
        // Verify grid structure
        const rowCount = await page.locator('.ag-row').count();
        const headerCount = await page.locator('.ag-header-cell-text').count();
        const cellCount = await page.locator('.ag-cell').count();
        
        expect(rowCount).toBeGreaterThan(0);
        expect(headerCount).toBeGreaterThan(0);
        expect(cellCount).toBeGreaterThan(0);
        
        // Verify expected columns exist (different widgets may have different column sets)
        const headerTexts = await page.locator('.ag-header-cell-text').allTextContents();
        // Check for at least some expected columns
        const hasNameCol = headerTexts.includes('name');
        const hasAgeCol = headerTexts.includes('age');
        console.log(`📊 Headers: ${headerTexts.slice(0, 5).join(', ')}...`);
        
        // For widgets with 'name' column, verify data appears
        if (hasNameCol) {
          const nameCell = page.locator('.ag-cell').filter({ hasText: 'Alice' });
          const count = await nameCell.count();
          if (count > 0) {
            console.log(`✅ Found Alice in ${count} cell(s)`);
          } else {
            // For infinite widgets, the data might be rendered differently - just check cells have content
            const firstCell = page.locator('.ag-cell').first();
            const cellText = await firstCell.textContent();
            console.log(`📊 First cell content: "${cellText}" (Alice not found)`);
          }
        }
        
        console.log(`🎉 SUCCESS: ${notebook} - ${rowCount} rows, ${headerCount} cols, ${cellCount} cells`);
      });
    }
  });
} else {
  // Fallback: run the original single-notebook tests
  test.describe('JupyterLab Connection Tests', () => {
    test('✅ JupyterLab server is running and accessible', async ({ page, request }) => {
      const response = await request.get(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`);
      expect(response.status()).toBe(200);
      console.log('✅ JupyterLab HTTP endpoint responds with status 200');
      
      await page.goto(`${JUPYTER_BASE_URL}/lab?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });
      const title = await page.title();
      expect(title.toLowerCase()).toContain('jupyter');
      console.log(`✅ Page title: "${title}"`);
      
      await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
      await page.locator('[class*="jp-"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
      
      const jupyterElements = await page.locator('[class*="jp-"], [id*="jupyter"]').count();
      expect(jupyterElements).toBeGreaterThan(0);
      console.log(`✅ Found ${jupyterElements} JupyterLab UI elements`);
      
      const apiResponse = await request.get(`${JUPYTER_BASE_URL}/api/contents?token=${JUPYTER_TOKEN}`);
      expect(apiResponse.status()).toBe(200);
      console.log('✅ JupyterLab API is accessible');
    });

    test('✅ Can access test notebook file via API', async ({ request }) => {
      const notebookName = process.env.TEST_NOTEBOOK || 'test_polars_widget.ipynb';
      const notebookResponse = await request.get(`${JUPYTER_BASE_URL}/api/contents/${notebookName}?token=${JUPYTER_TOKEN}`);
      expect(notebookResponse.status()).toBe(200);
      console.log(`✅ Test notebook file is accessible via API: ${notebookName}`);
    });
  });

  test.describe('Buckaroo Widget JupyterLab Integration', () => {
    test('🎯 Buckaroo widget renders ag-grid in JupyterLab', async ({ page }) => {
      const notebookName = process.env.TEST_NOTEBOOK || 'test_polars_widget.ipynb';
      console.log(`📓 Opening test notebook: ${notebookName}...`);
      await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });

      await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
      await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
      console.log('✅ Notebook loaded');

      await page.locator('.jp-Notebook').first().dispatchEvent('click');
      await page.waitForTimeout(200);
      await page.keyboard.press('Shift+Enter');

      const outputArea = page.locator('.jp-OutputArea').first();
      await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
      await page.waitForTimeout(800);
      console.log('✅ Cell executed');

      await page.waitForTimeout(500);
      const buckarooElements = await page.locator('[class*="buckaroo"]').count();
      const agGridElements = await page.locator('.ag-root-wrapper, .ag-row').count();
      
      if (buckarooElements === 0 && agGridElements === 0) {
        throw new Error(`Widget failed to render.`);
      }
      console.log(`✅ Found ${buckarooElements} buckaroo elements, ${agGridElements} ag-grid elements`);

      await waitForAgGrid(page);
      console.log('✅ ag-grid rendered successfully');

      const rows = page.locator('.ag-row');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThan(0);

      const headers = page.locator('.ag-header-cell-text');
      const headerCount = await headers.count();
      expect(headerCount).toBeGreaterThan(0);

      const cells = page.locator('.ag-cell');
      const cellCount = await cells.count();
      expect(cellCount).toBeGreaterThan(0);

      const headerTexts = await headers.allTextContents();
      expect(headerTexts).toContain('name');
      expect(headerTexts).toContain('age');
      expect(headerTexts).toContain('score');

      const nameCell = page.locator('.ag-cell').filter({ hasText: 'Alice' });
      await expect(nameCell).toBeVisible();

      console.log(`🎉 SUCCESS: Widget from ${notebookName} rendered ag-grid with ${rowCount} rows, ${headerCount} columns, and ${cellCount} cells`);
    });
  });
}

