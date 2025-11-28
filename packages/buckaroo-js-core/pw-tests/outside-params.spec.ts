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


