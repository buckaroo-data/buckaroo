import {
    CellRendererSelectorResult,
    ColDef,
    ColGroupDef,
    DomLayoutType,
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
    NormalColumnConfig,
    MultiIndexColumnConfig,
    ColDefOrGroup,
} from "./DFWhole";

import * as _ from "lodash";
import { getTextCellRenderer } from "./OtherRenderers";
import { getStyler } from "./Styler";
import { DFData, SDFMeasure, SDFT } from "./DFWhole";

import { CellRendererArgs, FormatterArgs, PinnedRowConfig } from "./DFWhole";
import { getTooltipParams } from "./SeriesSummaryTooltip";
import { getFormatterFromArgs, getCellRenderer, objFormatter, getFormatter } from "./Displayer";
import { CSSProperties, Dispatch, SetStateAction } from "react";
import { CommandConfigT } from "../CommandUtils";
import { KeyAwareSmartRowCache, PayloadArgs } from "./SmartRowCache";
import { colorSchemeDark, colorSchemeLight, themeAlpine, Theme } from "@ag-grid-community/theming";


// for now colDef stuff with less than 3 implementantions should stay in this file
// as implementations grow large or with many implmentations, they should move to separate files
// like displayer

export function getCellRendererorFormatter(
    dispArgs: DisplayerArgs,
):ColDef {
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
    //this is probably an error
    return {};
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
              { col_name: "index", header_name:"index",  displayer_args: { displayer: "obj" } },
              { col_name: col_name, header_name: col_name,  displayer_args: { displayer: "obj" } },
            ],
          pinned_rows: [],
	  left_col_configs: [
	    {
              col_name: 'index',
	      header_name: 'index',
              displayer_args: {
		displayer: 'string',
              },
            }
	]
	  
        },
        data: _.filter(
            _.map(full_summary_stats_df, (row) => _.pick(row, ["index", col_name])),
            { index: "dtype" },
        ),
    };
}

export const getFieldVal = (f:ColumnConfig) : string => {
  if(_.has(f, 'col_path')){
    return (f as MultiIndexColumnConfig).field;
  }
  return (f as NormalColumnConfig).col_name;
}

export function baseColToColDef (f:ColumnConfig) : ColDef {
  const color_map_config = f.color_map_config
    ? getStyler(f.color_map_config) : {};
  const colDef: ColDef = {
    field: getFieldVal(f),
    cellDataType: false,
    cellStyle: undefined, // necessary for colormapped columns to have a default
    ...getCellRendererorFormatter(f.displayer_args),
    ...color_map_config,
    ...getTooltipParams(f.tooltip_config),
    ...f.ag_grid_specs,
  };
    return colDef
}

export function normalColToColDef (f:NormalColumnConfig) : ColDef {
  const colDef: ColDef = {
    headerName: f.header_name,
    ...baseColToColDef(f)};
  return colDef
}

export const getSubChildren = (arr:ColumnConfig[], level:number): ColumnConfig[][] => {
  const keyFunc = (x:ColumnConfig) => {
    if(_.has(x, 'col_path')) {
      const xMICC: MultiIndexColumnConfig = x as MultiIndexColumnConfig
      return xMICC.col_path[level]
    }
    const xNCC: NormalColumnConfig = x as NormalColumnConfig;
    return xNCC.col_name + "!&single" + _.indexOf(arr, x).toString(); // bad magic value
  }
  return arr.reduce((acc: ColumnConfig[][], curr:ColumnConfig) => {
    
    const firstKey = keyFunc(curr)
    const lastGroup = acc[acc.length - 1];
    
    if (!lastGroup || keyFunc(lastGroup[0]) !== firstKey) {
      acc.push([curr]);
    } else {
      lastGroup.push(curr);
    }
    
    return acc;
  }, []);
};


export function childColDef(f:MultiIndexColumnConfig, level:number) : ColDefOrGroup {
  /*
  returns the proper colDef at level
   */
  console.log("f",f, f.ag_grid_specs)
  return {
    headerName:f.col_path[level],
    ...baseColToColDef(f),
  }
}



export function multiIndexColToColDef (f:MultiIndexColumnConfig[], level:number=0) : ColGroupDef {
  // this will return the nested groups of ColGroupDef with children
  if (f.length == 0) {
    // this will never happen
    throw new Error("f shouldn't be empty");
  }

  const rootColPath = f[0].col_path;
  const rootHeader = rootColPath[level]

  const rootDepth = rootColPath.length;
  if (level == rootDepth) {
    throw new Error("something went wrong, level is too deep");
  }
  const childLevel = level + 1;
  if(rootDepth == 1) {
    const colDef: ColGroupDef = {
      //headerName: rootHeader,
      children: _.map(f, (x) => childColDef(x, 0)),
      ...(f[0].ag_grid_specs)
    };

    console.log(" colDef from multiIndexColToColDef", colDef)
    return colDef
  }

  if (childLevel == (rootDepth -1)) {
    const colDef: ColGroupDef = {
      headerName: rootHeader,
      children: _.map(f, (x) => childColDef(x, childLevel)),
      ...(f[0].ag_grid_specs)
    };
    console.log(" colDef from multiIndexColToColDef", colDef)
    return colDef
  } else {
    const groupedColumnConfigs = getSubChildren(f, childLevel);
    const colDef: ColGroupDef = {
      headerName: rootHeader,
      children: _.map(groupedColumnConfigs, (x) => multiIndexColToColDef(x as MultiIndexColumnConfig[], childLevel)),
      ...(f[0].ag_grid_specs)
    };
    console.log(" colDef from multiIndexColToColDef", colDef)
    return colDef
  }
}


const switchToColDef = (x:ColumnConfig[]): ColDef|ColGroupDef => {
  if (x.length == 0) {
    //neverp
    throw new Error("x shouldn't be empty");
  }
  if(_.has(x[0], 'col_path')) {
    return multiIndexColToColDef(x as MultiIndexColumnConfig[])
  } else {
    if (x.length > 1) {
      throw new Error(`for NormalColumnConfig, length should be 1, improperly grouped ${x}`);
    }
    return normalColToColDef(x[0] as NormalColumnConfig)
  }
}
export function mergeCellClass(
  cOrig:ColDef|ColGroupDef, classSpec:"headerClass"|"cellClass", extraClass:string) : ColDef|ColGroupDef {
    const c = _.cloneDeep(cOrig);
    //@ts-ignore
    if(c[classSpec] === undefined) { 
      //@ts-ignore
      c[classSpec] = extraClass
    } else {
      console.log("c", c, classSpec)
      //@ts-ignore
      if(_.isArray(c[classSpec])) {
	//@ts-ignore
	c[classSpec].push(extraClass)
      } else {
	//@ts-ignore
	c[classSpec] = [c[classSpec], extraClass]
      }
    }
    return c
  }

export function dfToAgrid(
    dfviewer_config: DFViewerConfig,
): (ColDef|ColGroupDef)[] {
  /*
  gets the aggrid column config given the buckaroo inputs
   */
  const groupedIndexColumnConfigs = getSubChildren(dfviewer_config.left_col_configs, 0)
  const flattenedIndexColumnConfigs = groupedIndexColumnConfigs.map(switchToColDef)
  const lcc = flattenedIndexColumnConfigs.map((x) => mergeCellClass(x,"headerClass", "left_col_configs_header"))
  
  const lcc2 = lcc.map((x) => mergeCellClass(x,"cellClass", "left_col_configs_cell"))
  if (lcc2.length > 0) {
    const lastI = lcc2.length -1;
    lcc2[lastI] =  mergeCellClass(lcc2[lastI], "headerClass", "left_col_configs_header_last")
    lcc2[lastI] =  mergeCellClass(lcc2[lastI], "cellClass", "left_col_configs_cell_last")
  }
  const addPinned = (x:ColDef|ColGroupDef) :ColDef => {
    return {
    ...x,
    pinned:'left'}
  }
  const lcc3 = lcc2.map(addPinned)
  console.log("lcc3", lcc3);

  const columnConfigs: ColumnConfig[] =  dfviewer_config.column_config;
  const groupedColumnConfigs = getSubChildren(columnConfigs, 0);
  const flattenedColumnConfigs = groupedColumnConfigs.map(switchToColDef)

  const retMultiColumns:(ColDef|ColGroupDef)[] = [
    ...lcc2,
    ...flattenedColumnConfigs]
  return retMultiColumns
}

// this is very similar to the colDef parts of dfToAgrid
export function getCellRendererSelector(pinned_rows: PinnedRowConfig[], column_config: ColumnConfig[]) {
    const anyRenderer: CellRendererSelectorResult = {
        component: getTextCellRenderer(objFormatter),
      //params: {colDef: {cellClass:"pinned_row_cell_class"}}
    };

    // Pre-build a lookup from col_name → formatter for "inherit" pinned rows
    const colFormatterMap: Record<string, ReturnType<typeof getFormatter>> = {};
    for (const cc of column_config) {
        const colName = getFieldVal(cc);
        const formatter = getFormatterFromArgs(cc.displayer_args);
        if (formatter) {
            colFormatterMap[colName] = formatter;
        }
    }

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
            if (prc.displayer_args.displayer === "inherit") {
                const colFormatter = currentCol ? colFormatterMap[currentCol] : undefined;
                if (colFormatter) {
                    return {
                        component: getTextCellRenderer(colFormatter),
                    };
                }
                return anyRenderer;
            }
            const possibCellRenderer = getCellRenderer(prc.displayer_args as CellRendererArgs);

            if (possibCellRenderer === undefined) {
                const formattedRenderer: CellRendererSelectorResult = {
                    component: getTextCellRenderer(
                        getFormatter(prc.displayer_args as FormatterArgs),
                    ),
		  //		  params: {colDef: {cellClass:"pinned_row_cell_class"}}
                };
                return formattedRenderer;
            }
          return { component: possibCellRenderer, 
	    //params: {colDef: {cellClass:"pinned_row_cell_class"}}
	  };
        } else {
            return undefined; // rows that are not pinned don't use a row level cell renderer
        }
    };
}

export function extractSDFT(summaryStatsDf: DFData): SDFT {
    /*  histogram_bins are special cased because of how they are passed to rendereres in pinned_rows
	I think
     */
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
    return _.zipObject(allColumns, vals) as SDFT;
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
    const createTime =  new Date();
    const dsLoc: TimedIDatasource = {
        createTime,
        rowCount: undefined,
        getRows: (params: IGetRowsParams) => {
	    //@ts-ignore
	    console.log("gridUtils 198 calling getRows createTime", createTime, ((new Date()) - createTime));
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
            console.log("[getRows] dsPayloadArgs", dsPayloadArgs, "context.outside_df_params", outside_params_string);
            const successWrapper = (df:DFData, length:number) => {
		//@ts-ignore
                console.log("successWrapper called 217",  createTime, ((new Date()) - createTime));
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
export type SetColumnFunc = (newCol: [string, string]) => void;
export type PossibleAutosizeStrategy = SizeColumnsToFitProvidedWidthStrategy |
    SizeColumnsToContentStrategy;

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


export const getHeightStyle2 = (
    maxDataPinnedRows:number, // the maximum number of pinned rows across configs with data (not summary_stats which has no data)
    maxRows:number, // the maximum of pinned rows across configs or total_rows
    component_config?: ComponentConfig, //Very rarely set
    rowHeight?:number //very rarely set
): HeightStyleI => {
    /*
    rewritten for better caching
    */
    const hs = heightStyle({
        numRows: maxRows,
        pinnedRowLen: maxDataPinnedRows,
        location: window.location,
        compC: component_config,
        rowHeight: rowHeight,
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
    console.log("314, ", regularCompHeight, window.innerHeight, (compC?.height_fraction || 2), compC?.dfvHeight, regularCompHeight, dfvHeight);
    //314,  175.5 351 2 200 175.5 200
    //314,  175.5 351 2 undefined 175.5 175.5
    const regularDivStyle = { height: dfvHeight, overflow:"hidden" };
    const shortDivStyle = { minHeight: 50, maxHeight: dfvHeight, overflow:"hidden" };

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
    console.log("belowMinRows", belowMinRows, numRows, pinnedRowLen, maxRowsWithoutScrolling)
    //belowMinRows true 5 2 9
    //console.log("maxRowsWithoutScrolling", maxRowsWithoutScrolling, belowMinRows, numRows, dfvHeight, rowHeight);
    const shortMode = compC?.shortMode || (belowMinRows && rowHeight === undefined);
    console.log("shortMode", shortMode, compC?.shortMode, belowMinRows, rowHeight);
    const inIframeClass = inIframe ? "inIframe" : "";
    //console.log("gridUtils 350 heightstyle", dfvHeight)
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
    console.log("351 gridUtils", shortMode, shortDivStyle, regularDivStyle)
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



const sharedThemeParams = {
    spacing: 5,
    cellHorizontalPaddingScale: 0.3,
    columnBorder: true,
    rowBorder: false,
    rowVerticalPaddingScale: 0.5,
    wrapperBorder: false,
    fontSize: 12,
    dataFontSize: "12px" as const,
    headerFontSize: 14,
    iconSize: 10,
    headerVerticalPaddingScale: 0.6,
};

export const myThemeDark: Theme = themeAlpine.withPart(colorSchemeDark).withParams({
    ...sharedThemeParams,
    browserColorScheme: "dark",
    backgroundColor: "#181D1F",
    oddRowBackgroundColor: '#222628',
});

export const myThemeLight: Theme = themeAlpine.withPart(colorSchemeLight).withParams({
    ...sharedThemeParams,
    browserColorScheme: "light",
    backgroundColor: "#ffffff",
    oddRowBackgroundColor: '#f5f5f5',
});

/** @deprecated Use getThemeForScheme() instead */
export const myTheme: Theme = myThemeDark;

export type ThemeConfig = {
    colorScheme?: 'light' | 'dark' | 'auto';
    accentColor?: string;
    accentHoverColor?: string;
    backgroundColor?: string;
    foregroundColor?: string;
    oddRowBackgroundColor?: string;
    borderColor?: string;
};

export function resolveColorScheme(
    osScheme: 'light' | 'dark',
    themeConfig?: ThemeConfig
): 'light' | 'dark' {
    const override = themeConfig?.colorScheme;
    if (override && override !== 'auto') {
        return override;
    }
    return osScheme;
}

export function getThemeForScheme(scheme: 'light' | 'dark', themeConfig?: ThemeConfig): Theme {
    const base = scheme === 'light' ? myThemeLight : myThemeDark;
    if (!themeConfig) return base;

    const overrides: Record<string, any> = {};
    if (themeConfig.backgroundColor) overrides.backgroundColor = themeConfig.backgroundColor;
    if (themeConfig.foregroundColor) overrides.foregroundColor = themeConfig.foregroundColor;
    if (themeConfig.oddRowBackgroundColor) overrides.oddRowBackgroundColor = themeConfig.oddRowBackgroundColor;
    if (themeConfig.borderColor) overrides.borderColor = themeConfig.borderColor;

    if (Object.keys(overrides).length === 0) return base;
    return base.withParams(overrides);
}
