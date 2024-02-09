import React, { useState } from 'react';
import { bakedOperations } from '../baked_data/staticData';
import { DFViewerConfig, EmptyDf } from './DFViewerParts/DFWhole';
import { OperationViewer } from './Operations';
import { Operation } from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
//import {bakedCommandConfig} from './bakedOperationDefaults';
import { DependentTabs, OperationResult } from './DependentTabs';
import { tableDf, bakedCommandConfig } from '../baked_data/staticData';

export type OperationSetter = (ops: Operation[]) => void;
export interface WidgetConfig {
  showCommands: boolean;
}

export function ColumnsEditor({
  df_viewer_config,
  activeColumn,
  operations,
  setOperations,
  operationResult,
  commandConfig,
  widgetConfig,
}: {
  df_viewer_config: DFViewerConfig;
  activeColumn: string;
  operations: Operation[];
  setOperations: OperationSetter;
  operationResult: OperationResult;
  commandConfig: CommandConfigT;
  widgetConfig: WidgetConfig;
}) {
  const allColumns = df_viewer_config.column_config.map(
    (field) => field.col_name
  );
  return (
    <div className="columns-editor" style={{ width: '100%' }}>
      {widgetConfig.showCommands ? (
        <div>
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
      ) : (
        <span></span>
      )}
    </div>
  );
}

export function ColumnsEditorEx() {
  const [operations, setOperations] = useState(bakedOperations);

  const baseOperationResults: OperationResult = {
    transformed_df: EmptyDf,
    generated_py_code: 'default py code',
    transform_error: undefined,
  };
  return (
    <ColumnsEditor
      df_viewer_config={tableDf.dfviewer_config}
      activeColumn={'foo'}
      commandConfig={bakedCommandConfig}
      operations={operations}
      setOperations={setOperations}
      operationResult={baseOperationResults}
      widgetConfig={{ showCommands: true }}
    />
  );
}
