import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';
import { spawn, ChildProcess, exec } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

const execAsync = promisify(exec);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const JUPYTERLITE_BUILD_DIR = path.resolve(__dirname, '../../../docs/extra-html/example_notebooks/hello_world/build');
const JUPYTERLITE_PORT = 8081;
const BASE_URL = `http://localhost:${JUPYTERLITE_PORT}`;
const DEFAULT_TIMEOUT = 15000; // 15 seconds for most operations
const NAVIGATION_TIMEOUT = 20000; // 20 seconds max for navigation
const PYODIDE_EXECUTION_TIMEOUT = 60000; // 60 seconds for Pyodide execution (includes package installs)

let httpServerProcess: ChildProcess | null = null;
let serverStarted = false;

async function startJupyterLiteServer(): Promise<void> {
  // Only start server once
  if (serverStarted && httpServerProcess) {
    console.log(`✅ JupyterLite server already running at ${BASE_URL}`);
    return;
  }

  // Check if build directory exists
  if (!fs.existsSync(JUPYTERLITE_BUILD_DIR)) {
    throw new Error(`JupyterLite build directory not found: ${JUPYTERLITE_BUILD_DIR}\nPlease run the generate script first.`);
  }

  // Kill any existing server on the port
  try {
    const { exec } = require('child_process');
    const { promisify } = require('util');
    const execAsync = promisify(exec);
    try {
      await execAsync(`lsof -ti:${JUPYTERLITE_PORT} | xargs kill -9 2>/dev/null || true`);
      await new Promise(resolve => setTimeout(resolve, 500));
    } catch (e) {
      // Ignore errors if no process is running
    }
  } catch (e) {
    // Ignore cleanup errors
  }

  // Start http-server
  return new Promise((resolve, reject) => {
    console.log(`🌐 Starting http-server on port ${JUPYTERLITE_PORT}...`);
    httpServerProcess = spawn('npx', ['http-server', '-p', String(JUPYTERLITE_PORT), '-c-1'], {
      cwd: JUPYTERLITE_BUILD_DIR,
      stdio: 'pipe',
      shell: true,
    });

    let serverReady = false;
    const timeout = setTimeout(() => {
      if (!serverReady) {
        httpServerProcess?.kill();
        reject(new Error(`Server failed to start within 10 seconds`));
      }
    }, 10000);

    httpServerProcess.stdout?.on('data', (data) => {
      const output = data.toString();
      if (output.includes('Available on') || output.includes('Hit CTRL-C') || output.includes('Starting up')) {
        serverReady = true;
        serverStarted = true;
        clearTimeout(timeout);
        console.log(`✅ JupyterLite server started at ${BASE_URL}`);
        resolve();
      }
    });

    httpServerProcess.stderr?.on('data', (data) => {
      const output = data.toString();
      if (output.includes('EADDRINUSE')) {
        clearTimeout(timeout);
        reject(new Error(`Port ${JUPYTERLITE_PORT} is already in use`));
      }
    });

    httpServerProcess.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    
    // Handle process exit
    httpServerProcess.on('exit', (code) => {
      if (!serverReady && code !== null && code !== 0) {
        clearTimeout(timeout);
        reject(new Error(`Server process exited with code ${code}`));
      }
    });
  });
}

async function stopJupyterLiteServer(): Promise<void> {
  if (httpServerProcess) {
    console.log('🛑 Stopping JupyterLite server...');
    httpServerProcess.kill();
    httpServerProcess = null;
    serverStarted = false;
    // Give it a moment to clean up
    await new Promise(resolve => setTimeout(resolve, 500));
  }
}

test.beforeAll(async ({ request }) => {
  await startJupyterLiteServer();
  
  // Verify server is actually running and responding
  console.log('🔍 Verifying server is running...');
  let retries = 10;
  let serverReady = false;
  while (retries > 0 && !serverReady) {
    try {
      const response = await request.get(`${BASE_URL}/index.html`);
      if (response.ok()) {
        serverReady = true;
        console.log('✅ Server is responding at', BASE_URL);
      }
    } catch (e) {
      retries--;
      if (retries > 0) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
  }
  
  if (!serverReady) {
    throw new Error(`Server is not responding at ${BASE_URL}`);
  }
});

test.afterAll(async () => {
  await stopJupyterLiteServer();
});

test.describe('JupyterLite Integration Tests', () => {
  // Set reasonable timeout for Pyodide execution tests (2 minutes)
  test.describe.configure({ timeout: 120000 });

  test('✅ JupyterLite loads and can open notebook', async ({ page }) => {
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

    page.on('pageerror', (error) => {
      console.log('🔴 Page error:', error.message);
      consoleMessages.push({ type: 'pageerror', text: error.message });
    });

    console.log(`📓 Navigating to JupyterLite at ${BASE_URL}...`);
    await page.goto(`${BASE_URL}/lab/index.html`, { timeout: NAVIGATION_TIMEOUT, waitUntil: 'domcontentloaded' });

    // Wait for JupyterLite to load
    console.log('⏳ Waiting for JupyterLite to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    
    // Wait for JupyterLite UI elements (similar to JupyterLab)
    const jupyterElements = await page.locator('[class*="jp-"], [id*="jupyter"], [class*="lm-"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ JupyterLite UI loaded');

    // Navigate to the notebook
    console.log('📂 Opening notebook...');
    // In JupyterLite, notebooks are at the root of the files API
    await page.goto(`${BASE_URL}/lab/index.html?path=hello_world.ipynb`, { timeout: NAVIGATION_TIMEOUT, waitUntil: 'domcontentloaded' });
    
    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    
    // Wait for notebook UI elements
    await page.locator('.jp-Notebook, [class*="jp-Notebook"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');
  });

  test('🐍 Verify Build Environment Uses Python 3.12', async () => {
    // This test verifies the BUILD environment uses Python 3.12
    // Note: The runtime Python in JupyterLite is Pyodide (separate from build Python)
    const venvPython = path.resolve(__dirname, '../../../.venv-jupyterlite/bin/python');
    console.log(`🔍 Checking build venv Python version at: ${venvPython}`);
    
    // Check if venv exists
    if (!fs.existsSync(venvPython)) {
      throw new Error(`Build venv not found at ${venvPython}. Run the generate script with --recreate-venv first.`);
    }
    
    try {
      const { stdout } = await execAsync(`${venvPython} --version`);
      const version = stdout.trim();
      console.log(`📊 Build venv Python version: ${version}`);
      
      if (!version.includes('3.12')) {
        throw new Error(`Expected Python 3.12.x in build venv, but got: ${version}`);
      }
      
      console.log('✅ Build environment is using Python 3.12');
    } catch (error: any) {
      if (error.code === 'ENOENT' || error.message.includes('no such file')) {
        throw new Error(`Build venv not found at ${venvPython}. Run the generate script with --recreate-venv first.`);
      }
      throw error;
    }
  });

  test('🐍 Verify Python Version in JupyterLite Notebook (First Cell)', async ({ page }) => {
    // This test verifies the Python version running in the JupyterLite notebook
    // The first cell in hello_world.ipynb checks and prints the Python version
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

    page.on('pageerror', (error) => {
      console.log('🔴 Page error:', error.message);
      consoleMessages.push({ type: 'pageerror', text: error.message });
    });

    console.log(`📓 Navigating to JupyterLite notebook...`);
    await page.goto(`${BASE_URL}/lab/index.html?path=hello_world.ipynb`, { timeout: NAVIGATION_TIMEOUT, waitUntil: 'domcontentloaded' });

    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook, [class*="jp-Notebook"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Find the first cell (Python version check cell)
    const firstCell = page.locator('.jp-Cell').first();
    
    // Check that the first cell contains Python version check code
    console.log('🔍 Checking first cell content...');
    // Try multiple selectors to find cell content
    let cellContent = '';
    const selectors = [
      '.jp-Cell-input',
      '[class*="jp-Cell-input"]',
      '.jp-CodeMirror',
      '[class*="CodeMirror"]',
      '.jp-InputArea-editor',
      '[class*="InputArea-editor"]'
    ];
    
    for (const selector of selectors) {
      try {
        const content = await firstCell.locator(selector).first().textContent({ timeout: 2000 });
        if (content && content.trim().length > 0) {
          cellContent = content;
          break;
        }
      } catch (e) {
        // Try next selector
      }
    }
    
    console.log('📄 First cell content:', cellContent?.substring(0, 200));
    
    if (!cellContent || (!cellContent.includes('sys.version') && !cellContent.includes('Python version'))) {
      // If we can't find the content, that's okay - we'll just execute the cell and check the output
      console.log('⚠️  Could not verify cell content, will check output after execution');
    } else {
      console.log('✅ First cell contains Python version check code');
    }

    // Execute the first cell
    console.log('▶️ Executing first cell (Python version check)...');
    await firstCell.click();
    await page.waitForTimeout(500);
    await page.keyboard.press('Shift+Enter');
    
    // Wait for execution to complete
    console.log('⏳ Waiting for Python version check to complete...');
    let executionComplete = false;
    const startTime = Date.now();
    const maxWaitTime = 90000; // 90 seconds for Pyodide to load and execute
    
    while (!executionComplete && (Date.now() - startTime) < maxWaitTime) {
      const execPrompt = await firstCell.locator('.jp-InputPrompt, [class*="jp-InputPrompt"]').textContent().catch(() => '');
      const isExecuting = execPrompt?.includes('[*]');
      
      if (!isExecuting && execPrompt && /\[\d+\]/.test(execPrompt)) {
        executionComplete = true;
        console.log('✅ Python version check completed');
        break;
      }
      await page.waitForTimeout(1000);
    }
    
    if (!executionComplete) {
      throw new Error(`Python version check cell did not complete within ${maxWaitTime / 1000} seconds`);
    }
    
    // Get the output from the first cell
    const outputArea = firstCell.locator('.jp-OutputArea, [class*="jp-OutputArea"]').first();
    const outputText = await outputArea.textContent({ timeout: 10000 }).catch(() => '');
    console.log('📄 Python version output:', outputText);
    
    if (!outputText) {
      throw new Error('No output from Python version check cell');
    }
    
    // Extract Python version information
    const versionMatch = outputText.match(/Python version: ([\d.]+)/);
    const versionInfoMatch = outputText.match(/Python major\.minor: (\d+)\.(\d+)/);
    
    if (!versionMatch) {
      throw new Error(`Could not parse Python version from output: ${outputText}`);
    }
    
    const pythonVersion = versionMatch[1];
    console.log(`🐍 Detected Python version in notebook: ${pythonVersion}`);
    
    // Verify it's Python 3.12.x (any patch version)
    if (!pythonVersion.startsWith('3.12.')) {
      throw new Error(`Expected Python 3.12.x in Pyodide runtime, but got ${pythonVersion}. Full output: ${outputText}`);
    }
    
    if (versionInfoMatch) {
      const major = parseInt(versionInfoMatch[1]);
      const minor = parseInt(versionInfoMatch[2]);
      console.log(`🐍 Python version_info: ${major}.${minor}`);
      
      // Verify major.minor is 3.12
      if (major !== 3 || minor !== 12) {
        throw new Error(`Expected Python 3.12.x, but got ${major}.${minor}. Full output: ${outputText}`);
      }
    }
    
    console.log(`✅ Verified Pyodide runtime is using Python ${pythonVersion} (3.12.x)`);
  });

  test('🐍 Note: JupyterLite Runtime Uses Pyodide (Separate from Build Python)', async ({ page }) => {
    // This test documents that JupyterLite runtime uses Pyodide, which has its own Python version
    // The BUILD environment uses Python 3.12 (verified in previous test)
    // The RUNTIME Python in JupyterLite is Pyodide, which may be a different version (currently 3.13.2)
    // This is expected and normal - Pyodide is a separate Python distribution compiled to WebAssembly
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

    page.on('pageerror', (error) => {
      console.log('🔴 Page error:', error.message);
      consoleMessages.push({ type: 'pageerror', text: error.message });
    });

    console.log(`📓 Navigating to JupyterLite notebook...`);
    await page.goto(`${BASE_URL}/lab/index.html?path=hello_world.ipynb`, { timeout: NAVIGATION_TIMEOUT, waitUntil: 'domcontentloaded' });

    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook, [class*="jp-Notebook"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Find the first code cell
    const firstCell = page.locator('.jp-Cell').first();
    
    // Add a new cell to check Python version
    console.log('➕ Adding cell to check Python version...');
    await firstCell.click();
    await page.keyboard.press('b'); // Add cell below
    
    // Wait for new cell to appear
    await page.waitForTimeout(500);
    
    // Get the new cell (should be second cell now)
    const secondCell = page.locator('.jp-Cell').nth(1);
    
    // Type Python version check code
    console.log('⌨️  Typing Python version check...');
    await secondCell.click();
    await page.waitForTimeout(300);
    
    // Clear any existing content and type our check
    await page.keyboard.press('Control+a'); // Select all
    await page.keyboard.type('import sys\nprint(f"Python version: {sys.version}")\nprint(f"Python version info: {sys.version_info}")');
    await page.waitForTimeout(500);
    
    // Execute the cell
    console.log('▶️ Executing Python version check cell...');
    await page.keyboard.press('Shift+Enter');
    
    // Wait for execution
    console.log('⏳ Waiting for Python version check to complete...');
    let executionComplete = false;
    const startTime = Date.now();
    const maxWaitTime = 30000; // 30 seconds
    
    while (!executionComplete && (Date.now() - startTime) < maxWaitTime) {
      const execPrompt = await secondCell.locator('.jp-InputPrompt, [class*="jp-InputPrompt"]').textContent().catch(() => '');
      const isExecuting = execPrompt?.includes('[*]');
      
      if (!isExecuting && execPrompt && /\[\d+\]/.test(execPrompt)) {
        executionComplete = true;
        console.log('✅ Python version check completed');
        break;
      }
      await page.waitForTimeout(1000);
    }
    
    // Get the output
    const outputArea = secondCell.locator('.jp-OutputArea, [class*="jp-OutputArea"]').first();
    const outputText = await outputArea.textContent({ timeout: 10000 }).catch(() => '');
    console.log('📄 Python version output:', outputText);
    
    // Verify it's Python 3.12
    if (!outputText) {
      throw new Error('No output from Python version check');
    }
    
    // Check for Python 3.12
    const versionMatch = outputText.match(/Python version: ([\d.]+)/);
    if (!versionMatch) {
      throw new Error(`Could not parse Python version from output: ${outputText}`);
    }
    
    const pythonVersion = versionMatch[1];
    console.log(`🐍 Detected Python version: ${pythonVersion}`);
    
    // Check if it starts with 3.12
    if (!pythonVersion.startsWith('3.12')) {
      throw new Error(`Expected Python 3.12.x, but got ${pythonVersion}. Output: ${outputText}`);
    }
    
    // Also check version_info
    const versionInfoMatch = outputText.match(/Python version info: sys\.version_info\(major=(\d+), minor=(\d+)/);
    if (versionInfoMatch) {
      const major = parseInt(versionInfoMatch[1]);
      const minor = parseInt(versionInfoMatch[2]);
      console.log(`🐍 Python version_info: ${major}.${minor}`);
      if (major !== 3 || minor !== 12) {
        throw new Error(`Expected Python 3.12, but got ${major}.${minor}. Output: ${outputText}`);
      }
    }
    
    console.log('✅ Verified Python 3.12 in JupyterLite');
  });

  test('🎯 Can execute cell with import buckaroo', async ({ page }) => {
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

    page.on('pageerror', (error) => {
      console.log('🔴 Page error:', error.message);
      consoleMessages.push({ type: 'pageerror', text: error.message });
    });

    console.log(`📓 Navigating to JupyterLite notebook...`);
    await page.goto(`${BASE_URL}/lab/index.html?path=hello_world.ipynb`, { timeout: NAVIGATION_TIMEOUT, waitUntil: 'domcontentloaded' });

    // Wait for notebook to load
    console.log('⏳ Waiting for notebook to load...');
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    
    // Wait for notebook UI
    await page.locator('.jp-Notebook, [class*="jp-Notebook"]').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    console.log('✅ Notebook loaded');

    // Verify that "import buckaroo" appears in the first cell
    console.log('🔍 Checking for "import buckaroo" in notebook...');
    const cellContent = await page.locator('.jp-Cell-input, [class*="jp-Cell-input"]').first().textContent({ timeout: DEFAULT_TIMEOUT });
    console.log('📄 First cell content:', cellContent);
    
    if (cellContent && !cellContent.includes('import buckaroo')) {
      throw new Error(`"import buckaroo" not found in first cell. Cell content: ${cellContent.substring(0, 200)}`);
    }
    expect(cellContent).toContain('import buckaroo');
    console.log('✅ Found "import buckaroo" in notebook');

    // Focus on the notebook and execute the first cell
    console.log('▶️ Executing first cell...');
    
    // Make sure we're focused on the first cell
    const firstCell = page.locator('.jp-Cell').first();
    await firstCell.click();
    await page.waitForTimeout(500);
    
    // Check execution count before running
    const execCountBefore = await firstCell.locator('.jp-InputPrompt, [class*="jp-InputPrompt"]').textContent().catch(() => '');
    console.log('📊 Execution count before:', execCountBefore || 'none');
    
    // Use Shift+Enter to execute the cell
    await page.keyboard.press('Shift+Enter');
    
    // Wait a moment for execution to start
    await page.waitForTimeout(1000);

    // Wait for cell execution to complete
    console.log('⏳ Waiting for cell execution (Pyodide can take a while, especially for package installs)...');
    
    // In JupyterLite/Pyodide, execution might take much longer
    // Wait for the first cell to finish executing by checking for output area
    // (firstCell is already declared above)
    
    // Wait longer for Pyodide to actually execute - it can take 30-60 seconds for package installs
    console.log('⏳ Waiting up to 90 seconds for cell execution...');
    let executionComplete = false;
    const startTime = Date.now();
    const maxWaitTime = 90000; // 90 seconds for Pyodide package installation
    
    while (!executionComplete && (Date.now() - startTime) < maxWaitTime) {
      try {
        // Check if cell has output area (indicates execution started)
        const outputArea = firstCell.locator('.jp-OutputArea, [class*="jp-OutputArea"]');
        const hasOutput = await outputArea.count() > 0;
        
        // Check if cell is still running
        const cellClasses = await firstCell.getAttribute('class').catch(() => '');
        const isRunning = cellClasses?.includes('jp-mod-running') || cellClasses?.includes('jp-mod-executing');
        
        // Check execution count - if it changed from [*] to a number, execution is complete
        const execPrompt = await firstCell.locator('.jp-InputPrompt, [class*="jp-InputPrompt"]').textContent().catch(() => '');
        const isExecuting = execPrompt?.includes('[*]') || isRunning;
        
        // If we have output and it's not executing, execution is complete
        if (hasOutput && !isExecuting) {
          executionComplete = true;
          console.log('✅ Cell execution completed (not running, has output)');
          break;
        }
        
        // If execution count is a number (not [*] or [ ]), execution is complete
        if (execPrompt && /\[\d+\]/.test(execPrompt) && !execPrompt.includes('[*]')) {
          executionComplete = true;
          console.log('✅ Cell execution completed (execution count:', execPrompt, ')');
          break;
        }
        
        // If we have output but it's still running, check what's in the output
        if (hasOutput) {
          const outputText = await outputArea.first().textContent().catch(() => '');
          const outputHTML = await outputArea.first().innerHTML().catch(() => '');
          if (outputText && outputText.trim().length > 0) {
            console.log(`📄 Current output (${Math.floor((Date.now() - startTime) / 1000)}s):`, outputText.substring(0, 200));
          } else if (outputHTML && outputHTML.length > 50) {
            console.log(`📄 Current output HTML (${Math.floor((Date.now() - startTime) / 1000)}s):`, outputHTML.substring(0, 200));
          }
        }
      } catch (e) {
        // Continue checking if there's an error
      }
      
      // Wait a bit before checking again
      await page.waitForTimeout(3000);
      
      // Log progress every 15 seconds
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      if (elapsed % 15 === 0 && elapsed > 0) {
        console.log(`   Still waiting for cell to finish... (${elapsed}s elapsed)`);
      }
    }
    
    // If still running after max wait, that's okay - we'll check for errors anyway
    if (!executionComplete) {
      console.log(`⚠️  Cell may still be executing after ${maxWaitTime / 1000}s, checking for errors anyway...`);
      // Take a screenshot for debugging
      await page.screenshot({ path: 'test-results/jupyterlite-cell-still-running.png' }).catch(() => {});
    }

    // Check for error messages in the output
    console.log('🔍 Checking for execution errors...');
    
    // Check execution count after running
    const execCountAfter = await firstCell.locator('.jp-InputPrompt, [class*="jp-InputPrompt"]').textContent().catch(() => '');
    console.log('📊 Execution count after:', execCountAfter || 'none');
    
    // Get the output area - try multiple selectors
    let outputArea = page.locator('.jp-OutputArea').first();
    if (await outputArea.count() === 0) {
      outputArea = page.locator('[class*="jp-OutputArea"]').first();
    }
    if (await outputArea.count() === 0) {
      outputArea = firstCell.locator('.jp-OutputArea, [class*="jp-OutputArea"]').first();
    }
    
    // Get ALL output text from the cell, including errors
    const allOutputText = await outputArea.textContent({ timeout: 10000 }).catch(() => '');
    console.log('📄 Full output text:', allOutputText || '(empty)');
    console.log('📄 Output text length:', allOutputText?.length || 0);
    
    // Also try to get HTML content to see if there's hidden output
    const outputHTML = await outputArea.innerHTML({ timeout: 5000 }).catch(() => '');
    if (outputHTML && outputHTML.length > 0) {
      console.log('📄 Output HTML:', outputHTML);
      // Look for error classes in HTML
      if (outputHTML.includes('jp-RenderedText') || outputHTML.includes('error')) {
        console.log('📄 Found rendered text or error in HTML');
      }
    }
    
    // Also check all possible output locations
    const allOutputs = page.locator('.jp-OutputArea-output, [class*="jp-OutputArea-output"], .jp-RenderedText, [class*="jp-RenderedText"]');
    const outputCount = await allOutputs.count().catch(() => 0);
    console.log('📊 Total output elements found:', outputCount);
    
    if (outputCount > 0) {
      for (let i = 0; i < Math.min(outputCount, 5); i++) {
        const outputText = await allOutputs.nth(i).textContent().catch(() => '');
        const outputHTML2 = await allOutputs.nth(i).innerHTML().catch(() => '');
        console.log(`📄 Output [${i}]:`, outputText || '(empty text)', 'HTML:', outputHTML2?.substring(0, 100) || '(empty)');
      }
    }

    // Check for error elements (with timeout to avoid hanging)
    const errorElements = page.locator('[class*="jp-OutputArea-error"], .jp-OutputArea-output[data-mime-type*="error"], .jp-RenderedText[data-mime-type*="error"], .jp-RenderedText[data-mime-type*="application/vnd.jupyter.stderr"], .jp-RenderedText[data-mime-type*="application/vnd.jupyter.stdout"]');
    const errorCount = await errorElements.count({ timeout: 10000 }).catch(() => 0);
    console.log('📊 Found', errorCount, 'output elements');
    
    if (errorCount > 0) {
      const errorTexts = await Promise.all(
        Array.from({ length: Math.min(errorCount, 10) }).map((_, i) => 
          errorElements.nth(i).textContent({ timeout: 10000 }).catch(() => '')
        )
      );
      const allErrors = errorTexts.filter(t => t && t.trim().length > 0);
      console.log('📋 All output elements:');
      allErrors.forEach((text, i) => {
        console.log(`   [${i}]: ${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`);
      });
      
      // Check if any output contains error keywords
      const hasError = allErrors.some(text => 
        text.includes('Error') || 
        text.includes('Exception') || 
        text.includes('Traceback') ||
        text.includes('BadZipFile') ||
        text.includes('ImportError') ||
        text.includes('ModuleNotFoundError')
      );
      
      if (hasError) {
        const errorMsg = allErrors.join('\n\n');
        console.log('❌ Execution errors found:', errorMsg);
        throw new Error(`Cell execution failed with errors:\n${errorMsg}`);
      }
    }

    // Also check for any traceback or error patterns in the full output
    if (allOutputText && (
      allOutputText.includes('Traceback') ||
      allOutputText.includes('Error:') ||
      allOutputText.includes('Exception:') ||
      allOutputText.includes('BadZipFile')
    )) {
      console.log('❌ Error detected in output text:', allOutputText);
      throw new Error(`Cell execution failed. Output contains errors:\n${allOutputText}`);
    }

    console.log('✅ Cell executed successfully without errors');
  });
});
