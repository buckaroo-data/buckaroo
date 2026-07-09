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

export class SelectionBus {
    private target = new EventTarget();
    private bc: BroadcastChannel | null = null;

    constructor(broadcastName = "buckaroo-selection") {
        if (typeof BroadcastChannel !== "undefined") {
            this.bc = new BroadcastChannel(broadcastName);
            this.bc.onmessage = (ev) => this.dispatchLocal(ev.data as SelectionMessage);
        }
    }

    publish(channel: string, ids: Iterable<SelectionId>, source: string): void {
        const msg: SelectionMessage = { channel, ids: Array.from(ids), source };
        this.dispatchLocal(msg);
        this.bc?.postMessage(msg);
    }

    subscribe(channel: string, fn: Listener, ownSource?: string): () => void {
        const handler = (ev: Event) => {
            const msg = (ev as CustomEvent<SelectionMessage>).detail;
            if (msg.channel !== channel) return;
            if (ownSource && msg.source === ownSource) return;
            fn(msg);
        };
        this.target.addEventListener("selection", handler);
        return () => this.target.removeEventListener("selection", handler);
    }

    private dispatchLocal(msg: SelectionMessage) {
        this.target.dispatchEvent(new CustomEvent("selection", { detail: msg }));
    }
}

declare global {
    interface Window {
        __buckarooSelectionBus?: SelectionBus;
    }
}

export function getSelectionBus(): SelectionBus {
    if (typeof window === "undefined") return new SelectionBus();
    if (!window.__buckarooSelectionBus) {
        window.__buckarooSelectionBus = new SelectionBus();
    }
    return window.__buckarooSelectionBus;
}
