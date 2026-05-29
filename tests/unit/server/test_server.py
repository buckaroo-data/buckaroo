import json
import os
import sys
import tempfile

import pandas as pd
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

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
