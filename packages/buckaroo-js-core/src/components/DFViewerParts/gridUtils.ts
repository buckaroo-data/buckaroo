import {
    CellRendererSelectorResult,
    ColDef,
    DomLayoutType,
    GridOptions,
    ICellRendererParams,
    IDatasource,
    IGetRowsParams,
    SizeColumnsToContentStrategy,
    SizeColumnsToFitProvidedWidthStrategy,
} from "@ag-grid-community/core";

import {
    DFWhole,
    DisplayerArgs,
    cellRendererDisplayers,
    ColumnConfig,

    DFViewerConfig,
    ComponentConfig,
} from "./DFWhole";
import _, { zipObject } from "lodash";
import { getTextCellRenderer } from "./OtherRenderers";
import { getStyler } from "./Styler";
import { DFData, SDFMeasure, SDFT } from "./DFWhole";

import { CellRendererArgs, FormatterArgs, PinnedRowConfig } from "./DFWhole";
import { getTooltipParams } from "./SeriesSummaryTooltip";
import { getFormatterFromArgs, getCellRenderer, objFormatter, getFormatter } from "./Displayer";
import { CSSProperties, Dispatch, SetStateAction } from "react";
import { CommandConfigT } from "../CommandUtils";
import { KeyAwareSmartRowCache, PayloadArgs } from "./SmartRowCache";
import { colorSchemeDark, themeAlpine, Theme } from "@ag-grid-community/theming";


// for now colDef stuff with less than 3 implementantions should stay in this file
// as implementations grow large or with many implmentations, they should move to separate files
// like displayer

export function addToColDef(
    dispArgs: DisplayerArgs,
    //@ts-ignore
    summary_stats_column: SDFMeasure,
) {
    const formatter = getFormatterFromArgs(dispArgs);
    if (formatter !== undefined) {
        const colDefExtras: ColDef = { valueFormatter: formatter };
        return colDefExtras;
    }

    if (_.includes(cellRendererDisplayers, dispArgs.displayer)) {
        const crArgs: CellRendererArgs = dispArgs as CellRendererArgs;
        return {
            cellRenderer: getCellRenderer(crArgs),
        };
    }
    return undefined;
}


export function extractPinnedRows(sdf: DFData, prc: PinnedRowConfig[]) {
    return _.map(_.map(prc, "primary_key_val"), (x) => _.find(sdf, { index: x }));
}

export function extractSingleSeriesSummary(
    full_summary_stats_df: DFData,
    col_name: string,
): DFWhole {
    return {
        dfviewer_config: {
            column_config: [
                { col_name: "index", displayer_args: { displayer: "obj" } },
                { col_name: col_name, displayer_args: { displayer: "obj" } },
            ],
            pinned_rows: [],
        },
        data: _.filter(
            _.map(full_summary_stats_df, (row) => _.pick(row, ["index", col_name])),
            { index: "dtype" },
        ),
    };
}

export function dfToAgrid(
    dfviewer_config: DFViewerConfig,
    full_summary_stats_df: DFData,
): ColDef[] {
    //more convienient df format for some formatters
    const hdf = extractSDFT(full_summary_stats_df || []);

    const retColumns: ColDef[] = dfviewer_config.column_config.map((f: ColumnConfig) => {
        const single_series_summary_df = extractSingleSeriesSummary(
            full_summary_stats_df,
            f.col_name,
        );

        const color_map_config = f.color_map_config
            ? getStyler(f.color_map_config, f.col_name, hdf)
            : {};

        const colDef: ColDef = {
            field: f.col_name,
            headerName: f.col_name,
            cellDataType: false,
            cellStyle: {}, // necessary for colormapped columns to have a default
            ...addToColDef(f.displayer_args, hdf[f.col_name]),
            ...color_map_config,
            ...getTooltipParams(single_series_summary_df, f.tooltip_config),
            ...f.ag_grid_specs,
        };
        console.log("colDef", colDef)
        return colDef;
    });
    return retColumns;
}

// this is very similar to the colDef parts of dfToAgrid
export function getCellRendererSelector(pinned_rows: PinnedRowConfig[]) {
    const anyRenderer: CellRendererSelectorResult = {
        component: getTextCellRenderer(objFormatter),
    };
    return (params: ICellRendererParams<any, any, any>): CellRendererSelectorResult | undefined => {
        if (params.node.rowPinned) {
            const pk = _.get(params.node.data, "index");
            if (pk === undefined) {
                return anyRenderer; // default renderer
            }
            const maybePrc: PinnedRowConfig | undefined = _.find(pinned_rows, {
                primary_key_val: pk,
            });
            if (maybePrc === undefined) {
                return anyRenderer;
            }
            const prc: PinnedRowConfig = maybePrc;
            const currentCol = params.column?.getColId();
            if (
                (prc.default_renderer_columns === undefined && currentCol === "index") ||
                _.includes(prc.default_renderer_columns, currentCol)
            ) {
                return anyRenderer;
            }
            const possibCellRenderer = getCellRenderer(prc.displayer_args as CellRendererArgs);

            if (possibCellRenderer === undefined) {
                const formattedRenderer: CellRendererSelectorResult = {
                    component: getTextCellRenderer(
                        getFormatter(prc.displayer_args as FormatterArgs),
                    ),
                };
                return formattedRenderer;
            }
            return { component: possibCellRenderer };
        } else {
            return undefined; // rows that are not pinned don't use a row level cell renderer
        }
    };
}

export function extractSDFT(summaryStatsDf: DFData): SDFT {
    const maybeHistogramBins = _.find(summaryStatsDf, { index: "histogram_bins" }) || {};
    const maybeHistogramLogBins = _.find(summaryStatsDf, { index: "histogram_log_bins" }) || {};
    const allColumns: string[] = _.without(
        _.union(_.keys(maybeHistogramBins), _.keys(maybeHistogramLogBins)),
        "index",
    );
    const vals: SDFMeasure[] = _.map(allColumns, (colName) => {
        return {
            histogram_bins: _.get(maybeHistogramBins, colName, []) as number[],
            histogram_log_bins: _.get(maybeHistogramLogBins, colName, []) as number[],
        };
    });
    return zipObject(allColumns, vals) as SDFT;
}

export const getPayloadKey = (payloadArgs: PayloadArgs): string => {
    return `${payloadArgs.sourceName}-${payloadArgs.start}-${payloadArgs.end}-${payloadArgs.sort}-${payloadArgs.sort_direction}`;
};
export type CommandConfigSetterT = (setter: Dispatch<SetStateAction<CommandConfigT>>) => void;

export interface IDisplayArgs {
    data_key: string;
    df_viewer_config: DFViewerConfig;
    summary_stats_key: string;
}

export interface TimedIDatasource extends IDatasource {
    createTime: Date;
}


export const getDs = (
    src: KeyAwareSmartRowCache,
): TimedIDatasource => {
    const dsLoc: TimedIDatasource = {
        createTime: new Date(),
        rowCount: undefined,
        getRows: (params: IGetRowsParams) => {
            const sm = params.sortModel;
            const outside_params_string = JSON.stringify(params.context?.outside_df_params);
            const dsPayloadArgs = {
                sourceName: outside_params_string,
                start: params.startRow,
                end: params.startRow + 1000,
                origEnd: params.endRow,
                sort: sm.length === 1 ? sm[0].colId : undefined,
                sort_direction: sm.length === 1 ? sm[0].sort : undefined,
            };
            const successWrapper = (df:DFData, length:number) => {
                //console.log("successWrapper called 217", 
                //   [dsPayloadArgs.start, dsPayloadArgs.end], length)
                params.successCallback(df, length)
            }

            const failWrapper = () => {
                console.log("request failed for ", dsPayloadArgs)
                params.failCallback()
            }
            // src.getRequestRows(dsPayloadArgs, params.successCallback)
            src.getRequestRows(dsPayloadArgs, successWrapper, failWrapper)
        }
    };
    return dsLoc;
};
export type SetColumFunc = (newCol: string) => void;
export type PossibleAutosizeStrategy = SizeColumnsToFitProvidedWidthStrategy |
    SizeColumnsToContentStrategy;

export const getGridOptions = (
    setActiveCol: SetColumFunc,
    df_viewer_config: DFViewerConfig,
    defaultColDef: ColDef,
    columnDefs: ColDef[],
    domLayout: DomLayoutType,
    autoSizeStrategy: PossibleAutosizeStrategy
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
    maxRowsWithoutScrolling: number;
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
const inVSCcode = () => {
    // vscIPYWidgets will be present on window when rendered in VSCode
    //@ts-ignore
    if(window.vscIPyWidgets !== undefined) {
        return true
    }
    return false

}
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
    console.log("heightstyle", dfvHeight)
    if (isGoogleColab || inVSCcode() ) {
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
    numColumns: number
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



export const myTheme: Theme = themeAlpine.withPart(colorSchemeDark).withParams({
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