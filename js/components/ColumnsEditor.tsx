import React, { useState } from 'react';
import { DFWhole, EmptyDf, bakedOperations } from './staticData';
import { OperationViewer } from './Operations';
import { Operation } from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
//import {bakedCommandConfig} from './bakedOperationDefaults';
import { DependentTabs, OperationResult } from './DependentTabs';
import { staticData } from 'paddy-react-edit-list';

export type OperationSetter = (ops: Operation[]) => void;

export function ColumnsEditor({
  df,
  activeColumn,
  operations,
  setOperations,
  operationResult,

  commandConfig,
}: {
  df: DFWhole;
  activeColumn: string;
  operations: Operation[];
  setOperations: OperationSetter;
  operationResult: OperationResult;
  commandConfig: CommandConfigT;
}) {
  const allColumns = df.schema.fields.map((field) => field.name);
  //console.log('Columns Editor, commandConfig', commandConfig);
  return (
    <div className="columns-editor" style={{ width: '100%' }}>
      <OperationViewer
        operations={operations}
        setOperations={setOperations}
        activeColumn={activeColumn}
        allColumns={allColumns}
        commandConfig={commandConfig}
      />
      <DependentTabs
        filledOperations={operations}
        operationResult={operationResult}
      />
    </div>
  );
}

export function ColumnsEditorEx() {
  const [operations, setOperations] = useState(bakedOperations);

  const baseOperationResults: OperationResult = {
    transformed_df: EmptyDf,
    generated_py_code: 'default py code',
    transform_error: undefined,
    //      transform_error:"asdfasf"
  };
  return (
    <ColumnsEditor
      df={staticData.tableDf}
      activeColumn={'foo'}
      commandConfig={staticData.bakedCommandConfig}
      operations={operations}
      setOperations={setOperations}
      operationResult={baseOperationResults}
    />
  );
}
