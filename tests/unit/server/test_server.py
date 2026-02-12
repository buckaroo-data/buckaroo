import json
import os
import tempfile

import pandas as pd
import tornado.httpclient
import tornado.testing
import tornado.websocket

from buckaroo.server.app import make_app as _make_app


def make_app():
    return _make_app(open_browser=False)


def _write_test_csv(path):
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "age": [30, 25, 35, 28, 32],
        "score": [88.5, 92.3, 76.1, 95.0, 81.7],
    })
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
        self.assertEqual(body, {"status": "ok"})


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
            "payload_args": {"start": 0, "end": 10, "sourceName": "x", "origEnd": 10}
        }))

        json_frame = await ws.read_message()
        resp = json.loads(json_frame)
        self.assertEqual(resp["type"], "infinite_resp")
        self.assertIn("error_info", resp)

        ws.close()


class TestLoadPushesToWebSocket(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_load_pushes_metadata_to_ws(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_test_csv(f.name)
            try:
                # Create session and connect WS first (no data yet)
                sessions = self._app.settings["sessions"]
                sessions.create("push-1", "")

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/push-1")

                # POST /load (async) — should push metadata to the WS client
                await _async_fetch(self.get_http_port(), "/load",
                    method="POST",
                    body=json.dumps({"session": "push-1", "path": f.name}))

                msg = await ws.read_message()
                pushed = json.loads(msg)
                self.assertEqual(pushed["type"], "metadata")
                self.assertEqual(pushed["rows"], 5)

                ws.close()
            finally:
                os.unlink(f.name)
