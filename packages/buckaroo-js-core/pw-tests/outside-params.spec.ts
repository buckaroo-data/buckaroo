import { test, expect, Page } from "@playwright/test";
import { getRowContents, waitForCells } from "./ag-pw-utils";

const getFirstRowSlice = async (page: Page): Promise<string[] | null> => {
  try {
    const row = await getRowContents(page, 0);
    if (!row || row.length < 3) {
      return null;
    }
    return row.slice(0, 3);
  } catch {
    return null;
  }
};

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

test("Outside params ignores stale late response (A slow, B fast)", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--asymmetric-delay-a-slow-b-fast&globals=&args="
  );

  await page.getByRole("button", { name: "Toggle Params" }).click();
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 7000 }).toEqual(["", "B1", "B"]);
  await expect(page.getByTestId("outside-key")).toContainText("B");

  // Wait long enough for the stale A response to arrive and verify it does not overwrite B.
  await page.waitForTimeout(1500);
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 3000 }).toEqual(["", "B1", "B"]);
  await expect(page.getByTestId("outside-key")).toContainText("B");
});

test("Outside params rapid multi-toggle converges to final state", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--asymmetric-delay-a-slow-b-fast&globals=&args="
  );

  await page.getByRole("button", { name: "Rapid Toggle x3" }).click();
  await expect(page.getByTestId("outside-key")).toContainText("B");
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 7000 }).toEqual(["", "B1", "B"]);

  await page.waitForTimeout(1500);
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 3000 }).toEqual(["", "B1", "B"]);
  await expect(page.getByTestId("outside-key")).toContainText("B");
});

test("Outside params + sort remains synchronized in infinite mode", async ({ page }) => {
  await page.goto(
    "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-outsideparamsinconsistency--sort-and-toggle&globals=&args="
  );

  await waitForCells(page);
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 6000 }).toEqual(["", "A3", "A"]);

  // First click should sort ascending.
  await page.getByRole("columnheader", { name: "a" }).click();
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 6000 }).toEqual(["", "A1", "A"]);

  // Toggle source and ensure sort/result remains aligned with new outside params.
  await page.getByRole("button", { name: "Toggle Params" }).click();
  await expect(page.getByTestId("outside-key")).toContainText("B");
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 6000 }).toEqual(["", "B1", "B"]);

  // Second click should sort descending.
  await page.getByRole("columnheader", { name: "a" }).click();
  await expect.poll(async () => getFirstRowSlice(page), { timeout: 6000 }).toEqual(["", "B3", "B"]);
});
