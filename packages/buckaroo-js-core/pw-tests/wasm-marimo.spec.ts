import { test, expect, Page } from '@playwright/test';

/**
 * Smoke test for Buckaroo's marimo WASM notebook.
 *
 * In Pyodide/WASM the full anywidget rendering pipeline is not yet reliable,
 * so this test verifies that:
 *   1. The marimo WASM app boots (React shell renders)
 *   2. Pyodide initialises and executes at least the markdown cells
 *   3. The expected notebook content is visible on the page
 *
 * Full widget-rendering tests are tracked in
 * https://github.com/buckaroo-data/buckaroo/issues/513
 */

let sharedPage: Page;

test.describe('Buckaroo in Marimo WASM (Pyodide)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();
    await sharedPage.goto('/');

    // Wait for the marimo React app to mount (the #root div gets content)
    await sharedPage
      .locator('#root .contents')
      .first()
      .waitFor({ state: 'visible', timeout: 30_000 });

    // Wait for Pyodide to initialise and render at least the markdown cells.
    // The h1 "Buckaroo in Marimo WASM" comes from a mo.md() call that only
    // executes once the Python kernel is alive.
    await sharedPage
      .locator('h1#buckaroo-in-marimo-wasm')
      .waitFor({ state: 'visible', timeout: 120_000 });
  });

  test.afterAll(async () => {
    await sharedPage?.close();
  });

  test('marimo WASM app loads and renders notebook content', async () => {
    // --- 1. The page title should contain the notebook name ----------------
    const title = await sharedPage.title();
    expect(title.toLowerCase()).toContain('buckaroo');

    // --- 2. The main heading is rendered by the Python kernel --------------
    const h1 = sharedPage.locator('h1#buckaroo-in-marimo-wasm');
    await expect(h1).toBeVisible();
    await expect(h1).toHaveText('Buckaroo in Marimo WASM');

    // --- 3. At least two output-area divs are present (markdown cells) -----
    const outputAreas = await sharedPage.locator('.output-area').all();
    expect(outputAreas.length).toBeGreaterThanOrEqual(2);

    // --- 4. Notebook description paragraph is visible ----------------------
    const description = sharedPage.locator('text=Buckaroo widgets running in Pyodide/WASM');
    await expect(description.first()).toBeVisible();

    // --- 5. The footer note about first-load time is visible ---------------
    const note = sharedPage.locator('text=First load takes');
    await expect(note.first()).toBeVisible();
  });
});
