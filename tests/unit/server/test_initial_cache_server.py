"""Server integration for the initial-load cache — store wiring + observability.

These cover the *additive* half of the server integration (4b-i): ``/load_expr``
builds and stores an ``InitialCacheData`` bundle keyed by the expr hash, echoes a
correlation ``request_id``, and the ``/cache`` endpoint reports the store. The
hit fast-path (serve-from-cache + serve_window) lands separately.

xorq-gated: the bundle's first window comes from a real expr via
``window_to_parquet``. See docs/initial-load-cache-design.md.
"""
import json
import shutil
import sys
import tempfile

import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

xo = pytest.importorskip("xorq.api")

from buckaroo.server.app import make_app as _make_app  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="Temp file locking prevents cleanup on Windows")


def make_app():
    return _make_app(open_browser=False)


def _build_expr_dir(builds_root):
    expr = xo.memtable({
        'idx': list(range(10)),
        'name': ['alpha', 'beta', 'gamma', 'alpha', 'delta',
                 'epsilon', 'alpha', 'zeta', 'eta', 'alpha']}, name='t')
    return str(xo.build_expr(expr, builds_dir=builds_root))


async def _post(port, path, body):
    client = tornado.httpclient.AsyncHTTPClient()
    return await client.fetch(
        f"http://localhost:{port}{path}", method="POST", body=json.dumps(body),
        headers={"Content-Type": "application/json"}, raise_error=False)


async def _get(port, path):
    client = tornado.httpclient.AsyncHTTPClient()
    return await client.fetch(f"http://localhost:{port}{path}", method="GET", raise_error=False)


class TestInitialCacheServer(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_load_expr_stores_bundle_and_cache_reports_it(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "ic-1", "build_dir": build_path})
            self.assertEqual(resp.code, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["rows"], 10)
            # The load reports a cache block: first load is a miss that stores.
            cache = body["cache"]
            self.assertEqual(cache["status"], "miss")
            self.assertTrue(cache["data_id"])

            # /cache reflects the stored bundle.
            crep = json.loads((await _get(self.get_http_port(), "/cache")).body)
            self.assertEqual(crep["count"], 1)
            entry = crep["entries"][0]
            self.assertEqual(entry["data_id"], cache["data_id"])
            self.assertEqual(entry["total_rows"], 10)
            self.assertGreater(entry["bytes"], 0)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_request_id_echoed(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "ic-rq", "build_dir": build_path, "request_id": "rq-7"})
            body = json.loads(resp.body)
            self.assertEqual(body["cache"]["request_id"], "rq-7")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_initial_cache_false_skips_store(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "ic-off", "build_dir": build_path, "initial_cache": False})
            self.assertEqual(resp.code, 200)
            self.assertEqual(json.loads(resp.body)["cache"]["status"], "off")
            crep = json.loads((await _get(self.get_http_port(), "/cache")).body)
            self.assertEqual(crep["count"], 0)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_cache_endpoint_empty(self):
        crep = json.loads((await _get(self.get_http_port(), "/cache")).body)
        self.assertEqual(crep["count"], 0)
        self.assertEqual(crep["entries"], [])

    @tornado.testing.gen_test
    async def test_load_expr_hit_on_repeat(self):
        """Second load of the same expr is a cache HIT (same content-based
        data_id). The hit must still render correctly: the WS initial_state
        carries the bundle's df_display_args + df_meta."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            r1 = json.loads((await _post(self.get_http_port(), "/load_expr",
                {"session": "h-miss", "build_dir": build_path})).body)
            self.assertEqual(r1["cache"]["status"], "miss")

            r2 = json.loads((await _post(self.get_http_port(), "/load_expr",
                {"session": "h-hit", "build_dir": build_path})).body)
            self.assertEqual(r2["cache"]["status"], "hit")
            self.assertEqual(r2["rows"], 10)
            self.assertEqual(r2["cache"]["data_id"], r1["cache"]["data_id"])

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/h-hit")
            init = json.loads(await ws.read_message())
            self.assertEqual(init["df_meta"]["total_rows"], 10)
            self.assertIn("main", init["df_display_args"])
            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_hit_session_scrolls(self):
        """A cache-hit session serves both the cached head window (the fast
        path) and a sorted slice (which falls through to the warmed expr) —
        both return the full 10-row count."""
        import io

        import pyarrow.parquet as pq
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "hs-a", "build_dir": build_path})
            await _post(self.get_http_port(), "/load_expr",
                {"session": "hs-b", "build_dir": build_path})  # hit

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/hs-b")
            await ws.read_message()  # initial_state

            # Head window — served from the cache fast path.
            ws.write_message(json.dumps({"type": "infinite_request",
                "payload_args": {"start": 0, "end": 10, "sourceName": "default", "origEnd": 10}}))
            r = json.loads(await ws.read_message())
            self.assertEqual(r["length"], 10)
            self.assertEqual(pq.read_table(io.BytesIO(await ws.read_message())).num_rows, 10)

            # Sorted slice — falls through to the warmed expr (cheap dataflow).
            ws.write_message(json.dumps({"type": "infinite_request",
                "payload_args": {"start": 0, "end": 10, "sort": "a",
                    "sort_direction": "asc", "sourceName": "default", "origEnd": 10}}))
            r2 = json.loads(await ws.read_message())
            self.assertEqual(r2["length"], 10)
            self.assertNotIn("error_info", r2)
            await ws.read_message()  # binary
            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_mismatch_recomputes(self):
        """Same expr (same data_id) but a different data-touching config
        (init_sd) ⇒ the cached bundle's config_id no longer matches ⇒ the load
        recomputes rather than mis-serving. Reported as status='mismatch'."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "mm-1", "build_dir": build_path})  # miss, stores config A
            r2 = json.loads((await _post(self.get_http_port(), "/load_expr",
                {"session": "mm-2", "build_dir": build_path,
                 "init_sd": {"name": {"custom_stat": 5}}})).body)
            self.assertEqual(r2["cache"]["status"], "mismatch")
            self.assertEqual(r2["rows"], 10)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
