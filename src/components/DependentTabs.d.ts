import { default as React, CSSProperties, Dispatch, SetStateAction } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { DFWhole } from './DFViewerParts/DFWhole';
import { Operation } from './OperationUtils';
export declare function OperationDisplayer({ filledOperations, style, }: {
    filledOperations: Operation[];
    style: CSSProperties;
}): React.JSX.Element;
export declare function PythonDisplayer({ style, generatedPyCode, }: {
    style: CSSProperties;
    generatedPyCode: string;
}): import("react/jsx-runtime").JSX.Element;
export type OperationResult = {
    transformed_df: DFWhole;
    generated_py_code: string;
    transform_error?: string;
};
export type OrRequesterT = (ops: Operation[]) => void;
export type getOperationResultSetterT = (setter: Dispatch<SetStateAction<OperationResult>>) => OrRequesterT;
export declare const baseOperationResults: OperationResult;
export declare function TabComponent({ currentTab, _setTab, tabName, }: {
    currentTab: any;
    _setTab: any;
    tabName: any;
}): JSX.Element;
export declare function DependentTabs({ filledOperations, operation_result, }: {
    filledOperations: Operation[];
    operation_result: OperationResult;
}): import("react/jsx-runtime").JSX.Element;
