import * as React from "react";

import { BuckarooInfiniteWidget, DFViewerInfiniteDS, getKeySmartRowCache } from "../components/BuckarooWidgetInfinite";
import { preResolveDFDataDict } from "../components/DFViewerParts/resolveDFData";
import { WebSocketModel } from "./WebSocketModel";
import { DFMeta, BuckarooState, BuckarooOptions } from "../components/WidgetTypes";
import { CommandConfigT } from "../components/CommandUtils";
import { Operation } from "../components/OperationUtils";
import { OperationResult, baseOperationResults } from "../components/DependentTabs";
import { DFData, DFDataOrPayload } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";

// Defaults are only visible to the widgets if the server sends partial
// initial_state (it should always send these keys, but useState wants a
// fully-typed initializer, and the render guard below means the widgets
// never actually see these values).
const DEFAULT_DF_META: DFMeta = { total_rows: 0, columns: 0, filtered_rows: 0, rows_shown: 0 };
const DEFAULT_BUCKAROO_STATE: BuckarooState = {
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
};
const DEFAULT_BUCKAROO_OPTIONS: BuckarooOptions = {
    sampled: [],
    cleaning_method: [],
    post_processing: [],
    df_display: [],
    show_commands: [],
};
const DEFAULT_COMMAND_CONFIG: CommandConfigT = { argspecs: {}, defaultArgs: {} };

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
    initialState: Record<string, unknown>;
}

function pickMode(rawMode: unknown): BuckarooServerMode {
    if (rawMode === "buckaroo" || rawMode === "viewer") return rawMode;
    if (rawMode !== undefined && rawMode !== null) {
        console.warn(`[BuckarooServerView] unknown mode ${JSON.stringify(rawMode)} — falling back to "viewer".`);
    }
    return "viewer";
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
    const [dfMeta, setDfMeta] = React.useState<DFMeta>(DEFAULT_DF_META);
    const [dfDataDict, setDfDataDict] = React.useState<Record<string, DFData>>({});
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState<Record<string, IDisplayArgs>>({});
    const [buckarooState, setBuckarooStateLocal] = React.useState<BuckarooState>(DEFAULT_BUCKAROO_STATE);
    const [buckarooOptions, setBuckarooOptions] = React.useState<BuckarooOptions>(DEFAULT_BUCKAROO_OPTIONS);
    const [commandConfig, setCommandConfig] = React.useState<CommandConfigT>(DEFAULT_COMMAND_CONFIG);
    const [operationResults, setOperationResults] = React.useState<OperationResult>(baseOperationResults);
    const [operations, setOperations] = React.useState<Operation[]>([]);

    // Keep the latest onMetadata in a ref so we don't reconnect when the
    // host passes a fresh callback identity each render.
    const onMetadataRef = React.useRef(onMetadata);
    React.useEffect(() => { onMetadataRef.current = onMetadata; }, [onMetadata]);

    React.useEffect(() => {
        let cancelled = false;
        let ws: WebSocket | null = null;

        // Clear stale state from any previous wsUrl. Without this, a host
        // that recovers from a failed connection by updating wsUrl would
        // keep seeing the old error banner because the render guard checks
        // `if (error)` before rendering `ready`.
        setError(null);
        setReady(null);

        (async () => {
            try {
                ws = new WebSocket(wsUrl);
                ws.binaryType = "arraybuffer";

                await new Promise<void>((resolve, reject) => {
                    ws!.onopen = () => resolve();
                    ws!.onerror = (e) => reject(new Error(`WebSocket failed to open at ${wsUrl}: ${(e as any)?.message ?? "unknown"}`));
                });

                const initialState = await new Promise<Record<string, any>>((resolve, reject) => {
                    const onClose = () => {
                        ws!.removeEventListener("message", handler);
                        reject(new Error("WebSocket closed before initial_state was received"));
                    };
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
                const src = getKeySmartRowCache(model, (a: unknown, b: unknown) => console.error("[BuckarooServerView] cache error:", a, b));
                const mode: BuckarooServerMode = pickMode(initialState.mode);

                setDfMeta((initialState.df_meta as DFMeta) ?? DEFAULT_DF_META);
                setDfDataDict((initialState.df_data_dict as Record<string, DFData>) ?? {});
                setDfDisplayArgs((initialState.df_display_args as Record<string, IDisplayArgs>) ?? {});
                setBuckarooStateLocal((initialState.buckaroo_state as BuckarooState) ?? DEFAULT_BUCKAROO_STATE);
                setBuckarooOptions((initialState.buckaroo_options as BuckarooOptions) ?? DEFAULT_BUCKAROO_OPTIONS);
                setCommandConfig((initialState.command_config as CommandConfigT) ?? DEFAULT_COMMAND_CONFIG);
                setOperationResults((initialState.operation_results as OperationResult) ?? baseOperationResults);
                setOperations((initialState.operations as Operation[]) ?? []);

                if (initialState.metadata) onMetadataRef.current?.(initialState.metadata as BuckarooServerMetadata, initialState.prompt as string | undefined);

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

        const onMeta = (metadata: BuckarooServerMetadata, prompt?: string) => {
            onMetadataRef.current?.(metadata, prompt);
            setDfMeta((model.get("df_meta") as DFMeta | undefined) ?? { ...DEFAULT_DF_META, total_rows: metadata?.rows ?? 0 });
            preResolveDFDataDict((model.get("df_data_dict") as Record<string, DFDataOrPayload> | undefined) ?? {})
                .then((d) => setDfDataDict(d as Record<string, DFData>));
            setDfDisplayArgs((model.get("df_display_args") as Record<string, IDisplayArgs> | undefined) ?? {});
            setBuckarooStateLocal((model.get("buckaroo_state") as BuckarooState | undefined) ?? DEFAULT_BUCKAROO_STATE);
            setBuckarooOptions((model.get("buckaroo_options") as BuckarooOptions | undefined) ?? DEFAULT_BUCKAROO_OPTIONS);
            setCommandConfig((model.get("command_config") as CommandConfigT | undefined) ?? DEFAULT_COMMAND_CONFIG);
            setOperationResults((model.get("operation_results") as OperationResult | undefined) ?? baseOperationResults);
            setOperations((model.get("operations") as Operation[] | undefined) ?? []);
        };
        const onDfMeta = (v: DFMeta) => setDfMeta(v);
        const onDfDataDict = (v: Record<string, DFDataOrPayload>) => {
            preResolveDFDataDict(v).then((d) => setDfDataDict(d as Record<string, DFData>));
        };
        const onDfDisplayArgs = (v: Record<string, IDisplayArgs>) => setDfDisplayArgs(v);
        const onBState = (v: BuckarooState) => setBuckarooStateLocal(v);
        const onBOpts = (v: BuckarooOptions) => setBuckarooOptions(v);
        const onCmdCfg = (v: CommandConfigT) => setCommandConfig(v);
        const onOpRes = (v: OperationResult) => setOperationResults(v);
        const onOps = (v: Operation[]) => setOperations(v);

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

    const onBuckarooState = React.useCallback<React.Dispatch<React.SetStateAction<BuckarooState>>>((newState) => {
        if (!ready) return;
        const resolved = typeof newState === "function"
            ? (newState as (prev: BuckarooState) => BuckarooState)(buckarooState)
            : newState;
        ready.model.set("buckaroo_state", resolved);
        ready.model.save_changes();
    }, [ready, buckarooState]);

    const onOperations = React.useCallback((newOps: Operation[]) => {
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
