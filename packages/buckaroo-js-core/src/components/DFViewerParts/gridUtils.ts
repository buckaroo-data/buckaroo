import {
    CellRendererSelectorResult,
    ColDef,
    ICellRendererParams,
    IDatasource,
    IGetRowsParams,
} from "@ag-grid-community/core";

import {
    DFWhole,
    DisplayerArgs,
    cellRendererDisplayers,
    ColumnConfig,
    TooltipConfig,
    DFViewerConfig,
} from "./DFWhole";
import _, { zipObject } from "lodash";
import { getTextCellRenderer } from "./OtherRenderers";
import { getStyler } from "./Styler";
import { DFData, SDFMeasure, SDFT } from "./DFWhole";

import { CellRendererArgs, FormatterArgs, PinnedRowConfig } from "./DFWhole";
import { getBakedDFViewer, getSimpleTooltip } from "./SeriesSummaryTooltip";
import { getFormatterFromArgs, getCellRenderer, objFormatter, getFormatter } from "./Displayer";
import { Dispatch, SetStateAction } from "react";
import { CommandConfigT } from "../CommandUtils";
import { KeyAwareSmartRowCache, PayloadArgs } from "./SmartRowCache";

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

export function getTooltip(ttc: TooltipConfig, single_series_summary_df: DFWhole): Partial<ColDef> {
    switch (ttc.tooltip_type) {
        case "simple":
            return { tooltipComponent: getSimpleTooltip(ttc.val_column) };

        case "summary_series":
            return {
                tooltipComponent: getBakedDFViewer(single_series_summary_df),
                tooltipField: "index",
                tooltipComponentParams: {},
            };
    }
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

        const tooltip_config = f.tooltip_config
            ? getTooltip(f.tooltip_config, single_series_summary_df)
            : {};
        const colDef: ColDef = {
            field: f.col_name,
            headerName: f.col_name,
            cellDataType: false,
            cellStyle: {}, // necessary for colormapped columns to have a default
            ...addToColDef(f.displayer_args, hdf[f.col_name]),
            ...color_map_config,
            ...tooltip_config,
            ...f.ag_grid_specs,
        };
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
