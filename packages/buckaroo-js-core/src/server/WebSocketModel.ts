/**
 * WebSocketModel — drop-in replacement for anywidget's model interface.
 *
 * Implements the subset of the model API that getKeySmartRowCache() and
 * useModelState() depend on:
 *   - model.send(msg)           → sends JSON over WebSocket
 *   - model.on(event, handler)  → listens for events
 *   - model.off(event, handler) → removes listener
 *   - model.get(key)            → reads initial state
 *   - model.set(key, value)     → updates local state
 *   - model.save_changes()      → no-op (server doesn't need trait sync)
 *
 * Binary protocol (matching anywidget's msg + buffers pattern):
 *   Server sends a JSON text frame (infinite_resp), then a binary frame (Parquet).
 *   This class pairs them and emits "msg:custom" with (msg, [DataView]).
 */
import { isEqual, pick } from "lodash-es";

// Fields of buckaroo_state that make the server rerun the dataflow and
// broadcast a fresh initial_state. Mirrors _DATAFLOW_FIELDS in
// buckaroo/server/websocket_handler.py.
const DATAFLOW_FIELDS = ["post_processing", "cleaning_method", "quick_command_args"];

const dataflowFields = (bstate: unknown): Record<string, unknown> =>
    pick((bstate ?? {}) as Record<string, unknown>, DATAFLOW_FIELDS);

// Same opt-in gate as the [bk-flash …] timeline in BuckarooWidgetInfinite
// and DFViewerInfinite — flip `globalThis.__BK_FLASH__ = true` in DevTools.
const bkTs = (): string => {
    const d = new Date();
    const p2 = (n: number) => String(n).padStart(2, "0");
    const p3 = (n: number) => String(n).padStart(3, "0");
    return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}.${p3(d.getMilliseconds())}`;
};
const bkFlashOn = (): boolean =>
    typeof globalThis !== "undefined" && (globalThis as { __BK_FLASH__?: boolean }).__BK_FLASH__ === true;
const bkLog = (event: string, extra?: Record<string, unknown>): void => {
    if (!bkFlashOn()) return;
    // eslint-disable-next-line no-console
    console.log(`[bk-flash ${bkTs()}] ${event}`, extra ?? "");
};

export class WebSocketModel {
    private ws: WebSocket;
    private pendingMsg: any = null;
    private handlers: Map<string, Set<Function>> = new Map();
    private state: Record<string, any>;
    private pendingChanges: Set<string> = new Set();
    // Dataflow fields the server is expected to settle on: those of the last
    // buckaroo_state_change sent, or of the last initial_state applied.
    // While changeOutstanding, an initial_state whose dataflow fields differ
    // is a reply to an older change (or an overlay built from the pre-change
    // state) and would revert buckaroo_state, so it is dropped (#998).
    private expectedDataflow: Record<string, unknown>;
    private changeOutstanding: boolean = false;

    constructor(ws: WebSocket, initialState: Record<string, any>) {
        this.state = { ...initialState };
        this.ws = ws;
        this.expectedDataflow = dataflowFields(initialState.buckaroo_state);

        this.ws.onmessage = (event: MessageEvent) => {
            if (typeof event.data === "string") {
                const msg = JSON.parse(event.data);

                if (msg.type === "infinite_resp") {
                    // Expect a following binary frame — stash this JSON
                    this.pendingMsg = msg;
                } else if (msg.type === "metadata") {
                    // Server push — new file loaded. Update state and notify.
                    this.state._metadata = msg;
                    this.emit("metadata", msg);
                } else if (msg.type === "error") {
                    // No initial_state follows a failed state change.
                    if (msg.error_code === "state_change_error") {
                        this.changeOutstanding = false;
                    }
                } else if (msg.type === "initial_state") {
                    if (!this.shouldApplyInitialState(msg)) {
                        bkLog("initial_state dropped — stale reply while a buckaroo_state_change is outstanding", {
                            got: dataflowFields(msg.buckaroo_state),
                            expected: this.expectedDataflow,
                        });
                        return;
                    }
                    if (msg.buckaroo_state !== undefined) {
                        this.expectedDataflow = dataflowFields(msg.buckaroo_state);
                    }
                    this.changeOutstanding = false;
                    // Bulk state update from server
                    for (const [k, v] of Object.entries(msg)) {
                        if (k === "type") continue;
                        this.state[k] = v;
                        this.emit(`change:${k}`, v);
                    }
                    // Also emit "metadata" so components update filename/title/prompt
                    if (msg.metadata) {
                        this.emit("metadata", msg.metadata, msg.prompt);
                    }
                }
            } else {
                // Binary frame — pair with pending JSON message
                if (this.pendingMsg) {
                    const buffer = event.data instanceof ArrayBuffer
                        ? event.data
                        : (event.data as any).buffer ?? event.data;
                    const buffers = [new DataView(buffer)];
                    this.emit("msg:custom", this.pendingMsg, buffers);
                    this.pendingMsg = null;
                }
            }
        };
    }

    send(msg: any): void {
        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    get(key: string): any {
        return this.state[key];
    }

    set(key: string, value: any): void {
        this.state[key] = value;
        this.pendingChanges.add(key);
        this.emit(`change:${key}`, value);
    }

    save_changes(): void {
        if (this.ws.readyState !== WebSocket.OPEN) return;
        // Sync buckaroo_state changes back to the server
        if (this.pendingChanges.has("buckaroo_state")) {
            const newState = this.state["buckaroo_state"];
            // Only a dataflow change gets a reply, so only one is outstanding
            // (search_string, df_display, etc. would never be cleared).
            const dataflow = dataflowFields(newState);
            if (!isEqual(dataflow, this.expectedDataflow)) {
                this.expectedDataflow = dataflow;
                this.changeOutstanding = true;
            }
            this.ws.send(JSON.stringify({
                type: "buckaroo_state_change",
                new_state: newState,
            }));
        }
        this.pendingChanges.clear();
    }

    // A reply to the outstanding change carries its dataflow fields. A
    // message without buckaroo_state (viewer/lazy mode) or with different
    // metadata (a new dataset, so the outstanding change is moot) is not
    // a stale reply and is applied as before.
    private shouldApplyInitialState(msg: Record<string, any>): boolean {
        if (!this.changeOutstanding || msg.buckaroo_state === undefined) {
            return true;
        }
        if (!isEqual(msg.metadata, this.state.metadata)) {
            return true;
        }
        return isEqual(dataflowFields(msg.buckaroo_state), this.expectedDataflow);
    }

    on(event: string, handler: Function): void {
        if (!this.handlers.has(event)) {
            this.handlers.set(event, new Set());
        }
        this.handlers.get(event)!.add(handler);
    }

    off(event: string, handler: Function): void {
        this.handlers.get(event)?.delete(handler);
    }

    private emit(event: string, ...args: any[]): void {
        const handlers = this.handlers.get(event);
        if (!handlers) return;
        // Array.from to satisfy ES5 target without --downlevelIteration.
        // Also gives us a stable snapshot if a handler unsubscribes during emit.
        for (const h of Array.from(handlers)) {
            try {
                h(...args);
            } catch (e) {
                console.error(`[WebSocketModel] Error in handler for ${event}:`, e);
            }
        }
    }
}
