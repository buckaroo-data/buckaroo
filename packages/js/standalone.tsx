import * as React from "react";
import * as ReactDOM from "react-dom/client";
import srt from "buckaroo-js-core";
import { WebSocketModel } from "./WebSocketModel";
import "./widget.css";
import "../buckaroo-js-core/dist/style.css";

/**
 * Standalone entry point for the Buckaroo browser-tab viewer.
 *
 * 1. Reads session ID from URL path: /s/<session-id>
 * 2. Connects WebSocket to ws://<host>/ws/<session-id>
 * 3. Waits for initial_state message from server
 * 4. Creates a WebSocketModel (drop-in for anywidget model)
 * 5. Renders BuckarooInfiniteWidget (buckaroo mode) or DFViewerInfiniteDS (viewer mode)
 */

function getSessionId(): string {
    const match = window.location.pathname.match(/\/s\/([^/]+)/);
    if (!match) {
        throw new Error("No session ID found in URL. Expected /s/<session-id>");
    }
    return match[1];
}

function getWsUrl(sessionId: string): string {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/${sessionId}`;
}

function ViewerApp({ model, src }: { model: WebSocketModel; src: any }) {
    const [dfMeta, setDfMeta] = React.useState(model.get("df_meta") || { total_rows: 0 });
    const [dfDataDict, setDfDataDict] = React.useState(model.get("df_data_dict") || {});
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState(model.get("df_display_args") || {});

    React.useEffect(() => {
        const onMeta = (msg: any) => {
            setDfMeta(model.get("df_meta") || { total_rows: msg.rows || 0 });
            srt.preResolveDFDataDict(model.get("df_data_dict") || {}).then(setDfDataDict);
            setDfDisplayArgs(model.get("df_display_args") || {});
        };
        model.on("metadata", onMeta);

        const onDfMeta = (v: any) => setDfMeta(v);
        const onDfDataDict = (v: any) => {
            srt.preResolveDFDataDict(v).then(setDfDataDict);
        };
        const onDfDisplayArgs = (v: any) => setDfDisplayArgs(v);
        model.on("change:df_meta", onDfMeta);
        model.on("change:df_data_dict", onDfDataDict);
        model.on("change:df_display_args", onDfDisplayArgs);

        return () => {
            model.off("metadata", onMeta);
            model.off("change:df_meta", onDfMeta);
            model.off("change:df_data_dict", onDfDataDict);
            model.off("change:df_display_args", onDfDisplayArgs);
        };
    }, [model]);

    if (!dfDisplayArgs || !dfDisplayArgs["main"]) {
        return <div style={{ padding: 20, fontFamily: "sans-serif" }}>
            Waiting for data...
        </div>;
    }

    return (
        <div className="buckaroo_anywidget" style={{ width: "100%", height: "100vh" }}>
            <srt.DFViewerInfiniteDS
                df_meta={dfMeta}
                df_data_dict={dfDataDict}
                df_display_args={dfDisplayArgs}
                src={src}
                df_id={"standalone"}
            />
        </div>
    );
}

function BuckarooApp({ model, src }: { model: WebSocketModel; src: any }) {
    const [dfMeta, setDfMeta] = React.useState(model.get("df_meta") || { total_rows: 0 });
    const [dfDataDict, setDfDataDict] = React.useState(model.get("df_data_dict") || {});
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState(model.get("df_display_args") || {});
    const [buckarooState, setBuckarooState] = React.useState(model.get("buckaroo_state") || {});
    const [buckarooOptions, setBuckarooOptions] = React.useState(model.get("buckaroo_options") || {});
    const [commandConfig, setCommandConfig] = React.useState(model.get("command_config") || {});
    const [operationResults, setOperationResults] = React.useState(model.get("operation_results") || {});
    const [operations, setOperations] = React.useState(model.get("operations") || []);

    React.useEffect(() => {
        const onMeta = () => {
            setDfMeta(model.get("df_meta") || { total_rows: 0 });
            srt.preResolveDFDataDict(model.get("df_data_dict") || {}).then(setDfDataDict);
            setDfDisplayArgs(model.get("df_display_args") || {});
            setBuckarooState(model.get("buckaroo_state") || {});
            setBuckarooOptions(model.get("buckaroo_options") || {});
            setCommandConfig(model.get("command_config") || {});
            setOperationResults(model.get("operation_results") || {});
            setOperations(model.get("operations") || []);
        };
        model.on("metadata", onMeta);

        const onChange = (key: string, setter: (v: any) => void) => {
            const handler = (v: any) => setter(v);
            model.on(`change:${key}`, handler);
            return handler;
        };

        // df_data_dict needs async pre-resolution of parquet_b64 values
        const onDfDataDict = (v: any) => {
            srt.preResolveDFDataDict(v).then(setDfDataDict);
        };
        model.on("change:df_data_dict", onDfDataDict);

        const handlers: [string, Function][] = [
            ["df_meta", onChange("df_meta", setDfMeta)],
            ["df_display_args", onChange("df_display_args", setDfDisplayArgs)],
            ["buckaroo_state", onChange("buckaroo_state", setBuckarooState)],
            ["buckaroo_options", onChange("buckaroo_options", setBuckarooOptions)],
            ["command_config", onChange("command_config", setCommandConfig)],
            ["operation_results", onChange("operation_results", setOperationResults)],
            ["operations", onChange("operations", setOperations)],
        ];

        return () => {
            model.off("metadata", onMeta);
            model.off("change:df_data_dict", onDfDataDict);
            for (const [key, handler] of handlers) {
                model.off(`change:${key}`, handler);
            }
        };
    }, [model]);

    const onBuckarooState = React.useCallback((newState: any) => {
        // newState may be a value or a setter function
        const resolved = typeof newState === "function" ? newState(buckarooState) : newState;
        model.set("buckaroo_state", resolved);
        model.save_changes();
    }, [model, buckarooState]);

    const onOperations = React.useCallback((newOps: any) => {
        model.set("operations", newOps);
        model.save_changes();
    }, [model]);

    if (!dfDisplayArgs || !dfDisplayArgs["main"]) {
        return <div style={{ padding: 20, fontFamily: "sans-serif" }}>
            Waiting for data...
        </div>;
    }

    return (
        <div className="buckaroo_anywidget" style={{ width: "100%", height: "100vh" }}>
            <srt.BuckarooInfiniteWidget
                df_meta={dfMeta}
                df_data_dict={dfDataDict}
                df_display_args={dfDisplayArgs}
                operations={operations}
                on_operations={onOperations}
                operation_results={operationResults}
                command_config={commandConfig}
                buckaroo_state={buckarooState}
                on_buckaroo_state={onBuckarooState}
                buckaroo_options={buckarooOptions}
                src={src}
            />
        </div>
    );
}

async function main() {
    const sessionId = getSessionId();
    const wsUrl = getWsUrl(sessionId);

    const rootEl = document.getElementById("root");
    if (!rootEl) throw new Error("No #root element found");

    // Show connecting state
    rootEl.textContent = "Connecting...";

    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    // Wait for connection
    await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = (e) => reject(e);
    });

    // Wait for initial_state message
    const initialState = await new Promise<Record<string, any>>((resolve) => {
        const handler = (event: MessageEvent) => {
            if (typeof event.data === "string") {
                const msg = JSON.parse(event.data);
                if (msg.type === "initial_state") {
                    ws.removeEventListener("message", handler);
                    resolve(msg);
                }
            }
        };
        ws.addEventListener("message", handler);

        // If no data is loaded yet, render with empty state after a short timeout
        setTimeout(() => {
            ws.removeEventListener("message", handler);
            resolve({});
        }, 500);
    });

    // Pre-resolve parquet_b64 values in df_data_dict before creating the model.
    // hyparquet's parquetRead is async in esbuild bundles, so synchronous
    // resolveDFData() in React useMemo can't decode them. Pre-resolving here
    // ensures components receive plain DFData arrays.
    if (initialState.df_data_dict) {
        initialState.df_data_dict = await srt.preResolveDFDataDict(initialState.df_data_dict);
    }

    const model = new WebSocketModel(ws, initialState);

    // Create SmartRowCache — same function as Jupyter, just different model impl
    const setRespError = (a: any, b: any) => { console.log("setRespError", a, b); };
    const src = srt.getKeySmartRowCache(model, setRespError);

    const mode = initialState.mode || "viewer";

    // Render
    const root = ReactDOM.createRoot(rootEl);
    if (mode === "buckaroo") {
        root.render(<BuckarooApp model={model} src={src} />);
    } else {
        root.render(<ViewerApp model={model} src={src} />);
    }
}

main().catch((e) => {
    console.error("Buckaroo standalone init failed:", e);
    const rootEl = document.getElementById("root");
    if (rootEl) {
        rootEl.textContent = `Failed to connect: ${e.message}`;
    }
});
