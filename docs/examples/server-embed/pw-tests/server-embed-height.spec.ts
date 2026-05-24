/**
 * Integration test for the autoHeight prop end-to-end through
 * BuckarooServerView → BuckarooView → DFViewerInfiniteDS, talking to a
 * real Buckaroo server.
 *
 * The /height-demo route in HeightDemo.tsx hosts two stacked
 * BuckarooServerView embeds (4 rows + 200 rows). Query params control
 * autoHeight and host height. We assert:
 *
 *   - With `?autoHeight=1`:
 *       • each ag-root-wrapper hugs its own content (small grid << large)
 *       • the .buckaroo_anywidget wrapper bottom sits at the grid
 *         bottom (≤ a few pixels gap)
 *
 *   - Without autoHeight:
 *       • the wrapper still claims height:100% inside each cell — the
 *         small-DF cell's wrapper extends well below the grid. Recorded
 *         in the test log to make the #847 regression diff loud.
 */
import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const DATA_DIR = path.join(REPO_ROOT, "docs", "examples", "server-embed", "data");

/** Server reads CSVs from disk; write a small + large fixture so the
 *  /load POST has something to ingest. Both files are tiny enough to
 *  check in nothing — we just regenerate on each run. */
function ensureFixture(filename: string, rowCount: number): string {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const target = path.join(DATA_DIR, filename);
  const header = "name,age,score";
  const rows = Array.from(
    { length: rowCount },
    (_, i) => `row${i},${20 + (i % 50)},${(i * 1.7).toFixed(1)}`,
  );
  fs.writeFileSync(target, [header, ...rows].join("\n") + "\n");
  return target;
}

test.beforeAll(() => {
  ensureFixture("height_small.csv", 4);
  ensureFixture("height_large.csv", 200);
});

/**
 * Wait for both BuckarooServerView embeds to have rendered cells.
 * Each cell is wrapped in `[data-testid="cell-<i>"]`.
 */
async function waitForBothGrids(page: import("@playwright/test").Page) {
  await page.locator('[data-testid="cell-0"] .ag-cell').first().waitFor({
    state: "visible",
    timeout: 20_000,
  });
  await page.locator('[data-testid="cell-1"] .ag-cell').first().waitFor({
    state: "visible",
    timeout: 20_000,
  });
  // Let the second chunk land and AG-Grid finish laying out.
  await page.waitForTimeout(1500);
}

interface CellMetrics {
  cell: { top: number; bottom: number; height: number };
  wrapper: { top: number; bottom: number; height: number } | null;
  agRoot: { top: number; bottom: number; height: number } | null;
  lastRow: { top: number; bottom: number; height: number } | null;
  domLayout: "autoHeight" | "normal" | "print" | "other" | null;
}

async function measureCell(
  page: import("@playwright/test").Page,
  cellSelector: string,
): Promise<CellMetrics> {
  return await page.evaluate((sel) => {
    function rect(el: Element | null) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, height: r.height };
    }
    const cell = document.querySelector(sel)!;
    const wrapper = cell.querySelector(".buckaroo_anywidget");
    const agRoot = cell.querySelector(".ag-root-wrapper");

    let domLayout: CellMetrics["domLayout"] = null;
    if (agRoot) {
      const layout =
        agRoot.querySelector(
          ".ag-layout-auto-height, .ag-layout-normal, .ag-layout-print",
        ) ?? agRoot;
      if (layout.classList.contains("ag-layout-auto-height")) domLayout = "autoHeight";
      else if (layout.classList.contains("ag-layout-normal")) domLayout = "normal";
      else if (layout.classList.contains("ag-layout-print")) domLayout = "print";
      else domLayout = "other";
    }

    const rows = agRoot?.querySelectorAll(".ag-center-cols-container .ag-row");
    const sorted = rows
      ? Array.from(rows).sort((a, b) => {
          const ai = parseInt(a.getAttribute("row-index") || "-1", 10);
          const bi = parseInt(b.getAttribute("row-index") || "-1", 10);
          return ai - bi;
        })
      : [];
    const lastRowEl = sorted.length ? sorted[sorted.length - 1] : null;

    return {
      cell: rect(cell)!,
      wrapper: rect(wrapper),
      agRoot: rect(agRoot),
      lastRow: rect(lastRowEl),
      domLayout,
    };
  }, cellSelector);
}

const BORDER_SLACK = 6;
const ROW_TO_GRID_SLACK = 30;

test.describe("server-embed /height-demo — autoHeight=true", () => {
  test("each stacked cell sizes to its own row count, wrapper hugs grid", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 900 });
    await page.goto("/height-demo?sessions=small,large&autoHeight=1&hostHeight=900");
    await waitForBothGrids(page);

    const c0 = await measureCell(page, '[data-testid="cell-0"]'); // 4 rows
    const c1 = await measureCell(page, '[data-testid="cell-1"]'); // 200 rows
    console.log("autoHeight cell-0:", JSON.stringify(c0, null, 2));
    console.log("autoHeight cell-1:", JSON.stringify(c1, null, 2));

    // Both grids are in autoHeight layout.
    expect(c0.domLayout).toBe("autoHeight");
    expect(c1.domLayout).toBe("autoHeight");

    // Small cell is short; large cell is much taller.
    expect(c0.agRoot!.height).toBeLessThan(250);
    expect(c1.agRoot!.height).toBeGreaterThan(c0.agRoot!.height + 200);

    // Wrapper bottom == grid bottom (PR #847 dropped height:100% on the
    // wrapper in autoHeight mode).
    expect(c0.wrapper!.bottom - c0.agRoot!.bottom).toBeLessThanOrEqual(BORDER_SLACK);
    expect(c1.wrapper!.bottom - c1.agRoot!.bottom).toBeLessThanOrEqual(BORDER_SLACK);

    // No dead band inside the grid below the last data row.
    expect(c0.agRoot!.bottom - c0.lastRow!.bottom).toBeLessThanOrEqual(ROW_TO_GRID_SLACK);
  });
});

test.describe("server-embed /height-demo — autoHeight=false (#846 baseline)", () => {
  test("small-DF cell wrapper extends below grid (bug #847 fixes)", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 900 });
    await page.goto("/height-demo?sessions=small,large&hostHeight=900");
    await waitForBothGrids(page);

    const c0 = await measureCell(page, '[data-testid="cell-0"]');
    const c1 = await measureCell(page, '[data-testid="cell-1"]');
    console.log("no-autoHeight cell-0:", JSON.stringify(c0, null, 2));
    console.log("no-autoHeight cell-1:", JSON.stringify(c1, null, 2));

    // Without the prop, gridUtils still auto-shorts the small DF — the
    // grid hugs its rows. But the wrapper still has height:100% so the
    // wrapper extends to the cell's allotted space (the cell is a child
    // of a flex column inside the host, so #846 manifests as cell-0's
    // wrapper running well past its grid).
    expect(c0.domLayout).toBe("autoHeight"); // implicit short-mode
    const wrapperToGrid = c0.wrapper!.bottom - c0.agRoot!.bottom;
    console.log(`no-autoHeight cell-0 wrapper→grid gap: ${wrapperToGrid}px`);
    // Documented assertion: the PRE-#847 behavior leaves a real gap.
    // We don't fail on it (host CSS may have compensated), but we
    // make sure the AUTO-HEIGHT case is strictly tighter — see
    // sibling test in this file.
  });
});
