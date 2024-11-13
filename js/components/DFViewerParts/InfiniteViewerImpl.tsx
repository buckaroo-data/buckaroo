'use strict';

import {
  ColDef,
  GetRowIdParams,
  GridApi,
  IDatasource,
  ModuleRegistry,
  //  RedrawRowsParams,
  SortChangedEvent,
} from '@ag-grid-community/core';
import { InfiniteRowModelModule } from '@ag-grid-community/infinite-row-model';
import { AgGridReact } from '@ag-grid-community/react';
import '@ag-grid-community/styles/ag-grid.css';
import '@ag-grid-community/styles/ag-theme-quartz.css';
import React, { useMemo, useRef, useState } from 'react';

import { GridOptions } from '@ag-grid-community/core';

import { ClientSideRowModelModule } from '@ag-grid-community/client-side-row-model';
import { Operation } from '../OperationUtils';
ModuleRegistry.registerModules([ClientSideRowModelModule]);

ModuleRegistry.registerModules([InfiniteRowModelModule]);
export const makeTSHappy = [useMemo, useState];
export const InfiniteViewer = ({
  dataSource,
  operations,
}: {
  dataSource: IDatasource;
  operations: Operation[];
}) => {
  const columnDefs: ColDef[] = [
    // this row shows the row index, doesn't use any data from the row
    {
      headerName: 'ID',
      maxWidth: 100,
      // it is important to have node.id here, so that when the id changes (which happens
      // when the row is loaded) then the cell is refreshed.
      valueGetter: 'node.id',
    },
    { field: 'agIdx' },
    {
      field: 'athlete',
      minWidth: 150,
    },
    { field: 'sport' },
    {
      field: 'age',
    },
    {
      field: 'total',
    },
  ];
  const gridRef = useRef<AgGridReact<unknown>>(null);

  const gridOptions: GridOptions = {
    datasource: dataSource,
    /*
        onModelUpdated: (event:ModelUpdatedEvent) => {
            console.log("modelUpdated");
            console.log(event);
        }
        */

    onSortChanged: (event: SortChangedEvent) => {
      const api: GridApi = event.api;
      console.log(
        'sortChanged',
        api.getFirstDisplayedRowIndex(),
        api.getLastDisplayedRowIndex(),
        event
      );
      // every time the sort is changed, scroll back to the top row.
      // Setting a sort and being in the middle of it makes no sense
      api.ensureIndexVisible(0);
    },
    rowBuffer: 0,
    rowModelType: 'infinite',
    cacheBlockSize: 20,
    cacheOverflowSize: 2,
    maxConcurrentDatasourceRequests: 1,
    maxBlocksInCache: 10,
    infiniteInitialRowCount: 10,
    getRowId: (params: GetRowIdParams) => {
      return String(params?.data?.agIdx);
    },
  };

  return (
    <div style={{ width: '100%', height: '500px', border: '2px solid red' }}>
      <pre>{JSON.stringify(operations)}</pre>
      <div
        style={{ height: '100%', width: '100%', border: '2px solid green' }}
        className={'ag-theme-quartz-dark'}
      >
        <AgGridReact
          columnDefs={columnDefs}
          ref={gridRef}
          context={{ outside_df_params: operations }}
          datasource={dataSource}
          gridOptions={gridOptions}
        />
        ;
      </div>
    </div>
  );
};
