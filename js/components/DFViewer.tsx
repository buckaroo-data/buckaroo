import React, { useRef, CSSProperties } from 'react';
import _ from 'lodash';
import { DFWhole, EmptyDf } from './staticData';

import { updateAtMatch, dfToAgrid } from './gridUtils';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import { GridOptions } from 'ag-grid-community';

import { HistogramCell } from './CustomHeader';

export type setColumFunc = (newCol: string) => void;

export function DFViewer(
  {
    df,
    style,
    activeCol,
    setActiveCol,
  }: {
    df: DFWhole;
    style?: CSSProperties;
    activeCol?: string;
    setActiveCol?: setColumFunc;
  } = {
    df: EmptyDf,
    style: { height: '300px' },
    setActiveCol: () => null,
  }
) {
  const [agColsPure, agData] = dfToAgrid(df);
  // console.log('dfviewer agData', agData);

  const styledColumns = updateAtMatch(
    _.clone(agColsPure),
    activeCol || '___never',
    {
      cellStyle: { background: 'var(--ag-range-selection-background-color-3)' },
    },
    { cellStyle: {} }
  );

  const gridOptions: GridOptions = {
    rowSelection: 'single',
    onRowClicked: (event) => console.log('A row was clicked'),
    defaultColDef: {
      sortable: true,
      type: 'rightAligned',
      cellRendererSelector: (params) => {
        if (params.node.rowPinned) {
          return {
            component: HistogramCell,
            params: {
              style: { fontStyle: 'italic' },
            },
          };
        } else {
          // rows that are not pinned don't use any cell renderer
          return undefined;
        }
      },
    },

    onCellClicked: (event) => {
      const colName = event.column.getColId();
      if (setActiveCol === undefined || colName === undefined) {
        return;
      } else {
        setActiveCol(colName);
      }
    },
  };
  const gridRef = useRef<AgGridReact<unknown>>(null);

  const makeCondtionalAutosize = (count: number, delay: number) => {
    /*
      this code is buggy and I'm not confident in it. I'm very
      surprised that automatically autosizing AG-grid requires custom
      functions to be written vs just a flag.
      */

    let counter = count;
    let timer: NodeJS.Timeout;
    let colWidthHasBeenSet = false;
    let currentColWidth = -10;
    if (gridRef === undefined || gridRef.current === null) {
      currentColWidth = 200;
    } else {
      try {
        const dc = gridRef!.current!.columnApi.getAllDisplayedColumns();

        if (dc.length !== 0) {
          currentColWidth = dc[0].getActualWidth();
        } else {
          currentColWidth = 200;
        }
      } catch (e) {
        console.log('88, gridref not defined yet', e);
      }
    }

    const conditionallyAutosize = () => {
      if (gridRef !== undefined) {
        if (gridRef.current !== undefined && gridRef.current !== null) {
          if (gridRef.current.columnApi !== undefined) {
            gridRef.current.columnApi.autoSizeAllColumns();
            const dc = gridRef.current.columnApi.getAllDisplayedColumns();
            // console.log("bodyWidth", cm.bodyWidth)
            // console.log("cm", cm)

            if (dc.length !== 0) {
              const aw = dc[0].getActualWidth(); // this eventually changes after the resize
              //console.log("dc", aw);
              if (colWidthHasBeenSet === false) {
                currentColWidth = aw;
                colWidthHasBeenSet = true;
              } else {
                currentColWidth = aw;
              }
            }
            gridRef.current.forceUpdate();
          }
        }
      }
      //	    console.log("counter", counter, "colWidthHasBeenSet", colWidthHasBeenSet, originalColWidth, currentColWidth);
      if (counter > 0 && colWidthHasBeenSet === false) {
        counter -= 1;
        // console.log("no gridRef or gridRef.current, setting delay", counter)
        //@ts-ignore
        timer = setTimeout(conditionallyAutosize, delay);
        return;
      } else if (counter > 0 && currentColWidth === 200) {
        counter -= 1;

        // console.log(
        //     "new colwidth not recognized yet",
        //     counter, originalColWidth, gridRef.current!.columnApi!.columnModel!.displayedColumns[0].actualWidth)
        //@ts-ignore
        timer = setTimeout(conditionallyAutosize, delay);
        return;
      }
    };
    //@ts-ignore
    timer = setTimeout(conditionallyAutosize, delay);
    return () => clearTimeout(timer);
  };

  makeCondtionalAutosize(50, 350);
  const pinnedTopRowData = [df.table_hints];

  return (
    <div className="df-viewer">
      <div
        style={{ height: 400 }}
        className="theme-hanger ag-theme-alpine-dark"
      >
        <AgGridReact
          ref={gridRef}
          gridOptions={gridOptions}
          rowData={agData}
          pinnedTopRowData={pinnedTopRowData}
          columnDefs={styledColumns}
        ></AgGridReact>
      </div>
    </div>
  );
}
