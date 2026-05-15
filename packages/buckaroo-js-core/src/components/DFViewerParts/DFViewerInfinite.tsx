import {
    useCallback,
    useMemo,
    useEffect,
    useRef,
} from "react";
import * as _ from "lodash-es";
import { DFData, DFDataRow, DFViewerConfig, SDFT } from "./DFWhole";

import { getCellRendererSelector, dfToAgrid, extractPinnedRows, extractSDFT } from "./gridUtils";

import { AgGridReact } from "ag-grid-react"; // the AG Grid React Component
import {
    GetRowIdParams,
    GridApi,
    GridOptions,
    IDatasource,
    ModuleRegistry,
    ClientSideRowModelModule,
    InfiniteRowModelModule,
    CellStyleModule,
    ColumnAutoSizeModule,
    PinnedRowModule,
    RowSelectionModule,
    TooltipModule,
    TextFilterModule,
    SortChangedEvent,
    CellClassParams,
    RefreshCellsParams,
} from "ag-grid-community";
import {
    getAutoSize,
    getHeightStyle2,
    HeightStyleI,
    SetColumnFunc
} from "./gridUtils";
import { getThemeForScheme, resolveColorScheme, resolveThemeColors } from './gridUtils';
import { useColorScheme } from '../useColorScheme';
import type { ThemeConfig } from './gridUtils';

ModuleRegistry.registerModules([
    ClientSideRowModelModule,
    InfiniteRowModelModule,
    CellStyleModule,
    ColumnAutoSizeModule,
    PinnedRowModule,
    RowSelectionModule,
    TooltipModule,
    TextFilterModule,
]);

const AccentColor = "#2196F3"

// Shared label for swap-tracing console.logs. grep "[bk-flash]" in the
// browser console to see the timeline of a df_display toggle. Temporary —
// remove once the toggle path is confirmed working in production.
const bkLog = (event: string, extra?: Record<string, unknown>): void => {
    // eslint-disable-next-line no-console
    console.log(`[bk-flash ${performance.now().toFixed(1)}ms] ${event}`, extra ?? "");
};

export interface DatasourceWrapper {
    datasource: IDatasource;
    data_type: "DataSource";
    length: number; // length of full dataset, not most recent slice
    // maybe include the extra grid settings
}
export interface RawDataWrapper {
    data: DFData;
    length: number; // length of full dataset, not most recent slice
    data_type: "Raw";
}

export type DatasourceOrRaw = DatasourceWrapper | RawDataWrapper;

const staticGridOptions:GridOptions = {
    rowSelection: "single",
    enableCellTextSelection: true,
    tooltipShowDelay: 0,
    suppressFieldDotNotation:true,
    onRowClicked: (event) => {
        const sel = document.getSelection();
        if (sel === null) {
            return;
        }
        const range = document.createRange();
        const el = event?.event?.target;
        if (el === null || el === undefined) {
            return;
        }
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        //@ts-ignore
        range.selectNodeContents(el);
        sel.removeAllRanges();
        sel.addRange(range);
    },
};

/* these are gridOptions that should be fairly constant */
const outerGridOptions = (setActiveCol:SetColumnFunc, extra_grid_config?:GridOptions):GridOptions => {
    return {
        ...staticGridOptions,
        ...(extra_grid_config ? extra_grid_config : {}),
        onCellClicked: (event) => {
            const colName = event.column.getColId();
            if (setActiveCol === undefined || colName === undefined) {
                return;
            } else {
              const oldActiveCol = event.context.activeCol;
	      //@ts-ignore
	      const localActiveCol = [colName, event.column.colDef.headerName];
	      //@ts-ignore
              setActiveCol(localActiveCol)
              event.context.activeCol = localActiveCol;
                // this section is very performance sensitive.it controls which cells to rerender
                const args:RefreshCellsParams = {
                    rowNodes: event.api.getRenderedNodes(),
                    //@ts-ignore
                    columns: [event.api.getColumn(colName), event.api.getColumn(oldActiveCol[0])],
                    force:true
                }
                event.api.refreshCells(args)
            }
        },
    }
};

export function DFViewerInfinite({
    data_wrapper,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
    outside_df_params,
    error_info,
    max_rows_in_configs,
    view_name,
    data_key,
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    activeCol?: [string, string];
    setActiveCol: SetColumnFunc;
    // these are the parameters that could affect the table,
    // dfviewer doesn't need to understand them, but it does need to use
    // them as keys to get updated data
    outside_df_params?: any;
    error_info?: string;
    //splicing this in eventually
    max_rows_in_configs?:number // across all the configs what is the max rows
    // Identifies which df_display entry is active. When this changes, the
    // grid saves the previous view's column state (sort, widths, hide) and
    // applies the target view's saved state — or a "no sort" default on
    // first entry. Headers stay mounted across the swap.
    view_name?: string;
    // Identifies the underlying dataset (e.g. "main", "summary_stats"). Used
    // as a namespace in getRowId so rows from different datasets never share
    // a rowId, even though their `index` values overlap (row 0 in main is a
    // different record than row 0 in summary).
    data_key?: string;
}) {
    bkLog("DFViewerInfinite render", {
        view_name,
        data_key,
        data_type: data_wrapper.data_type,
        length: data_wrapper.length,
    });
    /*
    The idea is to do some pre-setup here for
    */
    const renderStartTime = useMemo(() => {
        //console.log("137renderStartTime");
        return Date.now();
    } , []);
    const totalRows=5;

    const compConfig =  df_viewer_config?.component_config;
    const rh = df_viewer_config?.extra_grid_config?.rowHeight;

    const hsCacheKey = JSON.stringify([totalRows,
        compConfig,
        rh]);
    //console.log("hsCacheKey", hsCacheKey);
    const hs:HeightStyleI = useMemo(() => {
        return getHeightStyle2(
            max_rows_in_configs || data_wrapper.length,
            df_viewer_config.pinned_rows.length,
            df_viewer_config?.component_config,
            df_viewer_config?.extra_grid_config?.rowHeight
        )}, [hsCacheKey]
    );
  const defaultActiveCol:[string, string] = ["", ""];
    const osColorScheme = useColorScheme();
    const rawThemeConfig = compConfig?.theme;
    const effectiveScheme = resolveColorScheme(osColorScheme, rawThemeConfig);
    const themeConfig = resolveThemeColors(effectiveScheme, rawThemeConfig);
    const defaultThemeClass = effectiveScheme === 'light' ? 'ag-theme-alpine' : 'ag-theme-alpine-dark';
    const divClass = `${defaultThemeClass} ${compConfig?.className || ''}`.trim();

    const bgColor = themeConfig?.backgroundColor || (effectiveScheme === 'light' ? '#ffffff' : '#181D1F');
    const themeStyle: React.CSSProperties = {
        ...hs.applicableStyle,
        ...(themeConfig?.accentColor ? { '--bk-accent-color': themeConfig.accentColor } as any : {}),
        ...(themeConfig?.accentHoverColor ? { '--bk-accent-hover-color': themeConfig.accentHoverColor } as any : {}),
        ...({ '--bk-bg-color': bgColor } as any),
        ...(themeConfig?.foregroundColor ? { '--bk-fg-color': themeConfig.foregroundColor } as any : {}),
    };

    return (
        <div className={`df-viewer  ${hs.classMode} ${hs.inIframe}`}>
            {error_info ? <pre>{error_info}</pre> : null}
            <div style={themeStyle}
                className={`theme-hanger ${divClass}`}>
                <DFViewerInfiniteInner
                    data_wrapper={data_wrapper}
                    df_viewer_config={df_viewer_config}
                    summary_stats_data={summary_stats_data || []}
                    activeCol={activeCol || defaultActiveCol}
                    setActiveCol={setActiveCol}
                    outside_df_params={outside_df_params}
                    renderStartTime={renderStartTime}
                    hs={hs}
                    themeConfig={themeConfig}
                    effectiveScheme={effectiveScheme}
                    view_name={view_name}
                    data_key={data_key}
                />
            </div>
        </div>)
}
export function DFViewerInfiniteInner({
    data_wrapper,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
    outside_df_params,
    renderStartTime: _renderStartTime,
    hs,
    themeConfig,
    effectiveScheme,
    view_name,
    data_key,
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
    summary_stats_data: DFData;
    activeCol: [string, string];
    setActiveCol: SetColumnFunc;
    // these are the parameters that could affect the table,
    // dfviewer doesn't need to understand them, but it does need to use
    // them as keys to get updated data
    outside_df_params?: any;
    renderStartTime:any;
    hs:HeightStyleI;
    themeConfig?: ThemeConfig;
    effectiveScheme?: 'light' | 'dark';
    view_name?: string;
    data_key?: string;
}) {
    bkLog("DFViewerInfiniteInner render", {
        view_name,
        data_key,
        data_type: data_wrapper.data_type,
        length: data_wrapper.length,
        outside_df_params,
    });


    /*
    const lastProps = useRef<any>(null);

    useEffect(() => {
        const now = Date.now();
        const timeSinceLastRender = now - renderStartTime.current;
        console.log(`[DFViewerInfinite] Render started at ${new Date(now).toISOString()}`);
        console.log(`[DFViewerInfinite] Time since last render: ${timeSinceLastRender}ms`);
        
        if (lastProps.current) {
            const changes = Object.keys(lastProps.current).filter(key => {
                return lastProps.current[key] !== {
                    data_wrapper,
                    df_viewer_config,
                    summary_stats_data,
                    activeCol,
                    outside_df_params,
                    error_info
                }[key];
            });
            console.log(`[DFViewerInfinite] Props that changed:`, changes);
        }
        
        lastProps.current = {
            data_wrapper,
            df_viewer_config,
            summary_stats_data,
            activeCol,
            outside_df_params,
            error_info
        };
        
        renderStartTime.current = now;
    }, [data_wrapper, df_viewer_config, summary_stats_data, activeCol, outside_df_params, error_info]);
    */
    const styledColumns = useMemo(() => {
        return dfToAgrid(df_viewer_config);
    }, [df_viewer_config]);

    // Column defs are ready

    const defaultColDef = useMemo( () => {
        return {
            sortable: true,
            type: "rightAligned",
            cellStyle: (params: CellClassParams) => {
                const colDef = params.column.getColDef();
                const field = colDef.field;
                const activeCol = params.context?.activeCol[0];
                if (params.node.isRowPinned()) {
                    return;
                }
                if (activeCol === field) {
                    //return {background:selectBackground}
                    return { background: themeConfig?.accentColor || AccentColor }

                }
                return { background: "inherit" }
            },
            enableCellChangeFlash: false,
            cellRendererSelector: getCellRendererSelector(df_viewer_config.pinned_rows, df_viewer_config.column_config)};
    }, [df_viewer_config.pinned_rows, df_viewer_config.column_config]);
    const histogram_stats:SDFT = extractSDFT(summary_stats_data);

    const extra_context = {
        activeCol,
        histogram_stats,
        pinned_rows_config:df_viewer_config.pinned_rows,
        // Available to getRowId so rows from different df_display entries
        // (main vs summary, etc.) don't share rowIds.
        data_key,
    }

    const pinned_rows = df_viewer_config.pinned_rows;
    // Always re-extract; upstream may mutate summary in-place without changing identity
    // Memoize to ensure it updates when summary_stats_data changes
    const topRowData = useMemo(
        () => extractPinnedRows(summary_stats_data, pinned_rows ? pinned_rows : []) as DFDataRow[],
        [summary_stats_data, pinned_rows]
    );
    // Pinned rows are extracted and ready


    const getRowId = useCallback(
        (params: GetRowIdParams) => {
            // Namespace rowIds by the active data_key so rows from different
            // datasets don't collide. "main" and "summary_stats" both have a
            // row at index 0 but they're different records — AG-Grid should
            // treat them as distinct identities, even when the grid stays
            // mounted across the swap.
            const ns = params.context?.data_key ?? "main";
            return `${ns}-${params?.data?.index}`;
        },
        [],
    );

    const resolvedScheme = effectiveScheme || 'dark';
    const myTheme = useMemo(() => getThemeForScheme(resolvedScheme, themeConfig).withParams({
        headerRowBorder: true,
        headerColumnBorder: true,
        headerColumnResizeHandleWidth: 0,
        ...(resolvedScheme === 'dark'
            ? { backgroundColor: themeConfig?.backgroundColor || "#121212", oddRowBackgroundColor: themeConfig?.oddRowBackgroundColor || '#3f3f3f' }
            : { backgroundColor: themeConfig?.backgroundColor || "#ffffff", oddRowBackgroundColor: themeConfig?.oddRowBackgroundColor || '#f0f0f0' }),
    }), [resolvedScheme, themeConfig]);
    const gridOptions: GridOptions = useMemo( () => {
        return {
        ...outerGridOptions(setActiveCol, df_viewer_config.extra_grid_config),
        domLayout:  hs.domLayout,
        autoSizeStrategy: df_viewer_config.extra_grid_config?.autoSizeStrategy || getAutoSize(styledColumns.length),
        onFirstDataRendered: (_params) => {
            bkLog("AgGrid onFirstDataRendered");
        },
        onModelUpdated: (_params) => {
            bkLog("AgGrid onModelUpdated");
        },
        onRowDataUpdated: (_params) => {
            bkLog("AgGrid onRowDataUpdated");
        },
        onSortChanged: (_event) => {
            bkLog("AgGrid onSortChanged", { sortModel: _event.api.getColumnState().filter((c: any) => c.sort) });
        },
        columnDefs:styledColumns,
        getRowId,
        rowModelType: "clientSide"}

    // NOTE: gating on `styledColumns` reference (which only changes when
    // df_viewer_config changes) rather than `JSON.stringify(styledColumns)` —
    // JSON.stringify drops function values, so it can't tell apart a colDef
    // with `valueFormatter: fn` from one with `cellRenderer: fn` (e.g. when a
    // search op adds highlight_regex to displayer_args). See highlight.test.tsx
    // "function-prop blind spot" tests.
    }, [styledColumns, hs, df_viewer_config.extra_grid_config, setActiveCol, getRowId]);

        // Extract datasource separately to ensure it updates when data_wrapper changes
        const datasource = useMemo(() => {
            bkLog("datasource useMemo recomputing", {
                data_type: data_wrapper.data_type,
                length: data_wrapper.length,
            });
            return data_wrapper.data_type === "DataSource" ? data_wrapper.datasource : {
                rowCount: data_wrapper.length,
                getRows: (_params: any) => {
                    console.debug("fake datasource getRows called, unexpected");
                    throw new Error("fake datasource getRows called, unexpected");
                }
            };
        }, [data_wrapper]);

        const finalGridOptions = useMemo( () => {
            return getFinalGridOptions(data_wrapper, gridOptions, hs);},
            [data_wrapper, gridOptions, hs]);
        // Use grid API to set pinned rows imperatively, avoiding a full React prop update that can flash
        const gridRef = useRef<AgGridReact<any> | null>(null);
        // Keep latest pinned rows in a ref so onGridReady can apply them once API is ready
        const topRowsRef = useRef<DFDataRow[] | null>(null);
        // Build a content signature based on visible fields and pinned values,
        // so we react to content changes even if the array identity is stable.
        const fieldsForSig = useMemo(() => {
            try {
                return (styledColumns as any[]).map((c: any) => c?.field).filter(Boolean);
            } catch {
                return [];
            }
        }, [styledColumns]);
        const pinnedSig = useMemo(() => {
            const vals = (topRowData || []).map((r: any) => fieldsForSig.map((f: string) => r?.[f]));
            const keys = (pinned_rows || []).map((p) => p.primary_key_val);
            return JSON.stringify({ k: keys, f: fieldsForSig, v: vals });
        }, [topRowData, fieldsForSig, pinned_rows]);
        useEffect(() => {
            try {
                const rows = (topRowData || []).map((r) => ({ ...r })); // force new refs
                topRowsRef.current = rows;
                gridRef.current?.api?.setGridOption('pinnedTopRowData', rows);
            } catch (_e) {
                // ignore until grid ready
            }
        }, [pinnedSig]);
        
        // Force update rowData when Raw data changes
        const rawDataSig = useMemo(() => {
            if (data_wrapper.data_type === "Raw") {
                return JSON.stringify(data_wrapper.data);
            }
            return null;
        }, [data_wrapper]);
        
        useEffect(() => {
            if (data_wrapper.data_type === "Raw" && gridRef.current?.api && rawDataSig) {
                try {
                    // Force AG Grid to update by setting rowData via API
                    gridRef.current.api.setGridOption('rowData', data_wrapper.data);
                } catch (_e) {
                    // ignore errors
                }
            }
        }, [rawDataSig, data_wrapper.data_type, data_wrapper]);

        // Data-identity signature: when outside_df_params content changes (e.g.
        // post_processing, cleaning_method, operations, df_display *within the
        // same data_type*), invalidate AG-Grid's infinite cache so it refetches
        // against the new sourceName. We do NOT remount — that's the React `key`
        // below, which is keyed only on data_type to handle the
        // DataSource<->Raw rowModelType switch that AG-Grid can't reconfigure
        // on a live instance.
        const outsideDFSig = useMemo(() => {
            try {
                return JSON.stringify(outside_df_params);
            } catch {
                return "no-outside-params";
            }
        }, [outside_df_params]);
        const firstSigRunRef = useRef(true);
        useEffect(() => {
            bkLog("outsideDFSig effect fired", {
                isFirstRun: firstSigRunRef.current,
                outsideDFSig,
                data_type: data_wrapper.data_type,
            });
            if (firstSigRunRef.current) {
                firstSigRunRef.current = false;
                return;
            }
            if (data_wrapper.data_type !== "DataSource") return;
            const api = gridRef.current?.api;
            if (!api) {
                bkLog("outsideDFSig effect — no api yet, skipping purge");
                return;
            }
            try {
                api.purgeInfiniteCache();
                bkLog("outsideDFSig effect — purgeInfiniteCache called");
            } catch (e) {
                bkLog("outsideDFSig effect — purgeInfiniteCache threw", { error: String(e) });
            }
        }, [outsideDFSig, data_wrapper.data_type]);

        // Per-view column state (sort, widths, hide, pinned, order) keyed by
        // view_name. Ephemeral — lives only as long as this component instance,
        // not persisted to buckaroo_state or anywhere upstream. On view_name
        // change: save current grid state under the previous view, then apply
        // the target view's saved state if any; otherwise blank the sort so
        // a freshly-entered view starts clean (summary stats in particular
        // are pre-ordered and sort by data value is meaningless).
        const viewStateRef = useRef<Record<string, { columnState: any[] }>>({});
        const prevViewNameRef = useRef<string | undefined>(view_name);
        useEffect(() => {
            bkLog("view_name effect fired", {
                from: prevViewNameRef.current,
                to: view_name,
                same: prevViewNameRef.current === view_name,
            });
            if (prevViewNameRef.current === view_name) return;
            const api = gridRef.current?.api;
            const prev = prevViewNameRef.current;
            prevViewNameRef.current = view_name;
            if (!api) {
                bkLog("view_name effect — no api yet, skipping save/restore");
                return;
            }
            // Save the outgoing view's state. If columnDefs changed across the
            // swap, AG-Grid will already have remapped state to the new column
            // shape — saving here records whatever AG-Grid currently believes
            // is the state. For the common case (same column_config across
            // views) this is the real outgoing state.
            if (prev !== undefined) {
                try {
                    const colState = api.getColumnState();
                    viewStateRef.current[prev] = { columnState: colState };
                    bkLog("view_name effect — saved state for prev view", { prev, colStateLen: colState.length });
                } catch (e) {
                    bkLog("view_name effect — getColumnState threw", { error: String(e) });
                }
            }
            const target = view_name !== undefined ? viewStateRef.current[view_name] : undefined;
            try {
                if (target?.columnState) {
                    api.applyColumnState({ state: target.columnState, applyOrder: true });
                    bkLog("view_name effect — applied stashed state for target view", { view_name });
                } else {
                    // First time entering this view — explicitly null out any
                    // sort that may have carried over from the previous view.
                    api.applyColumnState({ defaultState: { sort: null } });
                    bkLog("view_name effect — first entry, applied defaultState { sort: null }", { view_name });
                }
            } catch (e) {
                bkLog("view_name effect — applyColumnState threw", { error: String(e) });
            }
        }, [view_name]);

        return (

                <AgGridReact
                    ref={gridRef}
                    key={data_wrapper.data_type}
                    theme={myTheme}
                    loadThemeGoogleFonts
                    gridOptions={finalGridOptions}
                    defaultColDef={defaultColDef}
                    datasource={datasource}
                    columnDefs={styledColumns}
                    onGridReady={(params) => {
                        bkLog("AgGrid onGridReady", { view_name, data_key });
                        try {
                            // Ensure pinned rows are applied once API is ready
                            params.api.setGridOption('pinnedTopRowData', topRowsRef.current || []);
                        } catch (_e) {}
                    }}
                    context={{ outside_df_params, ...extra_context }}
                ></AgGridReact>
        );

}

// used to make sure there is a different element returned when
// Raw is used, so the component properly swaps over.
// Otherwise pinnedRows appear above the last scrolled position
// of the InfiniteRowSource vs having an empty data set.
const getFinalGridOptions = ( 
    data_wrapper: DatasourceOrRaw, gridOptions:GridOptions, hs: HeightStyleI
     ): GridOptions => {
    if (data_wrapper.data_type === "Raw") {
        return {
            ...gridOptions,
            rowData: data_wrapper.data,
            suppressNoRowsOverlay: true,
        };
    } else if (data_wrapper.data_type === "DataSource") {
        return getDsGridOptions(gridOptions, hs.maxRowsWithoutScrolling);
    } else {
        throw new Error(`Unexpected data_wrapper.data_type on  ${data_wrapper}`)
    }
 }

const getDsGridOptions = (origGridOptions: GridOptions, maxRowsWithoutScrolling:number):
 GridOptions => {
    const dsGridOptions: GridOptions = {
        ...origGridOptions,
        animateRows:false,
        suppressNoRowsOverlay: true,
        onSortChanged: (event: SortChangedEvent) => {
            const api: GridApi = event.api;
	    //@ts-ignore
            console.log(
                "sortChanged",
                api.getFirstDisplayedRowIndex(),
                api.getLastDisplayedRowIndex(),
                event,
            );
            // every time the sort is changed, scroll back to the top row.
            // Setting a sort and being in the middle of it makes no sense
            api.ensureIndexVisible(0);
        },
        rowBuffer: 20,
        rowModelType: "infinite",
        cacheBlockSize: maxRowsWithoutScrolling + 50,
        cacheOverflowSize: 0,
        maxConcurrentDatasourceRequests: 3,
        maxBlocksInCache: 0,
        // setting infiniteInitialRowCount causes a bad flash 
        // for object displaye columns while waiting for data. they show a column of None
        
        //infiniteInitialRowCount: maxRowsWithoutScrolling + 50
    };
    return dsGridOptions;
};export function DFViewer({
    df_data, df_viewer_config, summary_stats_data, activeCol, setActiveCol,
}: {
    df_data: DFData;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    activeCol?: [string, string];
    setActiveCol?: SetColumnFunc;
}) {
  const defaultSetColumnFunc = (newCol:[string, string]):void => {
        console.log("defaultSetColumnFunc", newCol)
    }
    const sac:SetColumnFunc = setActiveCol || defaultSetColumnFunc;
    
    return (
        <DFViewerInfinite
            data_wrapper={{
                data_type: "Raw",
                data: df_data,
                length: df_data.length
            }}
            df_viewer_config={df_viewer_config}
            summary_stats_data={summary_stats_data}
            activeCol={activeCol}
            setActiveCol={sac} />
    );
}

