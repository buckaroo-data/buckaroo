# Plan — Issue #773: `POST /load_expr` for `XorqBuckarooInfiniteWidget`

Standalone server can't construct `XorqBuckarooInfiniteWidget` —
`LoadHandler` is parquet/CSV-path-only and the xorq widget needs a
serialized expression (xorq build dir), not a file path. Result: any
host driving the server (incl. the PyData London demo's pydata-app)
ends up paging over a materialized parquet, defeating the push-down
design the xorq widget was built for.

## Direction

**Option A** — new endpoint `POST /load_expr`, per the issue. Keeps
`LoadHandler` pandas/polars-shaped; isolates the xorq dependency to a
separate handler that can be skipped when xorq isn't installed.

Widget itself (`XorqBuckarooInfiniteWidget`,
`buckaroo/xorq_buckaroo.py:296`) and dataflow (`XorqDataflow`,
`xorq_buckaroo.py:181`) already exist and push sort/limit/offset down
via `expr.limit(end-start, offset=start).to_pyarrow()`. This plan
wires the **server load + WebSocket dispatch + state-change** to that
machinery. No widget changes; one widget-side refactor (lift a
staticmethod to module level so the server can call it too).

## Resolved from codebase exploration

- `xo.load_expr(build_dir)` (xorq/ibis_yaml/compiler.py:739) is a
  function that returns a bare ibis expression. `help()` shows
  `ExprLoader` because of `@functools.wraps`, but the function itself
  returns the expr — no wrapper to store on the session.
- `xo.build_expr(expr, builds_dir=tmp_path)` writes a build dir and
  returns its path. Tests build fixtures on the fly; no checked-in
  artifact needed.
- `CustomizableDataflow._handle_widget_change` (dataflow.py:482) is
  an `@observe('widget_args_tuple')` on the **dataflow itself**.
  Populates `df_display_args` and `df_data_dict` on the dataflow.
  The widget's `_handle_widget_change` is a duplicate copy for the
  widget class. **Server does not need to instantiate the widget** —
  just a `XorqDataflow` subclass with `XorqInfiniteSampling`.

## Decisions

1. **Mode discriminator**: `session.mode = "buckaroo"` for both
   pandas-buckaroo and xorq. Add `session.backend = "pandas" | "xorq"`
   to discriminate inside the buckaroo arm. Frontend doesn't care;
   same JS widget renders.

2. **Session fields**: add `session.xorq_dataflow: Any = None` and
   `session.expr: Any = None`. Two parallel fields (not a single
   overloaded `dataflow`) so types stay distinct.

3. **Server-side xorq dataflow**: new file `buckaroo/server/xorq_loading.py`
   containing `XorqServerDataflow(XorqDataflow)` with `sampling_klass
   = XorqInfiniteSampling`. Mirrors `ServerDataflow(CustomizableDataflow)`
   in `data_loading.py`. Xorq import surface fully isolated to this
   module.

4. **Refactor**: extract `XorqBuckarooInfiniteWidget._window_to_parquet`
   (the push-down arrow→parquet slice at `xorq_buckaroo.py:361`) into
   a module-level `_window_to_parquet(processed_df, start, end,
   sort_col=None, ascending=True) -> bytes` in `xorq_buckaroo.py`.
   The widget's staticmethod becomes a one-line delegate. Server's
   `handle_infinite_request_xorq` imports the helper. One
   implementation of the push-down path — format can't drift between
   Jupyter and server.

5. **State change in v1**: loosen `_handle_buckaroo_state_change` to
   accept xorq sessions. `XorqAutocleaning` already implements
   push-down Search. Includes a test that proves Search round-trips
   to the backend.

6. **Optional dependency**: lazy `import` inside `LoadExprHandler.post`.
   Missing xorq → 501 `xorq_not_installed` with a `pip install
   buckaroo[xorq]` hint. Other endpoints unaffected.

7. **Stats latency**: synchronous in v1, matching pandas/polars
   `/load`. Async streaming stats (esp. for search) tracked
   separately in [`async-stats.md`](./async-stats.md) — biggest
   payoff is search-on-remote-backend where each keystroke
   re-runs the stats pipeline.

8. **Dispatch shape**: branch inside each existing `mode == "buckaroo"`
   arm at three sites:
   - `websocket_handler.py:_handle_infinite_request`
   - `websocket_handler.py:_handle_buckaroo_state_change`
   - `session.py:build_state_message`

   Each site: `if session.mode == "buckaroo":` then
   `if session.backend == "xorq": ... else: ...` inside.

## Scope

In:
- `POST /load_expr` endpoint accepting `{build_dir, session?,
  prompt?, no_browser?, component_config?}`.
- `XorqServerDataflow` (in `xorq_loading.py`).
- `handle_infinite_request_xorq(xorq_dataflow, payload_args)`
  (in `xorq_loading.py`) reusing `_window_to_parquet`.
- `session.backend`, `session.xorq_dataflow`, `session.expr` fields.
- WS dispatch updated at the three sites above.
- Three tests behind `pytest.importorskip("xorq.api")`.

Out:
- Widget changes beyond the refactor.
- Async stats (separate plan).
- Streaming exprs over WS.
- `cache_dir` arg (YAGNI; xorq defaults to `~/.cache/xorq`).
- Inline-bytes for `/load` (#768) — adjacent, separate PR.

## Files

1. **`buckaroo/xorq_buckaroo.py`** — extract `_window_to_parquet` to
   module level. Widget's staticmethod becomes `return
   _window_to_parquet(...)`. Pure refactor.
2. **`buckaroo/server/xorq_loading.py`** *(new)* — lazy-imports `xorq.api`.
   Contains `XorqServerDataflow(XorqDataflow)`, a `load_xorq_expr(build_dir)`
   helper, `get_xorq_buckaroo_display_state(xorq_dataflow)` (if the
   pandas `get_buckaroo_display_state` doesn't work as-is — verify
   before deciding), and `handle_infinite_request_xorq(xorq_dataflow,
   payload_args)`.
3. **`buckaroo/server/handlers.py`** — add `LoadExprHandler`.
   Lazy-imports `xorq_loading` inside `post()`; ImportError → 501.
   Sets `session.mode = "buckaroo"`, `session.backend = "xorq"`,
   `session.expr`, `session.xorq_dataflow`. Otherwise mirrors
   `LoadHandler`'s shape (error envelope, browser handling, push
   state to WS clients).
4. **`buckaroo/server/app.py`** — register `(r"/load_expr",
   LoadExprHandler)`.
5. **`buckaroo/server/session.py`** — add `backend: str = "pandas"`,
   `xorq_dataflow: Any = None`, `expr: Any = None` to `SessionState`.
   Update `build_state_message` so the existing `if session.mode ==
   "buckaroo":` branch handles both backends (reads from
   `session.xorq_dataflow` when `backend == "xorq"`, else
   `session.dataflow`).
6. **`buckaroo/server/websocket_handler.py`** — inside the existing
   `mode == "buckaroo"` arms of `_handle_infinite_request` and
   `_handle_buckaroo_state_change`, dispatch on `session.backend`.
   For `xorq`: call `handle_infinite_request_xorq` and mutate
   `xorq_dataflow.quick_command_args` / `.post_processing_method`
   respectively.
7. **`tests/unit/server/test_load_expr.py`** *(new)* — three tests
   behind `pytest.importorskip("xorq.api")`:
   - **400 case**: POST `/load_expr` with no `build_dir` → 400.
   - **WS push-down**: build a memtable via `xo.build_expr(...,
     builds_dir=tmp_path)`, POST `/load_expr` with the returned path,
     open `/ws/<session>` (using `tornado.websocket.websocket_connect`
     per `test_server.py`'s pattern), send `infinite_request{start:0,
     end:10}`, parse the binary parquet frame, assert 10 rows.
   - **WS state-change push-down**: same setup, send a
     `buckaroo_state_change` with a Search term that filters most
     rows out, then `infinite_request`, assert the parquet has the
     expected reduced row count. Proves Search hits the backend, not
     Python.

## Handler shape

```
POST /load_expr
body: {
  session?: str,            # minted if absent
  build_dir: str,           # abs path to a xorq build dir
  prompt?: str,
  no_browser?: bool,
  component_config?: dict,
}
response (200): {
  session, server_pid, browser_action,
  rows, columns: [{name, dtype}], path: build_dir
}
errors:
  400 missing_field        — no build_dir
  404 build_dir_not_found  — xo.load_expr raises FileNotFoundError
  501 xorq_not_installed   — ImportError on xorq.api
  500 load_expr_error      — anything else (with traceback under BUCKAROO_DEBUG)
```

## Implementation order (TDD per global CLAUDE.md)

1. **Commit 1 — refactor.** Extract `_window_to_parquet` to module
   level in `xorq_buckaroo.py`. Widget staticmethod becomes one-line
   delegate. Existing widget tests stay green. No new tests.
2. **Commit 2 — failing tests.** Add the three tests above. They
   fail because `/load_expr` returns 404 (route doesn't exist).
   Push, watch CI fail.
3. **Commit 3 — fix.** Handler + route + session fields + dispatch
   branches + state-change gate + `xorq_loading.py`. Push, watch CI
   green.

## Open question still worth confirming before coding

**Does `get_buckaroo_display_state(xorq_dataflow)` (the existing
pandas helper in `data_loading.py:58`) work as-is against
`XorqServerDataflow`?** The dataflow surface looks identical
(`df_data_dict`, `df_display_args`, `df_meta`,
`buckaroo_options`, `command_config`, …) but `XorqDataflow._get_summary_sd`
re-keys by rewritten column names (xorq_buckaroo.py:208), which
shouldn't affect the display-state extraction, only the internal sd
shape. If they differ in any field, carve out `get_xorq_buckaroo_display_state`
in `xorq_loading.py`. Verify in Commit 1 (or via a small probe before
Commit 1) so we don't discover it in Commit 3.
