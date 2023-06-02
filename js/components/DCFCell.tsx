import React, { useState, Dispatch, SetStateAction } from 'react';
import _ from 'lodash';
import { OperationResult, baseOperationResults } from './DependentTabs';
import { ColumnsEditor } from './ColumnsEditor';
import { tableDf, DFWhole } from './staticData';
import { DFViewer } from './DFViewer';
import { StatusBar, DfConfig } from './StatusBar';
import { CommandConfigT } from './CommandUtils';
import { bakedCommandConfig } from './bakedOperationDefaults';
import { Operation, bakedOperations } from './OperationUtils';

export type CommandConfigSetterT = (
  setter: Dispatch<SetStateAction<CommandConfigT>>
) => void;

/*
  Widget DCFCell is meant to be used with callback functions and passed values, not explicit http calls
 */
export function WidgetDCFCell({
  origDf,
  operations,
  on_operations,
  operation_results,
  commandConfig,
  dfConfig,
  on_dfConfig,
}: {
  origDf: DFWhole;
  operations: Operation[];
  on_operations: (ops: Operation[]) => void;
  operation_results: OperationResult;
  commandConfig: CommandConfigT;
  dfConfig: DfConfig;
  on_dfConfig: unknown;
}) {
  const [activeCol, setActiveCol] = useState('stoptime');

  return (
    <div
      className="dcf-root flex flex-col"
      style={{ width: '100%', height: '100%' }}
    >
      <div
        className="orig-df flex flex-row"
        style={{ height: '300px', overflow: 'hidden' }}
      >
        <StatusBar config={dfConfig} setConfig={on_dfConfig} />
        <DFViewer
          df={origDf}
          activeCol={activeCol}
          setActiveCol={setActiveCol}
        />
      </div>
      <ColumnsEditor
        df={origDf}
        activeColumn={activeCol}
        operations={operations}
        setOperations={on_operations}
        operationResult={operation_results}
        commandConfig={commandConfig}
      />
    </div>
  );
}

export function WidgetDCFCellExample() {
  const [sampleConfig, setConfig] = useState<DfConfig>({
    totalRows: 1309,
    columns: 30,
    rowsShown: 500,
    sampleSize: 10_000,
    sampled: true,
    summaryStats: false,
    reorderdColumns: false,
  });
  const [operations, setOperations] = useState<Operation[]>(bakedOperations);
  return (
    <WidgetDCFCell
      origDf={tableDf}
      operations={operations}
      on_operations={setOperations}
      operation_results={baseOperationResults}
      commandConfig={bakedCommandConfig}
      dfConfig={sampleConfig}
      on_dfConfig={setConfig}
    />
  );
}
