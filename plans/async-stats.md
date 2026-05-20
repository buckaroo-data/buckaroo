# Future work — async summary stats (esp. for search)

Seed for a separate issue; not part of #773's `/load_expr` PR.

## Problem

`XorqServerDataflow(expr, skip_main_serial=True)` runs the stats pipeline
synchronously inside the load/state-change request handler. Two paths
where this bites:

1. **Initial load** (`POST /load_expr`). Tornado IO loop blocks while
   `XorqStatPipeline` issues its batched aggregate + per-column
   histograms. #700 made each phase single-round-trip, so it's
   sub-second against a warm 50M-row Snowflake table — but a cold
   query, a wider table, or a slower backend can still push this
   into multi-second territory.

2. **Search / state change** (`buckaroo_state_change` WS message). This
   is the worse case. Every keystroke into the search box re-runs the
   stats pipeline against the filtered expression. On a remote backend,
   that's "user types `foo`" → six aggregate queries hit Snowflake
   (one per character of debounced input). Even sub-second per query
   stacks into a sluggish search experience.

## Idea

Run the stats pipeline off the Tornado IO loop and stream results to
the client as they arrive.

Shape (rough):
- `LoadExprHandler` returns the initial `df_meta` (rows, columns,
  schema) immediately — enough for the grid to render with row count
  and column headers.
- A background task (`IOLoop.run_in_executor` or a worker pool) runs
  `XorqServerDataflow(expr, ...)` to populate `merged_sd`,
  `df_data_dict`, `df_display_args`.
- When stats land, push a `stats_update` WS message to the session's
  clients with the new `df_data_dict` / `df_display_args`.
- For `buckaroo_state_change` (search), the same pattern: ack the
  filter immediately, push updated stats when ready. Coalesce or
  cancel in-flight stats jobs when a newer state change arrives, so
  fast typing doesn't queue up six dead queries.

Frontend should handle a partially-populated `df_data_dict` gracefully
(it already does for `skip_main_serial=True` infinite mode — `main: []`
with stats arriving later).

## Why not in #773

- #773 is about making the xorq widget *reachable* from the server.
  Synchronous stats matches the existing pandas/polars `/load`
  semantics today.
- Async streaming touches WS protocol (new message type), frontend
  partial-state handling, and stats-job cancellation. Each of those
  is a real design decision worth its own thread.
- The pandas/polars `/load` paths would benefit from the same
  treatment for large frames — this is really "async stats for the
  server" in general, not xorq-specific. Designing it once for both
  backends will be cleaner than xorq-only and then porting.

## Open questions to resolve when this becomes a real plan

1. Where do background stats jobs live? Per-session worker, global
   thread pool, or async via `asyncio.to_thread`?
2. Cancellation semantics: cancel in-flight stats when a new state
   change arrives, or let them finish and discard the result?
3. WS message type for incremental stats — new (`stats_update`), or
   reuse `initial_state` with a flag?
4. How does the frontend's grid render when row count is known but
   summary stats aren't yet? (Existing infinite mode renders main
   `[]` and column headers immediately — good baseline.)
5. Does the same machinery cover pandas/polars (long `groupby` /
   `describe`), or is it xorq-specific because remote-backend latency
   is the only place it actually hurts?
6. Interaction with the session eviction TTL — a stats job outliving
   its session is wasted work; needs an "is session still live" check
   before pushing results.

## Related

- #700 (closed) — `XorqStatPipeline` single-round-trip per phase. Sets
  the floor for how fast sync stats can ever be.
- #773 — the load-path issue this branched off of. Ships with sync
  stats per the v1 decision.
