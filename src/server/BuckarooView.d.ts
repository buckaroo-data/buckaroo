import { IModel } from './IModel';
import * as React from "react";
export type BuckarooServerMode = "viewer" | "buckaroo";
export interface BuckarooServerMetadata {
    path?: string;
    rows?: number;
    [k: string]: unknown;
}
export interface BuckarooViewProps {
    /** An already-connected model implementing {@link IModel}. The caller is
     *  responsible for transport setup (WebSocket, Tauri IPC, etc.) and for
     *  having received `initial_state` from the backend before mounting. */
    model: IModel;
    /** The first `initial_state` payload the model produced. Used to seed
     *  React state without waiting for `change:*` events. If `df_data_dict`
     *  contains base64-encoded parquet payloads they will be resolved on
     *  mount; pre-resolved values pass through unchanged. */
    initialState: Record<string, unknown>;
    /** Which widget to render — `"viewer"` for `DFViewerInfiniteDS`,
     *  `"buckaroo"` for the full `BuckarooInfiniteWidget`. */
    mode: BuckarooServerMode;
    /** Called when the backend pushes a `metadata` event (e.g. a new file
     *  was loaded). Useful for host apps that mirror the filename into a
     *  title bar. */
    onMetadata?: (metadata: BuckarooServerMetadata, prompt?: string) => void;
    /** Optional inline style applied to the wrapping div. The component
     *  defaults to `width:100%, height:100%`. */
    style?: React.CSSProperties;
    /** Optional className on the wrapping div. */
    className?: string;
    /** When true, render with AG Grid's `domLayout: "autoHeight"`: the grid
     *  grows to fit its row count instead of filling the parent container.
     *  Use for stacked-cell hosts (notebook-style embeds) where a fixed
     *  embed height looks wrong for both small and large dataframes.
     *  Overrides any `component_config.layoutType` set by the server. */
    autoHeight?: boolean;
}
export declare function pickMode(rawMode: unknown): BuckarooServerMode;
/**
 * BuckarooView — transport-agnostic Buckaroo widget renderer.
 *
 * Takes an already-connected {@link IModel} plus the `initial_state` payload
 * it produced, and renders the appropriate widget. Use this when the caller
 * owns transport setup and wants to keep WebSockets out of the renderer
 * (e.g. Tauri/Electron hosts relaying through IPC). For the common case
 * where you just want a WebSocket connection from the React tree, use
 * {@link BuckarooServerView}, which is a thin wrapper around this component.
 */
export declare function BuckarooView({ model, initialState, mode, onMetadata, style, className, autoHeight, }: BuckarooViewProps): React.ReactElement;
