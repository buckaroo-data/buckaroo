/**
 * Real-browser integration test for XorqBuckarooInfiniteWidget.
 *
 * Opens the notebook test_xorq_infinite_scroll.ipynb in JupyterLab,
 * executes the cell to render the widget against a 5000-row predictable
 * xorq expression, and exercises the infinite-scroll path:
 *
 *   1. Initial render: the first viewport's cells show the expected
 *      values from the [0, ~50) window. Verifies that the bytes Python
 *      writes (arrow → parquet, no pandas detour) are decoded by the
 *      JS frontend's hyparquet reader and rendered into the AG-Grid
 *      DOM with the right values.
 *
 *   2. Scroll to row ~1500: triggers a follow-up infinite_request
 *      that the Python widget answers with a *different* parquet slice
 *      (LIMIT/OFFSET pushed to the backend). The cells at the scrolled
 *      position show the values for that window, which is the contract
 *      we care about: paginated loading actually loads the right rows.
 *
 * Predictable data (matches the existing polars infinite-scroll test
 * so any assertion regressions are obvious):
 *
 *   row i  →  row_num=i, int_col=i+10, str_col="foo_{i+10}"
 */
import { test, expect, Page } from '@playwright/test';

const JUPYTER_BASE_URL = 'http://localhost:8889';
const JUPYTER_TOKEN = 'test-token-12345';
const DEFAULT_TIMEOUT = 10000;
const NAVIGATION_TIMEOUT = 12000;

async function waitForAgGrid(page: Page, timeout = 5000) {
    await page.locator('.ag-root-wrapper').first().waitFor({ state: 'attached', timeout });
    await page.locator('.ag-cell').first().waitFor({ state: 'attached', timeout });
}

async function openNotebookAndRun(page: Page, notebookName: string) {
    await page.goto(
        `${JUPYTER_BASE_URL}/lab/tree/${notebookName}?token=${JUPYTER_TOKEN}`,
        { timeout: NAVIGATION_TIMEOUT });
    await page.waitForLoadState('domcontentloaded', { timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook').first().waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    await page.locator('.jp-Notebook').first().dispatchEvent('click');
    await page.waitForTimeout(200);
    await page.keyboard.press('Shift+Enter');
    const outputArea = page.locator('.jp-OutputArea').first();
    await outputArea.waitFor({ state: 'attached', timeout: DEFAULT_TIMEOUT });
    // xorq + DataFusion startup is heavier than polars; allow the cell
    // to render before the widget paints.
    await page.waitForTimeout(2500);
    await waitForAgGrid(page, 10000);
}

test.describe('XorqBuckarooInfiniteWidget — JupyterLab integration', () => {
    test('initial render shows row 0 values from the xorq expression', async ({ page }) => {
        await openNotebookAndRun(page, 'test_xorq_infinite_scroll.ipynb');

        // Row 0 in the expression is row_num=0, int_col=10, str_col="foo_10".
        // AG-Grid renders the row indexed by absolute offset; the widget
        // returns the column data with rewritten names (a, b, c) but the
        // header_name is the original ("row_num", "int_col", "str_col"),
        // so we hunt for cell text rather than relying on column ids.
        const cellRowNum0 = page.locator('.ag-cell:has-text("foo_10")').first();
        await expect(cellRowNum0).toBeVisible({ timeout: 5000 });

        // Spot-check a couple more rows in the initial viewport.
        await expect(page.locator('.ag-cell:has-text("foo_11")').first()).toBeVisible();
        await expect(page.locator('.ag-cell:has-text("foo_15")').first()).toBeVisible();
    });

    test('scrolling far down fetches a new window and renders matching values', async ({ page }) => {
        await openNotebookAndRun(page, 'test_xorq_infinite_scroll.ipynb');

        // Anchor: confirm row 0 is visible before scrolling.
        await expect(page.locator('.ag-cell:has-text("foo_10")').first()).toBeVisible({ timeout: 5000 });

        // Scroll the main viewport ~30000px down. Default AG-Grid row
        // height varies; we don't care about hitting an exact row, just
        // that we end up far from the top. The assertions below read
        // the actually-visible row indices and check their values.
        const scrolled = await page.evaluate(() => {
            const viewports = [
                ...document.querySelectorAll('.ag-body-viewport'),
                ...document.querySelectorAll('.ag-center-cols-viewport'),
            ] as HTMLElement[];
            let main: HTMLElement | null = null;
            let max = 0;
            for (const vp of viewports) {
                if (vp.scrollHeight > max) { max = vp.scrollHeight; main = vp; }
            }
            if (!main) return { ok: false } as const;
            main.scrollTop = Math.min(30000, main.scrollHeight);
            return { ok: true, scrollTop: main.scrollTop } as const;
        });
        expect(scrolled.ok).toBe(true);

        // Let the follow-up infinite_request round-trip through the comm
        // channel + xorq backend.
        await page.waitForTimeout(2500);

        // Read what's actually rendered: grab data rows (the pinned-top
        // dtype row is in ``.ag-row`` too but lacks ``row-index``), parse
        // the row_num column's int and the str_col column's text, and
        // assert the predictable invariant ``str_col == "foo_{row_num + 10}"``.
        // This is the contract the widget is responsible for: every row
        // it ships, regardless of which window, carries consistent
        // per-row values.
        const visible = await page.evaluate(() => {
            const out: Array<{ rowNum: number, strCol: string }> = [];
            // ``[row-index]`` filters to body rows; pinned/dtype rows
            // don't carry that attribute.
            const rows = document.querySelectorAll('.ag-row[row-index]');
            for (const row of Array.from(rows)) {
                const cells = row.querySelectorAll('.ag-cell');
                if (cells.length < 3) continue;
                const rowNumText = (cells[0].textContent || '').replace(/[^0-9-]/g, '');
                const strColText = (cells[2].textContent || '').trim();
                const rowNum = parseInt(rowNumText, 10);
                if (Number.isNaN(rowNum)) continue;
                // Only count rows whose str_col looks like data — skips
                // any header / placeholder leaking through.
                if (!/^foo_\d+$/.test(strColText)) continue;
                out.push({ rowNum, strCol: strColText });
            }
            return out;
        });

        expect(
            visible.length,
            'expected at least some rows to be rendered after scroll').toBeGreaterThan(0);

        // We actually scrolled — the visible rows must include indices
        // far from 0 (allow a wide band — AG-Grid row height drives
        // exactly where we end up).
        const minRow = Math.min(...visible.map(r => r.rowNum));
        expect(
            minRow,
            `visible rows ${JSON.stringify(visible.slice(0, 3))} `
            + 'are still near the top — scroll didn\'t move').toBeGreaterThan(500);

        // Each visible row obeys the predictable pattern. This catches:
        //   - wrong window served (row_num would mismatch str_col)
        //   - off-by-one in offset (row_num would be shifted)
        //   - decoding bug (str_col missing or garbled)
        for (const { rowNum, strCol } of visible) {
            expect(strCol).toBe(`foo_${rowNum + 10}`);
        }
    });

    test('jumping back to the top after a deep scroll re-fetches row 0', async ({ page }) => {
        await openNotebookAndRun(page, 'test_xorq_infinite_scroll.ipynb');

        // Scroll deep first so the cache is populated for a window other
        // than the top.
        await page.evaluate(() => {
            const viewports = [...document.querySelectorAll('.ag-body-viewport')] as HTMLElement[];
            let main: HTMLElement | null = null;
            let max = 0;
            for (const vp of viewports) {
                if (vp.scrollHeight > max) { max = vp.scrollHeight; main = vp; }
            }
            if (main) main.scrollTop = Math.min(1500 * 20, main.scrollHeight);
        });
        await page.waitForTimeout(2000);

        // Now jump back to the top. The widget should serve the [0, ~50)
        // window again — either from cache or by re-issuing the bounded
        // query — and the row 0 cell text should be visible.
        await page.evaluate(() => {
            const viewports = [...document.querySelectorAll('.ag-body-viewport')] as HTMLElement[];
            let main: HTMLElement | null = null;
            let max = 0;
            for (const vp of viewports) {
                if (vp.scrollHeight > max) { max = vp.scrollHeight; main = vp; }
            }
            if (main) main.scrollTop = 0;
        });
        await page.waitForTimeout(1500);

        await expect(page.locator('.ag-cell:has-text("foo_10")').first()).toBeVisible({ timeout: 5000 });
    });
});
