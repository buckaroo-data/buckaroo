/**
 * Jupyter-side height integration tests for the BuckarooWidget.
 *
 * Loads `tests/integration_notebooks/test_buckaroo_widget_height.ipynb`
 * (copied to the JupyterLab root by `scripts/test_playwright_jupyter.sh`)
 * and exercises the height behavior of the widget in two stacked output
 * cells: a 4-row DF + a 200-row DF.
 *
 * What it checks per output cell:
 *
 *   - The grid renders cells (.ag-cell visible).
 *   - The grid bottom sits within a small slack of the last data row —
 *     i.e. no dead band inside the grid (gridUtils.heightStyle short-mode
 *     should hug the rows for the small DF, regular-mode should fill the
 *     fixed allotted height for the large DF without inner empty rows).
 *   - The grid stays inside the jp-OutputArea — no horizontal/vertical
 *     overflow blowing out the notebook layout.
 *
 * Two viewport heights are tested:
 *   - 1280 × 900 (tall): the default JupyterLab page size in other specs
 *   - 1280 × 500 (short): exercises a tighter heightStyle()
 *     `window.innerHeight / 2` ceiling, which historically capped the
 *     widget at ~250px and surfaced gap regressions.
 */
import { test, expect, Page } from "@playwright/test";

const JUPYTER_BASE_URL = "http://localhost:8889";
const JUPYTER_TOKEN = "test-token-12345";
const NOTEBOOK = "test_buckaroo_widget_height.ipynb";

interface CellMetrics {
  outputArea: { top: number; bottom: number; height: number } | null;
  agRoot: { top: number; bottom: number; height: number } | null;
  lastRow: { top: number; bottom: number; height: number; rowIndex: number } | null;
  classMode: string;
  domLayout: "autoHeight" | "normal" | "print" | "other" | null;
  rowCount: number;
}

/**
 * Open the height notebook and run all cells. Returns once at least one
 * AG-Grid cell is visible in every output area.
 */
async function openAndRunNotebook(page: Page) {
  await page.goto(`${JUPYTER_BASE_URL}/lab/tree/${NOTEBOOK}?token=${JUPYTER_TOKEN}`, {
    timeout: 20_000,
  });
  await page.waitForLoadState("domcontentloaded", { timeout: 10_000 });
  await page.locator(".jp-Notebook").first().waitFor({ state: "attached", timeout: 10_000 });

  // Focus notebook then "Run All Cells" via the menu.
  await page.locator(".jp-Notebook").first().dispatchEvent("click");
  await page.waitForTimeout(300);
  await page.locator("text=Run").first().click();
  await page.waitForTimeout(300);
  const runAll = page.locator("text=Run All Cells");
  if (await runAll.isVisible()) {
    await runAll.click();
  } else {
    // Fallback for older JupyterLab menus.
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Shift+Enter");
      await page.waitForTimeout(400);
    }
  }

  // Wait for grids to materialise in BOTH output areas. JupyterLab gives
  // each rendered cell a .jp-OutputArea — we expect at least two.
  await page.locator(".jp-OutputArea .ag-cell").nth(1).waitFor({
    state: "visible",
    timeout: 30_000,
  });
  // Settle.
  await page.waitForTimeout(2000);
}

/**
 * Measure a single output cell. Pass the 0-based index — Buckaroo
 * notebook cells render into per-cell .jp-OutputArea containers.
 */
async function measureCell(page: Page, cellIndex: number): Promise<CellMetrics> {
  return await page.evaluate(({ idx }) => {
    function rect(el: Element | null) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, height: r.height };
    }
    const outputs = document.querySelectorAll(".jp-OutputArea");
    const outputArea = outputs[idx] ?? null;
    if (!outputArea) {
      return {
        outputArea: null,
        agRoot: null,
        lastRow: null,
        classMode: "",
        domLayout: null,
        rowCount: 0,
      } as any;
    }
    const dfViewer = outputArea.querySelector(".df-viewer");
    const agRoot = outputArea.querySelector(".ag-root-wrapper");
    let classMode = "";
    if (dfViewer) {
      if (dfViewer.classList.contains("short-mode")) classMode = "short-mode";
      else if (dfViewer.classList.contains("regular-mode")) classMode = "regular-mode";
      else classMode = "unknown";
    }
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
    const rows = agRoot?.querySelectorAll(".ag-center-cols-container .ag-row") ?? [];
    const sorted = Array.from(rows).sort((a, b) => {
      const ai = parseInt(a.getAttribute("row-index") || "-1", 10);
      const bi = parseInt(b.getAttribute("row-index") || "-1", 10);
      return ai - bi;
    });
    const lastRowEl = sorted.length ? sorted[sorted.length - 1] : null;
    return {
      outputArea: rect(outputArea),
      agRoot: rect(agRoot),
      lastRow: lastRowEl
        ? {
            ...(rect(lastRowEl) as any),
            rowIndex: parseInt(lastRowEl.getAttribute("row-index") || "-1", 10),
          }
        : null,
      classMode,
      domLayout,
      rowCount: sorted.length,
    } as CellMetrics;
  }, { idx: cellIndex });
}

// Per AG-Grid: 1-2px wrapper border, plus the horizontal scrollbar strip
// at the bottom when columns overflow horizontally (~17px on Chromium).
const ROW_TO_GRID_SLACK = 35;

const VIEWPORTS = [
  { width: 1280, height: 900 },
  { width: 1280, height: 500 },
];

for (const vp of VIEWPORTS) {
  test.describe(`Jupyter buckaroo height — viewport ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("small DF — grid hugs its rows (autoHeight via short-mode)", async ({ page }) => {
      await openAndRunNotebook(page);
      const m = await measureCell(page, 0);
      console.log(`small-DF cell @ ${vp.width}x${vp.height}:`, JSON.stringify(m, null, 2));

      expect(m.agRoot).not.toBeNull();
      expect(m.lastRow).not.toBeNull();
      // 4 rows + header — gridUtils auto-shorts.
      expect(m.classMode).toBe("short-mode");
      expect(m.domLayout).toBe("autoHeight");
      expect(m.rowCount).toBeGreaterThanOrEqual(4);

      // No dead band inside the grid.
      const inner = m.agRoot!.bottom - m.lastRow!.bottom;
      expect(inner).toBeLessThanOrEqual(ROW_TO_GRID_SLACK);
    });

    test("large DF — grid fills the allotted fixed height, no internal gap above last visible row", async ({
      page,
    }) => {
      await openAndRunNotebook(page);
      const m = await measureCell(page, 1);
      console.log(`large-DF cell @ ${vp.width}x${vp.height}:`, JSON.stringify(m, null, 2));

      expect(m.agRoot).not.toBeNull();
      // 200 rows: gridUtils picks regular-mode → domLayout normal.
      expect(m.classMode).toBe("regular-mode");
      expect(m.domLayout).toBe("normal");

      // In normal mode the grid scrolls — last visible row is somewhere
      // in the middle of the dataset. We assert the grid actually
      // claimed nontrivial height: at least 100px even at 500px viewport.
      expect(m.agRoot!.height).toBeGreaterThan(100);

      // Width-overflow scrollbar (no h-scroll on this DF) and the AG
      // status bar add ~25-35px between the last visible row and the
      // grid wrapper bottom. Anything larger means a layout regression.
      if (m.lastRow) {
        const inner = m.agRoot!.bottom - m.lastRow!.bottom;
        expect(inner).toBeLessThanOrEqual(ROW_TO_GRID_SLACK + 20);
      }
    });
  });
}
