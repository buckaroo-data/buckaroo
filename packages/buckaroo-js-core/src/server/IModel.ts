/**
 * IModel — minimal transport-agnostic model interface that BuckarooView
 * depends on. Implemented by WebSocketModel (this package) and by host
 * adapters that relay buckaroo's server protocol through a non-WebSocket
 * transport (e.g. buckaroo-tauri-adapter's TauriIPCModel).
 *
 * This is the same surface anywidget exposes for traitlet sync, narrowed
 * to what getKeySmartRowCache and the BuckarooView state hooks call:
 *
 *   send(msg)               → ship a JSON message to the backend
 *   get(key) / set(key, v)  → read/write local state
 *   save_changes()          → flush set() calls back to the backend
 *   on(event, fn)           → subscribe to "change:<key>", "metadata", "msg:custom"
 *   off(event, fn)
 */
export interface IModel {
    send(msg: any): void;
    get(key: string): any;
    set(key: string, value: any): void;
    save_changes(): void;
    on(event: string, handler: (...args: any[]) => void): void;
    off(event: string, handler: (...args: any[]) => void): void;
}
