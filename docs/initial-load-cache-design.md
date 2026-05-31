# Initial-load cache — serve the first render without touching the data

## Status
Design only. No code yet. Branch `feat/initial-load-cache` off `main`.

## Problem

Buckaroo's first render is expensive: sample the frame, run the analysis
pipeline, style every column, serialize the first window of rows. For a
1M-row pandas frame or a xorq expression that has to execute, that work
happens every time the widget mounts or a server session opens — even
when neither the data nor the configuration changed since last time.

Hosts that *can* tell when the data changed (xorq has deterministic build
hashes; a file has a content hash / mtime) should be able to skip the
whole pipeline and replay a cached first render. That's the goal: get
everything needed to answer the frontend's opening requests —
`initial_state` plus the first `infinite_request` — from a cache, without
constructing the DataFrame or executing the expression.

## The two functions

```python
# buckaroo/cache/initial_cache.py

def get_initial_cache_data(
    df,                          # pd.DataFrame | pl.DataFrame | xorq expr
    *,
    analysis_klasses=None,       # default: the standard widget set
    styling_klasses=None,        # default: DefaultMainStyling + DefaultSummaryStatsStyling
    sampling_klass=None,         # default: ServerSampling
    init_sd=None,
    skip_stat_columns=None,
    window=1000,                 # rows pre-serialized for the first infinite_request
    data_id=None,                # caller's data identity, stamped into the bundle (opt)
    cache_version=None,          # extra string folded into config_id (opt)
) -> tuple[str, InitialCacheData]:
    """Run the pipeline ONCE and snapshot it. Returns (config_id, bundle)."""

def populate_from_cache_data(
    bundle: InitialCacheData,
    *,
    column_config_overrides=None,  # replay-time display knobs — re-style, no data touch
    component_config=None,
    extra_grid_config=None,
    pinned_rows=None,
    styling_klasses=None,          # swap styling at replay (see "requires_summary" caveat)
) -> CachedInitial:
    """Build an object that answers the opening requests from the bundle."""
```

`get_initial_cache_data` is the **producer** (runs once, touches the data,
emits a serializable bundle). `populate_from_cache_data` is the
**consumer** (touches nothing; serves the first render). This is the two
functions the request named — `get_initial_cache_data` returns exactly
`(config identifier, data structure)`.

`CachedInitial` is what the widget / server adapters drive:

```python
class CachedInitial:
    def initial_state(self, *, mode="viewer") -> dict: ...   # full server initial_state / widget traits
    def df_data_dict(self) -> dict: ...                      # {'main': [], 'all_stats': {...}, 'empty': []}
    def df_display_args(self) -> dict: ...                   # regenerated unless display knobs are default
    def df_meta(self) -> dict: ...
    def serve_window(self, payload_args, search_string="") -> tuple[dict, bytes] | None:
        ...  # returns (msg, parquet_bytes) for the cacheable first window; None => cache miss, use the source
```

## Why this is possible — the key codebase facts

1. **One terminal assembly point.** Everything the frontend gets on first
   render is built in `_handle_widget_change` (`dataflow.py:679-723`) from a
   single tuple `widget_args_tuple = (id, processed_df, merged_sd)`. It
   produces three traits: `df_data_dict`, `df_display_args`, `df_meta`. The
   server reads the same three via `get_buckaroo_display_state`
   (`data_loading.py:67-89`). Snapshot those three plus the first window and
   you have the entire first render.

2. **Styling never reads row values.** `get_dfviewer_config(sd, df)`
   (`styling_core.py:422-429`) calls `style_columns` (`:432-473`) and
   `get_left_col_configs` (`:326-370`). `style_column`
   (`customizations/styling.py:70-142`) reads only the per-column entry of
   the summary dict (`_type`, `orig_col_name`, displayer hints) — never a
   cell. `old_col_new_col(df)` and `get_left_col_configs(df)` read only
   `df.columns` / `df.index` *structure*. `merge_column_config`
   (`styling_core.py:231-254`) likewise. So `df_display_args` is a pure
   function of `(merged_sd, column schema)` — a **zero-row DataFrame** with
   the right columns/index regenerates it exactly. This is what lets
   styling and component config stay configurable at replay without
   touching the data.

3. **The window is one function call.** `handle_infinite_request_buckaroo`
   (`data_loading.py:92-130`) slices `processed_df[start:end]` →
   `to_parquet`. Call it once at `{start:0, end:window}` and cache the
   bytes; the consumer hands them back when the frontend asks for `[0, W)`
   unsorted/unfiltered.

4. **Serialization primitives already exist.** `pd_to_obj`
   (`serialization_utils.py:136-149`), `to_parquet` (`:192-242`),
   `sd_to_parquet_b64` (the `all_stats` payload). The wire formats the
   frontend already decodes (`resolveDFData.ts`, `ParquetB64Payload` in
   `DFWhole.ts`) are exactly what we cache.

5. **A hashing precedent exists.** `hash_chain` (`sd_cache.py:38-54`,
   blake2b → 16 hex). The current SD cache key folds in
   `id(self.analysis_klasses)` (`dataflow.py:545-546`) — process-local, no
   good for a persisted cache. The config fingerprint below replaces `id()`
   with stable class identity.

## What "buckaroo configuration" is — the config_id

`config_id` is a stable (cross-process) fingerprint of everything that
determines `merged_sd` and the row window — i.e. the expensive,
data-touching computation. Built like `hash_chain` over canonical JSON:

| In the key (changes the computation) | Out of the key (replay-time display) |
|---|---|
| `analysis_klasses` — `f"{module}.{qualname}"` per class, in order | `column_config_overrides` |
| `sampling_klass` params (`pre_limit`, `serialize_limit`) | `component_config` |
| `init_sd` (merged into `merged_sd`) | `extra_grid_config` |
| `skip_stat_columns` | `pinned_rows` |
| default cleaning / post-processing method (usually none) | `styling_klasses`† |
| `INITIAL_CACHE_VERSION` + optional `cache_version` arg | |

The split is the whole point: the key covers **what touches data**;
display knobs are applied fresh at replay against the cached `merged_sd`,
so re-theming or overriding a column never invalidates the cache and never
needs the frame.

† `styling_klasses` are out of the key because display is regenerated at
replay. Caveat: the cached `merged_sd` only contains stats produced by the
captured `analysis_klasses`. Replay-time styling must only `requires_summary`
stats within that set; `style_column` already falls back to `obj` for
missing stats (`customizations/styling.py:75-76`), so a mismatch degrades
gracefully rather than crashing.

`config_id` is the **configuration** half only — independent of the frame's
contents. The caller owns the **data identity** (xorq build hash, file
content hash) and forms the real cache key as `(data_id, config_id)`.
"Systems where we can figure out the reset" are exactly those that can
compute a stable `data_id` and detect when it moves. "Infinite variation"
falls out: an unbounded set of `(data_id, config_id)` pairs, each mapping
to one bundle — nothing enumerated. `data_id`, if supplied, is stamped into
the bundle so a stored bundle is self-describing. A convenience
`df_fingerprint(df)` (blake2b over `hash_pandas_object`) is offered for
in-memory frames that lack an external identity — but note it touches the
frame, which is fine at produce time (you hold the frame) and irrelevant at
replay (the consumer never does).

## The bundle — `InitialCacheData`

JSON-serializable end to end, so it persists to disk / redis / a build dir.

```python
InitialCacheData = TypedDict('InitialCacheData', {
  'cache_format_version': int,        # bundle schema version
  'config_id': str,
  'data_id': NotRequired[str],        # caller-supplied, optional
  'df_meta': dict,                    # {columns, rows_shown, total_rows, filtered_rows}
  'column_schema': {                  # enough to rebuild a zero-row df with the same a,b,c mapping
      'columns': list,                #   ordered ORIGINAL names (str or tuple for MultiIndex)
      'index': dict,                  #   {kind: 'range'|'single'|'multi', names: [...]}
  },
  'merged_sd': dict,                  # JSON-safe summary dict — source of truth for stats + styling regen
  'first_window': {
      'start': 0, 'end': int, 'total_rows': int,
      'parquet_b64': str,             # to_parquet(processed_df[0:window])
  },
  # config-derived, captured so initial_state is complete in 'buckaroo' mode:
  'buckaroo_options': dict,
  'command_config': dict,
  # fast-path prerenders (skip regen when display knobs are default):
  'df_display_args': dict,
  'all_stats_b64': dict,              # sd_to_parquet_b64(merged_sd) at capture
  'styling_klasses': list,            # f"{module}.{qualname}" for replay regen
})
```

`merged_sd` is the source of truth. `all_stats_b64` and `df_display_args`
are prerenders for the common case (no display overrides); when overrides
*are* passed, the consumer regenerates from `merged_sd` + the zero-row
schema df. Storing `merged_sd` JSON-safe needs a small serializer
(numpy scalars, `np.nan`, histogram lists/dicts) with a round-trip test:
`merged_sd → json → merged_sd → sd_to_parquet_b64` equals the captured
`all_stats_b64`.

## Serving the opening requests

The frontend's opening sequence (server `BuckarooView.tsx`; widget
`BuckarooWidgetInfinite.tsx`):

1. **initial_state** — `df_meta`, `df_data_dict` (`main` empty in infinite
   mode, `all_stats` populated), `df_display_args`, and in buckaroo mode
   `buckaroo_state` / `buckaroo_options` / `command_config`. All served from
   the bundle by `CachedInitial.initial_state()`.
2. **first `infinite_request {start:0, end:1000}`** (`getDs` in
   `gridUtils.ts` requests blocks of 1000). `serve_window` returns the
   cached parquet, echoing the caller's `payload_args` back as `key` and
   `total_rows` as `length`, matching `handle_infinite_request_buckaroo`'s
   response shape.

**The cache boundary** — `serve_window` returns `None` (miss → fall back to
the real source) for anything that isn't the opening window:

| Request | Served from cache? |
|---|---|
| `start==0, end<=window`, no sort, no search | yes |
| scroll past `window` | no — needs the frame |
| any sort | no — sort is whole-dataset |
| any search / filter | no |
| any cleaning / post-processing state change | no |

This keeps each bundle small and bounded (first window + stats + config,
never the whole frame), which is what makes "infinite variation" cheap to
store. Deep scroll, sort, filter, and ops are explicitly the source's job;
the cache only removes the first-paint cost.

## Styling stays configurable

`populate_from_cache_data(bundle, component_config=..., column_config_overrides=...)`:

1. Rebuild a **zero-row DataFrame** from `column_schema` (original column
   names + index structure; dtypes can be `object` — only names/structure
   matter, per fact 2). Same column order ⇒ same `old_col_new_col` a,b,c
   mapping ⇒ aligns with the cached parquet and `merged_sd`.
2. Regenerate `df_display_args` from `merged_sd` + the zero-row df + the
   styling classes + the passed overrides, reusing the **same assembly code**
   as the live path (see refactor below).

With no display knobs passed, the consumer returns the prerendered
`df_display_args` from the bundle directly — zero work. The frame is never
constructed in either case.

## Integration — additive, two thin adapters

Replay is fully **backend-agnostic**: the consumer only ever touches cached
bytes and dicts. Only *production* dispatches per backend (the window
serializer: pandas `to_parquet`, xorq `_window_to_parquet`, polars
`write_parquet`).

- **Refactor (shared by live + cache, no drift):** extract the display-args
  loop at `dataflow.py:705-723` into a module-level
  `build_df_display_args(merged_sd, df, display_klasses, overrides, pinned_rows, extra_grid_config, component_config)`.
  `_handle_widget_change` calls it; so does `populate_from_cache_data`. This
  mirrors the `_window_to_parquet` lift in the #773 plan.
- **Widget:** `BuckarooWidget.from_cache(bundle, **display_knobs)` — builds a
  widget whose traits are set from `CachedInitial`, and whose
  `infinite_request` handler (`buckaroo_widget.py`) tries `serve_window`
  first, falling back to the existing path only on a miss (and only if a
  frame was later bound).
- **Server:** new `POST /load_cache` accepting `{session?, cache_bundle | cache_path, component_config?, column_config_overrides?, ...}`, plus
  `create_session_from_cache` in `data_loading.py`. The WS dispatch in
  `_handle_infinite_request` (`websocket_handler.py:192-240`) tries
  `serve_window` before the dataflow. Mirrors the `LoadExprHandler` shape
  (`handlers.py:371-522`); registered in `app.py`. Session gains an optional
  `cached_initial: CachedInitial | None` field; the real dataflow is bound
  lazily only when a request misses the cache.

## Scope

In:
- `buckaroo/cache/initial_cache.py` — `get_initial_cache_data`,
  `populate_from_cache_data`, `CachedInitial`, the `InitialCacheData` types.
- `buckaroo/cache/fingerprint.py` — `config_fingerprint`, `df_fingerprint`,
  `INITIAL_CACHE_VERSION`.
- JSON-safe `merged_sd` (de)serializer (round-trip tested).
- `build_df_display_args` extracted from `_handle_widget_change`.
- Widget `from_cache` + server `/load_cache` adapters with `serve_window`
  fast paths.
- Tests (below).

Out (v1):
- Caching anything past the first window (sort/filter/scroll/ops stay on the
  source — by design).
- Caching cleaning/post-processing states.
- A built-in on-disk cache store / eviction policy. The bundle is
  serializable; *where* it lives and *when* it resets is the host's job
  (the "reset" the request points at). xorq desktop keys on its build hash.
- Auto-binding the source frame on miss inside the widget unless the caller
  passed one — a pure-cache widget that misses just reports the miss.

## Files

1. `buckaroo/cache/__init__.py`, `buckaroo/cache/initial_cache.py` *(new)* —
   producer/consumer/types. Producer constructs the existing
   `ServerDataflow` / polars / xorq dataflow once, snapshots
   `merged_sd` / `df_meta` / `df_display_args` / `all_stats` and the
   `{0:window}` parquet, computes `config_id`.
2. `buckaroo/cache/fingerprint.py` *(new)* — stable hashing.
3. `buckaroo/serialization_utils.py` — add `serialize_sd` / `deserialize_sd`
   (JSON-safe `merged_sd`) next to `sd_to_parquet_b64`.
4. `buckaroo/dataflow/dataflow.py` — extract `build_df_display_args`;
   `_handle_widget_change` delegates. Pure refactor, existing tests stay green.
5. `buckaroo/buckaroo_widget.py` — `from_cache` classmethod + `serve_window`
   in the infinite handler.
6. `buckaroo/server/data_loading.py` — `create_session_from_cache`.
7. `buckaroo/server/handlers.py`, `app.py`, `session.py`,
   `websocket_handler.py` — `/load_cache` + WS fast path + session field.
8. `tests/unit/cache/test_initial_cache.py`, `test_fingerprint.py`,
   `tests/unit/test_sd_serialize.py`, `tests/unit/server/test_load_cache.py`
   *(new)*.

## Implementation order (TDD, per CLAUDE.md — failing tests, then fix)

1. **Refactor.** Extract `build_df_display_args`. No new tests; existing
   suite stays green. (Separate, low-risk — likely reverted on its own if
   wrong, so its own commit per the global split rule.)
2. **Failing tests.** Bundle all of:
   - `config_fingerprint` is stable across processes and identical for two
     equal configs; differs when an analysis class is added/removed.
   - `serialize_sd` round-trips → `sd_to_parquet_b64` byte-equal to capture.
   - `get_initial_cache_data(df)` → bundle whose `initial_state` /
     `df_display_args` / first-window parquet equal a live `ServerDataflow`'s,
     **with the frame deleted before replay** (`gc`-assert no frame access:
     pass a frame subclass that raises on `__getitem__`/iteration after
     capture, prove `populate_from_cache_data` + `initial_state` +
     `serve_window({0,1000})` never trip it).
   - `serve_window` returns `None` for sort / search / `start>0` / `end>window`.
   - **replay-override parity:** capture a bundle with *no* overrides, then
     `populate_from_cache_data` with a non-trivial `component_config` +
     `column_config_overrides`; assert the resulting `df_display_args` is
     byte-equal to a live `ServerDataflow` built with those same knobs, while
     the raise-on-access frame proves replay never touches data. Confirms
     both knobs are honored at replay via the regeneration path —
     `merge_column_config` + the `main` `component_config` overlay
     (`dataflow.py:709-721`) — not just the prerendered fast path.
   - server `/load_cache` opening sequence (WS `initial_state` + first
     `infinite_request`) matches `/load`, behind the existing server-test
     pattern.
   Push, watch CI fail.
3. **Fix.** Implement the cache module, serializer, adapters, endpoint.
   Push, watch CI green.

## Open questions / risks

- **Class-logic drift.** `config_id` keys on class *name*, not source. If a
  class's logic changes without bumping `INITIAL_CACHE_VERSION` (or a
  per-class `cache_version`), the cache goes stale silently. Mitigation:
  bump `INITIAL_CACHE_VERSION` on releases that change analysis output, and
  recommend hosts fold the buckaroo package version into `data_id`.
- **Non-deterministic sampling.** `ServerSampling.pre_stats_sample`
  (`data_loading.py:28-38`) calls `df.sample(pre_limit)` unseeded for
  >1M-row frames, so two producer runs differ. Not a correctness problem —
  we snapshot one realization — but worth a note; consider a seed param.
- **Backend parity.** Confirm polars / xorq produce the same bundle field
  shapes as pandas (the #773 plan flagged the same verify-step for
  `get_buckaroo_display_state` against `XorqServerDataflow`). Replay is
  uniform; only the produce-time window serializer differs.
- **merged_sd fidelity.** numpy scalars, `np.nan`, nested histogram
  structures must survive JSON round-trip exactly — covered by the
  byte-equal test above.
- **MultiIndex.** Column/index reconstruction for the zero-row df must
  reproduce the exact `old_col_new_col` mapping for MultiIndex frames; test
  with a MultiIndex fixture.
