import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { DFMeta, BuckarooOptions, BuckarooState } from './WidgetTypes';
import { CustomCellEditorProps } from 'ag-grid-react';
import { ThemeConfig } from './DFViewerParts/gridUtils';
export type setColumFunc = (newCol: string) => void;
export declare const fakeSearchCell: (_params: any) => import("react/jsx-runtime").JSX.Element;
export declare const SearchEditor: React.MemoExoticComponent<({ value, onValueChange, stopEditing }: CustomCellEditorProps) => import("react/jsx-runtime").JSX.Element>;
export declare function StatusBar({ dfMeta, buckarooState, setBuckarooState, buckarooOptions, heightOverride, themeConfig, inFlight, componentConfig, }: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
    heightOverride?: number;
    themeConfig?: ThemeConfig;
    inFlight?: boolean;
    /** Opaque component_config blob from Python. Passed into the AG-Grid
     *  context so any cell renderer can read config keys without additional
     *  prop threading. New config keys (e.g. searchDebounceMs) are added to
     *  Python's ComponentConfig TypedDict; cell renderers read them via
     *  params.context.componentConfig. */
    componentConfig?: Record<string, unknown>;
}): import("react/jsx-runtime").JSX.Element;
