import React, {
  useState,
  useRef,
} from 'react';
import _ from 'lodash';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import {
  ColDef,
  GridOptions,
} from 'ag-grid-community';

export type setColumFunc = (newCol: string) => void;

export interface DfConfig {
  totalRows: number;
  columns: number;
  rowsShown: number;
  sampleSize: number;
  sampled: boolean;
  summaryStats: boolean;
  reorderdColumns: boolean;
}

const columnDefs: ColDef[] = [
  { field: 'totalRows' },
  { field: 'columns' },
  { field: 'rowsShown' },
  { field: 'sampleSize' },
  { field: 'sampled' },
  { field: 'summaryStats' },
  { field: 'reorderdColumns' },
];

export function StatusBar({ config, setConfig }: { config:any, setConfig:any }) {
  const {
    totalRows,
    columns,
    rowsShown,
    sampleSize,
    sampled,
    summaryStats,
    reorderdColumns,
  } = config;

  const rowData = [
    {
      totalRows,
      columns,
      rowsShown,
      sampleSize,
      sampled: sampled.toString(),
      summaryStats: summaryStats.toString(),
      reorderdColumns: reorderdColumns.toString(),
    },
  ];

  const updateDict = (event:any) => {
    const colName = event.column.getColId();
    if (colName === 'summaryStats') {
      setConfig({ ...config, summaryStats: !config.summaryStats });
    }
    else if (colName === 'sampled') {
      setConfig({ ...config, sampled: !config.sampled });
    } else if (colName === 'reorderdColumns') {
      setConfig({ ...config, reorderdColumns: !config.reorderdColumns });
    }
  };
  const gridOptions: GridOptions = {
    rowSelection: 'single',
  };

  const gridRef = useRef<AgGridReact<unknown>>(null);
  const defaultColDef = {
    type: 'left-aligned',
    cellStyle: { textAlign: 'left' },
  };
  return (
    <div className="statusBar">
      <div style={{ height: 50 }} className="theme-hanger ag-theme-alpine-dark">
        <AgGridReact
          ref={gridRef}
          onCellClicked={updateDict}
          gridOptions={gridOptions}
          defaultColDef={defaultColDef}
          rowData={rowData}
          columnDefs={columnDefs}
        ></AgGridReact>
      </div>
    </div>
  );
}

export function StatusBarEx() {
  const [sampleConfig, setConfig] = useState<DfConfig>({
    totalRows: 1309,
    columns: 30,
    rowsShown: 500,
    sampleSize: 10_000,
    sampled: true,
    summaryStats: false,
    reorderdColumns: false,
  });

  return <StatusBar config={sampleConfig} setConfig={setConfig} />;
}
