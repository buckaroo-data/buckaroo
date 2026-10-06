/**
 * Playwright test for summary stats that arrive after the rows (rows-first
 * c0a), on the StatsPendingPinnedRows "Manual" story.
 *
 * Before the stats arrive every pinned key shows a placeholder row with its own
 * row id, its label, and empty cells. After "Deliver stats now" the values
 * appear and the color-mapped column restyles.
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-statspendingpinnedrows--manual&globals=&args=";

test("pinned rows are placeholders until the summary stats arrive, then values and colors", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  await page.goto(STORY_URL);
  await waitForCells(page);

  const pinnedRows = page.locator(".ag-floating-top .ag-row");
  const distinctPinnedRowIds = async () => {
    const ids = await pinnedRows.evaluateAll((els) => els.map((e) => e.getAttribute("row-id")));
    return Array.from(new Set(ids)).sort();
  };
  const pinnedCell = (rowId: string, colId: string) =>
    page.locator(`.ag-floating-top .ag-row[row-id="${rowId}"] [col-id="${colId}"]`);
  const bodyCellA = page.locator('.ag-center-cols-container .ag-row[row-index="0"] [col-id="a"]');
  const backgroundOf = (loc: typeof bodyCellA) => loc.evaluate((el) => getComputedStyle(el).backgroundColor);

  // Before the stats: one placeholder per pinned key, labelled, value cells empty.
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual(["main-dtype", "main-histogram", "main-mean"]);
  await expect(pinnedCell("main-dtype", "index")).toHaveText("dtype");
  await expect(pinnedCell("main-dtype", "a")).toHaveText("");
  await expect(pinnedCell("main-mean", "a")).toHaveText("");
  await expect(bodyCellA).toHaveText("0");
  const backgroundBeforeBins = await backgroundOf(bodyCellA);

  // The stats arrive: values appear, and the color-mapped column restyles now
  // that its histogram bins exist.
  await page.getByTestId("deliver-stats").click();
  await expect(pinnedCell("main-dtype", "a")).toHaveText("int64");
  await expect(pinnedCell("main-mean", "b")).not.toHaveText("");
  await expect.poll(distinctPinnedRowIds).toEqual(["main-dtype", "main-histogram", "main-mean"]);
  await expect.poll(() => backgroundOf(bodyCellA), { timeout: 10_000 }).not.toBe(backgroundBeforeBins);
  expect(pageErrors).toEqual([]);
});
