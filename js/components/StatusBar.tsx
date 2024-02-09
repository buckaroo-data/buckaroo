// https://plnkr.co/edit/QTNwBb2VEn81lf4t?open=index.tsx
import React, { useState, useRef } from 'react';
import _ from 'lodash';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import { ColDef, GridOptions } from 'ag-grid-community';
import { basicIntFormatter } from './DFViewerParts/Displayer';
import { DFMeta } from './WidgetTypes';
import { BuckarooOptions } from './WidgetTypes';
import { BuckarooState, BKeys } from './WidgetTypes';
export type setColumFunc = (newCol: string) => void;

const getSearchForm = (initialVal: string, setSearchVal: any) => {
  return function MyForm() {
    function handleSubmit(e: any) {
      // Prevent the browser from reloading the page
      e.preventDefault();
      // Read the form data
      const form = e.target;
      const formData = new FormData(form);

      const entries = Array.from(formData.entries());

      const formDict = _.fromPairs(entries) as Record<string, string>;

      console.log('formDict', formDict);
      setSearchVal(formDict['search']);
    }

    return (
      <form method="post" onSubmit={handleSubmit}>
        <label>
          <input name="search" defaultValue={initialVal} />
        </label>
      </form>
    );
  };
};

const helpCell = function (params: any) {
  return (
    <a
      href="https://buckaroo-data.readthedocs.io/en/latest/feature_reference.html"
      target="_blank"
      rel="noopener"
    >
      ?
    </a>
  );
};

export function StatusBar({
  dfMeta,
  buckarooState,
  setBuckarooState,
  buckarooOptions,
}: {
  dfMeta: DFMeta;
  buckarooState: BuckarooState;
  setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
  buckarooOptions: BuckarooOptions;
}) {
  console.log('initial buckarooState', buckarooState);
  //   const optionCycles = _.fromPairs(
  // //    _.map(buckarooOptions, (v: any, k) => [k, ( k==='df_display' ? v :  _.concat([false], v) ) ])
  //     _.map(buckarooOptions, (v: any, k) => [k, ( k==='post_processing' ? v :  _.concat([false], v) ) ])

  //   ) as Record<BKeys, any[]>;
  const optionCycles = buckarooOptions;
  const idxs = _.fromPairs(
    _.map(_.keys(optionCycles), (k) => [
      k,
      _.indexOf(optionCycles[k as BKeys], buckarooState[k as BKeys]),
    ])
  );

  const nextIndex = (curIdx: number, arr: any[]) => {
    if (curIdx === arr.length - 1) {
      return 0;
    }
    return curIdx + 1;
  };

  const newBuckarooState = (k: BKeys) => {
    const arr = optionCycles[k];
    const curIdx = idxs[k];
    const nextIdx = nextIndex(curIdx, arr);
    const newVal = arr[nextIdx];
    const newState = _.clone(buckarooState);
    newState[k] = newVal;
    return newState;
  };
  const updateDict = (event: any) => {
    const colName = event.column.getColId();
    if (colName === 'search') {
      return;
    }
    if (_.includes(_.keys(buckarooState), colName)) {
      const nbstate = newBuckarooState(colName as BKeys);
      setBuckarooState(nbstate);
    }
  };
  const showSearch = false;
  const localSetSearchString = (search_query: string) => {
    setBuckarooState({ ...buckarooState, search_string: search_query });
  };

  const columnDefs: ColDef[] = [
    {
      field: 'search',
      width: 200,
      cellRenderer: getSearchForm(
        buckarooState.search_string,
        localSetSearchString
      ),
      hide: !showSearch,
    },

    {
      field: 'df_display',
      headerName: 'Σ', //note the greek symbols instead of icons which require buildchain work
      headerTooltip: 'Summary Stats',
      width: 120,
    },
    /*
    {
      field: 'auto_clean',
      //headerName: 'Σ', //note the greek symbols instead of icons which require buildchain work
      headerName: 'auto cleaning',
      headerTooltip: 'Auto Cleaning config',
      width: 120,
    },
    */
    {
      field: 'post_processing',
      //      headerName: "Θ",
      headerName: 'post processing',
      headerTooltip: 'post process method',
      width: 100,
    },
    {
      field: 'show_commands',
      headerName: 'λ',
      headerTooltip: 'Show Commands',
      width: 30,
    },

    { field: 'sampled', headerName: 'Ξ', headerTooltip: 'Sampled', width: 30 },
    {
      field: 'help',
      headerName: '?',
      headerTooltip: 'Help',
      width: 30,
      cellRenderer: helpCell,
    },
    { field: 'total_rows', width: 100 },
    { field: 'rows_shown', headerName: 'displayed', width: 85 },
    { field: 'columns', width: 75 },
  ];

  const rowData = [
    {
      total_rows: basicIntFormatter.format(dfMeta.total_rows),
      columns: dfMeta.columns,
      rows_shown: basicIntFormatter.format(dfMeta.rows_shown),
      sampled: buckarooState.sampled || '0',
      auto_clean: buckarooState.auto_clean || '0',
      df_display: buckarooState.df_display,
      post_processing: buckarooState.post_processing,
      show_commands: buckarooState.show_commands || '0',
    },
  ];

  const gridOptions: GridOptions = {
    suppressRowClickSelection: true,
  };

  const gridRef = useRef<AgGridReact<unknown>>(null);
  const defaultColDef = {
    //    type: 'left-aligned',
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
  const dfm: DFMeta = {
    columns: 5,
    rows_shown: 20,
    total_rows: 8_777_444,
  };

  const [bState, setBState] = useState<BuckarooState>({
    auto_clean: 'conservative',
    sampled: false,
    df_display: 'main',
    post_processing: 'asdf',
    show_commands: false,
    search_string: '',
  });

  const bOptions: BuckarooOptions = {
    auto_clean: ['aggressive', 'conservative'],
    post_processing: ['', 'asdf'],
    sampled: ['random'],
    show_commands: ['on'],
    df_display: ['main'],
  };

  return (
    <StatusBar
      dfMeta={dfm}
      buckarooState={bState}
      setBuckarooState={setBState}
      buckarooOptions={bOptions}
    />
  );
}
