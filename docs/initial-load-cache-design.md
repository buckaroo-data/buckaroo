# Initial-load cache — serve the first render without touching the data

## Status
Design only. Branch `feat/initial-load-cache`, PR #877. Core decisions locked in a
design review (recorded under Decisions). Two follow-ups split out: #880 (trim the
summary-stats wire payload to what the frontend reads) and #881 (DFViewer transport
abstraction — JSON / b64-parquet / binary per embedding).

## Problem

Buckaroo's first render is expensive: sample the frame, run the analysis pipeline,
style every column, serialize the first window. For a xorq expression the cost is
*executing the expression*; for a large pandas frame it's the sample+analysis. That
work happens on every mount / session open, even when neither the data nor the config
changed since last time.

The driving consumer is xorq desktop / pydata-app, where the expression's deterministic
build hash is a natural data identity. Such hosts can tell when the data changed, so
they should be able to hand Buckaroo a precomputed first-render bundle and skip the
pipeline entirely — *as long as the bundle provably matches the widget's configuration*.

## The handshake — validate, never blindly trust

The spine of the feature. The backend provides an **optional** cache bundle to the
widget/dataflow *alongside* the df/expr (which is held but not executed):

```
widget computes its OWN config_id from its live analysis_klasses + config,
and reads its live schema (df.columns/dtypes, or expr.schema() — no execution)
        │
   ┌────┴───────────────────────────────┐
   │ config_id + schema + version match  │ → hydrate traits from the bundle;
   └────┬───────────────────────────────┘    df/expr NEVER touched for first render
        │ any mismatch
        ▼
   warnings.warn(reason) → fall through to the normal pipeline (touch/execute df/expr)
```

Rules:
- The widget computes `config_id` **itself** from its own klasses and compares — it does
  not read-and-trust the bundle's claimed id. A cached SD that doesn't match the live
  `analysis_klasses` (or sampling / `init_sd` / `skip_stat_columns`) is rejected.
- A stale or foreign bundle costs a `warnings.warn` plus a normal compute — never a wrong
  render. The cache is an optimization hint, not a source of truth.
- The df/expr must be **available but unexecuted** so the fallback works. The win is that
  on a match it stays unexecuted. Out-of-window scroll / sort / filter / ops after a match
  use the normal push-down path, exactly as today.

This subsumes two guards that would otherwise be separate: **schema** validation (the
widget has the df/expr, so the live schema is free — no execution) and **version** /
config staleness both surface here as a warn-and-recompute, not a silent mis-serve.

## The two functions

```python
# buckaroo/cache/initial_cache.py

def get_initial_cache_data(
    df,                          # pd.DataFrame | pl.DataFrame | xorq expr
    *,
    analysis_klasses=None, styling_klasses=None, sampling_klass=None,
    init_sd=None, skip_stat_columns=None,
    window=1000,                 # rows pre-serialized for the first infinite_request
    data_id=None, cache_version=None,
) -> tuple[str, InitialCacheData]:
    """Run the pipeline ONCE and snapshot it. Returns (config_id, bundle)."""
```

The **producer**. The **consumer** is the handshake above: construct the widget/dataflow
with `initial_cache=bundle`; it validates and either hydrates or warns+recomputes.
Internally that's two helpers:

```python
def cache_mismatch_reason(bundle, *, analysis_klasses, sampling_klass, init_sd,
                          skip_stat_columns, schema) -> str | None:
    """None ⇒ safe to use. Else a human-readable reason for the warning."""

def apply_initial_cache(target, bundle) -> None:
    """Set df_data_dict / df_display_args / df_meta from the bundle. No dataflow built."""
```

## Decisions (locked)

- **Driving consumer:** xorq desktop / pydata-app. Expr execution is the cost to avoid;
  the build hash is the host's `data_id`.
- **config_id covers the data-touching computation only.** In: `analysis_klasses`
  (`module.qualname`, ordered), `sampling_klass` params, `init_sd`, `skip_stat_columns`,
  `INITIAL_CACHE_VERSION` (+ optional `cache_version` arg). Out (replay-time display knobs,
  regenerated from the bundle, never invalidate the cache): `column_config_overrides`,
  `component_config`, `extra_grid_config`, `pinned_rows`, `styling_klasses`. The handshake
  validates `config_id` **and** the live schema.
- **Stats storage:** the full `merged_sd` **minus `value_counts`** (nothing at replay
  recomputes from it), persisted losslessly as **binary parquet** via a type-tagged cell
  codec — **no pickle**. The codec tags the non-JSON-native types so they reconstruct
  exactly: `pd.Timestamp`/`pd.Timedelta`, stdlib `datetime`/`date`/`time`/`timedelta`,
  `Decimal`, `bytes`, numpy scalars, `np.datetime64`. Round-trip is **tested across all
  three backends** (pandas/polars/xorq emit different temporal/exotic types — see below).
- **Server stats delivery unchanged.** Replay reproduces today's `parquet_b64` in
  `initial_state`. Shrinking that payload is #880; choosing a binary transport is #881.
  Neither is in this PR.
- **No b64 in the persisted artifact** — parquet on disk; b64 only materializes at serve
  time where the existing wire protocol uses it.

### Backend temporal/exotic type surface (why cross-backend tests matter)

| type | pandas | polars | xorq |
|---|---|---|---|
| `pd.Timestamp` / `pd.Timedelta` | ✓ min/max/mode | — | — |
| stdlib `datetime`/`date`/`time`/`timedelta` | — | ✓ (`pl_stats_v2.py:86,91,92`) | possible via `_to_python_scalar` |
| `decimal.Decimal` | — | ✓ | — |
| `bytes` | — | ✓ | — |
| `np.datetime64` | mode → Timestamp | — | → `datetime.date` |

No pyarrow scalars anywhere. (`b64decode` itself is sub-ms to a few ms; the cost of b64 is
the flat +33% size, which is why the on-disk bundle stays binary.)

## Key codebase facts

1. **One terminal assembly point.** The first render is built in `_handle_widget_change`
   (`dataflow.py:679-723`) from `widget_args_tuple = (id, processed_df, merged_sd)` into
   `df_data_dict` / `df_display_args` / `df_meta`. The server reads the same three via
   `get_buckaroo_display_state` (`data_loading.py:67-89`).
2. **Styling never reads row values.** `get_dfviewer_config(sd, df)` (`styling_core.py:422-429`)
   → `style_columns` (`:432-473`) + `get_left_col_configs` (`:326-370`). `style_column`
   (`customizations/styling.py:70-142`) reads only the per-column SD entry; `old_col_new_col`
   and `get_left_col_configs` read only `df.columns` / `df.index` structure. So
   `df_display_args` is a pure function of `(merged_sd, column schema)` — a **zero-row
   DataFrame** regenerates it exactly. This is what keeps styling/component config
   configurable at replay without the data.
3. **The window is one call, exactly 1000 rows.** First paint fires a single
   `infinite_request {start:0, end:1000}` (`gridUtils.ts` `getDs`); the +200 prefetch
   (`SmartRowCache.maybeMakeLeadingRequest`) only fires after a scroll. So `serve_window`'s
   predicate is `start==0 ∧ end≤1000 ∧ no sort ∧ no search`. `handle_infinite_request_buckaroo`
   (`data_loading.py:92-130`) is the slice→`to_parquet` to cache against.
4. **Serialization primitives exist.** `to_parquet` (`serialization_utils.py:192-242`),
   `sd_to_parquet_b64` (`:397-440`) and its inverse (`:324`). The existing per-cell codec is
   **lossy** for temporal/Series (`default=str`, `:361-394`) — the type-tagged codec extends it.
5. **Hash precedent:** `hash_chain` (`sd_cache.py:38-54`). The live SD cache keys on
   `id(analysis_klasses)` (`dataflow.py:545-546`) — process-local; `config_id` replaces that
   with stable `module.qualname`.
6. **Wide frames already capped** at `max_columns=250` (`dataflow_extras.py`), so the cached
   window is column-bounded.

## The bundle — `InitialCacheData`

On disk: parquet files (binary) + a small JSON manifest. No b64.

```python
InitialCacheData = {
  'cache_format_version': int,
  'config_id': str,
  'data_id': str | None,              # caller-supplied; self-describing
  'df_meta': dict,                    # columns, rows_shown, total_rows, filtered_rows
  'column_schema': {                  # rebuild a zero-row df with the same a,b,c mapping
      'columns': list,                #   ordered ORIGINAL names (str | tuple for MultiIndex)
      'index': dict,                  #   {kind: range|single|multi, names: [...]}
      'dtypes': list,                 #   for the live-schema handshake check
  },
  'sd_parquet': '<file>',             # merged_sd minus value_counts, lossless type-tagged parquet
  'first_window_parquet': '<file>',   # to_parquet(processed_df[0:window]), binary
  'first_window': {'start': 0, 'end': int, 'total_rows': int},
  'df_display_args': dict,            # prerender for the zero-override common case
  'buckaroo_options': dict, 'command_config': dict,   # config-derived; complete the initial_state
  'styling_klasses': list,            # module.qualname, for replay regeneration
}
```

The `all_stats` wire payload (`{format:'parquet_b64', ...}`) is derived from `sd_parquet`
at serve time (or stored prerendered) to match the existing protocol exactly.

## Styling stays configurable

`initial_cache` + `column_config_overrides` / `component_config` at construction:
1. Rebuild a **zero-row DataFrame** from `column_schema` (names + index structure; dtypes
   need only match for the schema check). Same column order ⇒ same `old_col_new_col`
   mapping ⇒ aligns with the cached parquet and SD.
2. Regenerate `df_display_args` from the SD + zero-row df + styling klasses + overrides,
   reusing the **same assembly code** as the live path (refactor below). No display knobs ⇒
   use the prerendered `df_display_args` directly (zero work). The frame is never built.

## Serving the opening requests (on a successful handshake)

1. **initial_state** — `df_meta`, `df_data_dict` (`main` empty in infinite mode, `all_stats`
   from the bundle), `df_display_args`, and in buckaroo mode `buckaroo_state` /
   `buckaroo_options` / `command_config`.
2. **first `infinite_request {0,1000}`** — `serve_window` returns the cached parquet, echoing
   `payload_args` as `key` and `total_rows` as `length`.

Out-of-window scroll / sort / search / ops fall through to the normal source path (the
df/expr is present, unexecuted until now). That keeps each bundle small (first window +
SD + config), which is what makes unbounded `(data_id, config_id)` variation cheap.

## Integration — additive

- **Refactor:** extract the display-args loop (`dataflow.py:705-723`) into module-level
  `build_df_display_args(...)`; `_handle_widget_change` and the cache path both call it.
  Mirrors the `_window_to_parquet` lift in the #773 plan.
- **Widget:** new `initial_cache=` kwarg on `BuckarooWidget.__init__` (`buckaroo_widget.py:125`).
  Before building `InnerDataFlow`, run the handshake; on match, `apply_initial_cache` + return.
- **Server:** `/load` and `/load_expr` accept an `initial_cache` field; the dataflow runs the
  handshake before executing. WS `serve_window` fast path before the dataflow. Session keeps
  the path/build_dir it already has (`session.py:18-36`) for the unexecuted-fallback.

## Scope

In: `buckaroo/cache/` (producer, handshake helpers, types, type-tagged SD codec, fingerprint);
`build_df_display_args` refactor; widget `initial_cache` kwarg + server field; tests.

Out: trimming the stats *wire* payload (#880); a transport abstraction / binary stats on the
server (#881); caching anything past the first window (sort/filter/scroll/ops stay on the
source, by design); a built-in on-disk cache store / eviction (the host owns where bundles
live and when they reset — xorq keys on its build hash).

## Files

1. `buckaroo/cache/__init__.py`, `initial_cache.py` *(new)* — producer + handshake +
   `apply_initial_cache` + types.
2. `buckaroo/cache/fingerprint.py` *(new)* — `config_fingerprint`, `INITIAL_CACHE_VERSION`.
3. `buckaroo/serialization_utils.py` — type-tagged lossless SD↔parquet codec (extends the
   existing lossy encoder; drops `value_counts`).
4. `buckaroo/dataflow/dataflow.py` — extract `build_df_display_args`; `_handle_widget_change`
   delegates. Pure refactor.
5. `buckaroo/buckaroo_widget.py` — `initial_cache` kwarg + handshake.
6. `buckaroo/server/{handlers,app,session,websocket_handler}.py`, `data_loading.py` —
   `initial_cache` field, handshake, `serve_window` fast path.
7. `tests/unit/cache/` + `tests/unit/test_sd_codec.py` *(new)*.

## Implementation order (TDD — failing tests, then fix)

1. **Refactor.** Extract `build_df_display_args`. Existing suite stays green. Own commit.
2. **Failing tests** (one commit):
   - `config_fingerprint` stable across processes; identical for equal configs; differs when
     an analysis class is added/removed.
   - **SD codec cross-backend round-trip:** same temporal / `Decimal` / `bytes` / histogram
     fixtures → each of pandas/polars/xorq stats → encode → decode → equal. (`value_counts`
     absent.)
   - `get_initial_cache_data(df)` → bundle whose `initial_state` / `df_display_args` /
     first-window parquet equal a live `ServerDataflow`'s, **with the frame raising on access**
     (frame subclass that raises on `__getitem__`/iteration after capture; prove the match path
     + `serve_window({0,1000})` never trip it).
   - **handshake mismatch:** a bundle whose `config_id` (wrong `analysis_klasses`) or schema
     differs from the widget's live config ⇒ `warnings.warn` **and** a normal compute (the
     raise-on-access frame *is* touched). Assert both.
   - **replay-override parity:** capture with no overrides, then construct with non-trivial
     `component_config` + `column_config_overrides`; `df_display_args` byte-equal to a live
     `ServerDataflow` with the same knobs, frame untouched.
   - `serve_window` returns `None` for sort / search / `start>0` / `end>window`.
   - server opening sequence (`initial_state` + first `infinite_request`) on a matching bundle
     equals `/load`, with the expr unexecuted.
   Push, watch CI fail.
3. **Fix.** Cache module, codec, refactor wiring, widget kwarg, server field. Push, watch green.

## Open questions / risks

- **Version granularity.** Recommend a single global `INITIAL_CACHE_VERSION` + class
  `module.qualname` in `config_id`; no per-class `cache_version` (YAGNI). The handshake catches
  mismatches loudly, so silent staleness only happens if a class's logic changes *without* a
  version bump — mitigated by bumping `INITIAL_CACHE_VERSION` on releases that change analysis
  output, and by hosts folding the buckaroo version into `data_id`. **Confirm.**
- **Bundle transport to the server.** Recommend by **path** (server reads the parquet+manifest;
  avoids a multi-MB inline JSON), inline allowed for flexibility. **Confirm.**
- **Non-deterministic sampling.** `ServerSampling.pre_stats_sample` (`data_loading.py:28-38`)
  samples unseeded for >1M-row frames, so two producer runs differ. Fine (we snapshot one
  realization); consider a seed param.
- **Backend parity.** Confirm polars/xorq bundle field shapes match pandas (the #773 plan flagged
  the same for `get_buckaroo_display_state` vs `XorqServerDataflow`). Replay is uniform; only the
  produce-time window serializer differs per backend.
- **MultiIndex.** Zero-row df reconstruction must reproduce the exact `old_col_new_col` mapping;
  test with a MultiIndex fixture.
