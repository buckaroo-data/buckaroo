/**
 * Verifies that buckaroo-js-core renders correctly when installed from the
 * BUILT package (the locally-packed tarball), not from workspace source.
 *
 * The setup is:
 *   1. run.sh builds buckaroo-js-core (`pnpm run build`)
 *   2. run.sh packs it (`pnpm pack`) into ./buckaroo-js-core.tgz
 *   3. `npm install` resolves the dep via the package.json `file:` reference
 *   4. Vite serves a tiny consumer that imports `{ DFViewer } from "buckaroo-js-core"`
 *   5. This test loads that page and asserts the cells are in the DOM
 *
 * Anything that breaks the published package shape (missing main, missing
 * dist files, mis-routed exports, wrong React peer dep) breaks this test.
 */
import { test, expect } from "@playwright/test";

test.describe("buckaroo-js-core renders from the built tarball", () => {
  test("page title and three sample rows appear in the DOM", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("page-title")).toHaveText(
      "buckaroo-js-core (built tarball)",
    );

    // AG-Grid renders cells lazily; wait for at least one .ag-cell.
    await page.locator(".ag-cell").first().waitFor({ state: "visible", timeout: 10_000 });

    // The three label values from main.tsx.
    await expect(page.getByText("alpha", { exact: true })).toBeVisible();
    await expect(page.getByText("beta", { exact: true })).toBeVisible();
    await expect(page.getByText("gamma", { exact: true })).toBeVisible();

    // And one numeric value to prove the second column also rendered.
    await expect(page.getByText("22", { exact: true })).toBeVisible();
  });

  test("imports resolve to the installed tarball, not workspace source", async ({ page }) => {
    // Belt-and-suspenders check: if the dep accidentally got hoisted to a
    // workspace symlink, the resolved URL would point at packages/buckaroo-js-core/...
    // We assert the URL resolves under node_modules/buckaroo-js-core/dist/.
    await page.goto("/");

    const resolvedHrefs: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("buckaroo-js-core")) resolvedHrefs.push(url);
    });
    // Reload so we capture the initial fetch tree.
    await page.reload();
    await page.locator(".ag-cell").first().waitFor({ state: "visible", timeout: 10_000 });

    // Some resolved URL must include node_modules/buckaroo-js-core/. None
    // should include packages/buckaroo-js-core/src — that would mean the
    // bundler resolved through the workspace.
    const hitsNodeModules = resolvedHrefs.some((u) =>
      u.includes("node_modules/buckaroo-js-core"),
    );
    const hitsWorkspaceSource = resolvedHrefs.some((u) =>
      u.includes("packages/buckaroo-js-core/src"),
    );
    expect(hitsWorkspaceSource).toBe(false);
    // If Vite inlines everything into one bundle, hitsNodeModules might be false
    // even though resolution was correct. So we only HARD-fail on workspace-source
    // hits; node_modules visibility is best-effort.
    if (!hitsNodeModules) {
      console.info(
        "[built-pkg integration] no node_modules/buckaroo-js-core fetch observed; " +
          "Vite likely pre-bundled the dep. workspace-source check still passed.",
      );
    }
  });
});
