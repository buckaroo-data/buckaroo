/**
 * Playwright tests for the client half of the stats wire (rows-first c2), on
 * the StatsUpdateChannel "Manual" story: a real WebSocketModel and BuckarooView
 * on a fake in-page server, with stats_update frames delivered by button.
 *
 * The pinned `mean` row starts as a placeholder because the first frame
 * carries only the schema tier. Its stats come in two column chunks, `age`
 * then `score` (final), each padding the other column with null. Each test
 * checks the grid and the model state the story mirrors (df_meta.stats and the
 * stat rows in all_stats).
 */
import { test, expect, Page } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-server-statsupdatechannel--manual&globals=&args=";

const pinnedCell = (page: Page, rowId: string, colId: string) =>
  page.locator(`.df-viewer .ag-floating-top .ag-row[row-id="${rowId}"] [col-id="${colId}"]`);

async function openStory(page: Page) {
  await page.goto(STORY_URL);
  await waitForCells(page);
  await expect(page.locator(".df-viewer .ag-center-cols-container")).toContainText("Bob", { timeout: 10_000 });
  await expect(pinnedCell(page, "main-dtype", "age")).toHaveText("int64");
  await expect(pinnedCell(page, "main-mean", "index")).toHaveText("mean");
  await expect(pinnedCell(page, "main-mean", "age")).toHaveText("");
  await expect(page.getByTestId("model-stats")).toHaveText("pending schema gen 1");
}

test("column chunks of a stats_update merge into the pinned rows, the final one completes", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await openStory(page);

  // age chunk: age's mean arrives, score stays a placeholder, the gen stays pending.
  await page.getByTestId("deliver-age-gen-1").click();
  await expect(pinnedCell(page, "main-mean", "age")).toHaveText("31.00");
  await expect(pinnedCell(page, "main-mean", "score")).toHaveText("");
  await expect(page.getByTestId("model-stats")).toHaveText("pending schema gen 1");

  // score chunk (final): its null age leaves the merged age alone, and the
  // schema-tier dtype row is kept.
  await page.getByTestId("deliver-score-gen-1").click();
  await expect(pinnedCell(page, "main-mean", "score")).toHaveText("87.00");
  await expect(page.getByTestId("model-stats")).toHaveText("complete full gen 1");
  await expect(pinnedCell(page, "main-mean", "age")).toHaveText("31.00");
  await expect(pinnedCell(page, "main-dtype", "age")).toHaveText("int64");
  await expect(page.getByTestId("model-stat-rows")).toHaveText("dtype,mean");
  expect(pageErrors).toEqual([]);
});

test("stats for the state before a search are dropped, the search's own stats merge", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await openStory(page);

  const searchInput = page.locator(".FakeSearchEditor input[type='text']");
  await searchInput.fill("Alice");
  await searchInput.press("Enter");

  // The server answers the search with gen 2: filtered rows, schema-only stats.
  await expect(page.getByTestId("server-gen")).toHaveText("2");
  await expect(page.getByTestId("model-stats")).toHaveText("pending schema gen 2");
  const body = page.locator(".df-viewer .ag-center-cols-container");
  await expect(body).toContainText("Alice");
  await expect(body).not.toContainText("Bob");

  // gen 1's stats arrive late, after gen 2's initial_state: dropped.
  await page.getByTestId("deliver-age-gen-1").click();
  await page.getByTestId("deliver-score-gen-1").click();
  await expect(page.getByTestId("settled")).toHaveText("2");
  await expect(page.getByTestId("model-stats")).toHaveText("pending schema gen 2");
  await expect(page.getByTestId("model-stat-rows")).toHaveText("dtype");
  await expect(pinnedCell(page, "main-mean", "age")).toHaveText("");

  // gen 2's stats describe Alice alone.
  await page.getByTestId("deliver-age-gen-2").click();
  await page.getByTestId("deliver-score-gen-2").click();
  await expect(pinnedCell(page, "main-mean", "age")).toHaveText("25.00");
  await expect(pinnedCell(page, "main-mean", "score")).toHaveText("80.00");
  await expect(page.getByTestId("model-stats")).toHaveText("complete full gen 2");
  expect(pageErrors).toEqual([]);
});
