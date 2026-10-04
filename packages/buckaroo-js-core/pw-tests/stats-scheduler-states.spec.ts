/**
 * Playwright test for the client states of the stats wire (rows-first c4).
 *
 * The StatsSchedulerStates story flips df_meta.stats.status. Each status has
 * its own text in the status bar's stats column, the pinned area follows it as
 * in c0a, and switching between them moves nothing: the status bar and the
 * grid keep their boxes. In "not_computed" the status bar offers a Compute
 * summary stats button, which sends stats_request {force: true}.
 */
import { test, expect, Page } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-statsschedulerstates--primary&globals=&args=";

const boxes = async (page: Page) => {
  const round = (b: { x: number; y: number; width: number; height: number } | null) =>
    b && { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height) };
  return {
    statusBar: round(await page.locator(".status-bar").boundingBox()),
    grid: round(await page.locator(".df-viewer").boundingBox()),
    widget: round(await page.locator(".buckaroo-widget").boundingBox()),
  };
};

test("each stats status shows its own text in the status bar and nothing moves between them", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  await page.goto(STORY_URL);
  await waitForCells(page);

  const statsCell = page.getByTestId("stats-status");
  const pinnedRows = page.locator(".ag-floating-top .ag-row");
  const distinctPinnedRowIds = async () => {
    const ids = await pinnedRows.evaluateAll((els) => els.map((e) => e.getAttribute("row-id")));
    return Array.from(new Set(ids)).sort();
  };

  // pending: the loading text, and a placeholder for each pinned key.
  await expect(statsCell).toHaveAttribute("data-stats-status", "pending");
  await expect(statsCell).toContainText("Computing summary stats");
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual(["main-dtype", "main-mean"]);
  const reference = await boxes(page);
  expect(reference.statusBar).not.toBeNull();
  expect(reference.grid).not.toBeNull();

  // not_computed: the control, and no pinned rows.
  await page.getByTestId("status-not_computed").click();
  await expect(statsCell).toHaveAttribute("data-stats-status", "not_computed");
  await expect(page.getByRole("button", { name: "Compute summary stats" })).toBeVisible();
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual([]);
  expect(await boxes(page)).toEqual(reference);

  // error: the reason, and no pinned rows.
  await page.getByTestId("status-error").click();
  await expect(statsCell).toHaveAttribute("data-stats-status", "error");
  await expect(statsCell).toContainText("Stats error: stats_failed");
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual([]);
  expect(await boxes(page)).toEqual(reference);

  // complete: the values are in the pinned area where the placeholders were.
  await page.getByTestId("status-complete").click();
  await expect(statsCell).toHaveAttribute("data-stats-status", "complete");
  await expect(statsCell).toContainText("Summary stats ready");
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual(["main-dtype", "main-mean"]);
  await expect(page.locator('.ag-floating-top .ag-cell[col-id="a"]').first()).toHaveText("int64");
  expect(await boxes(page)).toEqual(reference);

  expect(pageErrors).toEqual([]);
});

test("the Compute summary stats control sends stats_request with force", async ({ page }) => {
  await page.goto(STORY_URL);
  await waitForCells(page);

  await page.getByTestId("status-not_computed").click();
  await page.getByRole("button", { name: "Compute summary stats" }).click();

  const sent = page.getByTestId("sent-log");
  await expect.poll(async () => JSON.parse((await sent.textContent()) ?? "[]")).toEqual([
    { type: "stats_request", stats_gen: 7, scope: "raw", force: true },
  ]);
});

test("no control is offered while the stats are pending, in error or complete", async ({ page }) => {
  await page.goto(STORY_URL);
  await waitForCells(page);

  const control = page.getByRole("button", { name: "Compute summary stats" });
  for (const status of ["pending", "error", "complete"]) {
    await page.getByTestId(`status-${status}`).click();
    await expect(page.getByTestId("stats-status")).toHaveAttribute("data-stats-status", status);
    await expect(control).toHaveCount(0);
  }
});
