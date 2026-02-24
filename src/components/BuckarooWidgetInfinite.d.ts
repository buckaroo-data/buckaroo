import { default as React } from '../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { OperationResult } from './DependentTabs';
import { DFDataOrPayload } from './DFViewerParts/DFWhole';
import { BuckarooState, BuckarooOptions, DFMeta } from './WidgetTypes';
import { CommandConfigT } from './CommandUtils';
import { Operation } from './OperationUtils';
import { IDisplayArgs } from './DFViewerParts/gridUtils';
import { DatasourceOrRaw } from './DFViewerParts/DFViewerInfinite';
import { IDatasource } from '@ag-grid-community/core';
import { KeyAwareSmartRowCache } from './DFViewerParts/SmartRowCache';
export declare const getDataWrapper: (data_key: string, df_data_dict: Record<string, DFDataOrPayload>, ds: IDatasource, total_rows?: number) => DatasourceOrRaw;
export declare const getKeySmartRowCache: (model: any, setRespError: any) => KeyAwareSmartRowCache;
export declare function BuckarooInfiniteWidget({ df_data_dict, df_display_args, df_meta, operations, on_operations, operation_results, command_config, buckaroo_state, on_buckaroo_state, buckaroo_options, src }: {
    df_meta: DFMeta;
    df_data_dict: Record<string, DFDataOrPayload>;
    df_display_args: Record<string, IDisplayArgs>;
    operations: Operation[];
    on_operations: (ops: Operation[]) => void;
    operation_results: OperationResult;
    command_config: CommandConfigT;
    buckaroo_state: BuckarooState;
    on_buckaroo_state: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckaroo_options: BuckarooOptions;
    src: KeyAwareSmartRowCache;
}): import("react/jsx-runtime").JSX.Element;
export declare function DFViewerInfiniteDS({ df_meta, df_data_dict, df_display_args, src, df_id, message_log, show_message_box }: {
    df_meta: DFMeta;
    df_data_dict: Record<string, DFDataOrPayload>;
    df_display_args: Record<string, IDisplayArgs>;
    src: KeyAwareSmartRowCache;
    df_id: string;
    message_log?: {
        messages?: Array<any>;
    };
    show_message_box?: {
        enabled?: boolean;
    };
}): import("react/jsx-runtime").JSX.Element;
