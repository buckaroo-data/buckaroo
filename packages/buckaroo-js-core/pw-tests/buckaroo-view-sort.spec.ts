/**
 * BuckarooView host sort (#984), against the BuckarooViewSort story.
 *
 * The story's fake model records the first infinite_request and serves rows
 * sorted the way the server would. The host passes
 * sort={ column: "fare", direction: "desc" }, where "fare" is the header of
 * the visible column `c` (a hidden column `b` carries the same header).
 */
import { test, expect } from "@playwright/test";
import { getCellLocator, waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-server-buckarooviewsort--host-sort&globals=&args=";

const lastSortChange = async (page: import("@playwright/test").Page) => {
  const changes = JSON.parse((await page.getByTestId("sort-changes").textContent()) || "[]");
  return changes.length ? changes[changes.length - 1] : "none";
};

test.describe("BuckarooView host sort", () => {
  test("the first row request already carries the host's sort, on the visible column", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    await expect(page.getByTestId("first-request")).toHaveText(
      JSON.stringify({ sort: "c", sort_direction: "desc" }),
    );
    await expect(getCellLocator(page, "a", 0)).toHaveText("Cumings");
    await expect(getCellLocator(page, "a", 1)).toHaveText("Futrelle");
  });

  test("sorting from a header reports the header name to onSortChange", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    await page.locator('.ag-header-cell[col-id="a"] .ag-header-cell-label').click();

    await expect.poll(() => lastSortChange(page), { timeout: 5000 }).toEqual({ column: "name", direction: "asc" });
    await expect(getCellLocator(page, "a", 0)).toHaveText("Allen");
  });
});
