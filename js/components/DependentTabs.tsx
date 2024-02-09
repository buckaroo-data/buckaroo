import React, {
  useState,
  CSSProperties,
  Dispatch,
  SetStateAction,
} from 'react';
import { DFWhole, EmptyDf } from './DFViewerParts/DFWhole';
import _ from 'lodash';
import { Operation } from './OperationUtils';

export function OperationDisplayer({
  filledOperations,
  style,
}: {
  filledOperations: Operation[];
  style: CSSProperties;
}): React.JSX.Element {
  const baseStyle: CSSProperties = { margin: '0', textAlign: 'left' };
  const localStyle: CSSProperties = { ...baseStyle, ...style };
  return (
    <div className="command-displayer" style={{ width: '100%' }}>
      <pre style={localStyle}>{JSON.stringify(filledOperations)}</pre>
    </div>
  );
}

export function PythonDisplayer({
  style,
  generatedPyCode,
}: {
  style: CSSProperties;
  generatedPyCode: string;
}) {
  const baseStyle: CSSProperties = { margin: '0', textAlign: 'left' };
  const localStyle: CSSProperties = { ...baseStyle, ...style };
  return (
    <div className="python-displayer" style={{ width: '100%' }}>
      <pre style={localStyle}>{generatedPyCode}</pre>
    </div>
  );
}

export function TransformViewer({
  style,
  transformedDf,
}: {
  style: CSSProperties;
  transformedDf: DFWhole;
}) {
  return <div className="transform-viewer">"transformed view"</div>;
}
export type OperationResult = {
  transformed_df: DFWhole;
  generated_py_code: string;
  transform_error?: string;
};

export type OrRequesterT = (ops: Operation[]) => void;
export type getOperationResultSetterT = (
  setter: Dispatch<SetStateAction<OperationResult>>
) => OrRequesterT;

export const baseOperationResults: OperationResult = {
  transformed_df: EmptyDf,
  generated_py_code: 'default py code',
};

export function TabComponent({
  currentTab,
  _setTab,
  tabName,
}: {
  currentTab: any;
  _setTab: any;
  tabName: any;
}): JSX.Element {
  return (
    <li
      onClick={() => {
        _setTab(tabName);
      }}
      className={currentTab === tabName ? 'active' : ''}
    >
      {tabName}
    </li>
  );
}

export function DependentTabs({
  filledOperations,
  operationResult,
}: {
  filledOperations: Operation[];
  operationResult: OperationResult;
}) {
  const [tab, _setTab] = useState('DataFrame');
  const style: CSSProperties = { height: '45vh' };
  return (
    <div className="dependent-tabs" style={{ width: '100%' }}>
      <ul className="tabs">
        <TabComponent
          currentTab={tab}
          _setTab={_setTab}
          tabName={'DataFrame'}
        />
        <TabComponent currentTab={tab} _setTab={_setTab} tabName={'Python'} />
        <TabComponent
          currentTab={tab}
          _setTab={_setTab}
          tabName={'Operations'}
        />
      </ul>
      <div className="output-area">
        {operationResult.transform_error ? (
          <div>
            <h2> error </h2>
            <PythonDisplayer
              style={style}
              generatedPyCode={operationResult.transform_error}
            />
          </div>
        ) : (
          <span></span>
        )}
        {
          {
            Operations: (
              <OperationDisplayer
                style={style}
                filledOperations={filledOperations}
              />
            ),
            Python: (
              <PythonDisplayer
                style={style}
                generatedPyCode={operationResult.generated_py_code}
              />
            ),
            DataFrame: (
              <TransformViewer
                style={style}
                transformedDf={operationResult.transformed_df}
              />
            ),
          }[tab]
        }
      </div>
    </div>
  );
}
