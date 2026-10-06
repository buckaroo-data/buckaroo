# ADR: Rows-first delivery with server-pushed summary stats

- **Status:** Proposed (2026-10-06). Revised the same day: stats are pushed by the server after rows instead of pulled by the client, and the design assumes ADR-001's cache. Implemented in part as draft PRs that are parked on purpose: rows-first delivery is wanted eventually, behind the out-of-core `scan_parquet` backend. Nothing in this ADR changes a default.
- **Affected code:** `buckaroo/server/session.py` (`build_state_message`, the session snapshot), `buckaroo/server/websocket_handler.py` (`DataStreamHandler._handle_infinite_request`, `on_message`), `buckaroo/server/handlers.py` (`/load_expr`, `/reload_expr`), `buckaroo/dataflow/dataflow.py` (`_get_summary_sd`, `_populate_sd_cache`, `_scope_cache_key`), `buckaroo/xorq_buckaroo.py`, `buckaroo/pluggable_analysis_framework/xorq_stat_pipeline.py`, and on the client `WebSocketModel.ts`, `StateOrchestrator.ts`, `BuckarooServerView.tsx` and `packages/js/standalone.tsx`.
- **Implementing PRs:** #1021 (schema tier core, xorq), #1022 (schema tier for pandas and polars), #1024 (wire: `stats_update`, `df_meta.stats`; its `stats_request` branch narrows to the explicit request in D2) and the client PR #1025 (merge `stats_update`). #1027's pending, not-computed and error states still apply. #1020, the client hardening that makes a two-message protocol safe, is already on main. #1026 (resumable units and `StatRun`), #1028 (request runs units for a time budget), #1030 (incremental requests), #1035 (column-chunk split of the xorq batch) and #1027's scheduler implement the client-pull design that D2 replaced. As of 2026-10-06 #1027, #1028 and #1030 are closed and #1026 and #1035 are open.
- **Related:** #998 and #1014 (stale replies), #896 (eager second window), #923 (aggregate-backed xorq row cost), #829 (filtered stats), ADR-001 (the stat cache, which this ADR assumes), ADR-003 (the stats policy that decides what a push contains).

## Terms

- **schema tier**: a dataflow built from dtypes and the row count only: identity and typing keys (`orig_col_name`, `rewritten_col_name`, `dtype`, `typing_stats`, `_type`, `is_*`, `length`), no data query beyond the count.
- **stats_delivery**: `inline` (stats computed in the dataflow constructor, today's behaviour) or `deferred` (schema-tier first message, stats afterwards).
- **stats_gen**: a server-owned counter that identifies the state a stats message describes. Bumped by `/load`, `/reload_expr` and any `buckaroo_state_change` that changes a dataflow field.
- **row reply**: the frames that answer one `infinite_request`: a JSON `infinite_resp`, then a binary parquet frame when the window is non-empty, then the same pair for the eager `second_request` (#896) when the request carries one.
- **stats policy**: ADR-003's `resolve_stats_policy` result for a session (`tier_target`, `auto_request`, `requestable`, `reason`).
- **push**: the `stats_update` messages the server sends a connection without being asked.

## Problem

On `/load_expr`, `XorqServerDataflow` computes summary stats inside its constructor, and `session.xorq_dataflow` is assigned only afterwards. No row is served until the stats finish. Across 115 tallyman loads, `firstpull.load_expr` has p50 1.29 s, p90 4.5 s and a maximum of 215.8 s, and stats are a median 93% of it. The worst load spent 162.5 s in a single batch aggregate. Constructing the same dataflow at the schema tier takes about 1 ms against 393 ms with stats on a 27-column entry.

The server is synchronous Tornado, so any stats query blocks every WebSocket message and HTTP request, `/health` included. Stats in a worker thread failed on xorq with `RuntimeError: Already borrowed` (two threads on one `SessionContext`). Stats stay on the loop, so what this ADR controls is their order relative to rows.

This ADR assumes ADR-001's cache works. A warm load reads its stats in a few milliseconds (about 2 ms for keys, 1 to 3 ms to read and coalesce, 1 ms to decode), which is about what a row window costs. Cold stats, on the first load of an entry or after a stat's code changes, still run on the loop for as long as they take. Bounding that is left to ADR-001 and ADR-003 (see "Not decided here").

Three facts of the current code get in the way of a second message:

1. A client that receives two `initial_state` frames can drop the second one while the first is decoding, and nothing in the protocol identifies which state a frame describes (#998). #1020, already on main, hardens the client for it.
2. `df_meta` is rebuilt wholesale on each state change, so a flag the dataflow writes there is lost at the next change.
3. A session snapshot is pushed from five places besides `open()`, so a check at connect time protects only the first message.

## Decisions

### D1. Stats travel in a typed `stats_update`, never a second `initial_state`

The first `initial_state` carries the schema tier and `df_meta.stats = {status, tier, gen, reason?}`. `status` is `complete`, `pending`, `not_computed` or `error`; absent `stats` means `complete`, which is what old servers send. Stats arrive as `stats_update {stats_gen, scope, tier, final, payload, elapsed_ms}`, where `payload` is a self-contained wide `DFEnvelope` that the client key-merges into `all_stats`. The server may split one run across several updates, for example one per tier; the last has `final: true`. An explicit request the server will not run gets `stats_aborted`. `PROTOCOL_VERSION` stays 1.

A second `initial_state` was rejected: existing clients can drop it, it reuses the message type whose lack of identity is #998, and it can say "not computed" only as a flag.

### D2. The server pushes stats after it has finished sending rows

On a deferred session the server sends a connection no summary stats until it has finished that connection's first row reply for the current `stats_gen`. Finished means every frame of the reply, the eager second window included, has been handed to the socket. The server waits on the `Future` that `write_message` returns for the reply's last frame, then reads or computes the stats and sends `stats_update`. A stats frame never lands inside a row reply, and stats are never computed while row bytes for that connection sit in Tornado's write buffer. An error reply counts as a finished reply, so a failed window does not leave the stats pending.

Each connection holds the `stats_gen` it is owed stats for. It is set when the connection is sent an `initial_state` that starts a `stats_gen` (connect, `/load`, `/reload_expr`, a dataflow-field change, D7) and cleared by the push. Such an `initial_state` carries `status: "pending"` and no stats, even when the session already holds them; a later frame for the same `stats_gen`, sent after the push, carries them as today.

What the push contains follows the session's stats policy (ADR-003). The server pushes the tier the policy runs automatically (`tier_target` when `auto_request` holds) and nothing above it. When the policy runs nothing, the push is a single `stats_update {final: true}` with `status: "not_computed"` and the policy fields, which ends the pending state. A tier above the pushed one runs only on an explicit `stats_request {stats_gen, scope, tier, columns?, force}`, which ADR-003's compute control sends.

Stats for a `stats_gen` are computed once per session, at the first connection's first row reply, and kept on the session (D5). A connection whose first row reply comes later is pushed the stored result. A session nobody views computes nothing, because nothing starts a push until a client asks for rows.

The push is one continuation registered on the write future. There is no timer, thread or chain of `add_callback` ticks. Before it runs it checks that the connection is still open and that `stats_gen` is still the one it was registered for. If either check fails it does nothing; a newer `stats_gen` gets its own push after that connection's next row reply.

A request-and-reply transport such as `IpcDuckModel` cannot receive a frame it did not ask for. It does not advertise `stats_update`, so a server speaking to one uses D6.

The earlier form of this decision had the client pull: after first paint the client sent `stats_request`, and the server ran resumable stat units for a bounded time per request (a unit plan and `StatRun` on the session, a cursor per connection, a 75 ms budget, a client scheduler). That machinery existed to keep a cold run from stalling row requests. With the cache, a warm push costs about what a row window costs, and on a cold run the units only spread the same work across requests. Pushing at load time, before any row request, was rejected because on a cold cache it puts stats ahead of rows again.

### D3. `stats_gen` keys every stats message; `state_seq` does not

The client drops a `stats_update` whose `stats_gen` differs from the one it holds, and advances its expected value on a broadcast frame. #1014's `state_seq` is client-owned, echoed to the originating client only, and not bumped by `/load` or `/reload_expr`, so it cannot guard a reply to a different client's state change. The two tokens are independent and #1014 does not conflict with this ADR.

### D4. The schema tier is a dataflow level, and the tier is part of the cache scope

`stats_tier` (`full` default, `schema`) is a dataflow attribute. At `schema`, `_get_summary_sd` returns the schema sd and runs no data query, and `add_analysis` gets its own tier check because it builds `DFStatsClass` itself. The tier joins `_scope_cache_key`, and a run assigns `summary_sd` only when it is a complete run. Without this, a schema-only construction followed by a full assignment never reaches `merged_sd`, because all three scopes hit the cache, and `_populate_sd_cache` can store a stale sd under a new filtered key (a probe stored `filtered_length` 1000 against a true 250).

`pinned_rows` is identical at every tier, so nothing has to be restored when stats finish. A pinned key with no value renders a placeholder with a unique row id while `pending`.

Pandas and polars dataflows accept the schema tier too, so one mechanism covers all three. Their `/load` path stays `full` and inline: eager stats cost 64 to 176 ms against 0.5 to 9 ms for a window, and deferring trades that for a second message and the layout problems of two messages.

### D5. The end of a run does the final assignment

When a run finishes, in this order: write the sd into `summary_stats_cache`, then assign `summary_sd`; refresh the session snapshot through one helper (replacing three copies) and set `status` to `complete` in the same step; attach the rebuilt `df_display_args` to the `final` update when its hash changed (a float `minWidth` was 114 with `max` 123456789.5 and 78 without stats). The snapshot is what D2 pushes to a connection that arrives later.

### D6. Clients without the capability get complete stats synchronously

Capability rides the connect URL, `?caps=stats_update`, because `open()` sends before any client hello. All six send sites and the highlight overlay go through one `build_state_message_for(session, client)`, which is also where a capable client's state-starting frame drops its stats (D2). A legacy client on a deferred session gets the stats computed synchronously before the first message built for it, which costs what today costs and, with the cache, a cache read. A permanent schema tier for them would strip stats at their first search, because stock clients search through `quick_command_args.search`. A new client against an old server sees no `df_meta.stats` and treats the session as complete.

### D7. Search and state changes

A dataflow-field change on a deferred session sets the traits at the schema tier, bumps `stats_gen` and broadcasts a `pending` frame. Each connection is then pushed the new stats after its next row reply (D2). This removes the double `_handle_widget_change` per search (596 ms to 12.7 ms on the 27-column entry). A `search_string` change touches no stats. Filtered stats are out of scope: after a search the client shows unfiltered stats with a note. #829 and #923 own the filtered case.

### D8. Telemetry

The push continuation and the `stats_request` branch enter `telemetry_context` with `session.tele_sink`, emit `stats.push` and `stats.request` spans, and count updates sent, pushes dropped as stale (closed connection or newer `stats_gen`) and errors. `stats.push` records the gap from the end of the row reply to the start of the push. `firstpull.load_expr` stops measuring stats, so tallyman must be told before the default flips, and `firstpull.stats_total` is emitted per completed run.

## Consequences

- The default stays `inline`. A host selects `deferred` per load with a body field. The new fields ride `dataflow_kwargs` and a stored pair, never the truthiness-based `has_config` tuple, or a host that sends them on every POST defeats the warm short-circuit.
- Tallyman pins `buckaroo-js-core` 0.15.8, so enabling deferred delivery for it needs a client release and a bump.
- `df_meta.stats` replaces per-cell sentinels and `stats_omitted` as the single flag for "stats are not here".
- A row request that arrives while a push is being built waits for it. With a warm cache that is the cache read. On a cold cache it is the whole stats run, which today happens before first paint and now happens after it. Flipping the default is gated on the cold case being acceptable, which ADR-001 and ADR-003 own.
- Time to complete stats grows by the time it takes to send the first rows, because stats start after them. The measure to hold is the end of the first row reply against the last `stats_update`.
- The pull-side PRs (#1026, #1028, #1030, #1035 and #1027's scheduler) are not needed under D2. #1027, #1028 and #1030 are closed. #1026 and #1035 are still open and are to be closed or cut down rather than rebased. The batch split in #1035 stays an option for cold stats (see "Not decided here").

## Alternatives considered

- A second partial `initial_state` (the #787 shape).
- Client-pulled stats with resumable units, per-connection cursors and a per-request time budget (the earlier D2).
- A push started at load, before any row request.
- A server-pushed chain of `add_callback` units.
- A worker thread (fails on xorq) or a child process for the batch tail (worked at 2.69 s while the parent paged 47 windows at p50 17 ms, but needs `cache_storage_path`, an identical `build_dir`, and process lifecycle and fork handling, #885).
- Reusing `state_seq` as the stats key.
- Deferring eager pandas and polars.

## Not decided here

- **Which stats a session runs at a given size.** That is ADR-003. This ADR pushes what that policy runs automatically and carries `not_computed` and the `tier` field on the wire.
- **Cold stats.** On a cache miss the push runs the stats on the loop, after rows, for as long as they take. Splitting that work (ADR-001's column bisect, D10, with #1038), the xorq batch split of #1035, or a child process for the batch tail are where that would be decided.
- **A lazy or `scan_parquet` backend.** The destination for polars `/load` is an out-of-core scan. It would reuse this protocol, and its design is a separate document that does not exist yet.
- **A host `row_count` hint** for aggregate-backed xorq, where `count()` executes the plan (#923).
- **Whether capability negotiation stays in the URL query** or becomes a client hello, which costs a round trip on every connect.
