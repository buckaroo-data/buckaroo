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
 * 5. Renders DFViewerInfiniteDS with SmartRowCache
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

function App({ model, src }: { model: WebSocketModel; src: any }) {
    const [dfMeta, setDfMeta] = React.useState(model.get("df_meta") || { total_rows: 0 });
    const [dfDataDict, setDfDataDict] = React.useState(model.get("df_data_dict") || {});
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState(model.get("df_display_args") || {});

    React.useEffect(() => {
        const onMeta = (msg: any) => {
            // Server pushed new file — re-read state
            setDfMeta(model.get("df_meta") || { total_rows: msg.rows || 0 });
            setDfDataDict(model.get("df_data_dict") || {});
            setDfDisplayArgs(model.get("df_display_args") || {});
        };
        model.on("metadata", onMeta);

        // Also listen for individual state changes
        const onDfMeta = (v: any) => setDfMeta(v);
        const onDfDataDict = (v: any) => setDfDataDict(v);
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

    // Don't render until we have display args
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

    const model = new WebSocketModel(ws, initialState);

    // Create SmartRowCache — same function as Jupyter, just different model impl
    const setRespError = (a: any, b: any) => { console.log("setRespError", a, b); };
    const src = srt.getKeySmartRowCache(model, setRespError);

    // Render
    const root = ReactDOM.createRoot(rootEl);
    root.render(<App model={model} src={src} />);
}

main().catch((e) => {
    console.error("Buckaroo standalone init failed:", e);
    const rootEl = document.getElementById("root");
    if (rootEl) {
        rootEl.textContent = `Failed to connect: ${e.message}`;
    }
});
