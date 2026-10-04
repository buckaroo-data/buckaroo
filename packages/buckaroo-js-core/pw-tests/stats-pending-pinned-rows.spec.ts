/**
 * Playwright test for the client states of the two-message protocol
 * (rows-first c0a).
 *
 * While summary stats have not arrived, `df_meta.stats.status` decides what
 * the pinned area shows. The StatsPendingPinnedRows story flips the status and
 * supplies the stats on "complete":
 *   - pending: every valueless pinned key shows a placeholder row with its own
 *     row id
 *   - not_computed: valueless pinned keys are omitted
 *   - complete: the values appear and the color-mapped column restyles
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-statspendingpinnedrows--primary&globals=&args=";

test("pinned rows follow df_meta.stats.status: placeholders, omitted, then values and colors", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  await page.goto(STORY_URL);
  await waitForCells(page);

  const pinnedRows = page.locator(".ag-floating-top .ag-row");
  const distinctPinnedRowIds = async () => {
    const ids = await pinnedRows.evaluateAll((els) => els.map((e) => e.getAttribute("row-id")));
    return Array.from(new Set(ids)).sort();
  };
  const bodyCellA = page.locator('.ag-center-cols-container .ag-row[row-index="0"] [col-id="a"]');
  const backgroundOf = (loc: typeof bodyCellA) => loc.evaluate((el) => getComputedStyle(el).backgroundColor);

  // pending: one placeholder per pinned key, each with its own row id.
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual(["main-dtype", "main-mean"]);
  await expect(bodyCellA).toHaveText("1");
  const backgroundBeforeBins = await backgroundOf(bodyCellA);

  // not_computed: the valueless keys are omitted.
  await page.getByTestId("status-not_computed").click();
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual([]);

  // complete: the values appear, and the color-mapped column restyles now
  // that its histogram bins exist.
  await page.getByTestId("status-complete").click();
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual(["main-dtype", "main-mean"]);
  await expect(page.locator('.ag-floating-top .ag-cell[col-id="a"]').first()).toHaveText("int64");
  await expect.poll(() => backgroundOf(bodyCellA), { timeout: 10_000 }).not.toBe(backgroundBeforeBins);
  expect(pageErrors).toEqual([]);
});
