import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { OperationResult } from './DependentTabs';
import { DFDataOrPayload } from './DFViewerParts/DFWhole';
import { BuckarooState, BuckarooOptions, DFMeta } from './WidgetTypes';
import { CommandConfigT } from './CommandUtils';
import { Operation } from './OperationUtils';
import { IDisplayArgs } from './DFViewerParts/gridUtils';
export declare function WidgetDCFCell({ df_data_dict, df_display_args, df_meta, operations, on_operations, operation_results, command_config, buckaroo_state, on_buckaroo_state, buckaroo_options, }: {
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
}): import("react/jsx-runtime").JSX.Element;
