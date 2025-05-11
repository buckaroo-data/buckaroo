import {
    useCallback,
    useMemo,
//    useEffect,
//    useRef,
} from "react";
import _ from "lodash";
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
} from "@ag-grid-community/core";
import { ClientSideRowModelModule } from "@ag-grid-community/client-side-row-model";
import { InfiniteRowModelModule } from "@ag-grid-community/infinite-row-model";

import {
    getAutoSize,
    getHeightStyle2,
    HeightStyleI,
    SetColumnFunc
} from "./gridUtils";
import { themeAlpine} from '@ag-grid-community/theming';
import { colorSchemeDark } from '@ag-grid-community/theming';

ModuleRegistry.registerModules([ClientSideRowModelModule]);
ModuleRegistry.registerModules([InfiniteRowModelModule]);


const AccentColor = "#2196F3"
const myTheme = themeAlpine.withPart(colorSchemeDark).withParams({
    spacing:5,
    browserColorScheme: "dark",
    cellHorizontalPaddingScale: 0.3,
    columnBorder: true,
    rowBorder: false,
    rowVerticalPaddingScale: 0.5,
    wrapperBorder: false,
    fontSize: 12,
    dataFontSize: "12px",
    headerFontSize: 14,
    iconSize: 10,
    backgroundColor: "#181D1F",

    oddRowBackgroundColor: '#222628',
    headerVerticalPaddingScale: 0.6,
//    cellHorizontalPadding: 3,

})


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
                //console.log("returning because setActiveCol is undefined");
                return;
            } else {
                //console.log("calling setActiveCol with", colName);
                //const oldActiveCol = event.context.activeCol;
                setActiveCol(colName);

                event.context.activeCol = colName;
                // this should force the selected column 
                //event.api.refreshCells({columns:[colName, oldActiveCol]})
                event.api.refreshCells({force:true})
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
    activeCol?: string;
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
    const divClass = df_viewer_config?.component_config?.className || "ag-theme-alpine-dark";
    return (
        <div className={`df-viewer  ${hs.classMode} ${hs.inIframe}`}>
            <pre>{error_info ? error_info : ""}</pre>
            <div style={hs.applicableStyle}
                className={`theme-hanger ${divClass}`}>
                <DFViewerInfiniteInner
                    data_wrapper={data_wrapper}
                    df_viewer_config={df_viewer_config}
                    summary_stats_data={summary_stats_data || []}
                    activeCol={activeCol || ""}
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
    renderStartTime,
    hs
}: {
    data_wrapper: DatasourceOrRaw;
    df_viewer_config: DFViewerConfig;
    summary_stats_data: DFData;
    activeCol: string;
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

    const defaultColDef = useMemo( () => {
        return {
            sortable: true,
            type: "rightAligned",
            cellStyle: (params:CellClassParams) => {
                const colDef = params.column.getColDef();
                const field = colDef.field;
                const activeCol = params.context?.activeCol;
                ///console.log("defaultColDef cellStyle params", params, colDef, field, params, activeCol);
                if(activeCol  === field) {
                    //return {background:selectBackground}
                    return {background: AccentColor}

                }
                return {background:"inherit"}
            },
            enableCellChangeFlash: false,
            cellRendererSelector: getCellRendererSelector(df_viewer_config.pinned_rows)};
    }, [df_viewer_config.pinned_rows]);
    const histogram_stats:SDFT = extractSDFT(summary_stats_data);

    const extra_context = {
        activeCol,
        histogram_stats,
        pinned_rows_config:df_viewer_config.pinned_rows
    }

    const pinned_rows = df_viewer_config.pinned_rows;
    const topRowData = extractPinnedRows(summary_stats_data, pinned_rows ? pinned_rows : []) as DFDataRow[];


    const getRowId = useCallback(
        (params: GetRowIdParams) => {
            const retVal = String(params?.data?.index) + params.context?.outside_df_params;
            return retVal;
        },
        [outside_df_params],
    );

    const gridOptions: GridOptions = useMemo( () => {
        return {
        ...outerGridOptions(setActiveCol, df_viewer_config.extra_grid_config),
        domLayout:  hs.domLayout,
        autoSizeStrategy: getAutoSize(styledColumns.length),
        onFirstDataRendered: (_params) => {
            console.log(`[DFViewerInfinite] AG-Grid finished rendering at ${new Date().toISOString()}`);
            console.log(`[DFViewerInfinite] Total render time: ${Date.now() - renderStartTime}ms`);
        },
        columnDefs:styledColumns,
        getRowId,
        rowModelType: "clientSide"}

    }, [styledColumns.length, JSON.stringify(styledColumns), hs, df_viewer_config.extra_grid_config, setActiveCol ]);

        const [finalGridOptions, datasource] = useMemo( () => {
            return getFinalGridOptions(data_wrapper, gridOptions, hs);},
            [data_wrapper, gridOptions, hs]);
            //console.log(styledColumns)
            //console.log(gridOptions)
        return (

                <AgGridReact
                    theme={myTheme}
                    loadThemeGoogleFonts
                    gridOptions={finalGridOptions}
                    defaultColDef={defaultColDef}
                    datasource={datasource}
                    pinnedTopRowData={topRowData}
                    columnDefs={styledColumns}
                    context={{ outside_df_params, ...extra_context }}
                ></AgGridReact>
        );

}

// used to make sure there is a different element returned when
// Raw is used, so the component properly swaps over.
// Otherwise pinnedRows appear above the last scrolled position
// of the InfiniteRowSource vs having an empty data set.
const getFinalGridOptions =( 
    data_wrapper: DatasourceOrRaw, gridOptions:GridOptions, hs: HeightStyleI,
     ): [GridOptions, IDatasource] => {
    if (data_wrapper.data_type === "Raw") {
        const fakeDatasource:IDatasource = {
            rowCount:data_wrapper.data.length,
            getRows: (_params: any) => {
                console.debug("fake datasource get rows called, unexpected");
                throw new Error("fake datasource get rows called, unexpected");
            }
        }
        return [{
            ...gridOptions,
            rowData: data_wrapper.data,
            suppressNoRowsOverlay: true,

        }, fakeDatasource];
    } else if (data_wrapper.data_type === "DataSource") {
        return [getDsGridOptions(gridOptions, hs.maxRowsWithoutScrolling ), data_wrapper.datasource];
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
    activeCol?: string;
    setActiveCol?: SetColumnFunc;
}) {
    const defaultSetColumnFunc = (newCol:string):void => {
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

