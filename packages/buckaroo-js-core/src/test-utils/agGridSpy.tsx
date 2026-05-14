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
import type { IGetRowsParams, RefreshCellsParams } from "ag-grid-community";

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
    applyColumnState: Array<any>;
    // Tests can populate this to control what getColumnState() returns. Use
    // setMockColumnState() to update.
    columnStateMock: any[];
}

const sharedCalls: AgGridSpyCalls = {
    mountCount: 0,
    setGridOption: [],
    refreshCells: [],
    refreshInfiniteCache: 0,
    purgeInfiniteCache: 0,
    getRowsCallArgs: [],
    rowIdsByIndex: new Map(),
    lastProps: null,
    onGridReadyCalled: 0,
    applyColumnState: [],
    columnStateMock: [],
};

export const resetSpy = (): void => {
    sharedCalls.mountCount = 0;
    sharedCalls.setGridOption = [];
    sharedCalls.refreshCells = [];
    sharedCalls.refreshInfiniteCache = 0;
    sharedCalls.purgeInfiniteCache = 0;
    sharedCalls.getRowsCallArgs = [];
    sharedCalls.rowIdsByIndex = new Map();
    sharedCalls.lastProps = null;
    sharedCalls.onGridReadyCalled = 0;
    sharedCalls.applyColumnState = [];
    sharedCalls.columnStateMock = [];
};

// Tests use this to seed what the next getColumnState() call returns —
// e.g. to simulate "user sorted column A asc in this view".
export const setMockColumnState = (state: any[]): void => {
    sharedCalls.columnStateMock = state;
};

/**
 * Factory called by `jest.mock("ag-grid-react", ...)` to install the spy.
 *
 * NOTE: jest.mock() factory bodies must not reference out-of-scope variables.
 * That's why this module exports `resetSpy` + `getSpyCalls` + the factory
 * rather than a closure-capturing builder. The factory inlines a reference to
 * `sharedCalls` via the module re-import, which is allowed.
 */
export const agGridReactMockFactory = () => {
    const ReactLocal = require("react") as typeof React;
    return {
        AgGridReact: ReactLocal.forwardRef((props: any, ref: any) => {
            sharedCalls.lastProps = props;

            // mount count: only increments on actual mount, not on prop update
            ReactLocal.useEffect(() => {
                sharedCalls.mountCount += 1;
                // no cleanup-side-effect; unmount is implied by mountCount delta
            }, []);

            const api = ReactLocal.useMemo(() => {
                return {
                    setGridOption: (key: string, value: unknown) => {
                        sharedCalls.setGridOption.push([key, value]);
                    },
                    refreshCells: (params: RefreshCellsParams) => {
                        sharedCalls.refreshCells.push(params);
                    },
                    refreshInfiniteCache: () => {
                        sharedCalls.refreshInfiniteCache += 1;
                    },
                    purgeInfiniteCache: () => {
                        sharedCalls.purgeInfiniteCache += 1;
                    },
                    getRenderedNodes: () => [],
                    getColumn: (colId: string) => ({
                        getColId: () => colId,
                        colDef: { headerName: colId, field: colId },
                    }),
                    getFirstDisplayedRowIndex: () => 0,
                    getLastDisplayedRowIndex: () => 0,
                    ensureIndexVisible: () => {},
                    getColumnState: () => sharedCalls.columnStateMock,
                    applyColumnState: (params: any) => {
                        sharedCalls.applyColumnState.push(params);
                    },
                };
            }, []);

            ReactLocal.useImperativeHandle(ref, () => ({ api }), [api]);

            // exercise getRowId for a stable sample of indexes so tests can
            // detect row-id salting from outside_df_params
            if (typeof props.gridOptions?.getRowId === "function") {
                for (const idx of [0, 1, 2]) {
                    try {
                        const rid = props.gridOptions.getRowId({
                            data: { index: idx },
                            context: props.context,
                        });
                        if (typeof rid === "string") {
                            const set = sharedCalls.rowIdsByIndex.get(idx) ?? new Set<string>();
                            set.add(rid);
                            sharedCalls.rowIdsByIndex.set(idx, set);
                        }
                    } catch {
                        // ignore
                    }
                }
            }

            // exercise getRows once per render so we can see what sourceName
            // the datasource builds from context.outside_df_params
            ReactLocal.useEffect(() => {
                const ds = props.datasource;
                if (!ds || typeof ds.getRows !== "function") return;
                const gr: IGetRowsParams = {
                    startRow: 0,
                    endRow: 100,
                    successCallback: () => {},
                    failCallback: () => {},
                    sortModel: [],
                    filterModel: {},
                    context: props.context,
                } as any;
                sharedCalls.getRowsCallArgs.push(gr);
                try {
                    ds.getRows(gr);
                } catch {
                    // some test stories throw on getRows; we only care about the args
                }
            }, [props.datasource]);

            // fire onGridReady so app code that registers options imperatively runs
            ReactLocal.useEffect(() => {
                sharedCalls.onGridReadyCalled += 1;
                props.onGridReady?.({ api });
            }, [api]);

            return ReactLocal.createElement("div", { "data-testid": "ag-grid-react-spy" });
        }),
    };
};

export const getSpyCalls = (): AgGridSpyCalls => sharedCalls;
