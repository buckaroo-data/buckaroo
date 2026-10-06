import asyncio
import json
import os
import sys
import tempfile
from unittest import mock

import pandas as pd
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

from buckaroo.server import telemetry
from buckaroo.server.app import make_app as _make_app

# Temp file cleanup fails on Windows due to file locking (WinError 32)
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Temp file locking prevents cleanup on Windows")


def make_app():
    return _make_app(open_browser=False)


def _write_test_csv(path):
    df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie", "Diana", "Eve"], "age": [30, 25, 35, 28, 32],
        "score": [88.5, 92.3, 76.1, 95.0, 81.7]})
    df.to_csv(path, index=False)
    return df


def _string_highlights(df_display_args):
    """The ``highlight_phrase`` of every string column across every display, as
    a set of tuples; ``None`` stands for a column with no highlight."""
    phrases = set()
    for dva in (df_display_args or {}).values():
        for col in ((dva or {}).get("df_viewer_config") or {}).get("column_config", []):
            disp = col.get("displayer_args") or {}
            if disp.get("displayer") == "string":
                phrase = disp.get("highlight_phrase")
                phrases.add(None if phrase is None else tuple(phrase))
    return phrases


async def _async_fetch(port, path, method="GET", body=None):
    """Async HTTP fetch for use inside @gen_test methods."""
    client = tornado.httpclient.AsyncHTTPClient()
    url = f"http://localhost:{port}{path}"
    kwargs = {"method": method}
    if body is not None:
        kwargs["body"] = body
        kwargs["headers"] = {"Content-Type": "application/json"}
    resp = await client.fetch(url, **kwargs, raise_error=False)
    return resp


class TestHealth(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_health_returns_ok(self):
        resp = self.fetch("/health")
        self.assertEqual(resp.code, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "ok")
        self.assertIn("pid", body)
        self.assertIn("started", body)
        self.assertIn("uptime_s", body)


class TestMakeAppDefaultNoBrowser(tornado.testing.AsyncHTTPTestCase):
    """``make_app()`` with no arguments must not open browser windows.

    The CLI passes ``open_browser`` explicitly (``--no-browser``), so the
    default only reaches library callers — tests and scripts that build a
    throwaway server. With the old default of True, every ``/load`` they made
    opened a Chrome window on a server that was gone a moment later."""

    def get_app(self):
        return _make_app()

    def test_default_is_no_browser(self):
        self.assertFalse(self._app.settings["open_browser"])

    def test_load_without_no_browser_opens_nothing(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                with mock.patch("buckaroo.server.handlers.find_or_create_session_window",
                    return_value="opened") as opener:
                    resp = self.fetch("/load", method="POST",
                        body=json.dumps({"session": "default-browser", "path": f.name}),
                        headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)
                self.assertEqual(json.loads(resp.body)["browser_action"], "disabled")
                opener.assert_not_called()
            finally:
                os.unlink(f.name)


class TestLoad(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_load_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "test-1", "path": f.name}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)
                body = json.loads(resp.body)
                self.assertEqual(body["session"], "test-1")
                self.assertEqual(body["rows"], 5)
                self.assertEqual(len(body["columns"]), 3)
            finally:
                os.unlink(f.name)

    def test_load_missing_file(self):
        resp = self.fetch("/load", method="POST",
            body=json.dumps({"session": "test-2", "path": "/nonexistent/file.csv"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 404)

    def test_load_bad_json(self):
        resp = self.fetch("/load", method="POST",
            body="not json",
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 400)

    def test_load_missing_fields(self):
        resp = self.fetch("/load", method="POST",
            body=json.dumps({"session": "x"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 400)

    def test_load_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"not a real xlsx")
            f.flush()
            try:
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "test-3", "path": f.name}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 400)
            finally:
                os.unlink(f.name)

    def test_load_lazy_without_polars_returns_missing_dependency(self):
        # mode="lazy" needs polars. When polars is absent the loader raises
        # ImportError; the handler must surface a clean 400 pointing at the
        # install extra, not a generic 500. Simulate polars-absent by making
        # load_file_lazy raise ImportError (mirrors `pip install buckaroo`
        # without the polars extra).
        def _no_polars(path):
            raise ImportError("No module named 'polars'")

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                with mock.patch("buckaroo.server.handlers.load_file_lazy", _no_polars):
                    resp = self.fetch("/load", method="POST",
                        body=json.dumps({"session": "test-lazy-nopolars",
                            "path": f.name, "mode": "lazy"}),
                        headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 400)
                body = json.loads(resp.body)
                self.assertEqual(body["error_code"], "missing_dependency")
                self.assertIn("buckaroo[polars]", body["message"])
            finally:
                os.unlink(f.name)

    def test_load_buckaroo_with_column_config_overrides(self):
        """POST /load with column_config_overrides should plumb through to
        the headless ServerDataflow so server-mode sessions can match a
        notebook widget's per-column display config (#860 demo case:
        PolarsBuckarooInfiniteWidget(df, init_sd=column_config_overrides, ...))."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                overrides = {"name": {"displayer_args": {"displayer": "string", "max_length": 5000}}}
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "cco-1", "path": f.name, "mode": "buckaroo",
                        "column_config_overrides": overrides}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)

                sessions = self._app.settings["sessions"]
                session = sessions.get("cco-1")
                self.assertIsNotNone(session)
                dvc = session.df_display_args["main"]["df_viewer_config"]
                # header_name carries the original column name; col_name is
                # the renamed (a/b/c/...) version.
                name_col = next(cc for cc in dvc["column_config"]
                    if cc.get("header_name") == "name")
                self.assertEqual(name_col["displayer_args"]["displayer"], "string")
                self.assertEqual(name_col["displayer_args"]["max_length"], 5000)
            finally:
                os.unlink(f.name)

    def test_load_buckaroo_with_extra_grid_config(self):
        """POST /load with extra_grid_config (rowHeight etc.) should
        reach df_viewer_config so AG-Grid picks it up."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                grid_cfg = {"rowHeight": 70, "pinnedRowHeight": 21}
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "egc-1", "path": f.name, "mode": "buckaroo",
                        "extra_grid_config": grid_cfg}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)

                session = self._app.settings["sessions"].get("egc-1")
                dvc = session.df_display_args["main"]["df_viewer_config"]
                self.assertEqual(dvc.get("extra_grid_config"), grid_cfg)
            finally:
                os.unlink(f.name)

    def test_load_buckaroo_with_init_sd(self):
        """POST /load with init_sd should apply to the headless dataflow
        the same way as the widget's init_sd kwarg."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                init_sd = {"name": {"displayer_args": {"displayer": "string", "max_length": 200}}}
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "isd-1", "path": f.name, "mode": "buckaroo", "init_sd": init_sd}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)

                session = self._app.settings["sessions"].get("isd-1")
                dvc = session.df_display_args["main"]["df_viewer_config"]
                name_col = next(cc for cc in dvc["column_config"]
                    if cc.get("header_name") == "name")
                self.assertEqual(name_col["displayer_args"]["displayer"], "string")
                self.assertEqual(name_col["displayer_args"]["max_length"], 200)
            finally:
                os.unlink(f.name)

    def test_load_buckaroo_without_optional_configs_keeps_defaults(self):
        """Default behaviour: omitting the new kwargs leaves
        extra_grid_config as the empty-dict default the headless dataflow
        already emits — same as a notebook BuckarooInfiniteWidget(df)."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "plain-1", "path": f.name, "mode": "buckaroo"}),
                    headers={"Content-Type": "application/json"})
                self.assertEqual(resp.code, 200)

                session = self._app.settings["sessions"].get("plain-1")
                dvc = session.df_display_args["main"]["df_viewer_config"]
                self.assertEqual(dvc.get("extra_grid_config"), {})
            finally:
                os.unlink(f.name)


class TestSessionPage(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_session_page_returns_html(self):
        resp = self.fetch("/s/test-session")
        self.assertEqual(resp.code, 200)
        self.assertIn(b"standalone.js", resp.body)
        self.assertIn(b"<div id=\"root\">", resp.body)


_OPERATOR_DATASETS = [{"label": "boston-pandas", "kind": "pandas",
    "target": "/opt/data/boston-pandas.parquet"}, {"label": "boston-lazy", "kind": "lazy",
        "target": "/opt/data/boston-lazy.parquet"}, {"label": "boston-xorq", "kind": "xorq",
            "target": "/opt/builds/boston-xorq"}]


class TestSessionPageNoHardCodedPaths(tornado.testing.AsyncHTTPTestCase):
    """Vanilla server (no --dataset flags) must not ship the author's
    personal paths. Pre-#811 the page baked in
    ``/tmp/restaurant-complaints-pandas.parquet`` and
    ``/Users/paddy/buckaroo/...`` as defaults."""

    def get_app(self):
        return _make_app(open_browser=False)

    def test_default_no_hard_coded_paths_in_html(self):
        resp = self.fetch("/s/sess-plain")
        self.assertEqual(resp.code, 200)
        body = resp.body.decode("utf-8")
        self.assertNotIn("/tmp/restaurant-complaints-pandas.parquet", body)
        self.assertNotIn("/Users/paddy/buckaroo/restaurant-complaints.parquet", body)
        self.assertNotIn("/tmp/buckaroo-builds-boston/", body)


class TestSessionPageConfiguredDatasets(tornado.testing.AsyncHTTPTestCase):
    """Operator-supplied datasets surface in the engine dropdown. See
    issue #811."""

    def get_app(self):
        return _make_app(open_browser=False, datasets=_OPERATOR_DATASETS)

    def test_configured_datasets_appear_in_html(self):
        resp = self.fetch("/s/sess-dropdown")
        self.assertEqual(resp.code, 200)
        body = resp.body.decode("utf-8")
        for ds in _OPERATOR_DATASETS:
            self.assertIn(ds["label"], body,
                f"dataset label {ds['label']!r} missing from /s/ HTML")
            self.assertIn(ds["target"], body,
                f"dataset target {ds['target']!r} missing from /s/ HTML")


_SCRIPT_BREAKOUT_DATASETS = [{"label": "evil", "kind": "pandas",
    "target": "</script><script>window.__pwned=1</script>"}]


class TestSessionPageScriptTagSafety(tornado.testing.AsyncHTTPTestCase):
    """Dataset targets are embedded inline in a ``<script
    type=\"application/json\">`` block. A target containing
    ``</script>`` must not break out — operator CLI args are
    low-trust, but escaping is cheap and unconditional."""

    def get_app(self):
        return _make_app(open_browser=False, datasets=_SCRIPT_BREAKOUT_DATASETS)

    def test_script_tag_in_target_does_not_break_out(self):
        resp = self.fetch("/s/sess-evil")
        self.assertEqual(resp.code, 200)
        body = resp.body.decode("utf-8")
        # Extract whatever the browser would see between the JSON-data
        # script's open tag and the FIRST ``</script>`` after it (which is
        # what the HTML parser uses as the terminator — there is no
        # nesting in raw text script content). If the operator-supplied
        # target was JSON-encoded but not HTML-script-escaped, the first
        # ``</script>`` is the one *inside* the target string, and the
        # extracted slice is truncated invalid JSON. ``json_encode``
        # rewrites ``</`` to ``<\\/``, so the only ``</script>`` after
        # the open tag is the legitimate terminator.
        open_tag = '<script id="buckaroo-datasets" type="application/json">'
        start = body.index(open_tag) + len(open_tag)
        end = body.index("</script>", start)
        payload = body[start:end]
        # If json_encode is in use, the payload is the entire dataset list
        # encoded as valid JSON — must parse cleanly and round-trip the
        # original target.
        parsed = json.loads(payload)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["target"],
            "</script><script>window.__pwned=1</script>")


class TestDatasetCLIParsing(tornado.testing.AsyncHTTPTestCase):
    """``--dataset NAME=KIND:PATH`` (repeatable) parses into the list of
    dicts that ``make_app(datasets=...)`` consumes. Centralising the
    parse in ``__main__`` keeps it covered by unit tests instead of
    relying on a live argparse invocation."""

    def get_app(self):
        # We don't need a live server for the parse test, but
        # AsyncHTTPTestCase still wants one.
        return _make_app(open_browser=False)

    def test_parse_dataset_spec_three_kinds(self):
        from buckaroo.server.__main__ import parse_dataset_spec

        specs = ["boston-pandas=pandas:/data/boston.parquet", "boston-lazy=lazy:/data/boston.parquet",
            "boston-xorq=xorq:/builds/boston-xorq"]
        parsed = [parse_dataset_spec(s) for s in specs]
        assert parsed == [{"label": "boston-pandas", "kind": "pandas", "target": "/data/boston.parquet"},
            {"label": "boston-lazy", "kind": "lazy", "target": "/data/boston.parquet"},
            {"label": "boston-xorq", "kind": "xorq", "target": "/builds/boston-xorq"}]

    def test_parse_dataset_spec_rejects_unknown_kind(self):
        from buckaroo.server.__main__ import parse_dataset_spec
        with pytest.raises(ValueError):
            parse_dataset_spec("foo=duckdb:/data/foo.parquet")

    def test_parse_dataset_spec_rejects_malformed(self):
        from buckaroo.server.__main__ import parse_dataset_spec
        with pytest.raises(ValueError):
            parse_dataset_spec("just-a-label-no-equals")
        with pytest.raises(ValueError):
            parse_dataset_spec("label=no-colon-after-kind")


class TestWebSocket(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_ws_connect_no_data(self):
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/empty-session")
        ws.close()

    @tornado.testing.gen_test
    async def test_ws_connect_with_data(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                # Load data first (async)
                resp = await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "ws-1", "path": f.name}))
                self.assertEqual(resp.code, 200)

                # Connect WebSocket
                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/ws-1")

                # Should receive initial_state
                msg = await ws.read_message()
                state = json.loads(msg)
                self.assertEqual(state["type"], "initial_state")
                self.assertIn("metadata", state)
                self.assertEqual(state["metadata"]["rows"], 5)

                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_ws_infinite_request(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "ws-2", "path": f.name}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/ws-2")

                # Read and discard initial_state
                await ws.read_message()

                # Send infinite_request
                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {
                        "start": 0, "end": 3,
                        "sourceName": "default", "origEnd": 3
                    }
                }))

                # Should get JSON text frame
                json_frame = await ws.read_message()
                resp = json.loads(json_frame)
                self.assertEqual(resp["type"], "infinite_resp")
                self.assertEqual(resp["length"], 5)
                self.assertEqual(resp["key"]["start"], 0)
                self.assertEqual(resp["key"]["end"], 3)

                # Should get binary Parquet frame
                binary_frame = await ws.read_message()
                self.assertIsInstance(binary_frame, bytes)
                self.assertGreater(len(binary_frame), 0)

                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_ws_sorted_request(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "ws-3", "path": f.name}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/ws-3")
                await ws.read_message()  # initial_state

                # Sort by "b" which is the renamed column for "age"
                # (columns are renamed a, b, c, ... by to_parquet)
                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {
                        "start": 0, "end": 5,
                        "sourceName": "sorted", "origEnd": 5,
                        "sort": "b", "sort_direction": "asc"
                    }
                }))

                json_frame = await ws.read_message()
                resp = json.loads(json_frame)
                self.assertEqual(resp["type"], "infinite_resp")
                self.assertEqual(resp["length"], 5)

                binary_frame = await ws.read_message()
                self.assertIsInstance(binary_frame, bytes)

                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_ws_search_string_pandas_buckaroo(self):
        """Regression for #838: ``search_string`` set via state_change
        must filter the pandas-buckaroo row-fetch dispatch. Fixture has
        5 rows; "Alice" appears 1x, so length drops to 1."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "ws-search", "path": f.name,
                        "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/ws-search")
                await ws.read_message()

                ws.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                await ws.read_message()

                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 5,
                        "sourceName": "default", "origEnd": 5}}))
                r = json.loads(await ws.read_message())
                self.assertEqual(r["type"], "infinite_resp")
                self.assertEqual(r["length"], 1)
                await ws.read_message()  # binary frame

                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_search_string_resets_on_load_reuse(self):
        """Codex P1 (#839): session.search_string must be cleared when
        /load replaces data on an existing buckaroo-mode session — else
        the stale term silently filters the newly loaded dataset."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-search-reuse"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name,
                        "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                ws.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                await ws.read_message()
                ws.close()

                # Reload — fresh client state has empty search_string;
                # the server must match.
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name,
                        "mode": "buckaroo"}))

                ws2 = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws2.read_message()

                ws2.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 5,
                        "sourceName": "default", "origEnd": 5}}))
                r = json.loads(await ws2.read_message())
                self.assertEqual(r["length"], 5,
                    f"stale search_string carried across /load — "
                    f"expected 5 rows, got {r['length']}")
                await ws2.read_message()  # binary
                ws2.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_search_string_echoed_in_overlay_buckaroo_state(self):
        """Codex P1 on #854: when a client sends a search-only state change,
        the server's overlay reply must carry that ``search_string`` inside
        ``buckaroo_state``. Otherwise the JS ``WebSocketModel`` replaces
        ``state.buckaroo_state`` wholesale with a copy missing the key,
        React's local ``buckarooState.search_string`` resets to ``""`` and
        the search box clears on every keystroke."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-search-echo"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()  # initial_state on connect

                ws.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                msg = json.loads(await ws.read_message())
                self.assertEqual(msg["type"], "initial_state")
                self.assertEqual(msg["buckaroo_state"].get("search_string"), "Alice",
                    "overlay reply must echo the client's search_string in buckaroo_state — "
                    "missing key would clobber the React-local value on every keystroke")
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_search_string_per_client_in_dataflow_broadcast(self):
        """Codex P1 on #854: when client A triggers a dataflow rebuild,
        the broadcast ``initial_state`` must carry *A's* per-client
        search_string back to A — and a separate client B sharing the
        session must see *its own* search_string (here ``""``), not A's.
        The session-level snapshot is search-agnostic; the per-client
        value lives only on the handler."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-search-broadcast"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws_a = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws_a.read_message()
                ws_b = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws_b.read_message()

                # A types a search — overlay-only, B unaffected.
                ws_a.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                await ws_a.read_message()  # consume A's overlay

                # Now A triggers a dataflow change. Server rebuilds and
                # broadcasts initial_state to both. Each client's msg
                # should carry their own search_string.
                ws_a.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {"sort": "name"},
                        "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                msg_a = json.loads(await ws_a.read_message())
                msg_b = json.loads(await ws_b.read_message())
                self.assertEqual(msg_a["buckaroo_state"].get("search_string"), "Alice",
                    "A's broadcast copy must preserve A's per-client search_string")
                self.assertEqual(msg_b["buckaroo_state"].get("search_string"), "",
                    "B's broadcast copy must carry B's empty search_string, not A's")
                ws_a.close()
                ws_b.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_seq_echoed_to_originating_client_only(self):
        """#998: a ``buckaroo_state_change`` that carries ``state_seq`` gets
        that value back as ``reply_seq`` on the ``initial_state`` sent to
        the client that made the change. The broadcast copy another
        client receives carries no ``reply_seq``, so that client applies
        it as it does any unsolicited state push."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-seq"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws_a = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                first = json.loads(await ws_a.read_message())
                self.assertNotIn("reply_seq", first, "a fresh connection's initial_state is unsolicited")
                ws_b = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws_b.read_message()

                ws_a.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "state_seq": 7,
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {"sort": "name"},
                        "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": ""}}))
                msg_a = json.loads(await ws_a.read_message())
                msg_b = json.loads(await ws_b.read_message())
                self.assertEqual(msg_a["type"], "initial_state")
                self.assertEqual(msg_a.get("reply_seq"), 7)
                self.assertEqual(msg_b["type"], "initial_state")
                self.assertNotIn("reply_seq", msg_b)
                ws_a.close()
                ws_b.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_seq_echoed_on_highlight_overlay(self):
        """#998: the per-client highlight overlay answers a state change
        too, so it carries ``reply_seq`` like a dataflow broadcast does.
        Otherwise an overlay for an earlier term could land after a later
        dataflow change and put the client's ``buckaroo_state`` back."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-seq-overlay"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                ws.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "state_seq": 3,
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": "Alice"}}))
                overlay = json.loads(await ws.read_message())
                self.assertEqual(overlay["type"], "initial_state")
                self.assertEqual(overlay.get("reply_seq"), 3)
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_seq_answered_for_no_op_change(self):
        """#998: a ``buckaroo_state_change`` with a ``state_seq`` is always
        answered, even when it changes no dataflow field. The client drops
        a reply older than its latest seq, so when a dataflow change (seq 1)
        is followed at once by a ``show_commands`` toggle (seq 2) the seq-1
        reply is dropped as stale. Without a reply for seq 2 the new
        df_display_args / df_data_dict never reach the client. The reply
        carries the change's own ``buckaroo_state`` so the toggle isn't undone."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-seq-noop"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                base = {"post_processing": "", "cleaning_method": "",
                    "quick_command_args": {"search": ["Al"]}, "df_display": "main",
                    "show_commands": False, "sampled": False, "search_string": ""}
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 1, "new_state": base}))
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 2, "new_state": {**base, "show_commands": True}}))

                first = json.loads(await ws.read_message())
                second = json.loads(await asyncio.wait_for(ws.read_message(), timeout=5))
                self.assertEqual(first.get("reply_seq"), 1)
                self.assertEqual(second["type"], "initial_state")
                self.assertEqual(second.get("reply_seq"), 2)
                self.assertTrue(second["buckaroo_state"]["show_commands"])
                self.assertEqual(second["df_display_args"], first["df_display_args"])
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_without_seq_stays_silent_on_no_op(self):
        """A client that sends no ``state_seq`` gets no reply for a change
        that touches no dataflow field, as before #998."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-noseq-noop"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "new_state": {"post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": True, "sampled": False, "search_string": ""}}))
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.read_message(), timeout=0.5)
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_seq_answered_when_change_fails(self):
        """#998: a numbered change that fails still gets a numbered reply.
        By the time seq 2 fails the client has dropped seq 1's reply as
        stale, so an error frame alone leaves it on the data from before
        both changes, with a df_meta that doesn't match the rows the server
        serves. The reply carries the session's current data (seq 1's) and
        the failed change's own ``buckaroo_state``, as the no-op ack does,
        so a search box holding the failed term doesn't see it reverted
        and send it again."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-seq-error"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                base = {"post_processing": "", "cleaning_method": "",
                    "quick_command_args": {"search": ["Al"]}, "df_display": "main",
                    "show_commands": False, "sampled": False, "search_string": ""}
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 1, "new_state": base}))
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 2, "new_state": {**base, "post_processing": "nonexistent_pp"}}))

                first = json.loads(await ws.read_message())
                error = json.loads(await asyncio.wait_for(ws.read_message(), timeout=5))
                reply = json.loads(await asyncio.wait_for(ws.read_message(), timeout=2))
                self.assertEqual(first.get("reply_seq"), 1)
                self.assertEqual(error["type"], "error")
                self.assertEqual(reply["type"], "initial_state")
                self.assertEqual(reply.get("reply_seq"), 2)
                self.assertEqual(reply["df_meta"], first["df_meta"])
                self.assertEqual(reply["df_data_dict"], first["df_data_dict"])
                self.assertEqual(reply["df_display_args"], first["df_display_args"])
                self.assertEqual(reply["buckaroo_state"]["post_processing"], "nonexistent_pp")
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_state_change_seq_overlay_keeps_change_ui_fields(self):
        """#998: the highlight overlay answers a numbered change, so the
        client applies its ``buckaroo_state``. That has to be the change's
        own, as the no-op ack's is. Built from the session's, it puts back
        ``show_commands`` and ``df_display``, which only a dataflow change
        records on the session."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-state-seq-overlay-ui"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                ws.write_message(json.dumps({"type": "buckaroo_state_change", "state_seq": 1,
                    "new_state": {"post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "summary",
                        "show_commands": True, "sampled": False, "search_string": "Al"}}))
                overlay = json.loads(await ws.read_message())
                self.assertEqual(overlay.get("reply_seq"), 1)
                self.assertEqual(overlay["buckaroo_state"]["search_string"], "Al")
                self.assertTrue(overlay["buckaroo_state"]["show_commands"])
                self.assertEqual(overlay["buckaroo_state"]["df_display"], "summary")
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_dataflow_broadcast_keeps_each_clients_live_highlight(self):
        """A dataflow change rebuilds the display config, and each client's
        copy of the broadcast keeps that client's live-search highlight, as
        the overlay and the no-op ack do. Without it the highlight comes and
        goes with whichever reply path ran last."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-broadcast-live-highlight"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws_a = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws_a.read_message()
                ws_b = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws_b.read_message()

                base = {"post_processing": "", "cleaning_method": "",
                    "quick_command_args": {}, "df_display": "main",
                    "show_commands": False, "sampled": False}
                ws_a.write_message(json.dumps({"type": "buckaroo_state_change", "state_seq": 1,
                    "new_state": {**base, "search_string": "Al"}}))
                overlay_a = json.loads(await ws_a.read_message())
                self.assertEqual(_string_highlights(overlay_a["df_display_args"]), {("Al",)})
                ws_b.write_message(json.dumps({"type": "buckaroo_state_change",
                    "new_state": {**base, "search_string": "Bo"}}))
                await ws_b.read_message()

                ws_a.write_message(json.dumps({"type": "buckaroo_state_change", "state_seq": 2,
                    "new_state": {**base, "quick_command_args": {"sort": "name"}, "search_string": "Al"}}))
                msg_a = json.loads(await ws_a.read_message())
                msg_b = json.loads(await ws_b.read_message())
                self.assertEqual(msg_a.get("reply_seq"), 2)
                self.assertEqual(_string_highlights(msg_a["df_display_args"]), {("Al",)})
                self.assertEqual(_string_highlights(msg_b["df_display_args"]), {("Bo",)})
                ws_a.close()
                ws_b.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_clearing_live_search_keeps_committed_highlight(self):
        """Clearing the live search term takes away its own highlight, not
        the committed search's: rows are still filtered by
        ``quick_command_args.search``, and the broadcast that applied it
        highlighted it."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                sid = "ws-clear-live-highlight"
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": sid, "path": f.name, "mode": "buckaroo"}))

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/{sid}")
                await ws.read_message()

                base = {"post_processing": "", "cleaning_method": "",
                    "quick_command_args": {"search": ["Bo"]}, "df_display": "main",
                    "show_commands": False, "sampled": False, "search_string": ""}
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 1, "new_state": base}))
                committed = json.loads(await ws.read_message())
                self.assertEqual(_string_highlights(committed["df_display_args"]), {("Bo",)})
                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 2, "new_state": {**base, "search_string": "Al"}}))
                live = json.loads(await ws.read_message())
                self.assertEqual(_string_highlights(live["df_display_args"]), {("Al",)})

                ws.write_message(json.dumps({"type": "buckaroo_state_change",
                    "state_seq": 3, "new_state": base}))
                cleared = json.loads(await ws.read_message())
                self.assertEqual(cleared.get("reply_seq"), 3)
                self.assertEqual(_string_highlights(cleared["df_display_args"]), {("Bo",)})
                ws.close()
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_ws_request_no_data_loaded(self):
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/no-data-session")

        ws.write_message(json.dumps({
            "type": "infinite_request",
            "payload_args": {"start": 0, "end": 10, "sourceName": "x", "origEnd": 10}}))

        json_frame = await ws.read_message()
        resp = json.loads(json_frame)
        self.assertEqual(resp["type"], "infinite_resp")
        self.assertIn("error_info", resp)

        ws.close()


class TestLoadPushesToWebSocket(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_load_pushes_full_state_to_ws(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                # Create session and connect WS first (no data yet)
                sessions = self._app.settings["sessions"]
                sessions.create("push-1", "")

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/push-1")

                # POST /load (async) — should push full state to the WS client
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "push-1", "path": f.name}))

                msg = await ws.read_message()
                pushed = json.loads(msg)
                self.assertEqual(pushed["type"], "initial_state")
                self.assertEqual(pushed["metadata"]["rows"], 5)
                self.assertIn("df_display_args", pushed)
                self.assertIn("df_data_dict", pushed)
                self.assertIn("df_meta", pushed)

                ws.close()
            finally:
                os.unlink(f.name)


class TestLoadTelemetry(tornado.testing.AsyncHTTPTestCase):
    """#996: /load takes ``telemetry_url`` the way /load_expr does (#943, #944):
    the sink is built once, stored on the session for the WS first-pull spans,
    and the load's steps emit ``firstpull.*`` records to it."""

    TELEMETRY_URL = "http://companion.invalid/internal/telemetry"

    def get_app(self):
        return make_app()

    async def _load(self, sid, path, captured, **extra):
        # Capture records in-process: make_http_sink -> list.append, so the
        # wiring (telemetry_url -> context -> spans) is what's under test. The
        # real POST has its own test (test_telemetry_sink.py).
        with mock.patch.object(telemetry, "make_http_sink", lambda url, **kw: captured.append):
            return await _async_fetch(self.get_http_port(), "/load", method="POST",
                body=json.dumps({"session": sid, "path": path,
                    "telemetry_url": self.TELEMETRY_URL, **extra}))

    async def _first_pull(self, sid):
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/{sid}")
        await ws.read_message()  # discard initial_state
        ws.write_message(json.dumps({
            "type": "infinite_request",
            "payload_args": {"start": 0, "end": 5, "sourceName": "default", "origEnd": 5}}))
        await ws.read_message()  # json frame
        await ws.read_message()  # binary frame
        ws.close()

    @tornado.testing.gen_test
    async def test_load_polars_emits_session_correlated_firstpull_spans(self):
        """A polars /load with telemetry_url emits the load's steps as
        firstpull.* records under the outer firstpull.load total, every one
        carrying the session as its trace and ``attrs.session``."""
        captured: list = []
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                resp = await self._load("ld-telem", f.name, captured,
                    mode="buckaroo", backend="polars")
                self.assertEqual(resp.code, 200)
            finally:
                os.unlink(f.name)

        names = [r["name"] for r in captured]
        for name in ("firstpull.load", "firstpull.file_load",
                     "firstpull.dataflow_construct", "firstpull.metadata"):
            self.assertIn(name, names, f"missing {name}; got {names}")
        self.assertTrue(all(r["trace"] == "ld-telem" for r in captured),
            f"all spans must carry the session trace; got {[r['trace'] for r in captured]}")
        self.assertTrue(all(r["source"] == "server" for r in captured))
        self.assertTrue(all(r["attrs"]["session"] == "ld-telem" for r in captured),
            f"all spans must carry attrs.session; got {[r['attrs'] for r in captured]}")
        outer = next(r for r in captured if r["name"] == "firstpull.load")
        self.assertEqual(outer["attrs"]["backend"], "polars")
        # The steps nest inside the outer total, so they close before it does.
        for r in captured:
            self.assertLessEqual(r["t_end_ms"], outer["t_end_ms"])

    @tornado.testing.gen_test
    async def test_load_pandas_emits_firstpull_spans(self):
        """The default pandas backend goes through the same spans."""
        captured: list = []
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                resp = await self._load("ld-pd-telem", f.name, captured, mode="buckaroo")
                self.assertEqual(resp.code, 200)
            finally:
                os.unlink(f.name)
        names = [r["name"] for r in captured]
        for name in ("firstpull.load", "firstpull.file_load",
                     "firstpull.dataflow_construct", "firstpull.metadata"):
            self.assertIn(name, names, f"missing {name}; got {names}")
        self.assertEqual(next(r for r in captured if r["name"] == "firstpull.load")
            ["attrs"]["backend"], "pandas")

    @tornado.testing.gen_test
    async def test_load_stores_sink_so_ws_first_pull_emits(self):
        """The sink built by /load is stored on the session, so the WS handler
        (a separate async context) emits firstpull.ws_first_payload through it,
        and builds it exactly once rather than again in the WS path."""
        captured: list = []
        sink_factory = mock.MagicMock(side_effect=lambda url, **kw: captured.append)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                with mock.patch.object(telemetry, "make_http_sink", sink_factory):
                    resp = await _async_fetch(self.get_http_port(), "/load", method="POST",
                        body=json.dumps({"session": "ld-ws", "path": f.name,
                            "mode": "buckaroo", "backend": "polars",
                            "telemetry_url": self.TELEMETRY_URL}))
                    self.assertEqual(resp.code, 200)
                    await self._first_pull("ld-ws")
            finally:
                os.unlink(f.name)
        self.assertEqual(sink_factory.call_count, 1,
            f"sink must be built once in /load and reused; got {sink_factory.call_count}")
        ws_span = next((r for r in captured if r["name"] == "firstpull.ws_first_payload"), None)
        self.assertIsNotNone(ws_span, f"no ws_first_payload span; got {[r['name'] for r in captured]}")
        self.assertEqual(ws_span["trace"], "ld-ws")

    @tornado.testing.gen_test
    async def test_load_rearms_first_pull_telemetry_on_repeat_load(self):
        """Each /load into an existing session re-arms first-pull telemetry
        (#944): the refreshed page opens a new WS and pulls a fresh
        time-to-first-rows, so the second pull's span must reach the second
        request's sink, not be dropped because the flag stayed True."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                first: list = []
                await self._load("ld-rearm", f.name, first, mode="buckaroo")
                await self._first_pull("ld-rearm")
                self.assertIn("firstpull.ws_first_payload", [r["name"] for r in first])

                second: list = []
                await self._load("ld-rearm", f.name, second, mode="buckaroo")
                await self._first_pull("ld-rearm")
                self.assertIn("firstpull.ws_first_payload", [r["name"] for r in second],
                    "a repeat /load must re-arm first-pull telemetry")
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_load_without_telemetry_url_clears_sink(self):
        """No telemetry_url: the sink is never built, and a sink left on the
        session by an earlier load is unbound, so the WS first pull emits
        nothing. The flag is still re-armed (perf logging reads it too)."""
        sessions = self._app.settings["sessions"]
        stale = sessions.create("ld-silent", "")
        stale.tele_sink = lambda record: None
        stale._perf_first_payload_seen = True
        sink_factory = mock.MagicMock()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                with mock.patch.object(telemetry, "make_http_sink", sink_factory):
                    resp = await _async_fetch(self.get_http_port(), "/load", method="POST",
                        body=json.dumps({"session": "ld-silent", "path": f.name}))
                self.assertEqual(resp.code, 200)
            finally:
                os.unlink(f.name)
        sink_factory.assert_not_called()
        session = sessions.get("ld-silent")
        self.assertIsNone(session.tele_sink)
        self.assertFalse(session._perf_first_payload_seen)
