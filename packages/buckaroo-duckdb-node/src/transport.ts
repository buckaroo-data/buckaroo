/**
 * `IModel`-over-IPC transport adapter (renderer side).
 *
 * Both sides of the wire are now in place. The PRODUCER (this file + the
 * backend) emits a single JSON `infinite_resp` whose `payload` is a bare
 * `parquet_b64` `DFEnvelope`. The CONSUMER — buckaroo-js-core's infinite
 * handler — decodes it via #933's `decodeDFData(msg.payload, buffers)`
 * (BuckarooWidgetInfinite.tsx:125), so an inline-parquet single-message reply
 * (no binary side-channel frame) renders end-to-end. The pre-#933 handler did
 * `parquetRead(buffers[0])` and could not consume this shape.
 *
 * aistudio has no Node webserver — it is Electron main + renderer over IPC
 * (`ipcMain.handle` / `ipcRenderer.invoke`). buckaroo-js-core runs in the
 * renderer and can't call native DuckDB bindings (they live in main). This
 * adapter implements the `IModel` seam the React tree already speaks:
 *
 *   model.send(msg)  →  invoke('buckaroo:msg', msg)  →  main answers  →
 *   adapter emits "msg:custom" with the reply.
 *
 * The "two frames" of `WebSocketModel` is a WebSocketModel implementation
 * detail; the React handler only needs the `"msg:custom"` event. The reply is
 * a single JSON object with an inline `parquet_b64` payload, so there is no
 * binary frame and no `buffers` array.
 */

import type { DuckBackend } from './backend.js';
import type { InitialStateMessage, PayloadResponse } from './wireTypes.js';

/** The `ipcRenderer.invoke`-shaped function the renderer hands in. */
export type IpcInvoke = (channel: string, msg: unknown) => Promise<unknown>;

/** Minimal structural copy of buckaroo-js-core's `IModel` (the only exported type). */
export interface IModel {
  send(msg: unknown): void;
  get(key: string): unknown;
  set(key: string, value: unknown): void;
  save_changes(): void;
  on(event: string, handler: (...args: unknown[]) => void): void;
  off(event: string, handler: (...args: unknown[]) => void): void;
}

type Handler = (...args: unknown[]) => void;

/**
 * Renderer-side `IModel`. Outgoing `infinite_request` messages are forwarded
 * over IPC; the main-process reply is re-emitted as a `"msg:custom"` event,
 * which is what `getKeySmartRowCache` listens for.
 */
export class IpcDuckModel implements IModel {
  private readonly invoke: IpcInvoke;
  private readonly channel: string;
  private readonly listeners = new Map<string, Set<Handler>>();
  private readonly state = new Map<string, unknown>();
  private readonly pendingChanges = new Set<string>();

  constructor(invoke: IpcInvoke, opts: { channel?: string } = {}) {
    this.invoke = invoke;
    this.channel = opts.channel ?? 'buckaroo:msg';
  }

  send(msg: unknown): void {
    void this.invoke(this.channel, msg).then((reply) => this.applyReply(reply));
  }

  get(key: string): unknown {
    return this.state.get(key);
  }
  set(key: string, value: unknown): void {
    this.state.set(key, value);
    this.pendingChanges.add(key);
    this.emit('change:' + key, value);
  }
  /**
   * Flush a pending `buckaroo_state` edit to the main process as a
   * `buckaroo_state_change` (mirrors `WebSocketModel.save_changes`), then apply
   * the returned `initial_state`. Without this the React search UI's
   * `set('buckaroo_state', …)` never reaches the backend over IPC.
   */
  save_changes(): void {
    const hadStateChange = this.pendingChanges.has('buckaroo_state');
    this.pendingChanges.clear();
    if (!hadStateChange) return;
    const msg = { type: 'buckaroo_state_change', new_state: this.state.get('buckaroo_state') };
    void this.invoke(this.channel, msg).then((reply) => this.applyReply(reply));
  }

  /**
   * Route a main-process reply. An `initial_state` is fanned out as `change:*`
   * events so the React tree re-renders (the filtered grid + highlight);
   * anything else (an `infinite_resp`) is re-emitted as `msg:custom` for the
   * row cache.
   */
  private applyReply(reply: unknown): void {
    if (reply === undefined || reply === null) return;
    const r = reply as { type?: string } & Record<string, unknown>;
    if (r.type === 'initial_state') {
      for (const [k, v] of Object.entries(r)) {
        if (k === 'type') continue;
        this.state.set(k, v);
        this.emit('change:' + k, v);
      }
      return;
    }
    this.emit('msg:custom', reply);
  }

  on(event: string, handler: Handler): void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set());
    this.listeners.get(event)!.add(handler);
  }
  off(event: string, handler: Handler): void {
    this.listeners.get(event)?.delete(handler);
  }
  private emit(event: string, ...args: unknown[]): void {
    for (const h of this.listeners.get(event) ?? []) h(...args);
  }
}

/** Pull the search term out of a `buckaroo_state_change` message, or '' if none. */
export function extractSearchTerm(msg: {
  new_state?: { quick_command_args?: Record<string, unknown> };
  quick_command_args?: Record<string, unknown>;
}): string {
  const qa = msg?.new_state?.quick_command_args ?? msg?.quick_command_args;
  const search = qa?.search;
  if (Array.isArray(search) && search.length > 0 && search[0] != null) {
    return String(search[0]);
  }
  return '';
}

/**
 * The main-process handler. Register with
 * `ipcMain.handle('buckaroo:msg', makeIpcMainHandler(backend))`.
 *
 * Returns the reply object the renderer re-emits as `"msg:custom"`. A
 * `buckaroo_state_change` carrying `quick_command_args.search` re-runs the
 * search and replies with a fresh `initial_state` (filtered stats +
 * highlight_phrase); other state changes are no-ops.
 */
export function makeIpcMainHandler(
  backend: DuckBackend,
): (
  event: unknown,
  msg: {
    type?: string;
    payload_args?: unknown;
    new_state?: { quick_command_args?: Record<string, unknown> };
    quick_command_args?: Record<string, unknown>;
  },
) => Promise<InitialStateMessage | PayloadResponse | null> {
  return async (_event, msg) => {
    switch (msg?.type) {
      case 'initial_state':
        return backend.initialState();
      case 'infinite_request':
        return backend.handleInfiniteRequest(msg.payload_args as never);
      case 'buckaroo_state_change':
        backend.setSearch(extractSearchTerm(msg));
        return backend.initialState();
      default:
        // other read-only state changes are no-ops
        return null;
    }
  };
}
