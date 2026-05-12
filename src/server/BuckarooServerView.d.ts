import * as React from "react";
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
/** Derive a Buckaroo server WebSocket URL from an HTTP server URL + session
 *  id. Accepts `http://...`, `https://...`, or already-`ws[s]://` URLs. */
export declare function buckarooWsUrl(serverUrl: string, sessionId: string): string;
export declare function BuckarooServerView({ wsUrl, renderConnecting, renderError, onMetadata, style, className, }: BuckarooServerViewProps): React.ReactElement;
