import React, { useRef, CSSProperties, useState } from 'react';
import _ from 'lodash';
import { ComponentConfig, DFData, DFViewerConfig } from './DFWhole';

import { dfToAgrid, extractPinnedRows } from './gridUtils';
import { replaceAtMatch } from '../utils';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import {
  DomLayoutType,
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

  const hs = heightStyle({
    numRows: agData.length,
    pinnedRowLen: df_viewer_config.pinned_rows.length,
    location: window.location,
    compC: df_viewer_config?.component_config,
    rowHeight: df_viewer_config?.extra_grid_config?.rowHeight,
  });

  return (
    <div className={`df-viewer  ${hs.classMode} ${hs.inIframe}`}>
      <div
        style={hs.applicableStyle}
        className="theme-hanger ag-theme-alpine-dark "
      >
        <AgGridReact
          ref={gridRef}
          domLayout={hs.domLayout}
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

interface HeightStyleArgs {
  numRows: number;
  pinnedRowLen: number;
  readonly location: Location;
  rowHeight?: number;
  compC?: ComponentConfig;
}
interface HeightStyleI {
  domLayout: DomLayoutType;
  inIframe: string;
  classMode: 'short-mode' | 'regular-mode';
  applicableStyle: CSSProperties;
}

export const heightStyle = (hArgs: HeightStyleArgs): HeightStyleI => {
  const { numRows, pinnedRowLen, location, rowHeight, compC } = hArgs;
  const isGoogleColab =
    location.host.indexOf('colab.googleusercontent.com') !== -1;

  const inIframe = window.parent !== window;
  const regularCompHeight = window.innerHeight / (compC?.height_fraction || 2);
  const dfvHeight = compC?.dfvHeight || regularCompHeight;
  const regularDivStyle = { height: dfvHeight };
  const shortDivStyle = { minHeight: 50, maxHeight: dfvHeight };

  const belowMinRows = numRows + pinnedRowLen < 10;

  const shortMode =
    compC?.shortMode || (belowMinRows && rowHeight === undefined);
  console.log(
    'shortMode',
    shortMode,
    'dfvHeight',
    dfvHeight,
    'isGoogleColab',
    isGoogleColab,
    'inIframe',
    inIframe
  );
  const inIframeClass = inIframe ? 'inIframe' : '';
  if (isGoogleColab || inIframe) {
    return {
      classMode: 'regular-mode',
      domLayout: 'normal',
      applicableStyle: { height: 500 },
      inIframe: inIframeClass,
    };
  }
  const domLayout: DomLayoutType =
    compC?.layoutType || (shortMode ? 'autoHeight' : 'normal');
  const applicableStyle = shortMode ? shortDivStyle : regularDivStyle;
  const classMode = shortMode ? 'short-mode' : 'regular-mode';
  return {
    classMode,
    domLayout,
    applicableStyle,
    inIframe: inIframeClass,
  };

  /*
  ab = window.location.host;
 "cskfus796ts-496ff2e9c6d22116-0-colab.googleusercontent.com"
 bc = window.location.pathname
 "/outputframe.html" 
*/
};

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
