/**
 * End-to-end test for the BuckarooServerView example app.
 *
 * Boots a real Buckaroo server + the example's Vite dev server (both
 * via playwright.config.ts webServer entries), opens the page, clicks
 * Load on the bundled citibike preset, and asserts the grid renders.
 *
 * What this proves:
 * - `/load` POST proxied through Vite reaches the Python server
 * - The server-issued `initial_state` reaches BuckarooServerView
 * - The WebSocket proxy (`/ws/<session>` → Buckaroo server) works
 * - Row data + column headers actually paint into AG-Grid
 */
import { test, expect } from "@playwright/test";

test.describe("BuckarooServerView playground", () => {
  test("loads the bundled citibike preset and renders grid cells", async ({ page }) => {
    await page.goto("/");

    // Pre-Load state: dropdown is there, no grid yet.
    await expect(page.getByRole("button", { name: /Load/ })).toBeVisible();
    await expect(page.getByText("Pick a dataset and hit Load.")).toBeVisible();

    // First preset is the bundled citibike file — just click Load.
    await page.getByRole("button", { name: /^Load$/ }).click();

    // Status text appears once /load returns. Citibike sample is 100k rows.
    await expect(page.getByText(/100,000 rows/)).toBeVisible({ timeout: 30_000 });

    // BuckarooServerView opens the WS, decodes initial_state, AG-Grid renders.
    await page
      .locator(".ag-cell")
      .first()
      .waitFor({ state: "visible", timeout: 20_000 });

    // A known column header from the citibike schema.
    await expect(page.locator(".ag-header-cell").getByText("tripduration")).toBeVisible();

    // At least a couple of body cells are populated.
    const cellCount = await page.locator(".ag-cell").count();
    expect(cellCount).toBeGreaterThan(5);
  });

  test("switching presets reconnects the view", async ({ page }) => {
    await page.goto("/");

    // Load citibike (preset index 0).
    await page.getByRole("button", { name: /^Load$/ }).click();
    await expect(page.getByText(/100,000 rows/)).toBeVisible({ timeout: 30_000 });
    await page
      .locator(".ag-cell")
      .first()
      .waitFor({ state: "visible", timeout: 20_000 });

    // Re-select citibike and reload — exercises the wsUrl `key` remount
    // path in App.tsx and confirms a second /load on the same session
    // returns metadata cleanly.
    await page.selectOption("select", "0");
    await page.getByRole("button", { name: /^Load$/ }).click();
    await expect(page.getByText(/100,000 rows/)).toBeVisible({ timeout: 30_000 });
    await page
      .locator(".ag-cell")
      .first()
      .waitFor({ state: "visible", timeout: 20_000 });
  });
});
