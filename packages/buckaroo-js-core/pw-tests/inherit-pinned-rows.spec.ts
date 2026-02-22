/**
 * Playwright tests for the "inherit" pinned row displayer.
 *
 * Verifies that pinned rows with displayer: "inherit" use the column's
 * own formatter:
 *   - Integer column (station_id): mean=894.8674 should render as "895"
 *   - Float column (temperature): mean=3.14159 should render as "3.142"
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

test.describe("Inherit pinned row displayer", () => {
  test("integer column: mean renders with 0 decimal places", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // mean=894.8674 on an int column (float 0 decimals) should show "895"
    const meanText = await getPinnedCellText(page, "mean", "station_id");
    expect(meanText).toBe("895");
  });

  test("integer column: all stats use integer formatting", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // std=1052.051 → "1,052"
    const stdText = await getPinnedCellText(page, "std", "station_id");
    expect(stdText).toBe("1,052");

    // min=0 → "0"
    const minText = await getPinnedCellText(page, "min", "station_id");
    expect(minText).toBe("0");

    // median=72 → "72"
    const medianText = await getPinnedCellText(page, "median", "station_id");
    expect(medianText).toBe("72");

    // max=3249 → "3,249"
    const maxText = await getPinnedCellText(page, "max", "station_id");
    expect(maxText).toBe("3,249");
  });

  test("float column: mean renders with 3 decimal places", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // mean=3.14159 on a float column (3 decimals) should show "3.142"
    const meanText = await getPinnedCellText(page, "mean", "temperature");
    expect(meanText).toBe("3.142");
  });

  test("float column: all stats use float formatting", async ({ page }) => {
    await page.goto(STORY_URL);
    await waitForCells(page);

    // std=1.7321 → "1.732"
    const stdText = await getPinnedCellText(page, "std", "temperature");
    expect(stdText).toBe("1.732");

    // min=0.5 → "0.500"
    const minText = await getPinnedCellText(page, "min", "temperature");
    expect(minText).toBe("0.500");

    // median=2.718 → "2.718"
    const medianText = await getPinnedCellText(page, "median", "temperature");
    expect(medianText).toBe("2.718");

    // max=99.9 → "99.900"
    const maxText = await getPinnedCellText(page, "max", "temperature");
    expect(maxText).toBe("99.900");
  });
});

/**
 * Tests for the SummaryView story — mimics the real summary stats tab
 * where column_config uses "obj" displayers (DefaultSummaryStatsStyling
 * doesn't override style_column). Inherit pinned rows should still
 * format numbers properly, not show raw floats.
 *
 * These tests are EXPECTED TO FAIL until the fix is implemented:
 * either DefaultSummaryStatsStyling overrides style_column() in Python,
 * or the JS inherit resolver gets the main view's column_config.
 */
const SUMMARY_VIEW_URL =
  "http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-dfviewer-inheritpinnedrows--summary-view&globals=&args=";

test.describe("Inherit pinned rows — summary view (obj column_config)", () => {
  test("integer column: mean should NOT show raw float", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // mean=894.8674 — should show "895" not "894.8674"
    const meanText = await getPinnedCellText(page, "mean", "station_id");
    expect(meanText).toBe("895");
  });

  test("integer column: std should NOT show raw float", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // std=1052.051 — should show "1,052" not "1052.051"
    const stdText = await getPinnedCellText(page, "std", "station_id");
    expect(stdText).toBe("1,052");
  });

  test("float column: mean should be formatted", async ({ page }) => {
    await page.goto(SUMMARY_VIEW_URL);
    await waitForCells(page);

    // mean=3.14159 — should show "3.142" not "3.14159"
    const meanText = await getPinnedCellText(page, "mean", "temperature");
    expect(meanText).toBe("3.142");
  });
});
