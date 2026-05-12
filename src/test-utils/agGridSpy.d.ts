import { IGetRowsParams, RefreshCellsParams } from 'ag-grid-community';
/**
 * Spy harness for the ag-grid-react mock used by the flash-matrix tests.
 *
 * Replaces the AgGridReact component with a stub that records:
 *   - mountCount               — how many times AgGridReact mounted
 *   - setGridOption[]          — every (key, value) passed to setGridOption
 *   - refreshCells[]            — every refreshCells call
 *   - refreshInfiniteCache      — count
 *   - purgeInfiniteCache        — count
 *   - getRowsCallArgs[]         — every IGetRowsParams passed to the datasource
 *   - rowIdsByIndex             — for each row index, the distinct row IDs produced
 *                                 by getRowId across renders (probes the row-id
 *                                 salting behavior)
 *   - lastProps                 — the most recent props object
 *
 * Use:
 *
 *   const spy = createAgGridSpy();
 *   spy.install();   // call BEFORE `render()` (jest.mock is hoisted by ts-jest;
 *                    //   install() resets the captured state instead)
 *
 *   render(<DFViewerInfinite ... />);
 *   expect(spy.calls.mountCount).toBe(1);
 */
import * as React from "react";
export interface AgGridSpyCalls {
    mountCount: number;
    setGridOption: Array<[string, unknown]>;
    refreshCells: RefreshCellsParams[];
    refreshInfiniteCache: number;
    purgeInfiniteCache: number;
    getRowsCallArgs: IGetRowsParams[];
    rowIdsByIndex: Map<number, Set<string>>;
    lastProps: any;
    onGridReadyCalled: number;
}
export declare const resetSpy: () => void;
/**
 * Factory called by `jest.mock("ag-grid-react", ...)` to install the spy.
 *
 * NOTE: jest.mock() factory bodies must not reference out-of-scope variables.
 * That's why this module exports `resetSpy` + `getSpyCalls` + the factory
 * rather than a closure-capturing builder. The factory inlines a reference to
 * `sharedCalls` via the module re-import, which is allowed.
 */
export declare const agGridReactMockFactory: () => {
    AgGridReact: React.ForwardRefExoticComponent<Omit<any, "ref"> & React.RefAttributes<unknown>>;
};
export declare const getSpyCalls: () => AgGridSpyCalls;
