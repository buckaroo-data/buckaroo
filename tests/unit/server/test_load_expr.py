"""End-to-end tests for POST /load_expr — server load path for
XorqBuckarooInfiniteWidget over a xorq/ibis expression."""
import io
import json
import shutil
import sys
import tempfile

import pyarrow.parquet as pq
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

xo = pytest.importorskip("xorq.api")

from buckaroo.server.app import make_app as _make_app  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Temp file locking prevents cleanup on Windows")


def make_app():
    return _make_app(open_browser=False)


def _build_expr_dir(builds_root):
    """Build a 10-row memtable to `builds_root` and return the build path.

    Rows have a `name` column where 'alpha' appears 4x — used by the
    search test to assert push-down filtering reduces the row count."""
    expr = xo.memtable({
        'idx': list(range(10)),
        'name': ['alpha', 'beta', 'gamma', 'alpha', 'delta',
                 'epsilon', 'alpha', 'zeta', 'eta', 'alpha'],
    }, name='t')
    return str(xo.build_expr(expr, builds_dir=builds_root))


async def _post(port, path, body):
    client = tornado.httpclient.AsyncHTTPClient()
    return await client.fetch(
        f"http://localhost:{port}{path}",
        method="POST", body=json.dumps(body),
        headers={"Content-Type": "application/json"},
        raise_error=False)


class TestLoadExpr(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_missing_build_dir(self):
        resp = self.fetch(
            "/load_expr", method="POST",
            body=json.dumps({"session": "lx-missing"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 400)

    @tornado.testing.gen_test
    async def test_ws_infinite_request_pushdown(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-1", "build_dir": build_path})
            self.assertEqual(resp.code, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["session"], "lx-1")
            self.assertEqual(body["rows"], 10)

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-1")
            await ws.read_message()  # discard initial_state

            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                    "sourceName": "default", "origEnd": 10}}))

            json_frame = await ws.read_message()
            r = json.loads(json_frame)
            self.assertEqual(r["type"], "infinite_resp")
            self.assertEqual(r["length"], 10)

            binary_frame = await ws.read_message()
            self.assertIsInstance(binary_frame, bytes)
            table = pq.read_table(io.BytesIO(binary_frame))
            self.assertEqual(table.num_rows, 10)

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_ws_search_pushdown(self):
        """Send a Search state change, then paginate — the row count must
        drop to the matches (`alpha` appears 4x in the fixture). Proves
        the filter pushed down to the xorq backend rather than running
        in Python over a pre-materialised frame."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-2", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-2")
            await ws.read_message()  # discard initial_state

            ws.write_message(json.dumps({
                "type": "buckaroo_state_change",
                "new_state": {
                    "post_processing": "",
                    "cleaning_method": "",
                    "quick_command_args": {"search": ["alpha"]},
                    "df_display": "main",
                    "show_commands": False,
                    "sampled": False,
                    "search_string": "alpha",
                }}))
            await ws.read_message()  # discard rebroadcast initial_state

            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                    "sourceName": "default", "origEnd": 10}}))

            r = json.loads(await ws.read_message())
            self.assertEqual(r["type"], "infinite_resp")
            self.assertEqual(r["length"], 4)

            binary_frame = await ws.read_message()
            table = pq.read_table(io.BytesIO(binary_frame))
            self.assertEqual(table.num_rows, 4)

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
