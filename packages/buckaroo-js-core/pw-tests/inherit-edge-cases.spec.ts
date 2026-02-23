/**
 * Edge-case tests for inherit displayer:
 * - String columns: inherit resolves to string formatter, counts show as plain numbers
 * - Large/small/negative numbers: formatting and alignment
 * - NaN values in string columns (mean of strings is null)
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const MIXED_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-inheritedgecases--mixed-types&globals=&args=";

const EXTREME_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-inheritedgecases--extreme-numbers&globals=&args=";

async function getPinnedCellText(
  page: import("@playwright/test").Page,
  rowLabel: string,
  colId: string,
): Promise<string> {
  const pinnedRows = page.locator(".ag-floating-top .ag-row");
  const count = await pinnedRows.count();
  for (let i = 0; i < count; i++) {
    const row = pinnedRows.nth(i);
    const indexCell = row.locator('[col-id="index"]');
    const indexText = (await indexCell.textContent())?.trim();
    if (indexText === rowLabel) {
      const targetCell = row.locator(`[col-id="${colId}"]`);
      return (await targetCell.textContent())?.trim() ?? "";
    }
  }
  throw new Error(`Pinned row "${rowLabel}" not found`);
}

test.describe("Inherit edge cases — mixed types", () => {
  test("string column: inherit non_null_count shows the number", async ({ page }) => {
    await page.goto(MIXED_URL);
    await waitForCells(page);

    // inherit on a string column: count=3 should render (string formatter just returns the value)
    const countText = await getPinnedCellText(page, "non_null_count", "str_col");
    expect(countText).toBe("3");
  });

  test("string column: inherit most_freq shows the string value", async ({ page }) => {
    await page.goto(MIXED_URL);
    await waitForCells(page);

    // most_freq="a" on a string column should render as "a"
    const freqText = await getPinnedCellText(page, "most_freq", "str_col");
    expect(freqText).toBe("a");
  });

  test("string column: inherit mean of strings shows None (null)", async ({ page }) => {
    await page.goto(MIXED_URL);
    await waitForCells(page);

    // mean is null for string columns — obj formatter renders null as "None"
    // string formatter just returns the value which is null
    const meanText = await getPinnedCellText(page, "mean", "str_col");
    // Could be "None", "null", or empty depending on formatter
    expect(["None", "null", ""]).toContain(meanText);
  });

  test("integer column: count uses integer formatting", async ({ page }) => {
    await page.goto(MIXED_URL);
    await waitForCells(page);

    const countText = await getPinnedCellText(page, "non_null_count", "int_col");
    expect(countText).toBe("3");
  });

  test("float column: count uses float formatting", async ({ page }) => {
    await page.goto(MIXED_URL);
    await waitForCells(page);

    // non_null_count=3 in float(3,3) column → "3.000"
    const countText = await getPinnedCellText(page, "non_null_count", "float_col");
    expect(countText).toBe("3.000");
  });
});

test.describe("Inherit edge cases — extreme numbers", () => {
  test("large integers format with commas", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);

    const meanText = await getPinnedCellText(page, "mean", "large");
    expect(meanText).toBe("2,000,000");
  });

  test("small floats format with 3 decimal places", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);

    const meanText = await getPinnedCellText(page, "mean", "small");
    expect(meanText).toBe("0.002");
  });

  test("negative integers format correctly", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);

    const meanText = await getPinnedCellText(page, "mean", "negative");
    expect(meanText).toBe("-200");

    const minText = await getPinnedCellText(page, "min", "negative");
    expect(minText).toBe("-300");
  });

  test("count row aligns with stats in large number column", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);

    // non_null_count=3 in integer(0,0) column → "3" (same formatter as "2,000,000")
    const countText = await getPinnedCellText(page, "non_null_count", "large");
    expect(countText).toBe("3");
  });

  test("count row aligns with stats in small float column", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);

    // non_null_count=3 in float(3,3) column → "3.000"
    const countText = await getPinnedCellText(page, "non_null_count", "small");
    expect(countText).toBe("3.000");
  });

  test("screenshot", async ({ page }) => {
    await page.goto(EXTREME_URL);
    await waitForCells(page);
    await page.waitForTimeout(300);

    await page.screenshot({
      path: "screenshots/extreme-numbers.png",
      fullPage: true,
    });
  });
});
