/**
 * Playwright tests for BuckarooInfiniteWidget storybook story.
 *
 * Tests two bugs:
 *   1. Toggling to "summary" view should show pinned summary stats rows
 *   2. Searching should filter the actual table data, not just the status bar count
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-buckaroowidgettest--primary&globals=&args=";

test.describe("BuckarooInfiniteWidget", () => {
  test("summary view toggle shows pinned summary stats rows", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // Wait for data to load in the main data grid (not the status bar grid)
    const dataGrid = page.locator(".df-viewer");
    await expect.poll(
      async () => {
        const text = await dataGrid.textContent();
        return text?.includes("Alice");
      },
      { timeout: 10_000 }
    ).toBe(true);

    // Toggle to "summary" view via the <select> dropdown in the StatusBar
    const dfDisplaySelect = page.locator('.ag-cell[col-id="df_display"] select');
    await dfDisplaySelect.selectOption("summary");

    // After toggling, the summary view should show pinned rows (summary stats).
    // Pinned rows appear in .ag-floating-top inside the .df-viewer grid.
    // The summary stats have rows like "dtype", "count", "unique", "mean", "min", "max"
    await expect.poll(
      async () => {
        const pinnedTop = dataGrid.locator(".ag-floating-top");
        const text = await pinnedTop.textContent();
        return text || "";
      },
      { timeout: 10_000, message: "Expected pinned summary stats rows to appear" }
    ).toContain("dtype");
  });

  test("search filters the table data, not just the status bar", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // Wait for initial data load
    const dataGrid = page.locator(".df-viewer");
    await expect.poll(
      async () => {
        const text = await dataGrid.textContent();
        return text?.includes("Alice") && text?.includes("Bob");
      },
      { timeout: 10_000 }
    ).toBe(true);

    // Type "Alice" in the search input and press Enter
    const searchInput = page.locator(".FakeSearchEditor input[type='text']");
    await searchInput.fill("Alice");
    await searchInput.press("Enter");

    // The table data should update to show only matching rows.
    // With the bug, the grid still shows all 5 rows because quick_command_args
    // wasn't included in mainDs deps or outsideDFParams.
    await expect.poll(
      async () => {
        const text = await dataGrid.textContent();
        // Alice should be present, Bob should not
        return text?.includes("Alice") && !text?.includes("Bob");
      },
      { timeout: 10_000, message: "Expected search to filter table: Alice visible, Bob not visible" }
    ).toBe(true);
  });
});
