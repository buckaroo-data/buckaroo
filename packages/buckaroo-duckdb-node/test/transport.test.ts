import { describe, it, expect, vi } from 'vitest';
import { extractSearchTerm, makeIpcMainHandler, IpcDuckModel } from '../src/transport';
import type { DuckBackend } from '../src/backend';

/** A tick to let the `invoke(...).then(...)` microtask in send/save_changes settle. */
const flush = () => new Promise((r) => setTimeout(r, 0));

describe('extractSearchTerm', () => {
  it('reads new_state.quick_command_args.search[0]', () => {
    expect(extractSearchTerm({ new_state: { quick_command_args: { search: ['Al'] } } })).toBe('Al');
  });
  it('falls back to a top-level quick_command_args', () => {
    expect(extractSearchTerm({ quick_command_args: { search: ['Bo'] } })).toBe('Bo');
  });
  it('is empty when there is no search term', () => {
    expect(extractSearchTerm({ new_state: { quick_command_args: {} } })).toBe('');
    expect(extractSearchTerm({})).toBe('');
  });
});

describe('makeIpcMainHandler', () => {
  function stubBackend() {
    return {
      initialState: vi.fn(async () => ({ type: 'initial_state' })),
      handleInfiniteRequest: vi.fn(async () => ({ type: 'infinite_resp' })),
      setSearch: vi.fn(),
    };
  }

  it('routes a buckaroo_state_change to setSearch + a fresh initial_state', async () => {
    const backend = stubBackend();
    const handler = makeIpcMainHandler(backend as unknown as DuckBackend);

    const reply = await handler(null, {
      type: 'buckaroo_state_change',
      new_state: { quick_command_args: { search: ['Al'] } },
    });

    expect(backend.setSearch).toHaveBeenCalledWith('Al');
    expect(backend.initialState).toHaveBeenCalledTimes(1);
    expect(reply).toEqual({ type: 'initial_state' });
  });

  it('clears the search when the term is gone', async () => {
    const backend = stubBackend();
    const handler = makeIpcMainHandler(backend as unknown as DuckBackend);
    await handler(null, { type: 'buckaroo_state_change', new_state: { quick_command_args: {} } });
    expect(backend.setSearch).toHaveBeenCalledWith('');
  });

  it('still answers initial_state and infinite_request', async () => {
    const backend = stubBackend();
    const handler = makeIpcMainHandler(backend as unknown as DuckBackend);
    await handler(null, { type: 'initial_state' });
    await handler(null, { type: 'infinite_request', payload_args: {} });
    expect(backend.initialState).toHaveBeenCalledTimes(1);
    expect(backend.handleInfiniteRequest).toHaveBeenCalledTimes(1);
  });
});

describe('IpcDuckModel state changes', () => {
  it('save_changes forwards a buckaroo_state_change and applies the returned initial_state', async () => {
    const refreshed = {
      type: 'initial_state',
      df_meta: { total_rows: 5, filtered_rows: 2 },
    };
    const invoke = vi.fn(async () => refreshed);
    const model = new IpcDuckModel(invoke);

    const changes: unknown[] = [];
    model.on('change:df_meta', (v) => changes.push(v));

    const newState = { quick_command_args: { search: ['Al'] } };
    model.set('buckaroo_state', newState);
    model.save_changes();
    await flush();

    // the pending buckaroo_state went over the wire as a state_change
    expect(invoke).toHaveBeenCalledWith('buckaroo:msg', {
      type: 'buckaroo_state_change',
      new_state: newState,
    });
    // the reply's keys were fanned out as change:* events (not msg:custom)
    expect(changes).toEqual([{ total_rows: 5, filtered_rows: 2 }]);
    expect(model.get('df_meta')).toEqual({ total_rows: 5, filtered_rows: 2 });
  });

  it('save_changes is a no-op when buckaroo_state was not touched', async () => {
    const invoke = vi.fn(async () => null);
    const model = new IpcDuckModel(invoke);
    model.set('something_else', 1);
    model.save_changes();
    await flush();
    expect(invoke).not.toHaveBeenCalled();
  });

  it('send re-emits an infinite_resp reply as msg:custom', async () => {
    const reply = { type: 'infinite_resp', length: 2 };
    const invoke = vi.fn(async () => reply);
    const model = new IpcDuckModel(invoke);

    const custom: unknown[] = [];
    model.on('msg:custom', (m) => custom.push(m));
    model.send({ type: 'infinite_request', payload_args: {} });
    await flush();

    expect(custom).toEqual([reply]);
  });
});
