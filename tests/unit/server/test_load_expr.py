"""End-to-end tests for POST /load_expr — server load path for
XorqBuckarooInfiniteWidget over a xorq/ibis expression."""
import io
import json
import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow.parquet as pq
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

xo = pytest.importorskip("xorq.api")

from buckaroo.server import telemetry  # noqa: E402
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


    @tornado.testing.gen_test
    async def test_cache_storage_path_accepted(self):
        """POST /load_expr with cache_storage_path must succeed and write cache
        files to the specified directory on stat execution."""
        builds_root = tempfile.mkdtemp()
        cache_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-cache", "build_dir": build_path,
                 "cache_storage_path": cache_root})
            self.assertEqual(resp.code, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["rows"], 10)
            # At least one cache file must have been written.
            cache_files = []
            for root, _dirs, files in os.walk(cache_root):
                cache_files.extend(files)
            self.assertGreater(len(cache_files), 0,
                f"expected cache files under {cache_root}, found none")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(cache_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_load_expr_telemetry_emits_session_correlated_spans(self):
        """#943: POST /load_expr with telemetry_url must emit session-correlated
        span records, including a firstpull.summary_stats span carrying the
        cache hit/miss signal (#944) — the one signal only the server observes.

        A cache_storage_path is supplied so the cold load is a genuine cache
        *miss* (every stat computed and written). That lets the test pin the
        exact cache_status — and the numeric hit/miss counts riding with it —
        rather than merely asserting "not a hit", which would still pass if the
        signal regressed to None (key present, value empty).
        """
        captured: list = []
        builds_root = tempfile.mkdtemp()
        cache_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            # Capture records in-process: make_http_sink → list.append, so no
            # HTTP round-trip — the wiring (telemetry_url → context → spans →
            # cache attrs) is what's under test. The real POST has its own test
            # (test_telemetry_sink.py).
            with patch.object(telemetry, "make_http_sink",
                lambda url, **kw: captured.append):
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-telem", "build_dir": build_path,
                     "cache_storage_path": cache_root,
                     "telemetry_url": "http://companion.invalid/internal/telemetry"})
            self.assertEqual(resp.code, 200)

            names = [r["name"] for r in captured]
            self.assertIn("firstpull.load_expr", names)
            self.assertIn("firstpull.summary_stats", names)
            # Every span shares the session id as its trace.
            self.assertTrue(all(r["trace"] == "lx-telem" for r in captured),
                f"all spans must carry the session trace; got {[r['trace'] for r in captured]}")
            self.assertTrue(all(r["source"] == "server" for r in captured))

            ss = next(r for r in captured if r["name"] == "firstpull.summary_stats")
            attrs = ss["attrs"]
            # Cold load against a fresh cache_root → a pure miss: status="miss",
            # zero hits, at least one miss. Pinning the value (not just "!= hit")
            # makes a dropped signal (cache_status=None) fail here.
            self.assertEqual(attrs["cache_status"], "miss")
            self.assertEqual(attrs["cache_hits"], 0)
            self.assertGreater(attrs["cache_misses"], 0)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(cache_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_ws_first_payload_emits_telemetry_span(self):
        """#943: the WS handler re-binds the telemetry sink from the session so
        the firstpull.ws_first_payload span (time-to-first-rows) — emitted in a
        different async context than the POST — is captured too."""
        captured: list = []
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            with patch.object(telemetry, "make_http_sink",
                lambda url, **kw: captured.append):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-ws-telem", "build_dir": build_path,
                     "telemetry_url": "http://companion.invalid/internal/telemetry"})

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/lx-ws-telem")
                await ws.read_message()  # discard initial_state
                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 10,
                        "sourceName": "default", "origEnd": 10}}))
                await ws.read_message()  # json frame
                await ws.read_message()  # binary frame
                ws.close()

            names = [r["name"] for r in captured]
            self.assertIn("firstpull.ws_first_payload", names)
            ws_span = next(r for r in captured
                if r["name"] == "firstpull.ws_first_payload")
            self.assertEqual(ws_span["trace"], "lx-ws-telem")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_telemetry_sink_built_once_not_rebuilt_by_ws(self):
        """#944: the sink is built once in /load_expr and stored on the session;
        the WS first-pull reuses session.tele_sink rather than rebuilding it.
        Pin make_http_sink to exactly one call across the POST + WS exchange —
        the WS still emits its span (proving reuse works), but a regression that
        re-introduced make_http_sink in the WS path would push call_count to 2
        and fail here even though span emission would look fine."""
        captured: list = []
        sink_factory = MagicMock(side_effect=lambda url, **kw: captured.append)
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            with patch.object(telemetry, "make_http_sink", sink_factory):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-once", "build_dir": build_path,
                     "telemetry_url": "http://companion.invalid/internal/telemetry"})

                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/lx-once")
                await ws.read_message()  # discard initial_state
                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 10,
                        "sourceName": "default", "origEnd": 10}}))
                await ws.read_message()  # json frame
                await ws.read_message()  # binary frame
                ws.close()

            # Built exactly once (in /load_expr), not again in the WS path.
            self.assertEqual(sink_factory.call_count, 1,
                f"sink must be built once and reused; got {sink_factory.call_count} builds")
            # ...and the reuse genuinely reaches the WS span (not a silent no-op).
            self.assertIn("firstpull.ws_first_payload", [r["name"] for r in captured])
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_load_expr_without_telemetry_url_is_silent(self):
        """#943: with no telemetry_url, the sink is never built — normal
        buckaroo usage emits nothing and is unaffected."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sink_factory = MagicMock()
            with patch.object(telemetry, "make_http_sink", sink_factory):
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-no-telem", "build_dir": build_path})
            self.assertEqual(resp.code, 200)
            sink_factory.assert_not_called()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_first_pull_telemetry_rearms_after_session_reload(self):
        """#944: reloading an expression into an existing session re-arms the
        first-pull telemetry. _perf_first_payload_seen is reset on a genuine
        /load_expr, so the next WS pull emits firstpull.ws_first_payload again.
        Before the reset the flag stayed True from the first load and every
        reload's time-to-first-rows span was silently dropped."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)

            async def _load_and_pull(captured, *, force_reload):
                body = {"session": "lx-rearm", "build_dir": build_path,
                    "telemetry_url": "http://companion.invalid/internal/telemetry"}
                if force_reload:
                    body["force_reload"] = True
                with patch.object(telemetry, "make_http_sink",
                    lambda url, **kw: captured.append):
                    await _post(self.get_http_port(), "/load_expr", body)
                    ws = await tornado.websocket.websocket_connect(
                        f"ws://localhost:{self.get_http_port()}/ws/lx-rearm")
                    await ws.read_message()  # discard initial_state
                    ws.write_message(json.dumps({
                        "type": "infinite_request",
                        "payload_args": {"start": 0, "end": 10,
                            "sourceName": "default", "origEnd": 10}}))
                    await ws.read_message()  # json frame
                    await ws.read_message()  # binary frame
                    ws.close()

            first: list = []
            await _load_and_pull(first, force_reload=False)
            self.assertIn("firstpull.ws_first_payload", [r["name"] for r in first])

            # Reload the same session (force_reload bypasses the warm-session
            # early-exit so the full load path, and the re-arm, runs). The next
            # first pull is a new time-to-first-rows and must emit again.
            second: list = []
            await _load_and_pull(second, force_reload=True)
            self.assertIn("firstpull.ws_first_payload", [r["name"] for r in second],
                "reloading the session must re-arm first-pull telemetry")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_ws_eager_second_request_emits_its_own_span(self):
        """#944: the eager second_request (part of the initial screen load) is
        instrumented as its own firstpull.ws_second_payload span — separate
        from the first pull — rather than only surfacing as a nested
        window_to_parquet record riding inside the first pull's context."""
        captured: list = []
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            with patch.object(telemetry, "make_http_sink",
                lambda url, **kw: captured.append):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-second", "build_dir": build_path,
                     "telemetry_url": "http://companion.invalid/internal/telemetry"})
                ws = await tornado.websocket.websocket_connect(
                    f"ws://localhost:{self.get_http_port()}/ws/lx-second")
                await ws.read_message()  # discard initial_state
                ws.write_message(json.dumps({
                    "type": "infinite_request",
                    "payload_args": {"start": 0, "end": 5,
                        "sourceName": "default", "origEnd": 5,
                        "second_request": {"start": 5, "end": 10,
                            "sourceName": "default", "origEnd": 10}}}))
                await ws.read_message()  # first json frame
                await ws.read_message()  # first binary frame
                await ws.read_message()  # second json frame
                await ws.read_message()  # second binary frame
                ws.close()

            names = [r["name"] for r in captured]
            self.assertIn("firstpull.ws_first_payload", names)
            self.assertIn("firstpull.ws_second_payload", names)
            second = next(r for r in captured
                if r["name"] == "firstpull.ws_second_payload")
            self.assertEqual(second["trace"], "lx-second")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)


class TestLoadExprPerfFixes(tornado.testing.AsyncHTTPTestCase):
    """Tests for #896 (shared backend) and #899 (warm-session early-exit)."""

    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_warm_session_skips_pipeline(self):
        """#899: a repeat POST with the same session_id + build_dir must return
        cached metadata without re-running the stat pipeline.

        Verified by patching load_expr_build_dir to raise on a second call —
        if the early-exit fires, the patch is never reached."""
        from unittest.mock import patch
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "lx-warm-reuse"

            resp1 = await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path})
            self.assertEqual(resp1.code, 200)
            body1 = json.loads(resp1.body)
            self.assertEqual(body1["rows"], 10)

            from buckaroo.server import xorq_loading
            with patch.object(xorq_loading, "load_expr_build_dir",
                side_effect=AssertionError("pipeline must not run for warm session")):
                resp2 = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})

            self.assertEqual(resp2.code, 200)
            body2 = json.loads(resp2.body)
            self.assertEqual(body2["rows"], 10)
            self.assertEqual(body2["session"], sid)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_new_session_always_runs_pipeline(self):
        """#899: two distinct session_ids must each run the full pipeline even
        when they share the same build_dir."""
        from unittest.mock import patch
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            from buckaroo.server import xorq_loading
            original = xorq_loading.load_expr_build_dir
            call_count = []
            def counting_loader(bd):
                call_count.append(bd)
                return original(bd)

            with patch.object(xorq_loading, "load_expr_build_dir", side_effect=counting_loader):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-distinct-a", "build_dir": build_path})
                await _post(self.get_http_port(), "/load_expr",
                    {"session": "lx-distinct-b", "build_dir": build_path})

            self.assertEqual(len(call_count), 2)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_force_reload_bypasses_warm_session(self):
        """#899: force_reload=true must bypass the warm-session early-exit and
        re-run the pipeline even for an already-loaded session_id."""
        from unittest.mock import patch
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "lx-force-reload"
            from buckaroo.server import xorq_loading
            original = xorq_loading.load_expr_build_dir
            calls = []
            def counting_loader(bd):
                calls.append(bd)
                return original(bd)

            with patch.object(xorq_loading, "load_expr_build_dir", side_effect=counting_loader):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})
                self.assertEqual(len(calls), 1)
                # Plain warm repeat takes the early-exit — no re-run.
                await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})
                self.assertEqual(len(calls), 1, "plain warm repeat must not re-run")
                # force_reload bypasses the early-exit — pipeline runs again.
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path, "force_reload": True})
                self.assertEqual(resp.code, 200)
                self.assertEqual(len(calls), 2, "force_reload must re-run the pipeline")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_warm_session_with_new_config_reruns(self):
        """#899: a warm POST that carries a config-bearing field (here
        component_config) must re-run the pipeline rather than silently
        returning stale cached metadata that ignores the new config."""
        from unittest.mock import patch
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "lx-warm-config"
            from buckaroo.server import xorq_loading
            original = xorq_loading.load_expr_build_dir
            calls = []
            def counting_loader(bd):
                calls.append(bd)
                return original(bd)

            with patch.object(xorq_loading, "load_expr_build_dir", side_effect=counting_loader):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})
                self.assertEqual(len(calls), 1)
                # Plain warm repeat takes the early-exit — no re-run.
                await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})
                self.assertEqual(len(calls), 1, "plain warm repeat must not re-run")
                # Same session + build_dir but with new config — must re-run.
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path,
                     "component_config": {"search_debounce": 100}})
                self.assertEqual(resp.code, 200)
                self.assertEqual(len(calls), 2, "new config must bypass the early-exit")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    def test_shared_backend_singleton(self):
        """#896: load_expr_build_dir must call xorq.config.default_backend()
        rather than connect() so xorq's process-wide singleton is reused across
        calls instead of a new SessionContext being minted each time."""
        from unittest.mock import patch

        from buckaroo.server import xorq_loading

        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            from xorq import config as xorq_config
            connect_calls = []
            original_default_backend = xorq_config.default_backend

            def tracking_default_backend():
                con = original_default_backend()
                connect_calls.append(id(con))
                return con

            with patch.object(xorq_config, "default_backend",
                side_effect=tracking_default_backend):
                xorq_loading.load_expr_build_dir(build_path)
                xorq_loading.load_expr_build_dir(build_path)

            # Both calls must return the same backend id — one singleton.
            self.assertEqual(len(connect_calls), 2)
            self.assertEqual(connect_calls[0], connect_calls[1],
                "load_expr_build_dir minted a new backend on the second call")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)


class TestReloadExpr(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_reload_expr_session_not_found(self):
        resp = self.fetch(
            "/reload_expr/no-such-session", method="POST", body="",
            headers={"Content-Type": "application/json"})
        self.assertEqual(resp.code, 404)
        body = json.loads(resp.body)
        self.assertEqual(body["error_code"], "session_not_found")

    @tornado.testing.gen_test
    async def test_reload_expr_not_xorq_session(self):
        """/reload_expr on a pandas session must return 400."""
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(csv_fd)
        try:
            import pandas as pd
            pd.DataFrame({"x": [1, 2]}).to_csv(csv_path, index=False)
            await _post(self.get_http_port(), "/load",
                {"session": "re-pandas", "path": csv_path, "mode": "buckaroo"})
            resp = await _post(self.get_http_port(), "/reload_expr/re-pandas", {})
            self.assertEqual(resp.code, 400)
            body = json.loads(resp.body)
            self.assertEqual(body["error_code"], "not_xorq_session")
        finally:
            os.unlink(csv_path)

    @tornado.testing.gen_test
    async def test_reload_expr_no_project_root(self):
        """Session loaded via /load_expr without project_root must return 400."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "re-no-pr", "build_dir": build_path})
            resp = await _post(self.get_http_port(), "/reload_expr/re-no-pr", {})
            self.assertEqual(resp.code, 400)
            body = json.loads(resp.body)
            self.assertEqual(body["error_code"], "no_project_root")
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_reload_expr_broadcasts_updated_options(self):
        """Adding a post_processing file to project_root and calling
        /reload_expr must surface the new method in buckaroo_options
        broadcast to WS clients — without re-executing the expression."""
        builds_root = tempfile.mkdtemp()
        project_root = tempfile.mkdtemp()
        pp_dir = os.path.join(project_root, "post_processing")
        os.makedirs(pp_dir)
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "re-broadcast"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path,
                 "project_root": project_root})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/{sid}")
            init_msg = json.loads(await ws.read_message())
            initial_options = init_msg.get("buckaroo_options", {})
            initial_pp = initial_options.get("post_processing", [])

            # Write a minimal post-processing file into the project.
            pp_file = os.path.join(pp_dir, "double_idx.py")
            with open(pp_file, "w") as f:
                f.write("def process(expr):\n    return expr\n")

            reload_resp = await _post(
                self.get_http_port(), f"/reload_expr/{sid}", {})
            self.assertEqual(reload_resp.code, 200)
            body = json.loads(reload_resp.body)
            self.assertEqual(body["session"], sid)
            self.assertGreaterEqual(body["klasses_loaded"], 1)

            # The WS client must receive an updated initial_state carrying
            # the new post-processing method in buckaroo_options.
            updated_msg = json.loads(await ws.read_message())
            self.assertEqual(updated_msg["type"], "initial_state")
            updated_options = updated_msg.get("buckaroo_options", {})
            updated_pp = updated_options.get("post_processing", [])
            self.assertGreater(len(updated_pp), len(initial_pp),
                f"expected new pp klass in options; before={initial_pp} after={updated_pp}")

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(project_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_reload_expr_returns_200_with_zero_klasses(self):
        """Empty project_root is valid — reload returns 200 with klasses_loaded=0."""
        builds_root = tempfile.mkdtemp()
        project_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "re-empty-pr"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path,
                 "project_root": project_root})

            resp = await _post(self.get_http_port(), f"/reload_expr/{sid}", {})
            self.assertEqual(resp.code, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["klasses_loaded"], 0)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(project_root, ignore_errors=True)
