# ADR: Rows-first delivery with client-pulled summary stats

- **Status:** Proposed (2026-10-06). Implemented as draft PRs that are parked on purpose: rows-first delivery is wanted eventually, behind the out-of-core `scan_parquet` backend. Nothing in this ADR changes a default.
- **Affected code:** `buckaroo/server/session.py` (`build_state_message`, the session snapshot), `buckaroo/server/websocket_handler.py` (`DataStreamHandler.on_message`), `buckaroo/server/handlers.py` (`/load_expr`, `/reload_expr`), `buckaroo/dataflow/dataflow.py` (`_get_summary_sd`, `_populate_sd_cache`, `_scope_cache_key`), `buckaroo/xorq_buckaroo.py`, `buckaroo/pluggable_analysis_framework/xorq_stat_pipeline.py`, and on the client `WebSocketModel.ts`, `StateOrchestrator.ts`, `BuckarooServerView.tsx` and `packages/js/standalone.tsx`.
- **Implementing PRs:** #1021 (schema tier core, xorq), #1022 (schema tier for pandas and polars), #1024 (wire: `stats_request`, `stats_update`, `df_meta.stats`), #1026 (resumable units and `StatRun`), #1028 (request runs units for a time budget), #1035 (column-chunk split of the xorq batch over HTTP), and the client PRs #1025 (merge `stats_update`), #1027 (scheduler) and #1030 (incremental requests). #1020, the client hardening that makes a two-message protocol safe, is already on main.
- **Related:** #998 and #1014 (stale replies), #923 (aggregate-backed xorq row cost), #829 (filtered stats), ADR-001 (the stat cache, which supplies `stat_columns` and cell storage that units can use), ADR-003 (which stats a session runs at all).

## Terms

- **schema tier**: a dataflow built from dtypes and the row count only: identity and typing keys (`orig_col_name`, `rewritten_col_name`, `dtype`, `typing_stats`, `_type`, `is_*`, `length`), no data query beyond the count.
- **stats_delivery**: `inline` (stats computed in the dataflow constructor, today's behaviour) or `deferred` (schema-tier first message, stats afterwards).
- **stats_gen**: a server-owned counter that identifies the state a stats message describes. Bumped by `/load`, `/reload_expr` and any `buckaroo_state_change` that changes a dataflow field.
- **unit**: the smallest piece of a stats run the server executes between two checks of the loop: on xorq the scalar batch, then one histogram query per column.
- **StatRun**: the per-session object holding a run's unit plan, an append-only list of finished fragments and an accumulator, keyed by `(stats_gen, scope)`.
- **StatCursor**: a connection's position in a StatRun's fragment list.
- **fragment**: `{orig_col: {stat: value}}` for one unit.

## Problem

On `/load_expr`, `XorqServerDataflow` computes summary stats inside its constructor, and `session.xorq_dataflow` is assigned only afterwards. No row is served until the stats finish. Across 115 tallyman loads, `firstpull.load_expr` has p50 1.29 s, p90 4.5 s and a maximum of 215.8 s, and stats are a median 93% of it. The worst load spent 162.5 s in a single batch aggregate. Constructing the same dataflow at the schema tier takes about 1 ms against 393 ms with stats on a 27-column entry.

The server is synchronous Tornado, so any stats query blocks every WebSocket message and HTTP request, `/health` included. Stats in a worker thread failed on xorq with `RuntimeError: Already borrowed` (two threads on one `SessionContext`). Heavy work therefore has to be cut into pieces small enough to run between loop turns.

Three facts of the current code get in the way of a second message:

1. A client that receives two `initial_state` frames can drop the second one while the first is decoding, and nothing in the protocol identifies which state a frame describes (#998). #1020, already on main, hardens the client for it.
2. `df_meta` is rebuilt wholesale on each state change, so a flag the dataflow writes there is lost at the next change.
3. A session snapshot is pushed from five places besides `open()`, so a check at connect time protects only the first message.

## Decisions

### D1. Stats travel in a typed `stats_update`, never a second `initial_state`

The first `initial_state` carries rows, the schema tier and `df_meta.stats = {status, tier, gen, reason?}`. `status` is `complete`, `pending`, `not_computed` or `error`; absent `stats` means `complete`, which is what old servers send. Stats arrive as `stats_update {stats_gen, scope, tier, final, remaining, payload, elapsed_ms}`, where `payload` is a self-contained wide `DFEnvelope` that the client key-merges into `all_stats`. A request the server will not run gets `stats_aborted`. `PROTOCOL_VERSION` stays 1.

A second `initial_state` was rejected: existing clients can drop it, it reuses the message type whose lack of identity is #998, and it can say "not computed" only as a flag.

### D2. The client pulls; the server runs no job of its own

After first paint the client sends `stats_request {stats_gen, scope, columns?, incremental?, force?}`. A synchronous branch in `DataStreamHandler.on_message` answers it. There is no timer, thread or `add_callback` chain, so a session nobody views computes nothing, and clients without a push channel (`IpcDuckModel`) are served.

The server-pushed chain (one unit per `add_callback` tick) was rejected: it needs cancellation checks on every path and burns the loop for unwatched sessions. A child process that runs the xorq batch against a cold cache worked (2.69 s child while the parent paged 47 windows at p50 17 ms) but needs `cache_storage_path` and an identical `build_dir` and brings process lifecycle and fork hazards (#885). It stays an option only if the batch split leaves a unit above the accepted stall.

### D3. `stats_gen` keys every stats message; `state_seq` does not

The client drops a `stats_update` whose `stats_gen` differs from the one it holds, and advances its expected value on a broadcast frame. #1014's `state_seq` is client-owned, echoed to the originating client only, and not bumped by `/load` or `/reload_expr`, so it cannot guard a reply to a different client's state change. The two tokens are independent and #1014 does not conflict with this ADR.

### D4. The schema tier is a dataflow level, and the tier is part of the cache scope

`stats_tier` (`full` default, `schema`) is a dataflow attribute. At `schema`, `_get_summary_sd` returns the schema sd and runs no data query, and `add_analysis` gets its own tier check because it builds `DFStatsClass` itself. The tier joins `_scope_cache_key`, and a run assigns `summary_sd` only when it is a complete run. Without this, a schema-only construction followed by a full assignment never reaches `merged_sd`, because all three scopes hit the cache, and `_populate_sd_cache` can store a stale sd under a new filtered key (a probe stored `filtered_length` 1000 against a true 250).

`pinned_rows` is identical at every tier, so nothing has to be restored when stats finish. A pinned key with no value renders a placeholder with a unique row id while `pending`.

Pandas and polars dataflows accept the schema tier too, so one mechanism covers all three. Their `/load` path stays `full` and inline: eager stats cost 64 to 176 ms against 0.5 to 9 ms for a window, and deferring trades that for a round trip and the layout problems of two messages.

### D5. A run is a list of units, kept on the session

`StatRun`, keyed by `(stats_gen, scope)`, lives on the session and is dropped when `stats_gen` changes. Each WebSocket handler keeps a `StatCursor`. The cache that ADR-001 adds (`stat_columns`, cell storage) gives xorq a place to keep finished cells across sessions; the StatRun is the in-session store that serves several clients and a reconnect without recomputation, and it works for all three backends.

On xorq the order is the scalar batch first (`length`, `null_count`, `min`, `max`, `mean`, `std`, `approx_median`, `distinct_count`), after which `histogram_bins` is a pure function of five stats and `color_map` needs no histogram query. Then one histogram query per column, with the columns the grid shows (the `columns` hint) first.

### D6. A request runs units for a bounded time, at least one

A request runs units for about 75 ms, at least one, and replies with the fragments beyond the client's cursor. With `incremental: true` the reply is `final: false` while units remain. A request without it runs everything in one call, which keeps old callers working and is the behaviour the client scheduler first shipped with. If the cursor is behind, the reply carries unseen fragments and runs nothing.

The latency floor of a row request is the longest unit. The xorq batch is the one unit that cannot be bounded as written (162.5 s observed), so #1035 splits it by column chunk behind `stat_chunk_cells`, enabled by a host over HTTP. The split is applied only to scan-backed sources: on a join, aggregate or diff it would re-execute the plan per chunk. The default flip stays gated on a measured maximum request length under a stated stall budget (250 ms proposed in the design notes; the per-request stall is an open question below).

### D7. The last unit does the final assignment

When the last unit finishes, in this order: write the sd into `summary_stats_cache`, then assign `summary_sd`; refresh the session snapshot through one helper (replacing three copies) and set `status` to `complete` in the same step; attach the rebuilt `df_display_args` to the `final` reply when its hash changed (a float `minWidth` was 114 with `max` 123456789.5 and 78 without stats); free the accumulator.

### D8. Clients without the capability get complete stats synchronously

Capability rides the connect URL, `?caps=stats_update`, because `open()` sends before any client hello. All six send sites and the highlight overlay go through one `build_state_message_for(session, client)`. A legacy client on a deferred session gets missing units run synchronously before each message built for it, which costs what today costs. A permanent schema tier for them would strip stats at their first search, because stock clients search through `quick_command_args.search`. A new client against an old server sees no `df_meta.stats` and treats the session as complete.

### D9. Search and state changes

A dataflow-field change on a deferred session sets the traits at the schema tier, bumps `stats_gen` and broadcasts a `pending` frame. This removes the double `_handle_widget_change` per search (596 ms to 12.7 ms on the 27-column entry). A `search_string` change touches no stats. Filtered stats are out of scope: after a search the client shows unfiltered stats with a note. #829 and #923 own the filtered case.

### D10. Telemetry

The `stats_request` branch enters `telemetry_context` with `session.tele_sink`, emits `stats.request` and `stats.unit` spans, and counts updates sent, dropped as stale and errors. `firstpull.load_expr` stops measuring stats, so tallyman must be told before the default flips, and `firstpull.stats_total` is emitted per completed run.

## Consequences

- The default stays `inline`. A host selects `deferred` per load with a body field. The new fields ride `dataflow_kwargs` and a stored pair, never the truthiness-based `has_config` tuple, or a host that sends them on every POST defeats the warm short-circuit.
- Tallyman pins `buckaroo-js-core` 0.15.8, so enabling deferred delivery for it needs a client release and a bump.
- `df_meta.stats` replaces per-cell sentinels and `stats_omitted` as the single flag for "stats are not here".
- A request can last as long as its longest unit, so the xorq batch split is a precondition for flipping the default, not an optimization.
- Time to the first complete stats grows, because stats now start after first paint. The measure to hold is first painted `infinite_resp` against last `stats_update`.

## Alternatives considered

- A second partial `initial_state` (the #787 shape).
- A server-pushed chain of `add_callback` units.
- A worker thread (fails on xorq) or a child process for the batch tail.
- Reusing `state_seq` as the stats key.
- Deferring eager pandas and polars.

## Not decided here

- **Which stats a session runs at a given size.** That is ADR-003. This ADR carries `not_computed` and the `tier` field on the wire but does not choose a tier.
- **A lazy or `scan_parquet` backend.** The destination for polars `/load` is an out-of-core scan. It would reuse this protocol, and its design is a separate document that does not exist yet.
- **Per-request stall.** 50 ms, 100 ms, 250 ms or the longest unit sets the time budget and how finely the batch must split.
- **Whether a child process may run the xorq batch tail.**
- **A host `row_count` hint** for aggregate-backed xorq, where `count()` executes the plan (#923).
- **Whether capability negotiation stays in the URL query** or becomes a client hello, which costs a round trip on every connect.
