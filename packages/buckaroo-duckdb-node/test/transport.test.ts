import { describe, it, expect, vi } from 'vitest';
import { extractSearchTerm, makeIpcMainHandler } from '../src/transport';
import type { DuckBackend } from '../src/backend';

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
