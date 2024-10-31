import React from 'react';

import { DFViewerConfig } from './DFViewerParts/DFWhole';
import { OperationViewer } from './Operations';
import { Operation } from './OperationUtils';
import { CommandConfigT } from './CommandUtils';
import { DependentTabs, OperationResult } from './DependentTabs';

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
}: {
  df_viewer_config: DFViewerConfig;
  activeColumn: string;
  operations: Operation[];
  setOperations: OperationSetter;
  operationResult: OperationResult;
  commandConfig: CommandConfigT;
}) {
  const allColumns = df_viewer_config.column_config.map(
    (field) => field.col_name
  );
  return (
    <div className="columns-editor" style={{ width: '100%' }}>
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
    </div>
  );
}
