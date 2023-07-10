import React, { useState } from 'react';
import { DFWhole, EmptyDf, bakedOperations } from './staticData';
import { OperationViewer } from './Operations';
import { Operation } from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
//import {bakedCommandConfig} from './bakedOperationDefaults';
import { DependentTabs, OperationResult } from './DependentTabs';
import { tableDf, bakedCommandConfig } from './staticData'

export type OperationSetter = (ops: Operation[]) => void;
export interface WidgetConfig {
  showCommands:boolean;
//  showTransformed:boolean;
}


export function ColumnsEditor({
  df,
  activeColumn,
  operations,
  setOperations,
  operationResult,
  commandConfig,
  widgetConfig
}: {
  df: DFWhole;
  activeColumn: string;
  operations: Operation[];
  setOperations: OperationSetter;
  operationResult: OperationResult;
  commandConfig: CommandConfigT;
  widgetConfig:WidgetConfig
}) {
  const allColumns = df.schema.fields.map((field) => field.name);
  //console.log('Columns Editor, commandConfig', commandConfig);
  return (
    <div className="columns-editor" style={{ width: '100%' }}>
      {(widgetConfig.showCommands) ? (
	<div>
      <OperationViewer
        operations={operations}
        setOperations={setOperations}
        activeColumn={activeColumn}
        allColumns={allColumns}
        commandConfig={commandConfig}/>
      <DependentTabs
        filledOperations={operations}
        operationResult={operationResult}
	/>
    </div>
    ) : <span></span>}
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
      df={tableDf}
      activeColumn={'foo'}
      commandConfig={bakedCommandConfig}
      operations={operations}
      setOperations={setOperations}
    operationResult={baseOperationResults}
    widgetConfig={{showCommands:true}}
    />
  );
}
