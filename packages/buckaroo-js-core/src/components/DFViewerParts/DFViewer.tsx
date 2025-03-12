import { CSSProperties } from "react";
import _ from "lodash";
import { ComponentConfig, DFData, DFViewerConfig } from "./DFWhole";

import { dfToAgrid, extractPinnedRows } from "./gridUtils";
import { replaceAtMatch } from "../utils";
import { AgGridReact } from "@ag-grid-community/react"; // the AG Grid React Component
import {
    ColDef,
    DomLayoutType,
    GridOptions,
    SizeColumnsToContentStrategy,
    SizeColumnsToFitProvidedWidthStrategy,
} from "@ag-grid-community/core";
import { getCellRendererSelector } from "./gridUtils";

import { ModuleRegistry } from "@ag-grid-community/core";
import { ClientSideRowModelModule } from "@ag-grid-community/client-side-row-model";

ModuleRegistry.registerModules([ClientSideRowModelModule]);
export type SetColumFunc = (newCol: string) => void;
export type PossibleAutosizeStrategy =
    | SizeColumnsToFitProvidedWidthStrategy
    | SizeColumnsToContentStrategy;

export const getGridOptions = (
    setActiveCol: SetColumFunc,
    df_viewer_config: DFViewerConfig,
    defaultColDef: ColDef,
    columnDefs: ColDef[],
    domLayout: DomLayoutType,
    autoSizeStrategy: PossibleAutosizeStrategy,
): GridOptions => {
    const gridOptions: GridOptions = {
        rowSelection: "single",

        enableCellTextSelection: true,
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
        tooltipShowDelay: 0,

        // defaultColDef needs to be specifically passed in as a prop to the component, not defined here,
        // otherwise updates aren't reactive

        onCellClicked: (event) => {
            const colName = event.column.getColId();
            if (setActiveCol === undefined || colName === undefined) {
                console.log("returning because setActiveCol is undefined");
                return;
            } else {
                console.log("calling setActiveCol with", colName);
                setActiveCol(colName);
            }
        },
        defaultColDef,
        columnDefs,
        domLayout,
        autoSizeStrategy,

        ...(df_viewer_config.extra_grid_config ? df_viewer_config.extra_grid_config : {}),
    };
    return gridOptions;
};

export function DFViewer({
    df_data: df,
    df_viewer_config,
    summary_stats_data,
    activeCol,
    setActiveCol,
}: {
    df_data: DFData;
    df_viewer_config: DFViewerConfig;
    summary_stats_data?: DFData;
    activeCol?: string;
    setActiveCol?: SetColumFunc;
}) {
    const agColsPure = dfToAgrid(df_viewer_config, summary_stats_data || []);
    const selectBackground =
        df_viewer_config?.component_config?.selectionBackground ||
        "var(--ag-range-selection-background-color-3)";
    const styledColumns = replaceAtMatch(_.clone(agColsPure), activeCol || "___never", {
        cellStyle: { background: selectBackground },
    });

    const defaultColDef = {
        sortable: true,
        type: "rightAligned",
        cellRendererSelector: getCellRendererSelector(df_viewer_config.pinned_rows),
    };

    //const gridRef = useRef<AgGridReact<unknown>>(null);
    const pinned_rows = df_viewer_config.pinned_rows;
    const topRowData = summary_stats_data
        ? extractPinnedRows(summary_stats_data, pinned_rows ? pinned_rows : [])
        : [];

    const divClass = df_viewer_config?.component_config?.className || "ag-theme-alpine-dark";
    const hs = getHeightStyle(df_viewer_config, df.length);
    const gridOptions = getGridOptions(
        setActiveCol as SetColumFunc,
        df_viewer_config,
        defaultColDef,
        _.cloneDeep(styledColumns),
        hs.domLayout,
        getAutoSize(styledColumns.length),
    );

    return (
        <div className={`df-viewer  ${hs.classMode} ${hs.inIframe}`}>
            <div style={hs.applicableStyle} className={`theme-hanger ${divClass}`}>
                <AgGridReact

                    domLayout={hs.domLayout}
                    defaultColDef={defaultColDef}
                    gridOptions={gridOptions}
                    rowData={df}
                    pinnedTopRowData={topRowData}
                    columnDefs={_.cloneDeep(styledColumns)}
                    autoSizeStrategy={getAutoSize(styledColumns.length)}
                ></AgGridReact>
            </div>
        </div>
    );
}

interface HeightStyleArgs {
    numRows: number;
    pinnedRowLen: number;
    readonly location: Location;
    rowHeight?: number;
    compC?: ComponentConfig;
}
export interface HeightStyleI {
    domLayout: DomLayoutType; // an ag-grid argument https://www.ag-grid.com/javascript-data-grid/grid-size/#dom-layout
    inIframe: string; // is this being rendered in an iFrame
    //the class for the outer wrapping div
    classMode: "short-mode" | "regular-mode"; 
    applicableStyle: CSSProperties;
    maxRowsWithoutScrolling:number;
}

export const getHeightStyle = (df_viewer_config: DFViewerConfig, numRows: number): HeightStyleI => {
    const hs = heightStyle({
        numRows: numRows,
        pinnedRowLen: df_viewer_config.pinned_rows.length,
        location: window.location,
        compC: df_viewer_config?.component_config,
        rowHeight: df_viewer_config?.extra_grid_config?.rowHeight,
    });
    return hs;
};
export const heightStyle = (hArgs: HeightStyleArgs): HeightStyleI => {
    /*
      This function is intended to consolidate all of the calculations for the vertical styling of the viewer

      
      */
    const { numRows, pinnedRowLen, location, rowHeight, compC } = hArgs;
    const isGoogleColab = location.host.indexOf("colab.googleusercontent.com") !== -1;

    const inIframe = window.parent !== window;
    const regularCompHeight = window.innerHeight / (compC?.height_fraction || 2);
    const dfvHeight = compC?.dfvHeight || regularCompHeight;
    const regularDivStyle = { height: dfvHeight };
    const shortDivStyle = { minHeight: 50, maxHeight: dfvHeight };

    // scrollSlop controls the tolerance for maxRowsWithoutScrolling
    // to enable scrolling anyway. scroll slop includes room for other
    // parts of the widget, notably the status bar

    // This still allows for scrolling of a single row. I'd rather
    // have the min scroll amount... if rows are hidden, at least 5
    // should be hidden... That would require sizing the whole widget
    // smaller in that case which is also messy and inconsistent. I
    // wish there were persistent side scrollbars a UI affordance we
    // have lost
    
    const scrollSlop = 3;

    // figured out default row height of 21.  Want to plumb back in to what is actually rendered.
    const maxRowsWithoutScrolling = Math.floor((dfvHeight / (rowHeight || 21)) - scrollSlop);



    const belowMinRows = (numRows + pinnedRowLen) < maxRowsWithoutScrolling;
    //console.log("maxRowsWithoutScrolling", maxRowsWithoutScrolling, belowMinRows, numRows, dfvHeight, rowHeight);
    const shortMode = compC?.shortMode || (belowMinRows && rowHeight === undefined);

    const inIframeClass = inIframe ? "inIframe" : "";
    if (isGoogleColab || inIframe) {
        return {
            classMode: "regular-mode",
            domLayout: "normal",
            applicableStyle: { height: 500 },
            inIframe: inIframeClass,
            maxRowsWithoutScrolling
        };
    }
    const domLayout: DomLayoutType = compC?.layoutType || (shortMode ? "autoHeight" : "normal");
    const applicableStyle = shortMode ? shortDivStyle : regularDivStyle;
    const classMode = shortMode ? "short-mode" : "regular-mode";
    return {
        classMode,
        domLayout,
        applicableStyle,
        inIframe: inIframeClass,
        maxRowsWithoutScrolling
    };
};
export const getAutoSize = (
    numColumns: number,
): SizeColumnsToFitProvidedWidthStrategy | SizeColumnsToContentStrategy => {
    if (numColumns < 1) {
        return {
            type: "fitProvidedWidth",
            width: window.innerWidth - 100,
        };
    }
    return {
        type: "fitCellContents",
    };
};
