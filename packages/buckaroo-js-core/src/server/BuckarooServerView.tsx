import * as React from "react";

import { BuckarooInfiniteWidget, DFViewerInfiniteDS, getKeySmartRowCache } from "../components/BuckarooWidgetInfinite";
import { preResolveDFDataDict } from "../components/DFViewerParts/resolveDFData";
import { WebSocketModel } from "./WebSocketModel";

/**
 * BuckarooServerView — embed a Buckaroo server session inside a React tree.
 *
 * This is the npm-module alternative to iframing `/s/<session-id>` from the
 * Buckaroo server. The component opens a WebSocket to the server, waits for
 * the `initial_state` message, builds the same model + row cache the
 * standalone bundle uses, and renders the appropriate widget based on the
 * server-reported `mode`.
 *
 *   import { BuckarooServerView } from "buckaroo-js-core";
 *   import "buckaroo-js-core/style.css";
 *
 *   <BuckarooServerView wsUrl="ws://localhost:8700/ws/my-session" />
 *
 * The server's session decides the widget — pass `mode="viewer"` to
 * /load for DFViewerInfiniteDS, `mode="buckaroo"` for the full UI. The host
 * app does no widget-class selection; it only cares about which session to
 * connect to.
 */

export type BuckarooServerMode = "viewer" | "buckaroo";

export interface BuckarooServerMetadata {
    path?: string;
    rows?: number;
    [k: string]: unknown;
}

export interface BuckarooServerViewProps {
    /** Full WebSocket URL (ws:// or wss://). For a server at host H serving
     *  session S, this is `ws://H/ws/S`. Use {@link buckarooWsUrl} if you
     *  have an HTTP server URL + session id and want it derived. */
    wsUrl: string;

    /** Optional renderer for the "connecting" / pre-initial_state state.
     *  Defaults to a plain "Connecting..." text. */
    renderConnecting?: () => React.ReactNode;

    /** Optional renderer for the error state. Receives the Error. Defaults
     *  to a plain error message. */
    renderError?: (err: Error) => React.ReactNode;

    /** Called once the server sends its first `metadata` payload (typically
     *  contains `path` and `rows`). Useful for host apps that want to mirror
     *  the filename into their own title bar. */
    onMetadata?: (metadata: BuckarooServerMetadata, prompt?: string) => void;

    /** Optional inline style applied to the wrapping div. The component
     *  defaults to `width:100%, height:100%`, so most consumers can rely on
     *  the parent's flex / grid sizing. */
    style?: React.CSSProperties;

    /** Optional className on the wrapping div. */
    className?: string;
}

interface ReadyState {
    model: WebSocketModel;
    src: ReturnType<typeof getKeySmartRowCache>;
    mode: BuckarooServerMode;
    initialState: Record<string, any>;
}

/** Derive a Buckaroo server WebSocket URL from an HTTP server URL + session
 *  id. Accepts `http://...`, `https://...`, or already-`ws[s]://` URLs. */
export function buckarooWsUrl(serverUrl: string, sessionId: string): string {
    const u = new URL(serverUrl);
    const protocol = u.protocol === "https:" || u.protocol === "wss:" ? "wss:" : "ws:";
    return `${protocol}//${u.host}/ws/${encodeURIComponent(sessionId)}`;
}

export function BuckarooServerView({
    wsUrl,
    renderConnecting,
    renderError,
    onMetadata,
    style,
    className,
}: BuckarooServerViewProps): React.ReactElement {
    const [ready, setReady] = React.useState<ReadyState | null>(null);
    const [error, setError] = React.useState<Error | null>(null);

    // Re-fired state values so React re-renders when the model emits change events.
    const [dfMeta, setDfMeta] = React.useState<any>({ total_rows: 0 });
    const [dfDataDict, setDfDataDict] = React.useState<Record<string, any>>({});
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState<Record<string, any>>({});
    const [buckarooState, setBuckarooStateLocal] = React.useState<any>({});
    const [buckarooOptions, setBuckarooOptions] = React.useState<any>({});
    const [commandConfig, setCommandConfig] = React.useState<any>({});
    const [operationResults, setOperationResults] = React.useState<any>({});
    const [operations, setOperations] = React.useState<any[]>([]);

    // Keep the latest onMetadata in a ref so we don't reconnect when the
    // host passes a fresh callback identity each render.
    const onMetadataRef = React.useRef(onMetadata);
    React.useEffect(() => { onMetadataRef.current = onMetadata; }, [onMetadata]);

    React.useEffect(() => {
        let cancelled = false;
        let ws: WebSocket | null = null;

        (async () => {
            try {
                ws = new WebSocket(wsUrl);
                ws.binaryType = "arraybuffer";

                await new Promise<void>((resolve, reject) => {
                    ws!.onopen = () => resolve();
                    ws!.onerror = (e) => reject(new Error(`WebSocket failed to open at ${wsUrl}: ${(e as any)?.message ?? "unknown"}`));
                });

                const initialState = await new Promise<Record<string, any>>((resolve, reject) => {
                    const onClose = () => reject(new Error("WebSocket closed before initial_state was received"));
                    const handler = (event: MessageEvent) => {
                        if (typeof event.data !== "string") return;
                        try {
                            const msg = JSON.parse(event.data);
                            if (msg.type === "initial_state") {
                                ws!.removeEventListener("message", handler);
                                ws!.removeEventListener("close", onClose);
                                resolve(msg);
                            }
                        } catch {
                            // ignore parse errors here; WebSocketModel handles binary frames separately
                        }
                    };
                    ws!.addEventListener("message", handler);
                    ws!.addEventListener("close", onClose);
                });

                if (cancelled) return;

                if (initialState.df_data_dict) {
                    initialState.df_data_dict = await preResolveDFDataDict(initialState.df_data_dict);
                }

                const model = new WebSocketModel(ws, initialState);
                const src = getKeySmartRowCache(model, (a: any, b: any) => console.error("[BuckarooServerView] cache error:", a, b));
                const mode: BuckarooServerMode = (initialState.mode === "buckaroo" ? "buckaroo" : "viewer");

                setDfMeta(initialState.df_meta || { total_rows: 0 });
                setDfDataDict(initialState.df_data_dict || {});
                setDfDisplayArgs(initialState.df_display_args || {});
                setBuckarooStateLocal(initialState.buckaroo_state || {});
                setBuckarooOptions(initialState.buckaroo_options || {});
                setCommandConfig(initialState.command_config || {});
                setOperationResults(initialState.operation_results || {});
                setOperations(initialState.operations || []);

                if (initialState.metadata) onMetadataRef.current?.(initialState.metadata, initialState.prompt);

                setReady({ model, src, mode, initialState });
            } catch (e) {
                if (cancelled) return;
                setError(e instanceof Error ? e : new Error(String(e)));
                try { ws?.close(); } catch {}
            }
        })();

        return () => {
            cancelled = true;
            try { ws?.close(); } catch {}
        };
    }, [wsUrl]);

    // Wire model change-events → React state once ready.
    React.useEffect(() => {
        if (!ready) return;
        const { model } = ready;

        const onMeta = (metadata: any, prompt?: string) => {
            onMetadataRef.current?.(metadata, prompt);
            setDfMeta(model.get("df_meta") || { total_rows: metadata?.rows || 0 });
            preResolveDFDataDict(model.get("df_data_dict") || {}).then(setDfDataDict);
            setDfDisplayArgs(model.get("df_display_args") || {});
            setBuckarooStateLocal(model.get("buckaroo_state") || {});
            setBuckarooOptions(model.get("buckaroo_options") || {});
            setCommandConfig(model.get("command_config") || {});
            setOperationResults(model.get("operation_results") || {});
            setOperations(model.get("operations") || []);
        };
        const onDfMeta = (v: any) => setDfMeta(v);
        const onDfDataDict = (v: any) => { preResolveDFDataDict(v).then(setDfDataDict); };
        const onDfDisplayArgs = (v: any) => setDfDisplayArgs(v);
        const onBState = (v: any) => setBuckarooStateLocal(v);
        const onBOpts = (v: any) => setBuckarooOptions(v);
        const onCmdCfg = (v: any) => setCommandConfig(v);
        const onOpRes = (v: any) => setOperationResults(v);
        const onOps = (v: any) => setOperations(v);

        model.on("metadata", onMeta);
        model.on("change:df_meta", onDfMeta);
        model.on("change:df_data_dict", onDfDataDict);
        model.on("change:df_display_args", onDfDisplayArgs);
        model.on("change:buckaroo_state", onBState);
        model.on("change:buckaroo_options", onBOpts);
        model.on("change:command_config", onCmdCfg);
        model.on("change:operation_results", onOpRes);
        model.on("change:operations", onOps);

        return () => {
            model.off("metadata", onMeta);
            model.off("change:df_meta", onDfMeta);
            model.off("change:df_data_dict", onDfDataDict);
            model.off("change:df_display_args", onDfDisplayArgs);
            model.off("change:buckaroo_state", onBState);
            model.off("change:buckaroo_options", onBOpts);
            model.off("change:command_config", onCmdCfg);
            model.off("change:operation_results", onOpRes);
            model.off("change:operations", onOps);
        };
    }, [ready]);

    const onBuckarooState = React.useCallback((newState: any) => {
        if (!ready) return;
        const resolved = typeof newState === "function" ? newState(buckarooState) : newState;
        ready.model.set("buckaroo_state", resolved);
        ready.model.save_changes();
    }, [ready, buckarooState]);

    const onOperations = React.useCallback((newOps: any) => {
        if (!ready) return;
        ready.model.set("operations", newOps);
        ready.model.save_changes();
    }, [ready]);

    const wrapperStyle: React.CSSProperties = { width: "100%", height: "100%", ...(style ?? {}) };

    if (error) {
        return (
            <div className={className} style={wrapperStyle}>
                {renderError ? renderError(error) : <div style={{ padding: 20, fontFamily: "sans-serif", color: "#b00020" }}>Failed to connect: {error.message}</div>}
            </div>
        );
    }
    if (!ready || !dfDisplayArgs?.main) {
        return (
            <div className={className} style={wrapperStyle}>
                {renderConnecting ? renderConnecting() : <div style={{ padding: 20, fontFamily: "sans-serif" }}>Connecting…</div>}
            </div>
        );
    }

    return (
        <div className={["buckaroo_anywidget", className].filter(Boolean).join(" ")} style={wrapperStyle}>
            {ready.mode === "buckaroo" ? (
                <BuckarooInfiniteWidget
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
                    src={ready.src}
                />
            ) : (
                <DFViewerInfiniteDS
                    df_meta={dfMeta}
                    df_data_dict={dfDataDict}
                    df_display_args={dfDisplayArgs}
                    src={ready.src}
                    df_id={"server"}
                />
            )}
        </div>
    );
}
