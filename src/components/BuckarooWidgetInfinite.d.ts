import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { OperationResult } from './DependentTabs';
import { DFData } from './DFViewerParts/DFWhole';
import { BuckarooState, BuckarooOptions, DFMeta } from './WidgetTypes';
import { CommandConfigT } from './CommandUtils';
import { Operation } from './OperationUtils';
import { IDisplayArgs } from './DFViewerParts/gridUtils';
import { DatasourceOrRaw } from './DFViewerParts/DFViewerInfinite';
import { IDatasource } from 'ag-grid-community';
import { KeyAwareSmartRowCache } from './DFViewerParts/SmartRowCache';
export declare const bkTs: () => string;
export declare const makeStaticInfiniteDs: (data: DFData, _label?: string) => IDatasource;
export declare const getDataWrapper: (data_key: string, df_data_dict: Record<string, DFData>, ds: IDatasource, total_rows?: number) => DatasourceOrRaw;
export declare const getKeySmartRowCache: (model: any, setRespError: any) => KeyAwareSmartRowCache;
export declare function BuckarooInfiniteWidget({ df_data_dict, df_display_args, df_meta, on_compute_stats, on_visible_columns, operations, on_operations, operation_results, command_config, buckaroo_state, on_buckaroo_state, buckaroo_options, src, dataframe_id, autoHeight, }: {
    df_meta: DFMeta;
    df_data_dict: Record<string, DFData>;
    df_display_args: Record<string, IDisplayArgs>;
    /** Sends a forced stats_request. Server entry points pass it; the Jupyter
     *  widget does not, and then the status bar offers no control. */
    on_compute_stats?: () => void;
    /** Called with the data columns the grid shows, now and whenever they change. */
    on_visible_columns?: (columns: string[]) => void;
    operations: Operation[];
    on_operations: (ops: Operation[]) => void;
    operation_results: OperationResult;
    command_config: CommandConfigT;
    buckaroo_state: BuckarooState;
    on_buckaroo_state: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckaroo_options: BuckarooOptions;
    src: KeyAwareSmartRowCache;
    dataframe_id?: string;
    /** When provided, overrides server-sent component_config.layoutType.
     *  true → domLayout "autoHeight" (grows with row count).
     *  false → domLayout "normal" (fills parent container).
     *  undefined → server value wins. */
    autoHeight?: boolean;
}): import("react/jsx-runtime").JSX.Element;
export declare function DFViewerInfiniteDS({ df_meta, df_data_dict, df_display_args, src, df_id, message_log, show_message_box, autoHeight, }: {
    df_meta: DFMeta;
    df_data_dict: Record<string, DFData>;
    df_display_args: Record<string, IDisplayArgs>;
    src: KeyAwareSmartRowCache;
    df_id: string;
    message_log?: {
        messages?: Array<any>;
    };
    show_message_box?: {
        enabled?: boolean;
    };
    /** When provided, overrides server-sent component_config.layoutType.
     *  true → domLayout "autoHeight"; false → "normal"; undefined → server wins. */
    autoHeight?: boolean;
}): import("react/jsx-runtime").JSX.Element;
