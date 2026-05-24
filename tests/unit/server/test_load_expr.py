"""End-to-end tests for POST /load_expr — server load path for
XorqBuckarooInfiniteWidget over a xorq/ibis expression."""
import io
import json
import os
import shutil
import sys
import tempfile

import pandas as pd
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

    @tornado.testing.gen_test
    async def test_ws_search_string_rowfetch(self):
        """Regression for #838: a ``buckaroo_state_change`` carrying only
        ``search_string`` (no ``quick_command_args.search``) must filter
        the row-fetch dispatch. The search_string path is the fast lane
        for live typing — it sidesteps the dataflow stat pipeline, which
        is too slow for ~10⁶-row parquet-backed exprs in pydata-app.

        Fixture has `alpha` in 4 of 10 rows; ``length`` must drop to 4.
        """
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-search", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-search")
            await ws.read_message()  # discard initial_state

            ws.write_message(json.dumps({
                "type": "buckaroo_state_change",
                "new_state": {
                    "post_processing": "",
                    "cleaning_method": "",
                    "quick_command_args": {},
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

    @tornado.testing.gen_test
    async def test_ws_search_string_cleared_returns_full_set(self):
        """Clearing search_string (sending ``""``) must restore the full
        row count. Mirrors the JS contract: an empty search box sends an
        empty term on every keystroke after clear."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-search-clear", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-search-clear")
            await ws.read_message()

            for term, expected in (("alpha", 4), ("", 10)):
                ws.write_message(json.dumps({
                    "type": "buckaroo_state_change",
                    "new_state": {
                        "post_processing": "", "cleaning_method": "",
                        "quick_command_args": {}, "df_display": "main",
                        "show_commands": False, "sampled": False,
                        "search_string": term}}))
                await ws.read_message()

                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 10,
                        "sourceName": "default", "origEnd": 10}}))
                r = json.loads(await ws.read_message())
                self.assertEqual(r["length"], expected,
                    f"search_string={term!r} expected length={expected}, got {r['length']}")
                await ws.read_message()  # binary frame

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_search_string_resets_on_load_expr_reuse(self):
        """Codex P1 (#839): session.search_string must be cleared when
        /load_expr replaces data on an existing session. Otherwise the
        stale term silently filters the newly loaded dataset even though
        the rebroadcast buckaroo_state shows an empty search box.

        Repro: set search_string="alpha" (filters to 4 rows), then
        /load_expr the same fixture again on the same session id. The
        next infinite_request must return length=10, not 4."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "lx-search-reuse"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/{sid}")
            await ws.read_message()

            # Type a search term — filters to 4 rows.
            ws.write_message(json.dumps({
                "type": "buckaroo_state_change",
                "new_state": {
                    "post_processing": "", "cleaning_method": "",
                    "quick_command_args": {}, "df_display": "main",
                    "show_commands": False, "sampled": False,
                    "search_string": "alpha"}}))
            await ws.read_message()
            ws.close()

            # Reload the dataset on the same session. The client's view
            # of buckaroo_state will be fresh (search_string=""), so the
            # server's must also be — else the row fetch silently filters.
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path})

            ws2 = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/{sid}")
            await ws2.read_message()

            ws2.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                    "sourceName": "default", "origEnd": 10}}))
            r = json.loads(await ws2.read_message())
            self.assertEqual(r["length"], 10,
                f"stale search_string carried across /load_expr — "
                f"expected 10 rows, got {r['length']}")
            await ws2.read_message()  # binary
            ws2.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_ws_infinite_request_clamps_oversized_window(self):
        """Regression for #797: a request with ``end >> total_rows``
        must clamp to ``MAX_INFINITE_WINDOW``. Pre-fix the xorq path
        returned the entire underlying table in one parquet frame —
        92 MB on the boston dataset.

        For test ergonomics ``MAX_INFINITE_WINDOW`` is lowered to 3
        and the existing 10-row fixture exposes the clamp without
        needing an 11k-row fixture.
        """
        from buckaroo.server import window as W
        original_max = W.MAX_INFINITE_WINDOW
        W.MAX_INFINITE_WINDOW = 3
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-clamp", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-clamp")
            await ws.read_message()  # discard initial_state

            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 99_999_999,
                    "sourceName": "default", "origEnd": 99_999_999}}))

            r = json.loads(await ws.read_message())
            self.assertEqual(r["type"], "infinite_resp")
            # `length` reports total table rows (unclamped) — that's
            # the contract clients depend on for the virtual-scroll
            # heuristic. Only the *window* must be clamped.
            self.assertEqual(r["length"], 10)

            binary_frame = await ws.read_message()
            self.assertIsInstance(binary_frame, bytes)
            table = pq.read_table(io.BytesIO(binary_frame))
            # 10-row table, end=99_999_999, MAX_INFINITE_WINDOW=3
            # → clamp(0, 99_999_999, 10) = (0, 10), then cap window
            # to 3 → window of 3 rows.
            self.assertEqual(table.num_rows, 3,
                f"window must clamp to MAX_INFINITE_WINDOW=3; "
                f"got {table.num_rows} (pre-fix: 10)")

            ws.close()
        finally:
            W.MAX_INFINITE_WINDOW = original_max
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_session_reuse_xorq_then_pandas(self):
        """A client that POSTs /load_expr and then POSTs /load with the
        same session id should see the pandas data on subsequent
        infinite_requests — not stale xorq results. Regression for the
        Codex P1 finding: backend / xorq_dataflow were sticky across
        session reuse."""
        builds_root = tempfile.mkdtemp()
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(csv_fd)
        try:
            build_path = _build_expr_dir(builds_root)
            pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(csv_path, index=False)

            sid = "lx-reuse"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path})
            await _post(self.get_http_port(), "/load",
                {"session": sid, "path": csv_path, "mode": "buckaroo"})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/{sid}")
            await ws.read_message()  # initial_state

            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                    "sourceName": "default", "origEnd": 10}}))

            r = json.loads(await ws.read_message())
            self.assertEqual(r["type"], "infinite_resp")
            # CSV fixture has 3 rows; xorq fixture has 10. A failure here
            # (length == 10) means dispatch is still serving xorq state.
            self.assertEqual(r["length"], 3)
            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            os.unlink(csv_path)


class TestLoadBackendXorq(tornado.testing.AsyncHTTPTestCase):
    """POST /load with backend="xorq" — wraps a parquet path in a
    deferred-read xorq expression and serves it through the same
    push-down path as /load_expr."""

    def get_app(self):
        return make_app()

    def test_invalid_backend_returns_400(self):
        resp = self.fetch("/load", method="POST",
            body=json.dumps({"session": "lb-bad", "path": "/tmp/x.parquet",
                "backend": "bogus"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 400)
        self.assertEqual(json.loads(resp.body)["error_code"], "invalid_backend")

    def test_xorq_backend_requires_buckaroo_mode(self):
        resp = self.fetch("/load", method="POST",
            body=json.dumps({"session": "lb-mode", "path": "/tmp/x.parquet",
                "backend": "xorq", "mode": "lazy"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 400)
        self.assertEqual(json.loads(resp.body)["error_code"],
            "invalid_mode_for_backend")

    @tornado.testing.gen_test
    async def test_xorq_load_failure_preserves_session_backend(self):
        """Codex P1 on #840: a failed xorq /load must not flip
        session.backend to 'xorq' before the load is known to succeed.
        Otherwise a session previously serving pandas ends up with
        backend='xorq' + xorq_dataflow=None, and the WS state-change
        handler silently drops further updates (websocket_handler.py:59)."""
        d = tempfile.mkdtemp()
        good_path = os.path.join(d, "good.parquet")
        bogus_path = os.path.join(d, "nonexistent.parquet")
        try:
            pd.DataFrame({"idx": list(range(3))}).to_parquet(good_path)

            # 1. Successful pandas load establishes prior session state.
            resp = await _post(self.get_http_port(), "/load",
                {"session": "lb-roll", "path": good_path, "mode": "buckaroo"})
            self.assertEqual(resp.code, 200)

            sessions = self._app.settings["sessions"]
            session = sessions.get("lb-roll")
            self.assertEqual(session.backend, "pandas")
            prior_dataflow = session.dataflow
            self.assertIsNotNone(prior_dataflow)

            # 2. Failed xorq load (path doesn't exist → 404).
            resp = await _post(self.get_http_port(), "/load",
                {"session": "lb-roll", "path": bogus_path,
                 "mode": "buckaroo", "backend": "xorq"})
            self.assertEqual(resp.code, 404)

            # 3. Session must not have been half-mutated. backend stays
            # 'pandas'; the existing pandas dataflow stays reachable so
            # WS dispatch can still answer buckaroo_state_change.
            self.assertEqual(session.backend, "pandas",
                "session.backend must not flip to 'xorq' on failed xorq load")
            self.assertIs(session.dataflow, prior_dataflow,
                "session.dataflow must survive a failed xorq load")
            self.assertIsNone(session.xorq_dataflow)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_xorq_not_installed_returns_501(self):
        """Codex P2 on #840: when xorq.api is not importable the handler
        must return 501 xorq_not_installed, not a generic 500 load_error.
        The probe in handlers.py has to be explicit — importing
        ``buckaroo.server.xorq_loading`` succeeds even without xorq
        because the transitive ``import xorq.api`` calls in
        ``xorq_stats_v2`` and ``xorq_stat_pipeline`` are guarded with
        try/except.

        Uses a real parquet path so the path-exists check passes; that
        way a 500 result here proves the bug isn't masked as file-not-
        found and is genuinely the unreachable 501 branch."""
        from unittest.mock import patch
        d = tempfile.mkdtemp()
        parquet_path = os.path.join(d, "p.parquet")
        try:
            pd.DataFrame({"idx": [0]}).to_parquet(parquet_path)
            # sys.modules[name] = None forces a subsequent `import name`
            # to raise ImportError. patch.dict restores the mapping so
            # other tests still see the real xorq.api.
            with patch.dict(sys.modules, {"xorq.api": None}):
                resp = self.fetch("/load", method="POST",
                    body=json.dumps({"session": "lb-noxorq",
                        "path": parquet_path,
                        "mode": "buckaroo", "backend": "xorq"}),
                    headers={"Content-Type": "application/json"})
            self.assertEqual(resp.code, 501)
            self.assertEqual(json.loads(resp.body)["error_code"],
                "xorq_not_installed")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_load_parquet_via_xorq_backend(self):
        """Happy path: POST /load with backend=xorq, then issue an
        infinite_request — the row count must come from the parquet via
        XorqServerDataflow, proving routing went through the xorq path."""
        d = tempfile.mkdtemp()
        parquet_path = os.path.join(d, "lb_fixture.parquet")
        try:
            pd.DataFrame({"idx": list(range(7)), "name": ["a", "b", "c", "d", "e", "f", "g"]}).to_parquet(parquet_path)

            resp = await _post(self.get_http_port(), "/load",
                {"session": "lb-ok", "path": parquet_path,
                 "mode": "buckaroo", "backend": "xorq"})
            self.assertEqual(resp.code, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["session"], "lb-ok")
            self.assertEqual(body["rows"], 7)
            self.assertEqual({c["name"] for c in body["columns"]}, {"idx", "name"})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lb-ok")
            await ws.read_message()  # initial_state

            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                    "sourceName": "default", "origEnd": 10}}))
            r = json.loads(await ws.read_message())
            self.assertEqual(r["type"], "infinite_resp")
            self.assertEqual(r["length"], 7)

            binary_frame = await ws.read_message()
            table = pq.read_table(io.BytesIO(binary_frame))
            self.assertEqual(table.num_rows, 7)
            ws.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)
