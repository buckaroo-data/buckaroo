import React, {
  useState,
  useEffect,
} from 'react';
import _ from 'lodash';
import {
  Operation,
  SetOperationsFunc,
  OperationEventFunc,
  NoArgEventFunc,
} from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
import { replaceInArr } from './utils';
import { bakedCommandConfig } from './bakedOperationDefaults';
import { OperationDetail } from './OperationDetail';
import { AgGridReact } from 'ag-grid-react'; // the AG Grid React Component
import { ColDef, GridOptions } from 'ag-grid-community';
import { updateAtMatch } from './gridUtils';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import { bakedOperations } from './staticData';

const getColumns = (passedOperations: Operation[]): ColDef[] =>
  _.map(Array.from(passedOperations.entries()), ([index, element]) => {
    const name = element[0]['symbol'];
    const key = name + index.toString();
    const column = { field: key, headerName: name }; // width: 20, maxWidth: 60};
    return column;
  });

export const OperationsList = ({
  operations,
  activeKey,
  setActiveKey,
}: {
  operations: Operation[];
  activeKey?: string;
  setActiveKey: React.Dispatch<React.SetStateAction<string>>;
}) => {
  const rowElements = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const rowEl: Record<string, string> = {};
      rowEl[key] = element[2];
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

  //console.log('OperationsList columns', columns);

  const gridOptions: GridOptions = {
    rowSelection: 'single',
    headerHeight: 30,
    //onRowClicked: (event) => console.log('A row was clicked'),
    onCellClicked: (event) => {
      const colName = event.column.getColId();
      //console.log('operationsList onCellClicked');
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

export const OperationAdder = ({ column, addOperationCb, defaultArgs }:{ column:string, addOperationCb:any, defaultArgs:any } ): JSX.Element => {
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
  const operationObjs = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const rowEl: Record<string, Operation> = {};
      rowEl[key] = element;
      return rowEl;
    }
  );
  //why am I doing this? probably something so I gauruntee a clean dict

  const operationDict = _.merge({}, ...operationObjs);

  const idxObjs = _.map(
    Array.from(operations.entries()),
    ([index, element]) => {
      const name = element[0]['symbol'];
      const key = name + index.toString();
      const rowEl: Record<string, number> = {};
      rowEl[key] = index;
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
      setActiveKey('');
      setOperations(_.filter(nextOperations) as Operation[]);
    };
  }

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
  //console.log('OperationsViewer operationDict', operationDict, 'activeKey', activeKey);
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
        />
      </div>
      {activeKey && (
        <OperationDetail
          command={operationDict[activeKey]}
          setCommand={getSetOperation(activeKey)}
          deleteCB={getDeleteOperation(activeKey)}
          columns={allColumns}
          commandPatterns={argspecs}
        />
      )}
    </div>
  );
};

export const Commands = () => {
  const [c, setC] = useState(bakedOperations);
  const [commandConfig, setCommandConfig] = useState(bakedCommandConfig);

  useEffect(() => {
    fetch('http://localhost:5000/dcf/command-config').then(async (response) => {
      setCommandConfig(await response.json());
    });
  }, []);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <OperationViewer
        operations={c}
        setOperations={setC}
        activeColumn={'new-column2'}
        allColumns={['foo-col', 'bar-col', 'baz-col']}
        commandConfig={commandConfig}
      />
      <code style={{ fontSize: '1em', textAlign: 'left' }}>
        {' '}
        {JSON.stringify(c, null, '\t\n\r')}{' '}
      </code>
    </div>
  );
};
