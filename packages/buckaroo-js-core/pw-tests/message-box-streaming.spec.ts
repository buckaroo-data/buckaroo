import { test, expect } from "@playwright/test";
import { agGridTest, waitForCells } from "./ag-pw-utils";

test.describe("MessageBox Streaming Updates", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to Storybook with the StreamingMessages story
    await page.goto(
      "http://localhost:6006/iframe.html?args=&id=buckaroo-messagebox--streaming-messages&viewMode=story"
    );
  });

  test("should display message box with red border", async ({ page }) => {
    const messageBox = page.locator('div[style*="border: 1px solid red"]');
    await expect(messageBox).toBeVisible();
  });

  test("should start with empty messages", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    const rowCount = await grid.getRowCount();
    expect(rowCount).toBe(0);
  });

  test("should add messages when streaming starts", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    
    // Click the start streaming button
    const startButton = page.getByRole("button", { name: /Start Streaming Messages/i });
    await startButton.click();
    
    // Wait for first message (cache message)
    await page.waitForTimeout(600);
    await grid.waitForCells();
    let rowCount = await grid.getRowCount();
    expect(rowCount).toBeGreaterThan(0);
    
    // Wait for second message (cache info)
    await page.waitForTimeout(600);
    await grid.waitForCells();
    rowCount = await grid.getRowCount();
    expect(rowCount).toBeGreaterThanOrEqual(2);
    
    // Wait for execution messages
    await page.waitForTimeout(2000);
    await grid.waitForCells();
    rowCount = await grid.getRowCount();
    expect(rowCount).toBeGreaterThanOrEqual(3);
  });

  test("should update table as new messages arrive", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    
    // Start streaming
    const startButton = page.getByRole("button", { name: /Start Streaming Messages/i });
    await startButton.click();
    
    // Wait for initial messages
    await page.waitForTimeout(2000);
    await grid.waitForCells();
    const initialRowCount = await grid.getRowCount();
    expect(initialRowCount).toBeGreaterThan(0);
    
    // Wait for more messages to arrive
    await page.waitForTimeout(3000);
    await grid.waitForCells();
    const finalRowCount = await grid.getRowCount();
    expect(finalRowCount).toBeGreaterThan(initialRowCount);
  });

  test("should display message columns correctly", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    
    // Start streaming
    const startButton = page.getByRole("button", { name: /Start Streaming Messages/i });
    await startButton.click();
    
    // Wait for messages
    await page.waitForTimeout(2000);
    await grid.waitForCells();
    
    // Check that expected columns exist by trying to get header locators
    const indexHeader = grid.getHeaderLocator({ colHeaderName: "index" });
    await expect(indexHeader).toBeVisible();
    
    const timeHeader = grid.getHeaderLocator({ colHeaderName: "time" });
    await expect(timeHeader).toBeVisible();
    
    const typeHeader = grid.getHeaderLocator({ colHeaderName: "type" });
    await expect(typeHeader).toBeVisible();
    
    const messageHeader = grid.getHeaderLocator({ colHeaderName: "message" });
    await expect(messageHeader).toBeVisible();
  });

  test("should handle execution messages with all fields", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    
    // Start streaming
    const startButton = page.getByRole("button", { name: /Start Streaming Messages/i });
    await startButton.click();
    
    // Wait for execution messages
    await page.waitForTimeout(5000);
    await grid.waitForCells();
    
    // Check that we have rows
    const rowCount = await grid.getRowCount();
    expect(rowCount).toBeGreaterThan(0);
    
    // Check first few rows for execution type
    let foundExecution = false;
    for (let i = 0; i < Math.min(rowCount, 10); i++) {
      try {
        const rowContents = await grid.getRowContents(i);
        const typeIndex = rowContents.findIndex((val, idx) => {
          // Find the type column by checking header
          return val === "execution";
        });
        if (typeIndex >= 0) {
          foundExecution = true;
          // Check for status column nearby
          const statusCell = await grid.getCellLocatorBy({ rowIndex: i, colHeaderName: "status" });
          const status = await statusCell.innerText();
          expect(["started", "finished", "error"]).toContain(status);
          break;
        }
      } catch (e) {
        // Continue to next row
      }
    }
    expect(foundExecution).toBe(true);
  });

  test("should show message count indicator", async ({ page }) => {
    const grid = agGridTest(page);
    await grid.waitForCells();
    
    // Start streaming
    const startButton = page.getByRole("button", { name: /Start Streaming Messages/i });
    await startButton.click();
    
    // Wait for messages
    await page.waitForTimeout(2000);
    
    // Check that message count is displayed
    const messageCountText = page.locator("text=/\\d+ message/i");
    await expect(messageCountText).toBeVisible();
  });
});

