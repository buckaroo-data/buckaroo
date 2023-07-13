import React, { useState, Dispatch, SetStateAction } from 'react';
import _ from 'lodash';
import { OperationResult, baseOperationResults } from './DependentTabs';
import { ColumnsEditor, WidgetConfig } from './ColumnsEditor';
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
  summaryDf
}: {
  origDf: DFWhole;
  operations: Operation[];
  on_operations: (ops: Operation[]) => void;
  operation_results: OperationResult;
  commandConfig: CommandConfigT;
  dfConfig: DfConfig;
  on_dfConfig: unknown;
  summaryDf: DFWhole
}) {
  const [activeCol, setActiveCol] = useState('stoptime');
  const widgetConfig: WidgetConfig = {showCommands:dfConfig.showCommands}
  const localDfConfig = {...dfConfig, 'rowsShown': origDf.data.length || 0}
  return (
    <div
      className="dcf-root flex flex-col"
      style={{ width: '100%', height: '100%' }}
    >
      <div
        className="orig-df flex flex-row"
        style={{ height: '450px', overflow: 'hidden' }}
      >
        <StatusBar config={localDfConfig} setConfig={on_dfConfig} />
        <DFViewer
          df={(dfConfig.summaryStats ? summaryDf : origDf) }
          activeCol={activeCol}
          setActiveCol={setActiveCol}
        />
      </div>
    {(widgetConfig.showCommands) ? (
      <ColumnsEditor
        df={origDf}
        activeColumn={activeCol}
        operations={operations}
        setOperations={on_operations}
        operationResult={operation_results}
        commandConfig={commandConfig}
        widgetConfig={widgetConfig}
	/>) : <span></span>}
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
    showCommands: true,
    //reorderdColumns: false,
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
    summaryDf={tableDf}
    />
  );
}
