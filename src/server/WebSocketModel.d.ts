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
export declare class WebSocketModel {
    private ws;
    private pendingMsg;
    private handlers;
    private state;
    private pendingChanges;
    constructor(ws: WebSocket, initialState: Record<string, any>);
    send(msg: any): void;
    get(key: string): any;
    set(key: string, value: any): void;
    save_changes(): void;
    on(event: string, handler: Function): void;
    off(event: string, handler: Function): void;
    private emit;
}
