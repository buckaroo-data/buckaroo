import { default as React } from '../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { DFMeta, BuckarooOptions, BuckarooState } from './WidgetTypes';
import { CustomCellEditorProps } from '@ag-grid-community/react';
export type setColumFunc = (newCol: string) => void;
export declare const fakeSearchCell: (_params: any) => import("react/jsx-runtime").JSX.Element;
export declare const SearchEditor: React.MemoExoticComponent<({ value, onValueChange, stopEditing }: CustomCellEditorProps) => import("react/jsx-runtime").JSX.Element>;
export declare function StatusBar({ dfMeta, buckarooState, setBuckarooState, buckarooOptions, heightOverride }: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
    heightOverride?: number;
}): import("react/jsx-runtime").JSX.Element;
