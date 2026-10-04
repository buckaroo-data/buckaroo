/**
 * Playwright test for the client states of the stats wire (rows-first c4).
 *
 * The StatsSchedulerStates story flips df_meta.stats.status. Each status has
 * its own text in the status bar's stats column, and the pinned area follows it
 * as in c0a. Switching between statuses moves nothing above or beside the grid:
 * the status bar keeps its box, and the grid keeps its position and width. The
 * grid's height changes only with the pinned area: placeholders hold the height
 * of the values that replace them, and omitted rows take theirs away. In
 * "not_computed" the status bar offers a Compute summary stats button, which
 * sends stats_request {force: true}.
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
  // Nothing above or beside the grid moves, whatever the status.
  const staysPut = async () => {
    const now = await boxes(page);
    expect(now.statusBar).toEqual(reference.statusBar);
    expect(now.grid).toMatchObject({ x: reference.grid!.x, y: reference.grid!.y, width: reference.grid!.width });
    return now;
  };

  // not_computed: the control, and no pinned rows.
  await page.getByTestId("status-not_computed").click();
  await expect(statsCell).toHaveAttribute("data-stats-status", "not_computed");
  await expect(page.getByRole("button", { name: "Compute summary stats" })).toBeVisible();
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual([]);
  const withoutPinned = await staysPut();
  // The omitted rows take their height with them.
  expect(withoutPinned.grid!.height).toBeLessThan(reference.grid!.height);

  // error: the reason, and no pinned rows.
  await page.getByTestId("status-error").click();
  await expect(statsCell).toHaveAttribute("data-stats-status", "error");
  await expect(statsCell).toContainText("Stats error: stats_failed");
  await expect.poll(distinctPinnedRowIds, { timeout: 10_000 }).toEqual([]);
  expect((await staysPut()).grid).toEqual(withoutPinned.grid);

  // complete: the values are in the pinned area where the placeholders were, so
  // the grid is as tall as it was while pending.
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
