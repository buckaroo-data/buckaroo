import {
    useCallback,
    useMemo,
    useEffect,
    useRef,
} from "react";
import { DFData, DFDataRow, DFViewerConfig, SDFT } from "./DFWhole";

import { getCellRendererSelector, dfToAgrid, extractPinnedRows, extractSDFT } from "./gridUtils";

import { AgGridReact } from "@ag-grid-community/react"; // the AG Grid React Component
import {
    GetRowIdParams,
    GridApi,
    GridOptions,
    IDatasource,
    ModuleRegistry,
    SortChangedEvent,
    CellClassParams,
    RefreshCellsParams,
    //ColDef,
} from "@ag-grid-community/core";
import { ClientSideRowModelModule } from "@ag-grid-community/client-side-row-model";
import { InfiniteRowModelModule } from "@ag-grid-community/infinite-row-model";

import {
    getAutoSize,
    getHeightStyle2,
    HeightStyleI,
    SetColumnFunc
} from "./gridUtils";
import { getThemeForScheme } from './gridUtils';
import { useColorScheme } from '../useColorScheme';

ModuleRegistry.registerModules([ClientSideRowModelModule]);
ModuleRegistry.registerModules([InfiniteRowModelModule]);


const AccentColor = "#2196F3"



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
    max_rows_in_configs
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

}) {
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
    const colorScheme = useColorScheme();
    const defaultThemeClass = colorScheme === 'light' ? 'ag-theme-alpine' : 'ag-theme-alpine-dark';
    const divClass = df_viewer_config?.component_config?.className || defaultThemeClass;
    return (
        <div className={`df-viewer  ${hs.classMode} ${hs.inIframe}`}>
            {error_info ? <pre>{error_info}</pre> : null}
            <div style={hs.applicableStyle}
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
    hs
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
    hs:HeightStyleI
}) {


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
                    return { background: AccentColor }

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
        pinned_rows_config:df_viewer_config.pinned_rows
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
            const outsideKey = JSON.stringify(params.context?.outside_df_params) || "";
            const retVal = `${String(params?.data?.index)}-${outsideKey}`;
            return retVal;
        },
        [outside_df_params],
    );

    const colorScheme = useColorScheme();
    const myTheme = useMemo(() => getThemeForScheme(colorScheme).withParams({
        headerRowBorder: true,
        headerColumnBorder: true,
        headerColumnResizeHandleWidth: 0,
        ...(colorScheme === 'dark'
            ? { backgroundColor: "#121212", oddRowBackgroundColor: '#3f3f3f' }
            : { backgroundColor: "#ffffff", oddRowBackgroundColor: '#f0f0f0' }),
    }), [colorScheme]);
    const gridOptions: GridOptions = useMemo( () => {
        return {
        ...outerGridOptions(setActiveCol, df_viewer_config.extra_grid_config),
        domLayout:  hs.domLayout,
        autoSizeStrategy: getAutoSize(styledColumns.length),
        onFirstDataRendered: (_params) => {
            // Grid finished rendering
        },
        columnDefs:styledColumns,
        getRowId,
        rowModelType: "clientSide"}

    }, [styledColumns.length, JSON.stringify(styledColumns), hs, df_viewer_config.extra_grid_config, setActiveCol, getRowId, outside_df_params ]);

        // Extract datasource separately to ensure it updates when data_wrapper changes
        const datasource = useMemo(() => {
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

        return (

                <AgGridReact
                    ref={gridRef}
                    key={JSON.stringify(outside_df_params) || "no-outside-params"}
                    theme={myTheme}
                    loadThemeGoogleFonts
                    gridOptions={finalGridOptions}
                    defaultColDef={defaultColDef}
                    datasource={datasource}
                    columnDefs={styledColumns}
                    onGridReady={(params) => {
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

