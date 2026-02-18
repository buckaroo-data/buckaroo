import React, { useMemo, useState } from "react";
import _ from "lodash";
import { OperationResult } from "./DependentTabs";
import { ColumnsEditor } from "./ColumnsEditor";

import { DFData, DFDataOrPayload } from "./DFViewerParts/DFWhole";
import { resolveDFData } from "./DFViewerParts/resolveDFData";
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
import { MessageBox } from "./MessageBox";

export const getDataWrapper = (
    data_key: string,
    df_data_dict: Record<string, DFDataOrPayload>,
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
        const resolved = resolveDFData(df_data_dict[data_key]);
        return {
            data_type: "Raw",
            data: resolved,
            length: resolved.length,
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
        console.log("got a message", msg);
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
            src.addErrorResponse(payload_response);
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
        console.log("about to read buffers[0]", buffers[0])            
        const table_bytes = buffers[0]
        const metadata = parquetMetadata(table_bytes.buffer)
        console.log("metadata", metadata)
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
        df_data_dict: Record<string, DFDataOrPayload>;
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

    const outerTime = new Date();
    const mainDs = useMemo(() => {
	//@ts-ignore
        console.log("recreating data source because operations changed", outerTime, ((new Date()) - outerTime))
            src.debugCacheState();
            return getDs(src);
            // getting a new datasource when operations or post-processing changes - necessary for forcing ag-grid complete updated
            // updating via post-processing changes appropriately.
            // forces re-render and dataload when not completely necessary if other
            // buckaroo_state props change
            //
            // putting buckaroo_state.post_processing doesn't work properly
        //}, [operations, buckaroo_state]);
        }, [operations, buckaroo_state.post_processing, buckaroo_state.cleaning_method]);
      const [activeCol, setActiveCol] = useState<[string, string]>(["a", "stoptime"]);

        const cDisp = df_display_args[buckaroo_state.df_display];

        const [data_wrapper, summaryStatsData] = useMemo(
            () => [
                getDataWrapper(cDisp.data_key, df_data_dict, mainDs, df_meta.total_rows),
                resolveDFData(df_data_dict[cDisp.summary_stats_key]),
            ],
            [cDisp, operations, buckaroo_state],
        );
        
        //used to denote "this dataframe has been transformed", This is
        //evantually spliced back into the request args from scrolling/
        //the data source
        const outsideDFParams = [operations, buckaroo_state.post_processing];
        return (
            <div className="dcf-root flex flex-col buckaroo-widget buckaroo-infinite-widget"
             style={{ width: "100%", height: "100%" }}>
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
export function DFViewerInfiniteDS({
        df_meta,
        df_data_dict,
        df_display_args,
        src,
        df_id,
        message_log,
        show_message_box
    }: {
        df_meta: DFMeta;
        df_data_dict: Record<string, DFDataOrPayload>;
        df_display_args: Record<string, IDisplayArgs>;
        src: KeyAwareSmartRowCache,
        df_id: string // the memory id
        message_log?: { messages?: Array<any> };
        show_message_box?: { enabled?: boolean };
    }) {
        // DFViewerInfiniteDS rendering
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
        }, []);
      const [activeCol, setActiveCol] = useState<[string, string]>(["a", "stoptime"]);

        const cDisp = df_display_args["main"];

        const [data_wrapper, summaryStatsData] = useMemo(
            () => [
                getDataWrapper(cDisp.data_key, df_data_dict, mainDs, df_meta.total_rows),
                resolveDFData(df_data_dict[cDisp.summary_stats_key]),
            ],
            [cDisp, df_data_dict, mainDs, df_meta.total_rows]
        );
        
        //used to denote "this dataframe has been transformed", This is
        //evantually spliced back into the request args from scrolling/
        //the data source
        //const outsideDFParams = ["unused", "unused"];
        const outsideDFParams: unknown = [df_id];
        

        const messagesEnabled = show_message_box?.enabled ?? false;
        // Ensure messages is always an array and reacts to changes
        const messages = React.useMemo(() => {
            const msgs = message_log?.messages;
            if (!msgs) return [];
            if (!Array.isArray(msgs)) {
                console.warn("[DFViewerInfiniteDS] message_log.messages is not an array:", typeof msgs, msgs);
                return [];
            }
            return msgs;
        }, [message_log?.messages]);
        
        // Debug: Log when messages change
        React.useEffect(() => {
            console.log("[DFViewerInfiniteDS] Message box state changed:", {
                messagesEnabled,
                messageCount: messages.length,
                message_log_type: typeof message_log,
                message_log_keys: message_log ? Object.keys(message_log) : null,
                message_log_messages_type: message_log?.messages ? typeof message_log.messages : null,
                message_log_messages_isArray: Array.isArray(message_log?.messages),
                firstFewMessages: messages.slice(0, 3),
            });
        }, [messages, messagesEnabled, message_log]);

        return (
            <div className="dcf-root flex flex-col buckaroo-widget buckaroo-infinite-widget"
             style={{ width: "100%", height: "100%" }}>
                <div
                    className="orig-df flex flex-row"
                    style={{
                        // height: '450px',
                        overflow: "hidden",
                    }}
                >
                {messagesEnabled && <MessageBox messages={messages} />}
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

            </div>
        );
    }
