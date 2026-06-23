import { test, expect } from '@playwright/test';
import { waitForCells, getCellLocator, getRowCount } from './ag-pw-utils';

// Integration coverage for the `json` DFEnvelope variant. The story mounts
// BuckarooStaticTable with a json envelope as df_data, so the rows reach the
// grid only if decodeDFData's json branch decoded the inline record array at
// the real ingestion edge.
test.describe('json DFEnvelope decodes through the JS ingestion edge', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto(
            'http://localhost:6006/iframe.html?viewMode=story&id=buckaroo-transport-jsonenvelope--primary&globals=&args='
        );
        await waitForCells(page);
    });

    test('renders the inline record-array rows decoded from the json envelope', async ({ page }) => {
        expect(await getRowCount(page)).toBe(2);

        await expect(getCellLocator(page, 'a', 0)).toHaveText('alpha');
        await expect(getCellLocator(page, 'b', 0)).toHaveText('foo');
        await expect(getCellLocator(page, 'a', 1)).toHaveText('beta');
        await expect(getCellLocator(page, 'b', 1)).toHaveText('bar');
    });
});
