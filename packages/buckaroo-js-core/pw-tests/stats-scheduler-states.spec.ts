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
 * sends stats_request {force: true, incremental: true} with the columns the grid
 * shows (rows-first c4b). While the stats are pending, a stat row that has
 * arrived for some columns leaves the cells of the others empty.
 *
 * The NotComputed story (rows-first c5) is a session the server's policy left
 * without stats. Its main view renders typed columns over the schema-tier
 * stats with no blank pinned row, its summary view shows why the stats are
 * missing with the control that asks for them (basic before full, with a
 * per-column form), and over the ceiling it says so and offers nothing.
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

test("the Compute summary stats control sends an incremental stats_request with force and a tier, and no columns hint", async ({ page }) => {
  await page.goto(STORY_URL);
  await waitForCells(page);

  await page.getByTestId("status-not_computed").click();
  await page.getByRole("button", { name: "Compute summary stats" }).click();

  // The story's server names no requestable tier, so the one it can be asked for
  // is full. The grid shows columns a and b, and the whole-table request does not
  // send them: on a forced request `columns` names what it is for (rows-first c5).
  const sent = page.getByTestId("sent-log");
  await expect.poll(async () => JSON.parse((await sent.textContent()) ?? "[]")).toEqual([
    { type: "stats_request", stats_gen: 7, scope: "raw", incremental: true, force: true, tier: "full" },
  ]);
});

test("a stat row that has arrived for one column leaves the other columns' cells empty while the stats are pending", async ({ page }) => {
  await page.goto(STORY_URL);
  await waitForCells(page);

  await page.getByTestId("status-partial").click();
  await expect(page.getByTestId("stats-status")).toHaveAttribute("data-stats-status", "pending");
  await expect(page.getByTestId("stats-status")).toContainText("Computing summary stats");

  const meanCell = (col: string) => page.locator(`.ag-floating-top .ag-row[row-id="main-mean"] [col-id="${col}"]`);
  await expect(meanCell("a")).toHaveText("2", { timeout: 10_000 });
  // Column b has no mean yet: the cell is empty.
  await expect(meanCell("b")).toHaveText("");
  // dtype came with the schema, for both columns.
  await expect(page.locator('.ag-floating-top .ag-row[row-id="main-dtype"] [col-id="b"]')).toHaveText("object");

  // The stats arrive for column b too: the cell fills in.
  await page.getByTestId("status-complete").click();
  await expect(meanCell("b")).toHaveText("N/A", { timeout: 10_000 });
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

const NOT_COMPUTED_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-statsschedulerstates--not-computed&globals=&args=";

const sentLog = async (page: Page): Promise<any[]> => JSON.parse((await page.getByTestId("sent-log").textContent()) ?? "[]");

test("a not computed session renders typed columns with no blank pinned rows", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  await page.goto(NOT_COMPUTED_URL);
  await waitForCells(page);

  // The columns are typed from the schema: integers without decimals, floats
  // with three, strings as they are.
  const firstRow = (col: string) => page.locator(`.ag-center-cols-container .ag-row[row-index="0"] [col-id="${col}"]`);
  await expect(firstRow("a")).toHaveText("1");
  await expect(firstRow("b")).toHaveText("x");
  await expect(firstRow("c")).toHaveText("1.500");

  // dtype came with the schema. histogram has no value and none is coming, so
  // there is one pinned row and no blank one.
  const pinnedRows = page.locator(".df-viewer .ag-floating-top .ag-row");
  // A pinned row renders once per column container, with the same id each time.
  await expect
    .poll(async () => Array.from(new Set(await pinnedRows.evaluateAll((els) => els.map((e) => e.getAttribute("row-id"))))))
    .toEqual(["main-dtype"]);
  const dtypeCell = (col: string) => page.locator(`.df-viewer .ag-floating-top .ag-row[row-id="main-dtype"] [col-id="${col}"]`);
  await expect(dtypeCell("a")).toHaveText("int64");
  await expect(dtypeCell("c")).toHaveText("float64");

  // The status bar says the stats are not computed and offers the control.
  await expect(page.getByTestId("stats-status")).toHaveAttribute("data-stats-status", "not_computed");
  await expect(page.getByRole("button", { name: "Compute summary stats" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("the summary view shows the empty state, and its control asks for the basic tier, for one column or all", async ({ page }) => {
  await page.goto(NOT_COMPUTED_URL);
  await waitForCells(page);
  await page.getByTestId("view-summary").click();

  const empty = page.getByTestId("stats-empty-state");
  await expect(empty).toBeVisible();
  await expect(empty).toContainText("not computed");
  await expect(empty).toContainText("12.4M rows x 3 columns");
  // The grid is not shown in its place.
  await expect(page.locator(".df-viewer")).toHaveCount(0);

  // The whole table: the smallest tier the server allows, force, no columns.
  await empty.getByRole("button", { name: "Compute basic stats" }).click();
  await expect.poll(() => sentLog(page)).toEqual([
    { type: "stats_request", stats_gen: 7, scope: "raw", incremental: true, force: true, tier: "scalar" },
  ]);

  // One column: the same request, naming the column by the grid's own name.
  await empty.getByRole("combobox", { name: "Columns to compute" }).selectOption("b");
  await empty.getByRole("button", { name: "Compute basic stats" }).click();
  await expect.poll(async () => (await sentLog(page)).length).toBe(2);
  expect((await sentLog(page))[1]).toEqual({
    type: "stats_request", stats_gen: 7, scope: "raw", incremental: true, force: true, tier: "scalar", columns: ["b"],
  });

  // Back to the main view: its grid is there again.
  await page.getByTestId("view-main").click();
  await expect(page.getByTestId("stats-empty-state")).toHaveCount(0);
  await waitForCells(page);
});

test("over the ceiling the summary view says so and offers no control, and the status bar offers none either", async ({ page }) => {
  await page.goto(NOT_COMPUTED_URL);
  await waitForCells(page);
  await page.getByTestId("policy-ceiling").click();
  await page.getByTestId("view-summary").click();

  const empty = page.getByTestId("stats-empty-state");
  await expect(empty).toContainText("over the size limit");
  await expect(page.getByRole("button", { name: /compute|continue/i })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "Columns to compute" })).toHaveCount(0);
  await expect(page.getByTestId("stats-status")).toContainText("Summary stats unavailable");
  expect(await sentLog(page)).toEqual([]);
});

test("a paused run offers Continue, which asks for the tier that is left", async ({ page }) => {
  await page.goto(NOT_COMPUTED_URL);
  await waitForCells(page);
  await page.getByTestId("policy-cost").click();
  await page.getByTestId("view-summary").click();

  await expect(page.getByTestId("stats-empty-state")).toContainText("paused");
  await page.getByTestId("stats-empty-state").getByRole("button", { name: "Continue computing stats" }).click();
  await expect.poll(() => sentLog(page)).toEqual([
    { type: "stats_request", stats_gen: 7, scope: "raw", incremental: true, force: true, tier: "full" },
  ]);
});
