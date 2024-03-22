import React, { useRef, CSSProperties, useState } from 'react';
import _ from 'lodash';
import { DFData, DFViewerConfig } from './DFWhole';

import { dfToAgrid, extractPinnedRows } from './gridUtils';
import { replaceAtMatch } from '../utils';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import {
  GridOptions,
  SizeColumnsToContentStrategy,
  SizeColumnsToFitProvidedWidthStrategy,
} from 'ag-grid-community';
import { summaryDfForTableDf, tableDf } from '../../baked_data/staticData';

import { getCellRendererSelector } from './gridUtils';

export type setColumFunc = (newCol: string) => void;

export function DFViewer({
  df_data: df,
  df_viewer_config,
  summary_stats_data,
  style,
  activeCol,
  setActiveCol,
}: {
  df_data: DFData;
  df_viewer_config: DFViewerConfig;
  summary_stats_data?: DFData;
  style?: CSSProperties;
  activeCol?: string;
  setActiveCol?: setColumFunc;
}) {
  /* = {
    df: EmptyDf.data,
    df_viewer_config: EmptyDf.dfviewer_config,
    summary_stats_data: [],
    style: { height: '300px' },
    setActiveCol: () => null,
  }*/
  //console.log("dfviewer df_viewer_config", df_viewer_config);
  //  console.log("summary_stats_data", summary_stats_data);
  //  console.log("full_object", {'df':df, 'df_viewer_config':df_viewer_config, 'summary_stats_data': summary_stats_data})
  const [agColsPure, agData] = dfToAgrid(
    df,
    df_viewer_config,
    summary_stats_data || []
  );

  const styledColumns = replaceAtMatch(
    _.clone(agColsPure),
    activeCol || '___never',
    {
      cellStyle: { background: 'var(--ag-range-selection-background-color-3)' },
    }
  );

  const defaultColDef = {
    sortable: true,
    type: 'rightAligned',
    cellRendererSelector: getCellRendererSelector(df_viewer_config.pinned_rows),
  };

  const gridOptions: GridOptions = {
    rowSelection: 'single',
    onRowClicked: (event) => console.log('A row was clicked'),
    tooltipShowDelay: 0,

    // defaultColDef needs to be specifically passed in as a prop to the component, not defined here,
    // otherwise updates aren't reactive

    onCellClicked: (event) => {
      const colName = event.column.getColId();
      if (setActiveCol === undefined || colName === undefined) {
        return;
      } else {
        setActiveCol(colName);
      }
    },
    ...(df_viewer_config.extra_grid_config
      ? df_viewer_config.extra_grid_config
      : {}),
  };
  const gridRef = useRef<AgGridReact<unknown>>(null);
  const pinned_rows = df_viewer_config.pinned_rows;
  const topRowData = summary_stats_data
    ? extractPinnedRows(summary_stats_data, pinned_rows ? pinned_rows : [])
    : [];

  const getAutoSize = ():
    | SizeColumnsToFitProvidedWidthStrategy
    | SizeColumnsToContentStrategy => {
    console.log('getAutoSize');

    if (styledColumns.length < 1) {
      return {
        type: 'fitProvidedWidth',
        width: window.innerWidth - 100,
      };
    }
    return {
      type: 'fitCellContents',
    };
  };

  const inIframe = window.parent !== window;
  const compC = df_viewer_config?.component_config;
  const dfvHeight =
    compC?.dfvHeight || window.innerHeight / (compC?.height_fraction || 2);
  const regularDivStyle = {
    height: dfvHeight,
  };

  const shortDivStyle = {
    minHeight: 50,
    maxHeight: dfvHeight,
  };

  const belowMinRows = agData.length + df_viewer_config.pinned_rows.length < 10;
  const shortMode =
    compC?.shortMode ||
    (belowMinRows &&
      df_viewer_config?.extra_grid_config?.rowHeight === undefined);
  const layoutType = compC?.layoutType || (shortMode ? 'autoHeight' : 'normal');
  const applicableStyle = shortMode ? shortDivStyle : regularDivStyle;
  console.log('shortMode', shortMode, dfvHeight, inIframe);
  return (
    <div
      className={`df-viewer  ${shortMode ? 'short-mode' : 'regular-mode'} ${
        inIframe ? 'in-iframe' : ''
      }`}
    >
      <div
        style={applicableStyle}
        className="theme-hanger ag-theme-alpine-dark "
      >
        <AgGridReact
          ref={gridRef}
          domLayout={layoutType}
          defaultColDef={defaultColDef}
          gridOptions={gridOptions}
          rowData={agData}
          pinnedTopRowData={topRowData}
          columnDefs={_.cloneDeep(styledColumns)}
          autoSizeStrategy={getAutoSize()}
        ></AgGridReact>
      </div>
    </div>
  );
}

export function DFViewerEx() {
  const [activeCol, setActiveCol] = useState('tripduration');
  return (
    <DFViewer
      df_data={tableDf.data}
      df_viewer_config={tableDf.dfviewer_config}
      summary_stats_data={summaryDfForTableDf}
      activeCol={activeCol}
      setActiveCol={setActiveCol}
    />
  );
}
