import {
  CellClassParams,
  CellRendererSelectorResult,
  ColDef,
  ICellRendererParams,
} from 'ag-grid-community';
import {
  BLUE_TO_YELLOW,
  DIVERGING_RED_WHITE_BLUE,
} from '../../baked_data/colorMap';

import {
  DFWhole,
  DisplayerArgs,
  cellRendererDisplayers,
  ColumnConfig,
  ColorMappingConfig,
  ColorMapRules,
  TooltipConfig,
  ColorWhenNotNullRules,
  DFViewerConfig,
} from './DFWhole';
import _, { zipObject } from 'lodash';
import { getTextCellRenderer } from './HistogramCell';

import { DFData, SDFMeasure, SDFT } from './DFWhole';

import { CellRendererArgs, FormatterArgs, PinnedRowConfig } from './DFWhole';
import { getBakedDFViewer } from './SeriesSummaryTooltip';
import {
  getFormatterFromArgs,
  getCellRenderer,
  objFormatter,
  getFormatter,
} from './Displayer';

// for now colDef stuff with less than 3 implementantions should stay in this file
// as implementations grow large or with many implmentations, they should move to separate files
// like displayer

export function addToColDef(
  dispArgs: DisplayerArgs,
  summary_stats_column: SDFMeasure
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

export function getHistoIndex(val: number, histogram_edges: number[]): number {
  /*
np.histogram([1, 2, 3, 4,  10, 20, 30, 40, 300, 300, 400, 500], bins=5)
( [  8,       0,     2,     1,     1], 
[  1. , 100.8, 200.6, 300.4, 400.2, 500. ])
The bottom matters for us, those are the endge

this means that 8 values are between 1 and 100.8  and 2 values are between 200.6 and 300.4
  */
  if (histogram_edges.length === 0) {
    return 0;
  }
  for (let i = 0; i < histogram_edges.length; i++) {
    if (val <= histogram_edges[i]) {
      return i;
    }
  }
  return histogram_edges.length;
}

export function colorMap(cmr: ColorMapRules, histogram_edges: number[]) {
  // https://colorcet.com/gallery.html#isoluminant
  // https://github.com/holoviz/colorcet/tree/main/assets/CET
  // https://github.com/bokeh/bokeh/blob/ed285b11ab196e72336b47bf12f44e1bef5abed3/src/bokeh/models/mappers.py#L304
  const maps: Record<string, string[]> = {
    BLUE_TO_YELLOW: BLUE_TO_YELLOW,
    DIVERGING_RED_WHITE_BLUE: DIVERGING_RED_WHITE_BLUE,
  };
  const cmap = maps[cmr.map_name];

  function numberToColor(val: number) {
    const histoIndex = getHistoIndex(val, histogram_edges);
    const scaledIndex = Math.round(
      (histoIndex / histogram_edges.length) * cmap.length
    );
    return cmap[scaledIndex];
  }

  function cellStyle(params: CellClassParams) {
    const val = cmr.val_column ? params.data[cmr.val_column] : params.value;
    const color = numberToColor(val);
    return {
      backgroundColor: color,
    };
  }

  const retProps = {
    cellStyle: cellStyle,
  };
  return retProps;
}

export function colorNotNull(cmr: ColorWhenNotNullRules) {
  function cellStyle(params: CellClassParams) {
    if (params.data === undefined) {
      return { backgroundColor: 'inherit' };
    }
    const val = params.data[cmr.exist_column];
    const valPresent = val && val !== null;
    const isPinned = params.node.rowPinned;
    const color = valPresent && !isPinned ? cmr.conditional_color : 'inherit';
    return {
      backgroundColor: color,
    };
  }

  const retProps = {
    cellStyle: cellStyle,
  };
  return retProps;
}

export function getStyler(
  cmr: ColorMappingConfig,
  col_name: string,
  histogram_stats: SDFT
) {
  switch (cmr.color_rule) {
    case 'color_map': {
      //block necessary because you cant define varaibles in case blocks
      const statsCol = cmr.val_column || col_name;
      const summary_stats_cell = histogram_stats[statsCol];

      if (
        summary_stats_cell &&
        summary_stats_cell.histogram_bins !== undefined
      ) {
        return colorMap(cmr, summary_stats_cell.histogram_bins);
      } else {
        console.log('histogram bins not found for color_map');
        return {};
      }
    }
    case 'color_not_null':
      return colorNotNull(cmr);
  }
}

export function extractPinnedRows(sdf: DFData, prc: PinnedRowConfig[]) {
  return _.map(_.map(prc, 'primary_key_val'), (x) => _.find(sdf, { index: x }));
}

export function getTooltip(
  ttc: TooltipConfig,
  single_series_summary_df: DFWhole
): Partial<ColDef> {
  switch (ttc.tooltip_type) {
    case 'simple':
      return { tooltipField: ttc.val_column };

    case 'summary_series':
      return {
        tooltipComponent: getBakedDFViewer(single_series_summary_df),
        tooltipField: 'index',
        tooltipComponentParams: {},
      };
  }
}

export function extractSingleSeriesSummary(
  full_summary_stats_df: DFData,
  col_name: string
): DFWhole {
  return {
    dfviewer_config: {
      column_config: [
        { col_name: 'index', displayer_args: { displayer: 'obj' } },
        { col_name: col_name, displayer_args: { displayer: 'obj' } },
      ],
      pinned_rows: [],
    },
    data: _.filter(
      _.map(full_summary_stats_df, (row) => _.pick(row, ['index', col_name])),
      { index: 'dtype' }
    ),
  };
}

export function dfToAgrid(
  tdf: DFData,
  dfviewer_config: DFViewerConfig,
  full_summary_stats_df: DFData
): [ColDef[], unknown[]] {
  //more convienient df format for some formatters
  const hdf = extractSDFT(full_summary_stats_df || []);

  const retColumns: ColDef[] = dfviewer_config.column_config.map(
    (f: ColumnConfig) => {
      const single_series_summary_df = extractSingleSeriesSummary(
        full_summary_stats_df,
        f.col_name
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
    }
  );
  return [retColumns, tdf];
}

// this is very similar to the colDef parts of dfToAgrid
export function getCellRendererSelector(pinned_rows: PinnedRowConfig[]) {
  const anyRenderer: CellRendererSelectorResult = {
    component: getTextCellRenderer(objFormatter),
  };
  return (
    params: ICellRendererParams<any, any, any>
  ): CellRendererSelectorResult | undefined => {
    if (params.node.rowPinned) {
      const pk = _.get(params.node.data, 'index');
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
      console.log('params', params);
      const currentCol = params.column?.getColId();
      if (
        (prc.default_renderer_columns === undefined &&
          currentCol === 'index') ||
        _.includes(prc.default_renderer_columns, currentCol)
      ) {
        return anyRenderer;
      }
      const possibCellRenderer = getCellRenderer(
        prc.displayer_args as CellRendererArgs
      );

      if (possibCellRenderer === undefined) {
        const formattedRenderer: CellRendererSelectorResult = {
          component: getTextCellRenderer(
            getFormatter(prc.displayer_args as FormatterArgs)
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
  const maybeHistogramBins =
    _.find(summaryStatsDf, { index: 'histogram_bins' }) || {};
  const maybeHistogramLogBins =
    _.find(summaryStatsDf, { index: 'histogram_log_bins' }) || {};
  const allColumns: string[] = _.without(
    _.union(_.keys(maybeHistogramBins), _.keys(maybeHistogramLogBins)),
    'index'
  );
  const vals: SDFMeasure[] = _.map(allColumns, (colName) => {
    return {
      histogram_bins: _.get(maybeHistogramBins, colName, []) as number[],
      histogram_log_bins: _.get(maybeHistogramLogBins, colName, []) as number[],
    };
  });
  return zipObject(allColumns, vals) as SDFT;
}

/*
I would love for extractSDF to be more elegant like the following function.  I just can't quite get it to work
time to move on

export function extractSDFT2(summaryStatsDf:DFData) : SDFT  {
  const rows = ['histogram_bins', 'histogram_log_bins']

  const extracted = _.map(rows, (pk) => {
    return _.find(summaryStatsDf,  {'index': pk}) || {}
  })
  const dupKeys: string[][] = _.map(extracted, _.keys);
  const allColumns: string[] = _.without(_.union(...dupKeys), 'index');
  const vals:SDFMeasure[] = _.map(allColumns, (colName) => {
    const pairs = _.map(_.zip(rows, extracted), (rname, row) => {
      return [rname, (_.get(row, colName, []) as number[])];
    })
    return _.fromPairs(pairs) as SDFMeasure;
  });
  return zipObject(allColumns, vals) as SDFT;
}
*/
