import { test, expect } from "@playwright/test";
import { getRowContents, waitForCells } from "./ag-pw-utils";

test("Outside params toggle updates rows (Primary)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--primary&globals=&args="
  );
  await waitForCells(page);
  // Be tolerant of initial grid render timing; poll until data present
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 3000 }).toEqual(["", "A1", "A"]);

  await page.getByRole("button", { name: "Toggle Params" }).click();
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "B1", "B"]);
});

test("Outside params toggle updates rows (WithDelay)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--with-delay&globals=&args="
  );
  await waitForCells(page);
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "A1", "A"]);
  await page.getByRole("button", { name: "Toggle Params" }).click();
  // allow the delayed datasource to re-resolve
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 7000 }).toEqual(["", "B1", "B"]);
});

test("C1: Stale slow-A response does not overwrite fast-B (AsymmetricDelay)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--asymmetric-delay&globals=&args="
  );
  await waitForCells(page);
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "A1", "A"]);

  await page.getByRole("button", { name: "Toggle Params" }).click();
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 3000 }).toEqual(["", "B1", "B"]);

  // Wait past A's delay (500ms + buffer) — rows should still show B data
  await page.waitForTimeout(700);
  const row = await getRowContents(page, 0);
  expect(row.slice(0, 3)).toEqual(["", "B1", "B"]);
});

test("C2: Rapid toggle stress — final state is consistent (RapidToggle)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--rapid-toggle&globals=&args="
  );
  await waitForCells(page);
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "A1", "A"]);

  await page.getByRole("button", { name: "Rapid Toggle (5x)" }).click();

  // Wait for all toggles to complete (5 * 50ms = 250ms + render time)
  await expect.poll(async () => {
    const span = await page.locator("span").filter({ hasText: "outside_df_params.key" }).textContent();
    return span;
  }, { timeout: 5000 }).toContain("A");

  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "A1", "A"]);
});

test("C3: Sort then toggle — rows update to new source (WithSort)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--with-sort&globals=&args="
  );
  await waitForCells(page);
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "A3", "A"]);

  await page.getByRole("button", { name: "Toggle Params" }).click();
  await expect.poll(async () => {
    const row = await getRowContents(page, 0);
    return row.slice(0, 3);
  }, { timeout: 5000 }).toEqual(["", "B2", "B"]);
});
