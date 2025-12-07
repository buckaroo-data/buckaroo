import { useMemo, useRef, useState } from "react";
import { DFData, DFViewerConfig } from "./DFViewerParts/DFWhole";
import { DFViewerInfinite } from "./DFViewerParts/DFViewerInfinite";
import { SetColumnFunc } from "./DFViewerParts/gridUtils";

export function MessageBox({
    messages,
}: {
    messages: Array<{
        time?: string;
        type?: string;
        message?: string;
        [key: string]: any;
    }>;
}) {
    // MessageBox rendering
    // Use a state-based key to force re-render when messages change
    const [updateKey, setUpdateKey] = useState(0);
    const prevMessageCountRef = useRef(0);
    
    // Convert messages to DFData format
    const messageData: DFData = useMemo(() => {
        if (!messages || messages.length === 0) {
            if (prevMessageCountRef.current !== 0) {
                prevMessageCountRef.current = 0;
                setUpdateKey(k => k + 1);
            }
            return [];
        }
        
        const data = messages.map((msg, idx) => {
            if (!msg || typeof msg !== 'object') {
                return {
                    index: idx,
                    time: "",
                    type: "",
                    message: String(msg || ""),
                };
            }
            return {
                index: idx,
                time: msg.time || "",
                type: msg.type || "",
                message: msg.message || "",
                ...Object.fromEntries(
                    Object.entries(msg).filter(([k]) => !["time", "type", "message"].includes(k))
                ),
            };
        });
        
        // Force update key change when message count changes
        if (messages.length !== prevMessageCountRef.current) {
            prevMessageCountRef.current = messages.length;
            setUpdateKey(k => k + 1);
        }
        
        return data;
    }, [messages]);

    // Create column config for message box
    const df_viewer_config: DFViewerConfig = useMemo(() => {
        if (!messages || messages.length === 0) {
            return {
                pinned_rows: [],
                column_config: [],
                left_col_configs: [
                    {
                        col_name: "index",
                        header_name: "index",
                        displayer_args: { displayer: "obj" },
                    },
                ],
            };
        }
        
        // Get all unique keys from messages to create columns dynamically
        const allKeys = new Set<string>();
        messages.forEach((msg) => {
            if (msg && typeof msg === 'object') {
                Object.keys(msg).forEach((k) => allKeys.add(k));
            }
        });
        
        // Always include index, time, type, message
        allKeys.add("index");
        allKeys.add("time");
        allKeys.add("type");
        allKeys.add("message");
        
        const column_config = Array.from(allKeys).map((key) => ({
            col_name: key,
            header_name: key,
            displayer_args: { displayer: "obj" as const },
        }));

        return {
            pinned_rows: [],
            column_config,
            left_col_configs: [
                {
                    col_name: "index",
                    header_name: "index",
                    displayer_args: { displayer: "obj" as const },
                },
            ],
        };
    }, [messages]);

    const defaultSetColumnFunc: SetColumnFunc = () => {};

    if (!messages || messages.length === 0) {
        return null;
    }

    return (
        <div
            style={{
                height: "300px",
                width: "100%",
                border: "1px solid red",
                marginTop: "10px",
                backgroundColor: "#1a1a1a",
            }}
        >
            <DFViewerInfinite
                key={`df-viewer-${updateKey}-${messageData.length}`}
                data_wrapper={{
                    data_type: "Raw",
                    data: messageData,
                    length: messageData.length,
                }}
                df_viewer_config={df_viewer_config}
                summary_stats_data={[]}
                activeCol={["", ""]}
                setActiveCol={defaultSetColumnFunc}
                error_info={""}
            />
        </div>
    );
}

