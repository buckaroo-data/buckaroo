"""End-to-end tests for POST /load_expr — server load path for
XorqBuckarooInfiniteWidget over a xorq/ibis expression."""
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow.parquet as pq
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

xo = pytest.importorskip("xorq.api")

from xorq.caching import ParquetSnapshotCache, ParquetStorage  # noqa: E402
from xorq.common.utils.provenance_utils import read_parquet_provenance  # noqa: E402

from buckaroo.server import telemetry, xorq_loading  # noqa: E402
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
            # The write side rides the span too (#951): the cold miss writes
            # snapshots with no write errors, so a cache that stops writing — or a
            # run with write_errors > 0 — is visible to the telemetry consumer.
            self.assertGreater(attrs["cache_snapshots"], 0)
            self.assertGreater(attrs["cache_bytes"], 0)
            self.assertEqual(attrs["cache_write_errors"], 0)
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

    @tornado.testing.gen_test
    async def test_first_pull_telemetry_rearms_after_warm_reload(self):
        """#944: a WARM re-POST — same session+build_dir, no force_reload, no
        config: the early-exit that returns cached metadata without re-running
        the pipeline — must still re-arm first-pull telemetry. The refreshed
        page's WS pull is a fresh time-to-first-rows. Before the fix the warm
        exit left _perf_first_payload_seen True from the first load and never
        (re)bound the sink, so the second pull's span was silently dropped.

        Distinct from test_first_pull_telemetry_rearms_after_session_reload,
        which exercises the force_reload (full-load) path; this one pins the
        early-exit path that skips the pipeline entirely."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)

            async def _load_and_pull(captured):
                with patch.object(telemetry, "make_http_sink",
                    lambda url, **kw: captured.append):
                    await _post(self.get_http_port(), "/load_expr",
                        {"session": "lx-warm", "build_dir": build_path,
                         "telemetry_url": "http://companion.invalid/internal/telemetry"})
                    ws = await tornado.websocket.websocket_connect(
                        f"ws://localhost:{self.get_http_port()}/ws/lx-warm")
                    await ws.read_message()  # discard initial_state
                    ws.write_message(json.dumps({
                        "type": "infinite_request",
                        "payload_args": {"start": 0, "end": 10,
                            "sourceName": "default", "origEnd": 10}}))
                    await ws.read_message()  # json frame
                    await ws.read_message()  # binary frame
                    ws.close()

            first: list = []
            await _load_and_pull(first)
            self.assertIn("firstpull.ws_first_payload", [r["name"] for r in first])

            # Second load is a WARM re-POST (same session, same build_dir, no
            # force_reload, no config): it hits the early-exit and returns cached
            # metadata. It must still re-arm first-pull telemetry and rebind the
            # sink, so the new pull's span lands in `second` rather than being
            # dropped (flag still True) or routed to the stale first-load sink.
            second: list = []
            await _load_and_pull(second)
            self.assertIn("firstpull.ws_first_payload", [r["name"] for r in second],
                "a warm re-POST must re-arm first-pull telemetry")
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
            def counting_loader(bd, **kwargs):
                call_count.append(bd)
                return original(bd, **kwargs)

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
            def counting_loader(bd, **kwargs):
                calls.append(bd)
                return original(bd, **kwargs)

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
            def counting_loader(bd, **kwargs):
                calls.append(bd)
                return original(bd, **kwargs)

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

    @tornado.testing.gen_test
    async def test_warm_exit_requires_a_xorq_session(self):
        """/load swaps a session to pandas but leaves its build_dir, so a later
        /load_expr of the same build must reload instead of taking the
        warm-session early-exit and returning the pandas metadata."""
        root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(os.path.join(root, "builds"))
            csv_path = os.path.join(root, "t.csv")
            pd.DataFrame({"a": [1, 2, 3]}).to_csv(csv_path, index=False)
            sid = "lx-xorq-pandas-xorq"
            for path, body in (
                    ("/load_expr", {"build_dir": build_path}),
                    ("/load", {"path": csv_path, "mode": "buckaroo"}),
                    ("/load_expr", {"build_dir": build_path})):
                resp = await _post(self.get_http_port(), path, {"session": sid, **body})
                self.assertEqual(resp.code, 200, resp.body)
            self.assertEqual(json.loads(resp.body)["rows"], 10,
                "early-exit returned the pandas session's metadata")
            session = self._app.settings["sessions"].get(sid)
            self.assertEqual(session.backend, "xorq")
            self.assertIsNotNone(session.xorq_dataflow)
        finally:
            shutil.rmtree(root, ignore_errors=True)

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

    @tornado.testing.gen_test
    async def test_reload_expr_preserves_load_expr_config(self):
        """#957: /reload_expr must rebuild the dataflow with the same
        cache_storage_path, column_config_overrides, extra_grid_config,
        init_sd and skip_stat_columns the session was loaded with — a
        reloaded session is the same session with fresh klasses, not a
        stripped-down one with stat caching off and column config gone."""
        builds_root = tempfile.mkdtemp()
        project_root = tempfile.mkdtemp()
        cache_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "re-keeps-config"
            overrides = {"name": {"displayer_args": {"displayer": "string", "max_length": 5000}}}
            grid_cfg = {"rowHeight": 70, "pinnedRowHeight": 21}
            init_sd = {"idx": {"displayer_args": {"displayer": "string", "max_length": 200}}}
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path,
                 "project_root": project_root, "cache_storage_path": cache_root,
                 "column_config_overrides": overrides, "extra_grid_config": grid_cfg,
                 "init_sd": init_sd, "skip_stat_columns": ["name"]})
            self.assertEqual(resp.code, 200)

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/{sid}")
            await ws.read_message()  # discard initial_state

            reload_resp = await _post(
                self.get_http_port(), f"/reload_expr/{sid}", {})
            self.assertEqual(reload_resp.code, 200)

            dataflow = self._app.settings["sessions"].get(sid).xorq_dataflow
            self.assertIsNotNone(dataflow.cache_storage,
                "reload dropped cache_storage_path — stats recompute uncached")
            self.assertEqual(dataflow.column_config_overrides, overrides)
            self.assertEqual(dataflow.init_sd, init_sd)
            self.assertEqual(dataflow.skip_stat_columns, {"name"})

            # The broadcast the open client renders must still carry the
            # caller's column and grid config.
            msg = json.loads(await ws.read_message())
            self.assertEqual(msg["type"], "initial_state")
            dvc = msg["df_display_args"]["main"]["df_viewer_config"]
            self.assertEqual(dvc.get("extra_grid_config"), grid_cfg)
            by_header = {cc.get("header_name"): cc for cc in dvc["column_config"]}
            self.assertEqual(by_header["name"]["displayer_args"]["max_length"], 5000)
            self.assertEqual(by_header["idx"]["displayer_args"]["max_length"], 200)
            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(project_root, ignore_errors=True)
            shutil.rmtree(cache_root, ignore_errors=True)


def _bake_from_build(build_path, host_cache):
    """Load the build with every cache node pointed at ``host_cache`` and
    execute it, the way tallyman bakes its compute cache (load_expr +
    ``portable.rewrite_cache_dirs``). Baking the in-memory expression instead
    would not do on xorq>=0.4: the build copies local reads into
    ``reads/``, so the loaded graph — and every cache key — differs from the
    in-memory one. Kept independent of ``xorq_loading.redirect_cache_dir`` so
    the test does not grade the redirect against itself."""
    from attr import evolve
    from xorq.common.utils.graph_utils import replace_nodes
    from xorq.expr.relations import CachedNode

    def replacer(node, kwargs):
        if kwargs:
            node = node.__recreate__(kwargs)
        if isinstance(node, CachedNode):
            cache = evolve(node.cache, storage=evolve(node.cache.storage, base_path=host_cache))
            return node.__recreate__(dict(zip(node.__argnames__, node.__args__)) | {"cache": cache})
        return node

    baked = replace_nodes(replacer, xo.load_expr(build_path)).to_expr()
    baked.execute()
    return baked


def _build_cached_expr_dir(root):
    """Build a two-level cached expression to ``<root>/builds`` and bake its
    snapshots under ``<root>/host_cache``, as an embedder (tallyman) does.

    The aggregate's cache node wraps a filter that is itself cached, so the
    outer node's parent carries a nested ``CachedNode``. Returns
    ``(build_path, host_cache, outer_snapshot_path)``."""
    from pathlib import Path
    from xorq.caching import ParquetSnapshotCache
    root = Path(root)
    pd.DataFrame({"g": [1, 1, 2], "v": [1.0, 2.0, 3.0]}).to_parquet(root / "t.parquet")
    host_cache = root / "host_cache"

    def cache():
        return ParquetSnapshotCache.from_kwargs(source=xo.connect(), base_path=host_cache)

    t = xo.deferred_read_parquet(str(root / "t.parquet"))
    inner = t.filter(t.v > 0).cache(cache=cache())
    expr = inner.group_by("g").agg(s=inner.v.sum()).cache(cache=cache())
    build_path = str(xo.build_expr(expr, builds_dir=root / "builds"))
    op = _bake_from_build(build_path, host_cache).op()
    outer_snapshot = Path(op.cache.storage.get_path(op.cache.calc_key(op.parent)))
    return build_path, host_cache, outer_snapshot


def _cache_node_paths(expr):
    from pathlib import Path
    from xorq.common.utils.graph_utils import walk_nodes
    from xorq.expr.relations import CachedNode
    return [Path(n.cache.storage.get_path(n.cache.calc_key(n.parent)))
        for n in walk_nodes((CachedNode,), expr)]


def _build_shared_cache_expr_dir(root):
    """Build, without baking, a DAG in which one cached filter feeds both a
    cached aggregate and an uncached one, unioned at the root. Returns
    ``(build_path, host_cache)``."""
    root = Path(root)
    pd.DataFrame({"g": [1, 1, 2], "v": [1.0, 2.0, 3.0]}).to_parquet(root / "t.parquet")
    host_cache = root / "host_cache"
    # One backend for both caches: the union needs both branches on it.
    con = xo.connect()

    def cache():
        return ParquetSnapshotCache.from_kwargs(source=con, base_path=host_cache)

    t = xo.deferred_read_parquet(str(root / "t.parquet"))
    inner = t.filter(t.v > 0).cache(cache=cache())
    cached_agg = inner.group_by("g").agg(s=inner.v.sum()).cache(cache=cache())
    plain_agg = inner.group_by("g").agg(s=inner.v.max())
    build_path = str(xo.build_expr(cached_agg.union(plain_agg), builds_dir=root / "builds"))
    return build_path, host_cache


def _load_and_heal(build_path, cache_dir):
    """Load the build pointed at ``cache_dir`` and heal its missing
    snapshots, as POST /load_expr does before building the dataflow."""
    expr = xorq_loading.load_expr_build_dir(build_path, cache_dir=str(cache_dir))
    xorq_loading.heal_missing_snapshots(expr)
    return expr


class TestLoadExprCacheDir(tornado.testing.AsyncHTTPTestCase):
    """#972: /load_expr must be able to point the build's cache nodes at the
    embedder's cache directory rather than xorq's default ~/.cache/xorq."""

    def get_app(self):
        return make_app()

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        # Stand in for ~/.cache/xorq so a miss is observable and never
        # writes into the real user cache.
        # xorq <0.4 binds get_xorq_cache_dir into caching.storage at import;
        # later versions look it up in caching_utils at call time.
        from pathlib import Path
        import xorq.caching.storage
        self.default_cache = os.path.join(self.root, "default_cache")
        targets = ["xorq.common.utils.caching_utils.get_xorq_cache_dir"]
        if hasattr(xorq.caching.storage, "get_xorq_cache_dir"):
            targets.append("xorq.caching.storage.get_xorq_cache_dir")
        self._default_patches = [patch(t, return_value=Path(self.default_cache)) for t in targets]
        for p in self._default_patches:
            p.start()

    def tearDown(self):
        for p in self._default_patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def _default_cache_parquets(self):
        from pathlib import Path
        return sorted(Path(self.default_cache).rglob("*.parquet"))

    def test_load_expr_build_dir_redirects_nested_cache_nodes(self):
        """Every cache node, the one nested in the outer node's parent
        included, resolves under cache_dir and finds the baked snapshot."""
        from buckaroo.server import xorq_loading
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        expr = xorq_loading.load_expr_build_dir(build_path, cache_dir=str(host_cache))
        paths = _cache_node_paths(expr)
        self.assertEqual(len(paths), 2)
        for p in paths:
            self.assertIn(host_cache, p.parents)
            self.assertTrue(p.exists(), f"baked snapshot not found at {p}")

    def test_load_expr_build_dir_without_cache_dir_unchanged(self):
        """Unset cache_dir keeps xorq's default resolution."""
        from buckaroo.server import xorq_loading
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        expr = xorq_loading.load_expr_build_dir(build_path)
        for p in _cache_node_paths(expr):
            self.assertNotIn(host_cache, p.parents)

    @tornado.testing.gen_test
    async def test_load_expr_reads_embedder_snapshots(self):
        """POST /load_expr with cache_dir serves the baked snapshots: nothing
        is written under the default cache dir, the host cache gains no
        files, and the session keeps cache_dir."""
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        baked = sorted(host_cache.rglob("*.parquet"))
        sid = "lx-cache-dir"
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": sid, "build_dir": build_path, "cache_dir": str(host_cache)})
        self.assertEqual(resp.code, 200, resp.body)
        self.assertEqual(json.loads(resp.body)["rows"], 2)

        self.assertEqual(self._default_cache_parquets(), [],
            "load_expr re-executed a cached sub-graph into the default cache dir")
        self.assertEqual(sorted(host_cache.rglob("*.parquet")), baked)
        session = self._app.settings["sessions"].get(sid)
        self.assertEqual(session.cache_dir, str(host_cache))
        for p in _cache_node_paths(session.expr):
            self.assertIn(host_cache, p.parents)

    @tornado.testing.gen_test
    async def test_warm_repost_with_new_cache_dir_reloads(self):
        """A repeat POST that changes cache_dir must not take the warm-session
        early-exit — the loaded expression still points at the old dir."""
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        sid = "lx-cache-dir-change"
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": sid, "build_dir": build_path})
        self.assertEqual(resp.code, 200, resp.body)
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": sid, "build_dir": build_path, "cache_dir": str(host_cache)})
        self.assertEqual(resp.code, 200, resp.body)
        session = self._app.settings["sessions"].get(sid)
        self.assertEqual(session.cache_dir, str(host_cache))
        for p in _cache_node_paths(session.expr):
            self.assertIn(host_cache, p.parents)

    def test_heal_writes_through_its_own_tmp_file(self):
        """xorq's ``ParquetStorage.put`` writes through a fixed
        ``<key>.parquet.tmp``, so two writers of one key clobber each other's
        partial file. The heal writes a missing snapshot through a temp file
        of its own and takes no lock: another writer's in-flight tmp is left
        alone, and no ``.lock`` file is left in the embedder's cache."""
        build_path, host_cache, outer_snapshot = _build_cached_expr_dir(self.root)
        outer_snapshot.unlink()
        other_tmp = outer_snapshot.with_name(outer_snapshot.name + ".tmp")
        other_tmp.write_bytes(b"another writer, mid-write")
        expr = _load_and_heal(build_path, host_cache)
        self.assertTrue(other_tmp.exists(),
            "the heal wrote through xorq's fixed tmp and renamed another writer's file")
        self.assertEqual(other_tmp.read_bytes(), b"another writer, mid-write")
        self.assertEqual(sorted(host_cache.rglob("*.tmp")), [other_tmp])
        self.assertEqual(sorted(host_cache.rglob("*.lock")), [])
        self.assertTrue(outer_snapshot.exists())
        self.assertEqual(sorted(expr.execute()["s"]), [3.0, 3.0])

    def test_heal_leaves_inner_snapshot_under_baked_outer(self):
        """A missing inner snapshot under a baked outer one is never read,
        because the outer snapshot answers every query, so the heal must not
        recompute it (xorq's own execute() doesn't)."""
        build_path, host_cache, outer_snapshot = _build_cached_expr_dir(self.root)
        paths = _cache_node_paths(
            xorq_loading.redirect_cache_dir(xo.load_expr(build_path), host_cache))
        inner_snapshot = next(p for p in paths if p != outer_snapshot)
        inner_snapshot.unlink()
        _load_and_heal(build_path, host_cache)
        self.assertFalse(inner_snapshot.exists(),
            "the heal recomputed an inner snapshot the baked outer one makes unreachable")
        self.assertEqual(sorted(host_cache.rglob("*.parquet")), [outer_snapshot])

    def test_heal_writes_shared_inner_before_outer(self):
        """When a cached filter is shared by a cached aggregate and, through an
        uncached aggregate, the root, the heal must still write the filter's
        snapshot before the cached aggregate's. Otherwise running the
        aggregate's parent has xorq write the filter through its own put."""
        build_path, host_cache = _build_shared_cache_expr_dir(self.root)
        put_keys = []
        xorq_put = ParquetStorage.put

        def recording_put(storage, key, value, parquet_metadata=None):
            put_keys.append(key)
            return xorq_put(storage, key, value, parquet_metadata=parquet_metadata)

        with patch.object(ParquetStorage, "put", recording_put):
            expr = _load_and_heal(build_path, host_cache)
        self.assertEqual(put_keys, [],
            "a snapshot was written by xorq's put rather than by the heal")
        paths = _cache_node_paths(expr)
        self.assertEqual(len(paths), 2)
        for p in paths:
            self.assertTrue(p.exists(), f"heal did not write {p}")

    def test_heal_stamps_root_provenance(self):
        """xorq stamps provenance on the snapshot of the root cache node it
        executes. A root snapshot the heal writes carries the same metadata
        the embedder's own execute() would have written."""
        build_path, host_cache, outer_snapshot = _build_cached_expr_dir(self.root)
        baked = read_parquet_provenance(outer_snapshot)
        self.assertTrue(baked)
        outer_snapshot.unlink()
        _load_and_heal(build_path, host_cache)
        self.assertEqual(read_parquet_provenance(outer_snapshot), baked)

    def test_heal_logs_each_snapshot_it_writes(self):
        """A heal against a baked cache usually means ``cache_dir`` is spelled
        differently from the path the snapshots were baked under: xorq hashes
        ``base_path`` into the outer node's key, so the lookup misses and the
        snapshot is recomputed. Each write is logged with its path so the
        mismatch is visible."""
        build_path, host_cache, outer_snapshot = _build_cached_expr_dir(self.root)
        outer_snapshot.unlink()
        with self.assertLogs("buckaroo.server.xorq_loading", level="INFO") as logs:
            _load_and_heal(build_path, host_cache)
        self.assertTrue(any(str(outer_snapshot) in line for line in logs.output), logs.output)

    @tornado.testing.gen_test
    async def test_cache_dir_must_be_an_absolute_path(self):
        """A relative cache_dir would resolve against the server's working
        directory, not the embedder's, and a non-string can't be a path.
        Both are rejected with 400."""
        build_path = _build_expr_dir(os.path.join(self.root, "builds"))
        for bad in ("relative/cache", 1, ["/abs"]):
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-bad-cache-dir", "build_dir": build_path, "cache_dir": bad})
            self.assertEqual(resp.code, 400, (bad, resp.body))
            self.assertEqual(json.loads(resp.body)["error_code"], "invalid_cache_dir")

    @tornado.testing.gen_test
    async def test_repost_without_cache_dir_keeps_the_sessions(self):
        """cache_dir persists across re-POSTs like the other config. A warm
        re-POST that omits it takes the early-exit, and a forced reload that
        omits it still points at the session's cache_dir, never ~/.cache/xorq."""
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        sid = "lx-cache-dir-sticky"
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": sid, "build_dir": build_path, "cache_dir": str(host_cache)})
        self.assertEqual(resp.code, 200, resp.body)
        original = xorq_loading.load_expr_build_dir
        calls = []

        def counting_loader(bd, **kwargs):
            calls.append(bd)
            return original(bd, **kwargs)

        with patch.object(xorq_loading, "load_expr_build_dir", side_effect=counting_loader):
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path})
            self.assertEqual(resp.code, 200, resp.body)
            self.assertEqual(calls, [], "a warm re-POST without cache_dir re-ran the pipeline")
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path, "force_reload": True})
            self.assertEqual(resp.code, 200, resp.body)
            self.assertEqual(len(calls), 1)
        session = self._app.settings["sessions"].get(sid)
        self.assertEqual(session.cache_dir, str(host_cache))
        for p in _cache_node_paths(session.expr):
            self.assertIn(host_cache, p.parents)
        self.assertEqual(self._default_cache_parquets(), [])

    @tornado.testing.gen_test
    async def test_missing_build_dir_is_not_found(self):
        """A build dir that doesn't exist is a 404 build_dir_not_found. xorq
        reports it as an OSError from reading ``profiles.yaml``, not a
        FileNotFoundError, so the handler can't rely on the exception type."""
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": "lx-no-build", "build_dir": os.path.join(self.root, "nope")})
        self.assertEqual(resp.code, 404, resp.body)
        self.assertEqual(json.loads(resp.body)["error_code"], "build_dir_not_found")

    @tornado.testing.gen_test
    async def test_heal_file_not_found_is_a_load_error(self):
        """A FileNotFoundError raised by the heal (a snapshot dir pruned
        mid-write, say) is a load failure (500) for a build dir that exists,
        not build_dir_not_found."""
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        with patch.object(xorq_loading, "heal_missing_snapshots",
            side_effect=FileNotFoundError(str(host_cache / "parquet"))):
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-heal-fnf", "build_dir": build_path, "cache_dir": str(host_cache)})
        self.assertEqual(resp.code, 500, resp.body)
        self.assertEqual(json.loads(resp.body)["error_code"], "load_expr_error")

    @tornado.testing.gen_test
    async def test_cache_heal_has_its_own_span(self):
        """The heal runs cached sub-graphs, so it gets its own
        firstpull.cache_heal span instead of inflating firstpull.expr_load,
        which the perf harness reads as just the expression build."""
        build_path, host_cache, outer_snapshot = _build_cached_expr_dir(self.root)
        outer_snapshot.unlink()
        captured: list = []
        with patch.object(telemetry, "make_http_sink", lambda url, **kw: captured.append):
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-heal-span", "build_dir": build_path,
                 "cache_dir": str(host_cache),
                 "telemetry_url": "http://companion.invalid/internal/telemetry"})
        self.assertEqual(resp.code, 200, resp.body)
        self.assertIn("firstpull.cache_heal", [r["name"] for r in captured])
