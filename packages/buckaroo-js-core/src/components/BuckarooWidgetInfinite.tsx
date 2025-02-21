import { useMemo, useState } from "react";
import _ from "lodash";
import { OperationResult } from "./DependentTabs";
import { ColumnsEditor } from "./ColumnsEditor";

import { DFData } from "./DFViewerParts/DFWhole";
import { StatusBar } from "./StatusBar";
import { BuckarooState } from "./WidgetTypes";
import { BuckarooOptions } from "./WidgetTypes";
import { DFMeta } from "./WidgetTypes";
import { CommandConfigT } from "./CommandUtils";
import { Operation } from "./OperationUtils";
import {
    getDs,
    getPayloadKey,
    IDisplayArgs,
    LruCache,
    PayloadArgs,
    PayloadResponse,
} from "./DFViewerParts/gridUtils";
import { DatasourceOrRaw, DFViewerInfinite } from "./DFViewerParts/DFViewerInfinite";
import { IDatasource } from "@ag-grid-community/core";

export const getDataWrapper = (
    data_key: string,
    df_data_dict: Record<string, DFData>,
    ds: IDatasource,
    total_rows?: number
): DatasourceOrRaw => {
    if (data_key === "main") {
        return {
            data_type: "DataSource",
            datasource: ds,
            length: total_rows || 50,
        };
    } else {
        return {
            data_type: "Raw",
            data: df_data_dict[data_key],
            length: df_data_dict[data_key].length,
        };
    }
};

export function BuckarooInfiniteWidget({
    //@ts-ignore
    payload_args,
    on_payload_args,
    payload_response,
    df_data_dict,
    df_display_args,
    df_meta,
    operations,
    on_operations,
    operation_results,
    command_config,
    buckaroo_state,
    on_buckaroo_state,
    buckaroo_options,
}: {
    payload_args: PayloadArgs;
    on_payload_args: (pa: PayloadArgs) => void;
    payload_response: PayloadResponse;
    df_meta: DFMeta;
    df_data_dict: Record<string, DFData>;
    df_display_args: Record<string, IDisplayArgs>;
    operations: Operation[];
    on_operations: (ops: Operation[]) => void;
    operation_results: OperationResult;
    command_config: CommandConfigT;
    buckaroo_state: BuckarooState;
    on_buckaroo_state: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckaroo_options: BuckarooOptions;
}) {
    // We wonly want to create respCache once, there are some swapover
    // recreation of datasource where the old respCache gets incoming response
    // only to be destroyed
    const respCache = useMemo(() => new LruCache<PayloadResponse>(), []);
    const mainDs = useMemo(() => {
        const t = new Date();
        console.log("recreating data source because operations changed", t);
        return getDs(on_payload_args, respCache);
        // getting a new datasource when operations or post-processing changes - necessary for forcing ag-grid complete updated
        // updating via post-processing changes appropriately.
        // forces re-render and dataload when not completely necessary if other
        // buckaroo_state props change
        //
        // putting buckaroo_state.post_processing doesn't work properly
    }, [operations, buckaroo_state]);
    const cacheKey = getPayloadKey(payload_response.key);
    console.log("setting respCache", cacheKey, payload_response);
    respCache.put(getPayloadKey(payload_response.key), payload_response);

    const [activeCol, setActiveCol] = useState("stoptime");

    const cDisp = df_display_args[buckaroo_state.df_display];

    const [data_wrapper, summaryStatsData] = useMemo(
        () => [
            getDataWrapper(cDisp.data_key, df_data_dict, mainDs, df_meta.total_rows),
            df_data_dict[cDisp.summary_stats_key],
        ],
        [cDisp, operations, buckaroo_state],
    );

    const outsideDFParams = [operations, buckaroo_state.post_processing];
    return (
        <div className="dcf-root flex flex-col" style={{ width: "100%", height: "100%" }}>
            <div
                className="orig-df"
                style={{
                    // height: '450px',
                    overflow: "hidden",
                }}
            >
                <StatusBar
                    dfMeta={df_meta}
                    buckarooState={buckaroo_state}
                    setBuckarooState={on_buckaroo_state}
                    buckarooOptions={buckaroo_options}
                />
                <DFViewerInfinite
                    data_wrapper={data_wrapper}
                    df_viewer_config={cDisp.df_viewer_config}
                    summary_stats_data={summaryStatsData}
                    outside_df_params={outsideDFParams}
                    activeCol={activeCol}
                    setActiveCol={setActiveCol}
                    error_info={payload_response.error_info}
                />
            </div>
            {buckaroo_state.show_commands ? (
                <ColumnsEditor
                    df_viewer_config={cDisp.df_viewer_config}
                    activeColumn={activeCol}
                    operations={operations}
                    setOperations={on_operations}
                    operation_result={operation_results}
                    command_config={command_config}
                />
            ) : (
                <span></span>
            )}
        </div>
    );
}
