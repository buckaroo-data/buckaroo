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
 *
 * State-change sequencing (#998):
 *   Each buckaroo_state_change carries an incrementing `state_seq`. The
 *   server echoes it as `reply_seq` on the initial_state it sends back to
 *   this client. A reply whose `reply_seq` is older than the latest
 *   `state_seq` sent answers a change that a later one has superseded, so
 *   it is dropped; applying it would set buckaroo_state back and make the
 *   grid purge and re-request rows for the old state. An initial_state
 *   with no `reply_seq` (another tab's change, a /load push, a fresh
 *   connection) always applies.
 */
export declare class WebSocketModel {
    private ws;
    private pendingMsg;
    private handlers;
    private state;
    private pendingChanges;
    private stateSeq;
    constructor(ws: WebSocket, initialState: Record<string, any>);
    send(msg: any): void;
    get(key: string): any;
    set(key: string, value: any): void;
    save_changes(): void;
    on(event: string, handler: Function): void;
    off(event: string, handler: Function): void;
    private emit;
}
