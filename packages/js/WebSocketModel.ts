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
export class WebSocketModel {
    private ws: WebSocket;
    private pendingMsg: any = null;
    private handlers: Map<string, Set<Function>> = new Map();
    private state: Record<string, any>;
    private pendingChanges: Set<string> = new Set();

    constructor(ws: WebSocket, initialState: Record<string, any>) {
        this.state = { ...initialState };
        this.ws = ws;

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
                } else if (msg.type === "initial_state") {
                    // Bulk state update from server
                    for (const [k, v] of Object.entries(msg)) {
                        if (k === "type") continue;
                        this.state[k] = v;
                        this.emit(`change:${k}`, v);
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
            this.ws.send(JSON.stringify({
                type: "buckaroo_state_change",
                new_state: this.state["buckaroo_state"],
            }));
        }
        this.pendingChanges.clear();
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
        if (handlers) {
            for (const h of handlers) {
                try {
                    h(...args);
                } catch (e) {
                    console.error(`[WebSocketModel] Error in handler for ${event}:`, e);
                }
            }
        }
    }
}
