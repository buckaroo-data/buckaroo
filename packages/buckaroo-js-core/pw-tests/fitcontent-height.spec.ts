/**
 * Playwright test for the `layoutType: "fitContent"` height mode.
 *
 * The FitContentHeight story mounts the widget (5 rows) in a 600px container.
 * In fitContent mode the widget sizes its own box to its content, so:
 *   1. The widget root (.buckaroo-widget) is far shorter than the 600px host.
 *   2. There is no gap between the bottom of the table and the bottom of the
 *      widget (the widget ends flush with its content).
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-fitcontentheight--primary&globals=&args=";

const CONTAINER_HEIGHT = 600;

test.describe("fitContent layout mode", () => {
  test("widget sizes to its content, not the 600px host container", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    const dataGrid = page.locator(".df-viewer");
    await expect
      .poll(async () => (await dataGrid.textContent())?.includes("Alice"), { timeout: 10_000 })
      .toBe(true);

    // 1. The widget root collapsed well under the 600px container height.
    await expect
      .poll(
        async () => {
          const box = await page.locator(".buckaroo-widget").boundingBox();
          return box ? Math.round(box.height) : CONTAINER_HEIGHT;
        },
        { timeout: 10_000, message: "Expected the widget to shrink below the 600px container" }
      )
      .toBeLessThan(CONTAINER_HEIGHT - 150);

    // 2. No gap: the widget root ends flush with its content (.orig-df).
    const gap = await page.evaluate(() => {
      const root = document.querySelector(".buckaroo-widget");
      const content = document.querySelector(".buckaroo-widget .orig-df");
      if (!root || !content) return 9999;
      return Math.round(root.getBoundingClientRect().bottom - content.getBoundingClientRect().bottom);
    });
    expect(gap).toBeLessThanOrEqual(8);
  });
});
