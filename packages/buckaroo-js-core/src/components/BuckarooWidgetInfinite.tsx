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
    IDisplayArgs
} from "./DFViewerParts/gridUtils";
import { DatasourceOrRaw, DFViewerInfinite } from "./DFViewerParts/DFViewerInfinite";
import { IDatasource } from "@ag-grid-community/core";
import { KeyAwareSmartRowCache, PayloadArgs, PayloadResponse, RequestFN } from "./DFViewerParts/SmartRowCache";
import { parquetRead, parquetMetadata } from 'hyparquet'

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
/*
const gensym = () => {
    let a = 0;
    return () => {
        a += 1;
        return a;
    }
}
*/
//const counter = gensym()
export const getKeySmartRowCache = (model: any, setRespError:any) => {
    //const symNum = counter();
    const reqFn: RequestFN = (pa: PayloadArgs) => {
        model.send({ type: 'infinite_request', payload_args: pa })
    }
    const src = new KeyAwareSmartRowCache(reqFn)

    model.on("msg:custom", (msg: any, buffers: any[]) => {
        if (msg?.type !== "infinite_resp") {
            console.log("bailing not infinite_resp")
            return
        }
        if (msg.data === undefined) {
            console.log("bailing no data", msg)
            return
        }
        const payload_response = msg as PayloadResponse;
        if (payload_response.error_info !== undefined) {
            console.log("there was a problem with the request, not adding to the cache")
            console.log(payload_response.error_info)
            setRespError(payload_response.error_info)
            return
        }
        /*
        console.log("92 got a response for ", symNum, 
            //creationTime.getUTCSeconds(), creationTime.getUTCMilliseconds() ,
            payload_response.key);
        */

        if(payload_response.key.request_time !== undefined ) {

            //@ts-ignore
            const now = (new Date()) - 1 as number
            const respTime = now - payload_response.key.request_time;
            console.log(`response before ${[payload_response.key.start, payload_response.key.origEnd, payload_response.key.end]} parse took ${respTime}`)
        }
            
        const table_bytes = buffers[0]
        const metadata = parquetMetadata(table_bytes.buffer)

        parquetRead({
            file: table_bytes.buffer,
            metadata:metadata,
            rowFormat: 'object',
            onComplete: data => {
                //@ts-ignore
                const parqData:DFData = data as DFData
                payload_response.data = parqData
                src.addPayloadResponse(payload_response);
            }
        })
    })
    return src;
}

export function BuckarooInfiniteWidget({
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
        src
    }: {
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
        src: KeyAwareSmartRowCache
    }) {
    console.log("132 BuckarooInfiniteWidget");
        // we only want to create KeyAwareSmartRowCache once, it caches sourceName too
        // so having it live between relaods is key
        //const [respError, setRespError] = useState<string | undefined>(undefined);


        const mainDs = useMemo(() => {
            console.log("recreating data source because operations changed", new Date());
            src.debugCacheState();
            return getDs(src);
            // getting a new datasource when operations or post-processing changes - necessary for forcing ag-grid complete updated
            // updating via post-processing changes appropriately.
            // forces re-render and dataload when not completely necessary if other
            // buckaroo_state props change
            //
            // putting buckaroo_state.post_processing doesn't work properly
        }, [operations, buckaroo_state]);
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
                    className="orig-df flex flex-row"
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
                        error_info={""}
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
