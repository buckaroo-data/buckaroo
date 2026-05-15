import React, { useEffect, useMemo, useRef, useState } from "react";
import * as _ from "lodash-es";
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
import { IDatasource, IGetRowsParams } from "ag-grid-community";
import { KeyAwareSmartRowCache, PayloadArgs, PayloadResponse, RequestFN } from "./DFViewerParts/SmartRowCache";
import { parquetRead, parquetMetadata } from 'hyparquet'
import { MessageBox } from "./MessageBox";

// Shared label for the swap-tracing console.logs added to debug summary-stats
// toggle issues. grep "[bk-flash]" in the browser console to see the timeline.
const bkLog = (event: string, extra?: Record<string, unknown>): void => {
    // Use performance.now for sub-ms ordering across the React render → AG-Grid
    // commit boundary. Logs are intentionally chatty — pull them out once the
    // toggle path is confirmed working.
    // eslint-disable-next-line no-console
    console.log(`[bk-flash ${performance.now().toFixed(1)}ms] ${event}`, extra ?? "");
};

// Wrap a static DFData array in a fake IDatasource. Used for summary stats
// and other small pre-loaded datasets so they can share the same AG-Grid
// rowModelType ("infinite") as the live main dataset. Without this, swapping
// df_display from "main" to "summary" flips data_wrapper.data_type from
// DataSource to Raw and forces an AG-Grid remount (rowModelType can't be
// reconfigured live). With this, headers stay mounted across the swap.
export const makeStaticInfiniteDs = (data: DFData, label?: string): IDatasource => {
    bkLog("makeStaticInfiniteDs constructed", { label, dataLen: data.length });
    return {
        rowCount: data.length,
        getRows: (params: IGetRowsParams) => {
            // Static data is always available — respond synchronously, no loading
            // state, no network round-trip.
            const slice = data.slice(params.startRow, params.endRow);
            bkLog("fakeDs.getRows ENTER", {
                label,
                startRow: params.startRow,
                endRow: params.endRow,
                sortModel: params.sortModel,
                sliceLen: slice.length,
                lastRow: data.length,
            });
            params.successCallback(slice, data.length);
            bkLog("fakeDs.getRows EXIT (successCallback called)", { label });
        },
    };
};

export const getDataWrapper = (
    data_key: string,
    df_data_dict: Record<string, DFData>,
    ds: IDatasource,
    total_rows?: number
): DatasourceOrRaw => {
    bkLog("getDataWrapper called", {
        data_key,
        hasKeyInDict: df_data_dict[data_key] !== undefined,
        total_rows,
    });
    if (data_key === "main") {
        return {
            data_type: "DataSource",
            datasource: ds,
            length: total_rows || 50,
        };
    }
    const data = df_data_dict[data_key];
    if (data === undefined) {
        bkLog("getDataWrapper WARNING — data is undefined", { data_key, availableKeys: Object.keys(df_data_dict) });
    }
    return {
        data_type: "DataSource",
        datasource: makeStaticInfiniteDs(data || [], data_key),
        length: (data || []).length,
    };
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
            return
        }
        if (msg.data === undefined) {
            return
        }
        const payload_response = msg as PayloadResponse;
        if (payload_response.error_info !== undefined) {
            src.addErrorResponse(payload_response);
            console.error("[buckaroo] infinite_resp error:", payload_response.error_info)
            setRespError(payload_response.error_info)
            return
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
        src,
        dataframe_id,
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
        src: KeyAwareSmartRowCache;
        // Opaque opt-in identity for the underlying dataframe. When the value
        // changes the widget treats it as a "different dataframe" event:
        //   - activeCol resets to default
        //   - dataframe_id participates in outside_df_params so SmartRowCache
        //     sourceName picks up the new identity
        //
        // NOTE: in addition to this explicit prop, the widget internally derives
        // an *effective* dataframe id that also bumps on row-content-changing
        // state: operations, post_processing, cleaning_method, and
        // quick_command_args (which carries sort/search/etc.). Those state
        // changes legitimately alter row identity, so we cannot do in-place
        // cell updates safely — getRowId=String(index) would match the wrong
        // record. The naive correct behavior is to remount the grid on those
        // changes too. This means the visible flash returns for those specific
        // operations; UI-only state changes (show_commands, theme, etc.)
        // still get the in-place update path.
        dataframe_id?: string;
    }) {
    bkLog("BuckarooInfiniteWidget render", {
        df_display: buckaroo_state.df_display,
        post_processing: buckaroo_state.post_processing,
        cleaning_method: buckaroo_state.cleaning_method,
        quick_command_args: buckaroo_state.quick_command_args,
        dataframe_id,
        opsLen: operations.length,
    });
        // we only want to create KeyAwareSmartRowCache once, it caches sourceName too
        // so having it live between relaods is key
        //const [respError, setRespError] = useState<string | undefined>(undefined);

    const mainDs = useMemo(() => {
            // getDs(src) returns a closure that pulls rows from `src` (the
            // KeyAwareSmartRowCache). State changes (operations,
            // post_processing, cleaning_method, quick_command_args) flow into
            // requests via `outside_df_params` context at getRows time — they
            // are NOT captured by this closure. So mainDs is structurally
            // invariant under those state changes; refresh is driven by
            // effectiveDataframeId (remount) and outsideDFSig (purge).
            bkLog("mainDs useMemo recomputed");
            return getDs(src);
        }, [src]);
      const [activeCol, setActiveCol] = useState<[string, string]>(["a", "stoptime"]);

        // Reset activeCol on dataframe_id change. The DFViewerInfinite key below
        // remounts the grid; this handles the bit of state that lives above it.
        const prevDfIdRef = useRef(dataframe_id);
        useEffect(() => {
            if (prevDfIdRef.current !== dataframe_id) {
                prevDfIdRef.current = dataframe_id;
                setActiveCol(["a", "stoptime"]);
            }
        }, [dataframe_id]);

        const cDisp = df_display_args[buckaroo_state.df_display];

        const [data_wrapper, summaryStatsData] = useMemo(
            () => [
                getDataWrapper(cDisp.data_key, df_data_dict, mainDs, df_meta.total_rows),
                df_data_dict[cDisp.summary_stats_key],
            ],
            [cDisp, df_data_dict, mainDs, df_meta.total_rows],
        );

        //used to denote "this dataframe has been transformed", This is
        //evantually spliced back into the request args from scrolling/
        //the data source. dataframe_id participates so the SmartRowCache
        //sourceName picks up an explicit "different dataframe" event.
        const outsideDFParams = useMemo(
            () => {
                bkLog("outsideDFParams useMemo recomputed", {
                    quick_command_args: buckaroo_state.quick_command_args,
                    df_display: buckaroo_state.df_display,
                });
                return [operations, buckaroo_state.post_processing, buckaroo_state.cleaning_method, buckaroo_state.quick_command_args, buckaroo_state.df_display, dataframe_id];
            },
            [operations, buckaroo_state.post_processing, buckaroo_state.cleaning_method, buckaroo_state.quick_command_args, buckaroo_state.df_display, dataframe_id],
        );

        // Effective remount key. Bundles dataframe_id with the
        // row-content-changing state fields so any of them triggers a full
        // grid remount. See the dataframe_id prop docs above for rationale —
        // in-place updates aren't safe when row identity isn't stable.
        //
        // quick_command_args is deliberately excluded: every command routed
        // through it today is filter-like (Search, OnlyOutliers) — row
        // identity prefixes stay stable across the filter, only ordering and
        // membership change. The purge effect from #729 (fires when
        // outside_df_params changes) + namespaced getRowId from #739 give
        // correct cell-update-in-place semantics for that case. The remaining
        // bundled fields (operations, post_processing, cleaning_method) still
        // auto-bump pending follow-up work to let the Python side declare
        // per-command dataframe_id bumping (default bump, opt-out per command).
        const effectiveDataframeIdPrev = useRef<string | null>(null);
        const effectiveDataframeId = useMemo(
            () => {
                const v = JSON.stringify([
                    dataframe_id,
                    operations,
                    buckaroo_state.post_processing,
                    buckaroo_state.cleaning_method,
                ]);
                const prev = effectiveDataframeIdPrev.current;
                effectiveDataframeIdPrev.current = v;
                if (prev === null) {
                    bkLog("effectiveDataframeId computed (initial)", { value: v });
                } else if (prev !== v) {
                    // Real change — DFViewerInfinite remounts. If this fires
                    // on a search keystroke the PR #743 fix regressed:
                    // quick_command_args is intentionally NOT in deps.
                    bkLog("effectiveDataframeId CHANGED (REMOUNT)", { from: prev, to: v });
                }
                return v;
            },
            [dataframe_id, operations, buckaroo_state.post_processing, buckaroo_state.cleaning_method],
        );
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
                        themeConfig={cDisp.df_viewer_config?.component_config?.theme}
                    />
                    <DFViewerInfinite
                        key={effectiveDataframeId}
                        data_wrapper={data_wrapper}
                        df_viewer_config={cDisp.df_viewer_config}
                        summary_stats_data={summaryStatsData}
                        outside_df_params={outsideDFParams}
                        activeCol={activeCol}
                        setActiveCol={setActiveCol}
                        error_info={""}
                        view_name={buckaroo_state.df_display}
                        data_key={cDisp.data_key}
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
        df_data_dict: Record<string, DFData>;
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


        const mainDs = useMemo(() => getDs(src), [src]);
      const [activeCol, setActiveCol] = useState<[string, string]>(["a", "stoptime"]);

        const cDisp = df_display_args["main"];

        const [data_wrapper, summaryStatsData] = useMemo(
            () => [
                getDataWrapper(cDisp.data_key, df_data_dict, mainDs, df_meta.total_rows),
                df_data_dict[cDisp.summary_stats_key],
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
