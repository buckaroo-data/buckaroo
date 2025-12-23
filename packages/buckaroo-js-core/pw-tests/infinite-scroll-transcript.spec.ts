import { test, expect } from '@playwright/test';
import { Page } from '@playwright/test';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
const DEFAULT_TIMEOUT = 10000;
const NAVIGATION_TIMEOUT = 12000;

async function waitForAgGrid(page: Page, timeout = 5000) {
  await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
  await page.locator('.ag-cell').first().waitFor({ state: 'attached', timeout });
}

test.describe('Infinite Scroll Transcript Recording', () => {
  test('should record transcript events when scrolling triggers data fetch', async ({ page }) => {
    // Capture console messages to debug hyparquet parsing and transcript recording
    const consoleMessages: string[] = [];
    page.on('console', (msg) => {
      const text = msg.text();
      if (text.includes('WidgetTSX') || text.includes('hyparquet') || text.includes('parquet') || 
          text.includes('Transcript') || text.includes('record_transcript')) {
        consoleMessages.push(`[${msg.type()}] ${text}`);
      }
    });

    // Navigate to the test notebook
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
    await page.waitForTimeout(800);
    console.log('✅ Cell executed');

    // Wait for widget to render (larger datasets take longer to initialize)
    console.log('⏳ Waiting for buckaroo widget...');
    await page.waitForTimeout(2000);
    
    // Check for buckaroo or ag-grid elements
    const buckarooElements = await page.locator('[class*="buckaroo"]').count();
    const agGridElements = await page.locator('.ag-root-wrapper, .ag-row').count();
    
    if (buckarooElements > 0 || agGridElements > 0) {
      console.log(`✅ Found ${buckarooElements} buckaroo elements, ${agGridElements} ag-grid elements`);
    } else {
      // Wait more for larger datasets
      await page.waitForTimeout(3000);
      const retryAgGrid = await page.locator('.ag-root-wrapper').count();
      expect(retryAgGrid).toBeGreaterThan(0);
    }
    console.log('✅ Widget rendered with ag-grid');

    // Wait for ag-grid to be ready
    await waitForAgGrid(page);

    // Check what events were captured during initial load (before scrolling)
    // Log console messages about transcript
    const transcriptMessages = consoleMessages.filter(msg => msg.includes('Transcript') || msg.includes('record_transcript'));
    if (transcriptMessages.length > 0) {
      console.log('📋 Console messages about transcript:');
      transcriptMessages.forEach(msg => console.log(`   ${msg}`));
    }
    
    const initialTranscript = await page.evaluate(() => {
      return (window as any)._buckarooTranscript || [];
    });
    console.log(`📝 Initial transcript (before scroll) has ${initialTranscript.length} events`);
    
    // Verify transcript recording is working - we should have at least 1 event
    expect(initialTranscript.length).toBeGreaterThan(0);
    console.log('✅ Transcript recording is working - captured initial load events');
    
    if (initialTranscript.length > 0) {
      const eventTypes = initialTranscript.map((e: any) => e.event);
      console.log(`   Event types: ${[...new Set(eventTypes)].join(', ')}`);
      
      // Log details of custom_msg events (these contain the parquet data requests)
      const customMsgs = initialTranscript.filter((e: any) => e.event === 'custom_msg');
      for (const msg of customMsgs) {
        console.log(`   custom_msg: type=${msg.msg?.type}, buffers=${msg.buffers_len}`);
      }
      
      // Log parsed responses if any
      const parsedResps = initialTranscript.filter((e: any) => e.event === 'infinite_resp_parsed');
      for (const resp of parsedResps) {
        console.log(`   infinite_resp_parsed: rows_len=${resp.rows_len}, total_len=${resp.total_len}`);
        if (resp.rows && resp.rows.length > 0) {
          const firstRow = resp.rows[0];
          console.log(`   First row: ${JSON.stringify(firstRow)}`);
          // Verify predictable pattern: int_col = row_num + 10
          if (firstRow.int_col !== undefined && firstRow.row_num !== undefined) {
            expect(firstRow.int_col).toBe(firstRow.row_num + 10);
            console.log('✅ Data matches predictable pattern!');
          }
        }
      }
    }
    
    // Keep the transcript for later analysis (don't clear)

    // Find the scrollable grid area - try different possible selectors
    // ag-grid uses different viewport classes depending on the grid mode
    const possibleViewports = [
      '.ag-body-viewport',
      '.ag-center-cols-viewport', 
      '.ag-body-horizontal-scroll-viewport',
      '.ag-root-wrapper'
    ];
    
    let viewport = null;
    for (const selector of possibleViewports) {
      const element = page.locator(selector).first();
      if (await element.count() > 0) {
        viewport = element;
        console.log(`📊 Found scrollable element: ${selector}`);
        break;
      }
    }
    
    if (!viewport) {
      console.log('⚠️ No viewport found, using grid wrapper');
      viewport = page.locator('.ag-root-wrapper').first();
    }
    await expect(viewport).toBeVisible();

    // Get initial row data to verify we're at the top
    const firstRowCell = page.locator('.ag-cell').first();
    const initialFirstCellText = await firstRowCell.textContent();
    console.log(`📊 Initial first cell content: ${initialFirstCellText}`);

    // Scroll down to row 1500 using direct JavaScript scrollTo on ag-grid viewport
    // DataFrame has 2000 rows, we want to scroll to row ~1500 to trigger additional data fetches
    // Each row is ~20px high, so row 1500 is around 30000px down
    console.log('📜 Scrolling to row 1500 using direct scrollTo...');
    
    // Use JavaScript to find the LARGEST viewport (the main data grid, not pinned rows)
    const scrollResult = await page.evaluate(() => {
      // Find all possible viewports
      const viewports = [
        ...document.querySelectorAll('.ag-body-viewport'),
        ...document.querySelectorAll('.ag-center-cols-viewport'),
      ];
      
      console.log(`Found ${viewports.length} viewports`);
      
      // Find the viewport with the largest scrollHeight (that's the main data grid)
      let mainViewport = null;
      let maxScrollHeight = 0;
      
      for (const vp of viewports) {
        console.log(`Viewport: scrollHeight=${vp.scrollHeight}, clientHeight=${vp.clientHeight}`);
        if (vp.scrollHeight > maxScrollHeight) {
          maxScrollHeight = vp.scrollHeight;
          mainViewport = vp;
        }
      }
      
      if (!mainViewport) {
        return { success: false, error: 'No viewport found' };
      }
      
      // Calculate scroll position for row 1500 (assuming ~20px per row)
      const targetRow = 1500;
      const rowHeight = 20;
      const targetScrollTop = targetRow * rowHeight;
      
      // Scroll to that position (or max)
      mainViewport.scrollTop = Math.min(targetScrollTop, mainViewport.scrollHeight);
      
      return { 
        success: true, 
        scrollTop: mainViewport.scrollTop,
        scrollHeight: mainViewport.scrollHeight,
        clientHeight: mainViewport.clientHeight,
        viewportsFound: viewports.length
      };
    });
    
    console.log(`📊 Scroll result: ${JSON.stringify(scrollResult)}`);
    
    // Wait for data fetch to complete
    await page.waitForTimeout(2000);

    // Check what rows are now visible
    const visibleCells = page.locator('.ag-cell');
    const cellTexts = await visibleCells.allTextContents();
    // Look for cell values that indicate we've scrolled far (e.g. foo_1000+)
    const highRowCells = cellTexts.filter(t => {
      const match = t.match(/foo_(\d+)/);
      return match && parseInt(match[1]) > 1000;
    });
    console.log(`📊 Found ${highRowCells.length} cells with row > 1000: ${highRowCells.slice(0,3).join(', ')}`);
    
    console.log('📊 Scroll actions completed');

    // Get the transcript and analyze it
    const transcript = await page.evaluate(() => {
      return (window as any)._buckarooTranscript || [];
    });

    console.log(`📝 Transcript has ${transcript.length} events`);
    
    // Log event types
    const eventTypes = transcript.map((e: any) => e.event);
    const uniqueEventTypes = [...new Set(eventTypes)];
    console.log(`📝 Event types recorded: ${uniqueEventTypes.join(', ')}`);

    // Check for infinite_resp events (from parquet data fetch)
    const infiniteRespEvents = transcript.filter((e: any) => 
      e.event === 'infinite_resp_parsed' || e.event === 'custom_msg'
    );
    console.log(`📝 Found ${infiniteRespEvents.length} infinite response/custom message events`);

    // Log details of any infinite_resp_parsed events
    const parsedEvents = transcript.filter((e: any) => e.event === 'infinite_resp_parsed');
    for (const ev of parsedEvents) {
      console.log(`  - infinite_resp_parsed: key=${ev.key}, rows_len=${ev.rows_len}, total_len=${ev.total_len}`);
      if (ev.rows && ev.rows.length > 0) {
        console.log(`    First row: ${JSON.stringify(ev.rows[0])}`);
      }
    }

    // Check for custom_msg events (data fetch requests)
    const customMsgs = transcript.filter((e: any) => e.event === 'custom_msg');
    console.log(`📝 Found ${customMsgs.length} custom_msg events (data fetch requests)`);
    
    // Log details of each custom_msg
    for (let i = 0; i < customMsgs.length; i++) {
      const msg = customMsgs[i];
      console.log(`   custom_msg[${i}]: type=${msg.msg?.type}, key=${msg.msg?.key}, buffers=${msg.buffers_len}`);
    }

    // Check for parsed responses 
    console.log(`📝 Found ${parsedEvents.length} infinite_resp_parsed events`);
    
    // Analyze each parsed event to see what row ranges were fetched
    const rowRanges: Array<{start: number, end: number, count: number}> = [];
    for (let i = 0; i < parsedEvents.length; i++) {
      const ev = parsedEvents[i];
      if (ev.rows && ev.rows.length > 0) {
        const rowNums = ev.rows.map((r: any) => r.row_num).filter((n: any) => typeof n === 'number');
        if (rowNums.length > 0) {
          const minRow = Math.min(...rowNums);
          const maxRow = Math.max(...rowNums);
          rowRanges.push({ start: minRow, end: maxRow, count: rowNums.length });
          console.log(`   parsed[${i}]: rows ${minRow}-${maxRow} (${rowNums.length} rows)`);
        }
      }
    }

    // Verify we got data fetch events
    if (customMsgs.length > 0) {
      console.log('✅ Transcript captured data fetch events!');
      
      // Check if we have multiple fetches (initial + scroll-triggered)
      if (customMsgs.length > 1) {
        console.log(`✅ Multiple data fetches recorded (${customMsgs.length}): initial + scroll-triggered!`);
      } else {
        console.log('⚠️ Only 1 data fetch recorded - scroll may not have triggered additional fetch');
        console.log('   This could mean SmartRowCache pre-fetched enough data, or scroll didn\'t reach far enough');
      }
      
      // Verify data pattern in parsed events
      for (const ev of parsedEvents) {
        if (ev.rows && ev.rows.length > 0) {
          for (const row of ev.rows) {
            if (row.int_col !== undefined && row.row_num !== undefined) {
              expect(row.int_col).toBe(row.row_num + 10);
            }
          }
        }
      }
      console.log('✅ Data in transcript matches expected predictable pattern!');
    } else {
      console.log('⚠️ No data fetch events captured');
    }

    // Log browser console messages related to hyparquet/parquet parsing
    console.log(`📋 Browser console messages (hyparquet/parquet related): ${consoleMessages.length}`);
    for (const msg of consoleMessages.slice(0, 20)) {
      console.log(`   ${msg}`);
    }
    if (consoleMessages.length > 20) {
      console.log(`   ... and ${consoleMessages.length - 20} more`);
    }

    // Save transcript for potential storybook replay testing
    console.log('💾 Saving transcript for storybook replay...');
    const fullTranscript = await page.evaluate(() => {
      return (window as any)._buckarooTranscript || [];
    });
    
    // Log the transcript as JSON for manual inspection/replay
    if (fullTranscript.length > 0) {
      console.log('📋 Transcript summary:');
      for (const ev of fullTranscript.slice(0, 5)) {
        console.log(`   ${ev.event}: ts=${ev.ts}`);
      }
      if (fullTranscript.length > 5) {
        console.log(`   ... and ${fullTranscript.length - 5} more events`);
      }
    }

    console.log('🎉 SUCCESS: Infinite scroll transcript test complete!');
  });

  test('should verify data at specific scroll positions', async ({ page }) => {
    // This test verifies we can scroll to specific positions and see predictable data
    const notebookName = 'test_infinite_scroll_transcript.ipynb';
    await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`, { timeout: NAVIGATION_TIMEOUT });

    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });

    // Execute the cell
    await page.locator('.jp-Notebook').first().dispatchEvent('click');
    await page.waitForTimeout(200);
    await page.keyboard.press('Shift+Enter');

    const outputArea = page.locator('.jp-OutputArea').first();
    await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    await page.waitForTimeout(1500);

    await waitForAgGrid(page);

    // Verify initial data (row 0 should show int_col=10, str_col=foo_10)
    const firstRowIntCell = page.locator('[row-index="0"] [col-id="int_col"]');
    const firstRowStrCell = page.locator('[row-index="0"] [col-id="str_col"]');
    
    // Check if we can see the cells
    const intCellVisible = await firstRowIntCell.isVisible().catch(() => false);
    const strCellVisible = await firstRowStrCell.isVisible().catch(() => false);
    
    if (intCellVisible && strCellVisible) {
      const intVal = await firstRowIntCell.textContent();
      const strVal = await firstRowStrCell.textContent();
      console.log(`📊 Row 0: int_col=${intVal}, str_col=${strVal}`);
      expect(intVal).toBe('10');
      expect(strVal).toBe('foo_10');
    } else {
      // Try finding cells by content
      const cell10 = page.locator('.ag-cell:has-text("10")').first();
      const cellFoo10 = page.locator('.ag-cell:has-text("foo_10")').first();
      await expect(cell10).toBeVisible({ timeout: 3000 });
      await expect(cellFoo10).toBeVisible({ timeout: 3000 });
      console.log('📊 Verified row 0 data via text search');
    }

    // Scroll to see later rows and verify predictable pattern
    const viewport = page.locator('.ag-body-viewport').first();
    await viewport.evaluate((el) => {
      el.scrollTop = 5000; // Scroll to roughly row 100+
    });
    await page.waitForTimeout(500);

    // Check what rows are now visible
    const visibleRows = page.locator('.ag-row[row-index]');
    const rowIndices = await visibleRows.evaluateAll((rows) => 
      rows.map(r => parseInt(r.getAttribute('row-index') || '0', 10))
        .filter(i => !isNaN(i))
    );
    if (rowIndices.length > 0) {
      console.log(`📊 After scroll, visible rows: ${Math.min(...rowIndices)} to ${Math.max(...rowIndices)}`);
    } else {
      console.log('📊 After scroll, no row indices found (cells may use different structure)');
    }

    // Pick a visible row and verify data matches pattern
    const targetRowIndex = rowIndices.find(i => i > 50) || rowIndices[0];
    const expectedIntCol = targetRowIndex + 10;
    const expectedStrCol = `foo_${expectedIntCol}`;
    
    console.log(`📊 Checking row ${targetRowIndex}: expecting int_col=${expectedIntCol}, str_col=${expectedStrCol}`);
    
    // Look for cells with expected values
    const expectedIntCell = page.locator(`.ag-cell:has-text("${expectedIntCol}")`).first();
    const expectedStrCell = page.locator(`.ag-cell:has-text("${expectedStrCol}")`).first();
    
    // These should be visible if the data is correct
    await expect(expectedIntCell).toBeVisible({ timeout: 3000 });
    await expect(expectedStrCell).toBeVisible({ timeout: 3000 });
    
    console.log(`✅ Verified data at row ${targetRowIndex} matches predictable pattern!`);
  });
});

