import { BuckarooServerMetadata, BuckarooServerMode } from './BuckarooView';
import * as React from "react";
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
     *  fixed embed height looks wrong for both small and large dataframes. */
    autoHeight?: boolean;
}
/** Derive a Buckaroo server WebSocket URL from an HTTP server URL + session
 *  id. Accepts `http://...`, `https://...`, or already-`ws[s]://` URLs. */
export declare function buckarooWsUrl(serverUrl: string, sessionId: string): string;
export declare function BuckarooServerView({ wsUrl, renderConnecting, renderError, onMetadata, style, className, autoHeight, }: BuckarooServerViewProps): React.ReactElement;
