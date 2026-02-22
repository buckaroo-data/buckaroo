/**
 * Playwright tests for the "inherit" pinned row displayer.
 *
 * Verifies that pinned rows with displayer: "inherit" use the column's
 * own formatter:
 *   - Integer column (station_id): mean=429.2 should render as "429"
 *   - Float column (temperature): mean=21.34 should render as "21.340"
 */
import { test, expect } from "@playwright/test";
import { waitForCells } from "./ag-pw-utils";

const STORY_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-inheritpinnedrows--primary&globals=&args=";

/** Helper: get text content of a pinned row cell */
async function getPinnedCellText(
  page: import("@playwright/test").Page,
  rowLabel: string,
  colId: string,
): Promise<string> {
  // Pinned rows live in .ag-floating-top. Find the row whose index cell matches rowLabel.
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

/** Helper: get the right edge (in px) of the innermost text span in a pinned row cell */
async function getPinnedCellRightEdge(
  page: import("@playwright/test").Page,
  rowLabel: string,
  colId: string,
): Promise<number> {
  const pinnedRows = page.locator(".ag-floating-top .ag-row");
  const count = await pinnedRows.count();
  for (let i = 0; i < count; i++) {
    const row = pinnedRows.nth(i);
    const indexCell = row.locator('[col-id="index"]');
    const indexText = (await indexCell.textContent())?.trim();
    if (indexText === rowLabel) {
      const targetCell = row.locator(`[col-id="${colId}"]`);
      // Get the right edge of the innermost span (the actual text container)
      return await targetCell.evaluate((el) => {
        const spans = el.querySelectorAll("span");
        const innermost = spans[spans.length - 1] || el;
        return innermost.getBoundingClientRect().right;
      });
    }
  }
  throw new Error(`Pinned row "${rowLabel}" not found`);
}

test.describe("Inherit pinned row displayer", () => {
  test("integer column: mean renders with 0 decimal places", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // mean=429.2 on an int column (float 0 decimals) should show "429"
    const meanText = await getPinnedCellText(page, "mean", "station_id");
    expect(meanText).toBe("429");
  });

  test("integer column: all stats use integer formatting", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // std=86.967 → "87"
    const stdText = await getPinnedCellText(page, "std", "station_id");
    expect(stdText).toBe("87");

    // min=293 → "293"
    const minText = await getPinnedCellText(page, "min", "station_id");
    expect(minText).toBe("293");

    // median=435 → "435"
    const medianText = await getPinnedCellText(page, "median", "station_id");
    expect(medianText).toBe("435");

    // max=519 → "519"
    const maxText = await getPinnedCellText(page, "max", "station_id");
    expect(maxText).toBe("519");
  });

  test("float column: mean renders with 3 decimal places", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // mean=21.34 on a float column (3 decimals) should show "21.340"
    const meanText = await getPinnedCellText(page, "mean", "temperature");
    expect(meanText).toBe("21.340");
  });

  test("float column: all stats use float formatting", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // std=2.597 → "2.597"
    const stdText = await getPinnedCellText(page, "std", "temperature");
    expect(stdText).toBe("2.597");

    // min=18.3 → "18.300"
    const minText = await getPinnedCellText(page, "min", "temperature");
    expect(minText).toBe("18.300");

    // median=21.0 → "21.000"
    const medianText = await getPinnedCellText(page, "median", "temperature");
    expect(medianText).toBe("21.000");

    // max=25.1 → "25.100"
    const maxText = await getPinnedCellText(page, "max", "temperature");
    expect(maxText).toBe("25.100");
  });
});

/**
 * Tests for the SummaryView story — mimics the real summary stats tab.
 * DefaultSummaryStatsStyling now inherits style_column() from
 * DefaultMainStyling, so column_config has proper formatters.
 * Inherit pinned rows resolve correctly.
 */
const SUMMARY_VIEW_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-inheritpinnedrows--summary-view&globals=&args=";

test.describe("Inherit pinned rows — summary view", () => {
  test("integer column: mean renders with 0 decimal places", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // mean=429.2 on an int column should show "429"
    const meanText = await getPinnedCellText(page, "mean", "station_id");
    expect(meanText).toBe("429");
  });

  test("integer column: std renders with 0 decimal places", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // std=86.967 → "87"
    const stdText = await getPinnedCellText(page, "std", "station_id");
    expect(stdText).toBe("87");
  });

  test("float column: mean renders with 3 decimal places", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // mean=21.34 → "21.340"
    const meanText = await getPinnedCellText(page, "mean", "temperature");
    expect(meanText).toBe("21.340");
  });

  test("freq rows: integer column uses integer formatting", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // most_freq=519 on int column → "519"
    const freqText = await getPinnedCellText(page, "most_freq", "station_id");
    expect(freqText).toBe("519");
  });

  test("freq rows: float column uses float formatting", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // most_freq=22.5 on float(3) column → "22.500"
    const freqText = await getPinnedCellText(page, "most_freq", "temperature");
    expect(freqText).toBe("22.500");
  });
});

/**
 * Alignment tests — count rows must use the column's formatter so digits
 * align vertically with inherit rows (mean, std, etc.).
 *
 * In a float(3,3) column, non_null_count=5 must render as "5.000" (not "5")
 * so its ones digit aligns with the ones digits of "21.340", "2.597", etc.
 */
test.describe("Summary view — count rows use column formatter for alignment", () => {
  test("float column: non_null_count uses column float formatting", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // non_null_count=5 in float(3,3) column should show "5.000" not "5"
    const countText = await getPinnedCellText(page, "non_null_count", "temperature");
    expect(countText).toBe("5.000");
  });

  test("float column: null_count uses column float formatting", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // null_count=0 in float(3,3) column should show "0.000" not "0"
    const countText = await getPinnedCellText(page, "null_count", "temperature");
    expect(countText).toBe("0.000");
  });

  test("integer column: non_null_count uses column integer formatting", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // non_null_count=5 in integer(0,0) column should show "5"
    const countText = await getPinnedCellText(page, "non_null_count", "station_id");
    expect(countText).toBe("5");
  });

  test("float column: count and mean right edges align within 1px", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);
    await page.waitForTimeout(300);

    const countRight = await getPinnedCellRightEdge(page, "non_null_count", "temperature");
    const meanRight = await getPinnedCellRightEdge(page, "mean", "temperature");
    // Right edges of innermost text spans should be within 1px
    expect(Math.abs(countRight - meanRight)).toBeLessThan(1);
  });
});
