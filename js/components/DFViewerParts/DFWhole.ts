// I'm not sure about adding underlying types too

import { ColDef, GridOptions } from 'ag-grid-community';
import _ from 'lodash';

type AGGrid_ColDef = ColDef;

export interface ObjDisplayerA {
  displayer: 'obj';
  max_length?: number;
}
export interface BooleanDisplayerA {
  displayer: 'boolean';
}
export interface StringDisplayerA {
  displayer: 'string';
  max_length?: number;
}
export interface FloatDisplayerA {
  displayer: 'float';
  min_fraction_digits: number;
  max_fraction_digits: number;
}

export interface DatetimeDefaultDisplayerA {
  displayer: 'datetimeDefault';
}
export interface IntegerDisplayerA {
  displayer: 'integer';
  min_digits: number;
  max_digits: number;
}

export interface DatetimeLocaleDisplayerA {
  displayer: 'datetimeLocaleString';
  locale: 'en-US' | 'en-GB' | 'en-CA' | 'fr-FR' | 'es-ES' | 'de-DE' | 'ja-JP';
  args: Intl.DateTimeFormatOptions;
}

// Used DisplayerA instead of FormatterArgs,  Displayer makes sense from the python side
// python doesn't care that histogram requires a cellRenderer and Integer only changes the formatter
export type FormatterArgs =
  | ObjDisplayerA
  | BooleanDisplayerA
  | StringDisplayerA
  | FloatDisplayerA
  | DatetimeDefaultDisplayerA
  | DatetimeLocaleDisplayerA
  | IntegerDisplayerA;

export interface HistogramDisplayerA {
  displayer: 'histogram';
}

export interface LinkifyDisplayerA {
  displayer: 'linkify';
}
export interface BooleanCheckboxDisplayerA {
  displayer: 'boolean_checkbox';
}

export interface Base64PNGImageDisplayerA {
  displayer: 'Base64PNGImageDisplayer';
}

export interface SVGDisplayerA {
  displayer: 'SVGDisplayer';
}

export type CellRendererArgs =
  | HistogramDisplayerA
  | LinkifyDisplayerA
  | BooleanCheckboxDisplayerA
  | Base64PNGImageDisplayerA
  | SVGDisplayerA;

export type DisplayerArgs = FormatterArgs | CellRendererArgs;

export const cellRendererDisplayers = [
  'histogram',
  'linkify',
  'Base64PNGImageDisplayer',
  'SVGDisplayer',
];

//ColorMapRules
export interface ColorMapRules {
  color_rule: 'color_map';
  map_name: 'BLUE_TO_YELLOW' | 'DIVERGING_RED_WHITE_BLUE';
  //optional, the column to base the ranges on.  the proper histogram_bins must still be sent in for that column
  val_column?: string;
}

//if exist_column is not null,  set cell style to condtional_color... used for highlighting changed values or errored_rows
export interface ColorWhenNotNullRules {
  color_rule: 'color_not_null';
  conditional_color: string | 'red';
  exist_column: string;
}

export interface ColorFromColumn {
  color_rule: 'color_from_column';
  col_name: string;
}

export type ColorMappingConfig =
  | ColorMapRules
  | ColorWhenNotNullRules
  | ColorFromColumn;

//TooltipRules
export interface SimpleTooltip {
  tooltip_type: 'simple';
  val_column: string;
}

export interface SummarySeriesTooltip {
  tooltip_type: 'summary_series';
}

export type TooltipConfig = SimpleTooltip | SummarySeriesTooltip; //more to be added

export type ColumnConfig = {
  col_name: string;
  displayer_args: DisplayerArgs;
  color_map_config?: ColorMappingConfig;
  tooltip_config?: TooltipConfig;
  ag_grid_specs?: AGGrid_ColDef;
};

export type PinnedRowConfig = {
  primary_key_val: string;
  displayer_args: DisplayerArgs;
  //used to render index column values with string not the specified displayer, otherwise the column will be listed as NaN or blank
  //by default the "index" column is always rendered with "obj"
  default_renderer_columns?: string[];
};

export type ComponentConfig = {
  height_fraction?: number;
  // temporary debugging props
  dfvHeight?: number;
  layoutType?: 'autoHeight' | 'normal';
  shortMode?: boolean;
};

export interface DFViewerConfig {
  pinned_rows: PinnedRowConfig[];
  column_config: ColumnConfig[];
  extra_grid_config?: GridOptions;
  component_config?: ComponentConfig;
}

export type DFDataRow = Record<
  string,
  string | number | boolean | any[] | Record<string, any> | null
>;

export type DFData = DFDataRow[];

/*
When I want to start tagging metadata onto DFData
export interface DFData {
  rows: DFDataRow[];
  //data_meta expansion point for typing info about the data as needed by non-display stuff
  // typing,  sorting, null handling I'm not sure about it
};
*/

export interface DFWhole {
  dfviewer_config: DFViewerConfig;
  data: DFData;
}

export const EmptyDf: DFWhole = {
  dfviewer_config: {
    pinned_rows: [],
    column_config: [],
  },
  data: [],
};

//actually SDFT is summary stats transposed to be useful
// SDFT[col][stat_name]
// SDFT really only needs histogramBins and histogramLogBins and...? at this point
//type SDFT = any;

export interface SDFMeasure {
  histogram_bins: number[];
  histogram_log_bins: number[];
}

export type SDFT = Record<string, SDFMeasure>;
