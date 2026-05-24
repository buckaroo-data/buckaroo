import * as React from "react";

import { preResolveDFDataDict } from "../components/DFViewerParts/resolveDFData";
import { WebSocketModel } from "./WebSocketModel";
import {
    BuckarooView,
    BuckarooServerMetadata,
    BuckarooServerMode,
    pickMode,
} from "./BuckarooView";

// Re-export the shared types so existing `import { BuckarooServerMode } from
// ".../BuckarooServerView"` paths keep working.
export type { BuckarooServerMetadata, BuckarooServerMode };

/**
 * BuckarooServerView — embed a Buckaroo server session inside a React tree.
 *
 * This is the npm-module alternative to iframing `/s/<session-id>` from the
 * Buckaroo server. The component opens a WebSocket to the server, waits for
 * the `initial_state` message, builds the same model + row cache the
 * standalone bundle uses, and delegates rendering to {@link BuckarooView}.
 *
 *   import { BuckarooServerView } from "buckaroo-js-core";
 *   import "buckaroo-js-core/style.css";
 *
 *   <BuckarooServerView wsUrl="ws://localhost:8700/ws/my-session" />
 *
 * Hosts that need to keep WebSockets out of the renderer (Tauri, Electron,
 * Wails) should instead construct an {@link IModel} via their IPC adapter
 * and mount {@link BuckarooView} directly — see the docstring on that
 * component for the no-WebSocket path.
 */

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

    /** When true, render with AG Grid's `domLayout: "autoHeight"`: the grid
     *  grows to fit its row count instead of filling the parent container.
     *  Use for stacked-cell hosts (notebook-style embeds) where a single
     *  fixed embed height looks wrong for both small and large dataframes.
     *  Overrides any `component_config.layoutType` set by the server. */
    autoHeight?: boolean;
}

interface ReadyState {
    model: WebSocketModel;
    mode: BuckarooServerMode;
    initialState: Record<string, unknown>;
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
    autoHeight,
}: BuckarooServerViewProps): React.ReactElement {
    const [ready, setReady] = React.useState<ReadyState | null>(null);
    const [error, setError] = React.useState<Error | null>(null);

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
                const mode: BuckarooServerMode = pickMode(initialState.mode);

                setReady({ model, mode, initialState });
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

    const wrapperStyle: React.CSSProperties = { width: "100%", height: "100%", ...(style ?? {}) };

    if (error) {
        return (
            <div className={className} style={wrapperStyle}>
                {renderError ? renderError(error) : <div style={{ padding: 20, fontFamily: "sans-serif", color: "#b00020" }}>Failed to connect: {error.message}</div>}
            </div>
        );
    }
    if (!ready) {
        return (
            <div className={className} style={wrapperStyle}>
                {renderConnecting ? renderConnecting() : <div style={{ padding: 20, fontFamily: "sans-serif" }}>Connecting…</div>}
            </div>
        );
    }

    return (
        <BuckarooView
            model={ready.model}
            initialState={ready.initialState}
            mode={ready.mode}
            onMetadata={onMetadata}
            style={style}
            className={className}
            autoHeight={autoHeight}
        />
    );
}
