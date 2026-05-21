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
