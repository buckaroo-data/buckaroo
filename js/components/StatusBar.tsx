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
  showCommands:boolean;
  showTransformed:boolean;
}

const columnDefs: ColDef[] = [
  { field: 'summaryStats',
    headerName:'Σ',
    headerTooltip:'Summary Stats',
    width:30
  },
  { field: 'reorderdColumns',
  headerName: "Θ",
  headerTooltip:"Reorder Columns",
  width:30
},
  { field: 'showTransformed',
  headerName:"Δ",
  headerTooltip:"Show Transformation",
  width:30
},
  { field: 'showCommands',
  headerName: "λ",
  headerTooltip:"Show Commands",
  width:30
},

  { field: 'sampled',
  headerName: "Ξ",
  headerTooltip:"Sampled",
  width:30
},
  { field: 'totalRows', width:100},
  { field: 'columns', width:100 },
  { field: 'rowsShown', width:120},
  { field: 'sampleSize', width:120 }
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
    showTransformed,
    showCommands
  } = config;

  const rowData = [
    {
      totalRows,
      columns,
      rowsShown,
      sampleSize,
      sampled: sampled  ? "Ϋ" : "ό",
      summaryStats: summaryStats ? "Ϋ" : "ό",
      reorderdColumns: reorderdColumns ? "Ϋ" : "ό",
      showTransformed: showTransformed ? "Ϋ" : "ό",
      showCommands: showCommands ? "Ϋ" : "ό",
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
    } else if (colName === 'showTransformed') {
      setConfig({ ...config, showTransformed: !config.showTransformed });
    } else if (colName === 'showCommands') {
      setConfig({ ...config, showCommands: !config.showCommands });
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
    reorderdColumns: true,
    showTransformed: true,
    showCommands: true,
  });

  return <StatusBar config={sampleConfig} setConfig={setConfig} />;
}
