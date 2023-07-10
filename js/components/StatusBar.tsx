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
import { intFormatter } from './gridUtils';
export type setColumFunc = (newCol: string) => void;

export interface DfConfig {
  totalRows: number;
  columns: number;
  rowsShown: number;
  sampleSize: number;
  sampled: boolean;
  summaryStats: boolean;
  showCommands:boolean;
  //reorderdColumns: boolean;
}


const columnDefs: ColDef[] = [
  { field: 'summaryStats',
    headerName:'Σ',
    headerTooltip:'Summary Stats',
    width:30
  },
//   { field: 'reorderdColumns',
//   headerName: "Θ",
//   headerTooltip:"Reorder Columns",
//   width:30
// },
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
  { field: 'help',
  headerName: "?",
  headerTooltip:"Help",
    width:30,
    cellRenderer: function(params:any) {
      return <a href="https://buckaroo-data.readthedocs.io/en/latest/feature_reference.html" target="_blank" rel="noopener">?</a>}
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
    showCommands,
    //reorderdColumns
  } = config;

  const rowData = [
    {
      totalRows: intFormatter.format(totalRows),
      columns,
      rowsShown : intFormatter.format(rowsShown),
      sampleSize : intFormatter.format(sampleSize),
      sampled: sampled  ? "1" : "0",
      summaryStats: summaryStats ? "1" : "0",
      // reorderdColumns: reorderdColumns ? "Ϋ" : "ό",
      showCommands: showCommands ? "1" : "0"
    },
  ];

  const updateDict = (event:any) => {
    const colName = event.column.getColId();
    if (colName === 'summaryStats') {
      setConfig({ ...config, summaryStats: !config.summaryStats });
    }
    else if (colName === 'sampled') {
      setConfig({ ...config, sampled: !config.sampled });
    } else if (colName === 'showCommands') {
      setConfig({ ...config, showCommands: !config.showCommands });
    }
    // } else if (colName === 'reorderdColumns') {
    //   setConfig({ ...config, reorderdColumns: !config.reorderdColumns });

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
    showCommands: true,
    //reorderdColumns: true,
  });

  return <StatusBar config={sampleConfig} setConfig={setConfig} />;
}
