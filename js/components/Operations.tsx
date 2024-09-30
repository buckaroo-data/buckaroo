import React, { useState } from 'react';
import _ from 'lodash';
import {
  Operation,
  SetOperationsFunc,
  OperationEventFunc,
  NoArgEventFunc,
} from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
import { replaceInArr } from './utils';

import { OperationDetail } from './OperationDetail';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import { ColDef, GridOptions } from 'ag-grid-community';
//import { CustomCellRendererProps } from '@ag-grid-community/react';

import { updateAtMatch } from './utils';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';

export const OperationsList = ({
  operations,
  activeKey,
  setActiveKey,
  delKey,
}: {
  operations: Operation[];
  activeKey?: string;
  setActiveKey: React.Dispatch<React.SetStateAction<string>>;
  delKey: any;
}) => {
  const renderOperation = (params: any) => (
    <span className="missionSpan">
      <span
        style={{
          height: 30,
          width: 30,
          margin: 3,
          paddingBottom: 8,
          float: 'left',
          background: 'grey',
        }}
        onClick={delKey(params.value[0])}
      >
        X
      </span>
      <span>{params.value[1]}</span>
    </span>
  );

  const getColumns = (passedOperations: Operation[]): ColDef[] =>
    _.map(Array.from(passedOperations.entries()), ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const column = {
        field: key,
        headerName: name,
        cellRenderer: renderOperation,
      }; // width: 20, maxWidth: 60};
      return column;
    });

  const rowElements: Record<string, [string, string]>[] = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const rowEl: Record<string, [string, string]> = {};
      rowEl[key] = [key, element[2]]; //key, colName
      return rowEl;
    }
  );
  const rows = [_.merge({}, ...rowElements)];
  const columns = getColumns(operations);

  const styledColumns = updateAtMatch(
    _.clone(columns),
    activeKey || '___never',
    {
      cellStyle: { background: 'var(--ag-range-selection-background-color-3)' },
    },
    { cellStyle: {} }
  );

  const gridOptions: GridOptions = {
    rowSelection: 'single',
    headerHeight: 30,
    onCellClicked: (event) => {
      const colName = event.column.getColId();
      setActiveKey(colName);
    },
  };
  return (
    <div style={{ height: 78, width: 1000 }} className="ag-theme-alpine">
      <AgGridReact
        gridOptions={gridOptions}
        rowData={rows}
        columnDefs={styledColumns}
      ></AgGridReact>
    </div>
  );
};

export const OperationAdder = ({
  column,
  addOperationCb,
  defaultArgs,
}: {
  column: string;
  addOperationCb: any;
  defaultArgs: any;
}): JSX.Element => {
  const addOperationByName = (localOperationName: string) => {
    return () => {
      const defaultOperation = defaultArgs[localOperationName];
      addOperationCb(replaceInArr(defaultOperation, 'col', column));
    };
  };

  return (
    <div className="operation-adder">
      <span className={'column-name'}> Column: {column}</span>
      <fieldset>
        {_.keys(defaultArgs).map((optionVal) => (
          <button key={optionVal} onClick={addOperationByName(optionVal)}>
            {' '}
            {optionVal}{' '}
          </button>
        ))}
      </fieldset>
    </div>
  );
};

export const OperationViewer = ({
  operations,
  setOperations,
  activeColumn,
  allColumns,
  commandConfig,
}: {
  operations: Operation[];
  setOperations: SetOperationsFunc;
  activeColumn: string;
  allColumns: string[];
  commandConfig: CommandConfigT;
}) => {
  const opToKey = (idx: number, op: Operation): string => {
    const name = op[0]['symbol'];
    return name + idx.toString();
  };

  const operationObjs = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const rowEl: Record<string, Operation> = {};
      rowEl[opToKey(index, element)] = element;
      return rowEl;
    }
  );
  //why am I doing this? probably something so I gauruntee a clean dict

  const operationDict = _.merge({}, ...operationObjs);

  const idxObjs = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const rowEl: Record<string, number> = {};
      rowEl[opToKey(index, element)] = index;
      return rowEl;
    }
  );
  const keyToIdx = _.merge({}, ...idxObjs);

  // previously was null
  const [activeKey, setActiveKey] = useState('');

  function getSetOperation(key: string): OperationEventFunc {
    return (newOperation: Operation) => {
      const index = keyToIdx[key];
      const nextOperations = operations.map((c, i) => {
        if (i === index) {
          return newOperation;
        } else {
          return c;
        }
      });
      console.log('about to call setOperations', key, newOperation);
      setOperations(nextOperations);
    };
  }

  function getDeleteOperation(key: string): NoArgEventFunc {
    return (): void => {
      const index = keyToIdx[key];
      const nextOperations = operations.map((c, i) => {
        if (i === index) {
          return undefined;
        } else {
          return c;
        }
      });
      //const newIdx = Math.max(0, index - 1);
      const newOps = _.filter(nextOperations) as Operation[];
      console.log('getDeleteOperations', operations.length, newOps.length);
      setOperations(newOps);
      //setActiveKey(opToKey(newIdx, newOps[newIdx]));
      //setActiveKey('');
    };
  }

  const getColumns = (passedOperations: Operation[]): ColDef[] =>
    _.map(Array.from(passedOperations.entries()), ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const column = { field: key, headerName: name }; // width: 20, maxWidth: 60};
      return column;
    });
  const addOperation: OperationEventFunc = (newOperation: Operation) => {
    const newOperationArr = [...operations, newOperation];
    setOperations(newOperationArr);
    const newOperationKey =
      getColumns(newOperationArr)[newOperationArr.length - 1].field;
    if (newOperationKey !== undefined) {
      setActiveKey(newOperationKey);
    }
  };
  const { argspecs, defaultArgs } = commandConfig;
  return (
    <div className="command-viewer">
      <OperationAdder
        column={activeColumn}
        addOperationCb={addOperation}
        defaultArgs={defaultArgs}
      />
      <div className="operations-box">
        <h4> Operations </h4>
        <OperationsList
          operations={operations}
          activeKey={activeKey}
          setActiveKey={setActiveKey}
          delKey={getDeleteOperation}
        />
      </div>
      {activeKey && (
        <OperationDetail
          command={operationDict[activeKey]}
          setCommand={getSetOperation(activeKey)}
          columns={allColumns}
          commandPatterns={argspecs}
        />
      )}
    </div>
  );
};
