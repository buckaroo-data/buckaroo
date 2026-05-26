/**
 * Frontend-only selection bus for linked brushing. Publishers (e.g. a Vega
 * brush, a row-click handler, a "select these ids" button) emit a set of
 * ids on a named channel; subscribers (DFViewer instances, charts) react.
 *
 * Same-page subscribers receive events via an internal EventTarget. When
 * `BroadcastChannel` is available, messages also cross iframe / tab
 * boundaries — useful inside JupyterLab where each widget output is its
 * own iframe.
 *
 * No Python round trip, no kernel comm. Messages dedupe by `source` so a
 * publisher does not receive its own echo.
 */
export type SelectionId = string | number;
export interface SelectionMessage {
    channel: string;
    ids: SelectionId[];
    source: string;
}
type Listener = (msg: SelectionMessage) => void;
export declare class SelectionBus {
    private target;
    private bc;
    constructor(broadcastName?: string);
    publish(channel: string, ids: Iterable<SelectionId>, source: string): void;
    subscribe(channel: string, fn: Listener, ownSource?: string): () => void;
    private dispatchLocal;
}
declare global {
    interface Window {
        __buckarooSelectionBus?: SelectionBus;
    }
}
export declare function getSelectionBus(): SelectionBus;
export {};
