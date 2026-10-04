"""End-to-end tests for POST /load_expr — server load path for
XorqBuckarooInfiniteWidget over a xorq/ibis expression."""
import dataclasses
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow.parquet as pq
import pytest
import tornado.gen
import tornado.httpclient
import tornado.testing
import tornado.websocket

xo = pytest.importorskip("xorq.api")

import xorq.caching.storage  # noqa: E402
from attr import evolve  # noqa: E402
from xorq.caching import ParquetSnapshotCache, ParquetStorage  # noqa: E402
from xorq.common.utils.graph_utils import replace_nodes, walk_nodes  # noqa: E402
from xorq.common.utils.provenance_utils import read_parquet_provenance  # noqa: E402
from xorq.expr.relations import CachedNode  # noqa: E402

from buckaroo.dataflow.dataflow import assemble_merged_sd  # noqa: E402
from buckaroo.dataflow.sd_cache import split_chain_by_scope  # noqa: E402
from buckaroo.jlisp.lisp_utils import s as lisp_sym  # noqa: E402
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis  # noqa: E402
from buckaroo.pluggable_analysis_framework.stat_units import merge_fragments  # noqa: E402
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline  # noqa: E402
from buckaroo.serialization_utils import resolve_summary_stats_payload  # noqa: E402
from buckaroo.server import stats_wire, telemetry, xorq_loading  # noqa: E402
from buckaroo.server.app import make_app as _make_app  # noqa: E402
from buckaroo.server.stat_run import StatRun  # noqa: E402
from buckaroo.server.stats_wire import start_stat_run  # noqa: E402
from buckaroo.server.websocket_handler import DataStreamHandler  # noqa: E402
from tests.unit.dataflow.scoped_summary_stats_test import (  # noqa: E402
    _OverridingPostProcessing, _scope_inputs, _scope_sds_by_units)

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
    async def test_ws_search_keeps_column_order(self):
        """Search's sd_updates only name the string column; the grid
        must keep the expression's column order, not move `name` ahead
        of `idx` (#988)."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "lx-order", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/lx-order")

            def headers(msg):
                return [cc["header_name"] for cc in
                    msg["df_display_args"]["main"]["df_viewer_config"]["column_config"]]

            initial = json.loads(await ws.read_message())
            self.assertEqual(headers(initial), ["idx", "name"])

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
            searched = json.loads(await ws.read_message())
            self.assertEqual(searched["type"], "initial_state")
            self.assertEqual(headers(searched), ["idx", "name"])

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


def _stats_tier_expr():
    """A 5-row table whose float column has a 1e9 maximum, so its estimated
    column width depends on the min and max that only full stats supply."""
    return xo.memtable({
        "price": [12.5, 18.9, 7.4, 22.1, 1e9],
        "qty": [1, 2, 1, 3, 2],
        "category": ["a", "b", "a", "c", "b"]})


def _build_dataflow(expr=None, **kwargs):
    return xorq_loading.XorqServerDataflow(
        _stats_tier_expr() if expr is None else expr, skip_main_serial=True, **kwargs)


def _three_scope_dataflow(expr=None, **kwargs):
    """A dataflow with a user op (clean scope) and a search (filt scope) active,
    so raw, clean and filt each hold their own summary-stats cache entry."""
    dataflow = _build_dataflow(expr, **kwargs)
    dataflow.operations = [[lisp_sym("fillna"), {"symbol": "df"}, "qty", 0]]
    dataflow.quick_command_args = {"search": ["a"]}
    return dataflow


def _spy_data_queries(monkeypatch):
    """Record the outermost op of every materialisation (``execute`` and
    ``to_pyarrow``), and every stat query XorqStatPipeline sends."""
    from xorq.vendor.ibis.expr.types.core import Expr

    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline
    ops, stat_queries = [], []
    original_execute, original_to_pyarrow = Expr.execute, Expr.to_pyarrow
    original_stat_execute = XorqStatPipeline._execute

    def spy_execute(self, *args, **kwargs):
        ops.append(type(self.op()).__name__)
        return original_execute(self, *args, **kwargs)

    def spy_to_pyarrow(self, *args, **kwargs):
        ops.append(type(self.op()).__name__)
        return original_to_pyarrow(self, *args, **kwargs)

    def spy_stat_execute(self, query):
        stat_queries.append(type(query.op()).__name__)
        return original_stat_execute(self, query)

    monkeypatch.setattr(Expr, "execute", spy_execute)
    monkeypatch.setattr(Expr, "to_pyarrow", spy_to_pyarrow)
    monkeypatch.setattr(XorqStatPipeline, "_execute", spy_stat_execute)
    return ops, stat_queries


def _without_min_width(column_config):
    return [{**cc, "ag_grid_specs": {k: v for k, v in cc["ag_grid_specs"].items() if k != "minWidth"}}
        for cc in column_config]


def _as_json(sd):
    """Comparable form of an sd: json equates NaN with NaN where == would not."""
    return json.dumps(sd, sort_keys=True, default=str)


class _NoopPostProcessing(ColAnalysis):
    provides_defaults = {}
    post_processing_method = "noop_post"

    @classmethod
    def post_process_df(cls, expr):
        return [expr, {}]


class TestStatsTierSchema:
    """``XorqServerDataflow(..., stats_tier="schema")`` (rows-first s1): the
    dataflow publishes identity and typing for every column, with no data query
    beyond the cached row count."""

    def test_matches_full_stats_display_state(self):
        expr = _stats_tier_expr()
        full = _build_dataflow(expr)
        schema = _build_dataflow(expr, stats_tier="schema")
        assert schema.df_display_args.keys() == full.df_display_args.keys()
        for name, full_arg in full.df_display_args.items():
            schema_arg = schema.df_display_args[name]
            assert schema_arg["data_key"] == full_arg["data_key"]
            assert schema_arg["summary_stats_key"] == full_arg["summary_stats_key"]
            full_cfg, schema_cfg = full_arg["df_viewer_config"], schema_arg["df_viewer_config"]
            assert schema_cfg["pinned_rows"] == full_cfg["pinned_rows"]
            assert (_without_min_width(schema_cfg["column_config"])
                == _without_min_width(full_cfg["column_config"]))

    def test_min_width_is_the_stats_derived_difference(self):
        expr = _stats_tier_expr()
        widths = {}
        for tier in ("full", "schema"):
            cfg = _build_dataflow(expr, stats_tier=tier).df_display_args["main"]["df_viewer_config"]
            widths[tier] = {cc["header_name"]: cc["ag_grid_specs"]["minWidth"]
                for cc in cfg["column_config"]}
        # price's 1e9 maximum widens it under full stats; without min and max
        # the estimate falls back to a one-digit value.
        assert widths["schema"]["price"] < widths["full"]["price"]

    def test_schema_sd_is_the_schema_keys_of_the_full_sd(self):
        expr = _stats_tier_expr()
        full_sd = _build_dataflow(expr).merged_sd
        schema_sd = _build_dataflow(expr, stats_tier="schema").merged_sd
        assert schema_sd.keys() == full_sd.keys()
        for col, stats in schema_sd.items():
            assert {"orig_col_name", "rewritten_col_name", "dtype", "_type", "is_numeric",
                "is_integer", "is_float", "is_bool", "is_datetime", "is_string",
                "length"} <= stats.keys()
            assert "mean" not in stats and "histogram" not in stats
            assert stats == {k: full_sd[col][k] for k in stats}

    def test_issues_no_data_query_besides_the_cached_count(self, monkeypatch):
        ops, stat_queries = _spy_data_queries(monkeypatch)
        dataflow = _build_dataflow(stats_tier="schema")
        dataflow.quick_command_args = {"search": ["a"]}
        dataflow.add_analysis(_NoopPostProcessing)
        assert stat_queries == []
        assert ops and set(ops) == {"CountStar"}

    def test_the_spy_sees_stat_queries_at_the_full_tier(self, monkeypatch):
        ops, stat_queries = _spy_data_queries(monkeypatch)
        _build_dataflow()
        assert stat_queries, "the spy would not notice a stat query"
        assert set(ops) - {"CountStar"}

    def test_init_sd_hints_and_overrides_still_apply(self):
        dataflow = _build_dataflow(
            stats_tier="schema",
            init_sd={"qty": {"displayer_args": {"displayer": "string", "max_length": 200}}},
            column_config_overrides={
                "category": {"displayer_args": {"displayer": "string", "max_length": 5000}}})
        cfg = dataflow.df_display_args["main"]["df_viewer_config"]["column_config"]
        by_header = {cc["header_name"]: cc for cc in cfg}
        assert by_header["qty"]["displayer_args"]["max_length"] == 200
        assert by_header["category"]["displayer_args"]["max_length"] == 5000

    def test_skipped_column_keeps_init_sd_typing(self):
        """A column in ``skip_stat_columns`` gets only name, dtype and length
        from the pipeline, so its ``_type`` comes from ``init_sd``. The schema
        tier must not layer the schema-derived typing keys over it."""
        expr = _stats_tier_expr()
        kwargs = {
            "init_sd": {"qty": {"_type": "float", "mean": 1.8, "min": 1, "max": 3}},
            "skip_stat_columns": ["qty"]}
        full = _build_dataflow(expr, **kwargs)
        schema = _build_dataflow(expr, stats_tier="schema", **kwargs)

        def merged(dataflow, orig_col):
            return next(v for v in dataflow.merged_sd.values() if v["orig_col_name"] == orig_col)

        assert merged(full, "qty")["_type"] == "float"
        assert merged(schema, "qty")["_type"] == "float"
        assert not {"is_numeric", "is_integer", "is_float"} & merged(schema, "qty").keys()
        assert merged(schema, "price")["_type"] == "float"
        assert merged(schema, "price")["is_float"] is True
        full_cfg = full.df_display_args["main"]["df_viewer_config"]["column_config"]
        schema_cfg = schema.df_display_args["main"]["df_viewer_config"]["column_config"]
        assert _without_min_width(schema_cfg) == _without_min_width(full_cfg)

    def test_sorted_infinite_request_works(self):
        dataflow = _build_dataflow(stats_tier="schema")
        qty = next(k for k, v in dataflow.merged_sd.items() if v["orig_col_name"] == "qty")
        resp, parquet = xorq_loading.handle_infinite_request_xorq(
            dataflow, {"start": 0, "end": 5, "sourceName": "default",
                "sort": qty, "sort_direction": "desc"})
        assert "error_info" not in resp
        assert resp["length"] == 5
        assert pq.read_table(io.BytesIO(parquet)).column(qty).to_pylist() == [3, 2, 2, 1, 1]

    def test_pending_state_writes_no_full_tier_cache_key(self):
        dataflow = _three_scope_dataflow(stats_tier="schema")
        chains = split_chain_by_scope(dataflow.operations)
        full_keys = {dataflow._scope_cache_key(chain, tier="full") for chain in chains.values()}
        assert len(full_keys) == 3, "raw, clean and filt must each have their own key"
        assert dataflow.summary_stats_cache
        assert not full_keys & dataflow.summary_stats_cache.keys()

    def test_later_full_assignment_reaches_merged_sd_for_all_scopes(self):
        expr = _stats_tier_expr()
        full = _three_scope_dataflow(expr)
        dataflow = _three_scope_dataflow(expr, stats_tier="schema")
        assert "mean" not in dataflow.merged_sd["a"]
        assert {"mean", "cleaned_mean", "filtered_mean"} <= full.merged_sd["a"].keys()

        dataflow.stats_tier = "full"
        dataflow.summary_sd = full.summary_sd

        assert _as_json(dataflow.merged_sd) == _as_json(full.merged_sd)

    def test_a_summary_sd_from_another_tier_is_not_cached_under_the_new_tier(self):
        """An sd computed at the schema tier must not become the full tier's
        entry because the tier flipped before the next cascade: a present key
        is a hit, so it would never be repaired."""
        dataflow = _three_scope_dataflow(stats_tier="schema")
        stale = {col: {**stats, "stale": True} for col, stats in dataflow.summary_sd.items()}

        dataflow.stats_tier = "full"
        dataflow.summary_sd = stale

        filt_sd = dataflow.summary_stats_cache[dataflow.filt_sd_key]
        assert "mean" in filt_sd["a"] and "stale" not in filt_sd["a"]
        assert "filtered_mean" in dataflow.merged_sd["a"]

    def test_full_scope_sds_cached_first_are_used_without_a_stat_query(self, monkeypatch):
        expr = _stats_tier_expr()
        full = _three_scope_dataflow(expr)
        dataflow = _three_scope_dataflow(expr, stats_tier="schema")
        cache = dict(dataflow.summary_stats_cache)
        for scope, chain in split_chain_by_scope(dataflow.operations).items():
            cache[dataflow._scope_cache_key(chain, tier="full")] = full.summary_stats_cache[
                getattr(full, f"{scope}_sd_key")]
        dataflow.summary_stats_cache = cache
        _ops, stat_queries = _spy_data_queries(monkeypatch)

        dataflow.stats_tier = "full"
        dataflow.summary_sd = full.summary_sd

        assert stat_queries == []
        assert _as_json(dataflow.merged_sd) == _as_json(full.merged_sd)


class TestLoadExprStatsPolicy(tornado.testing.AsyncHTTPTestCase):
    """``stats_tier`` and ``stats_delivery`` on POST /load_expr and
    /reload_expr (rows-first s1). The pair is stored beside dataflow_kwargs,
    replayed by /reload_expr, and kept out of the has_config tuple."""

    def get_app(self):
        return make_app()

    def _session(self, sid):
        return self._app.settings["sessions"].get(sid)

    @tornado.testing.gen_test
    async def test_defaults_are_full_and_inline(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "sp-default", "build_dir": build_path})
            self.assertEqual(resp.code, 200)
            session = self._session("sp-default")
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "inline"))
            self.assertEqual(session.xorq_dataflow.stats_tier, "full")
            self.assertIn("mean", session.xorq_dataflow.merged_sd["a"])
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_schema_tier_builds_a_schema_dataflow(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "sp-schema", "build_dir": build_path, "stats_tier": "schema"})
            self.assertEqual(resp.code, 200)
            self.assertEqual(json.loads(resp.body)["rows"], 10)
            session = self._session("sp-schema")
            self.assertEqual((session.stats_tier, session.stats_delivery), ("schema", "inline"))
            self.assertEqual(session.xorq_dataflow.stats_tier, "schema")
            self.assertNotIn("mean", session.xorq_dataflow.merged_sd["a"])
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_deferred_delivery_publishes_a_schema_dataflow_and_serves_rows(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            resp = await _post(self.get_http_port(), "/load_expr",
                {"session": "sp-deferred", "build_dir": build_path, "stats_delivery": "deferred"})
            self.assertEqual(resp.code, 200)
            session = self._session("sp-deferred")
            # The session still targets full stats; the dataflow is built at
            # the schema tier until a later phase delivers them.
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "deferred"))
            self.assertEqual(session.xorq_dataflow.stats_tier, "schema")

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/sp-deferred")
            initial = json.loads(await ws.read_message())
            self.assertEqual(initial["type"], "initial_state")
            self.assertEqual(initial["df_meta"]["total_rows"], 10)
            ws.write_message(json.dumps({"type": "infinite_request",
                "payload_args": {"start": 0, "end": 10, "sourceName": "default", "origEnd": 10}}))
            rows = json.loads(await ws.read_message())
            self.assertEqual(rows["length"], 10)
            self.assertNotIn("error_info", rows)
            table = pq.read_table(io.BytesIO(await ws.read_message()))
            self.assertEqual(table.num_rows, 10)
            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_deferred_delivery_runs_no_stat_query(self):
        from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline
        builds_root = tempfile.mkdtemp()
        stat_queries = []
        original = XorqStatPipeline._execute

        def spy(pipeline, query):
            stat_queries.append(query)
            return original(pipeline, query)

        try:
            build_path = _build_expr_dir(builds_root)
            with patch.object(XorqStatPipeline, "_execute", spy):
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": "sp-deferred-q", "build_dir": build_path,
                     "stats_delivery": "deferred"})
            self.assertEqual(resp.code, 200)
            self.assertEqual(stat_queries, [])
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_invalid_values_are_a_400(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            for field, code in (("stats_tier", "invalid_stats_tier"),
                    ("stats_delivery", "invalid_stats_delivery")):
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": "sp-bad", "build_dir": build_path, field: "sometimes"})
                self.assertEqual(resp.code, 400)
                self.assertEqual(json.loads(resp.body)["error_code"], code)
            self.assertIsNone(self._session("sp-bad"))
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_warm_repost_with_an_unchanged_pair_short_circuits(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            body = {"session": "sp-warm", "build_dir": build_path,
                "stats_tier": "schema", "stats_delivery": "deferred"}
            self.assertEqual((await _post(self.get_http_port(), "/load_expr", body)).code, 200)
            with patch.object(xorq_loading, "load_expr_build_dir",
                side_effect=AssertionError("an unchanged pair must take the warm exit")):
                same = await _post(self.get_http_port(), "/load_expr", body)
                omitted = await _post(self.get_http_port(), "/load_expr",
                    {"session": "sp-warm", "build_dir": build_path})
            self.assertEqual(same.code, 200)
            self.assertEqual(omitted.code, 200, "omitting the pair keeps the session's")
            session = self._session("sp-warm")
            self.assertEqual((session.stats_tier, session.stats_delivery), ("schema", "deferred"))
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_the_default_pair_sent_on_every_post_does_not_defeat_the_warm_exit(self):
        """has_config tests truthiness, so a host that always sends the pair
        would rebuild on every POST if the fields were in it (#944)."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            body = {"session": "sp-warm-default", "build_dir": build_path,
                "stats_tier": "full", "stats_delivery": "inline"}
            self.assertEqual((await _post(self.get_http_port(), "/load_expr", body)).code, 200)
            with patch.object(xorq_loading, "load_expr_build_dir",
                side_effect=AssertionError("the warm exit must not see the pair as config")):
                resp = await _post(self.get_http_port(), "/load_expr", body)
            self.assertEqual(resp.code, 200)
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_warm_repost_with_a_changed_pair_rebuilds(self):
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "sp-changed"
            original = xorq_loading.load_expr_build_dir
            calls = []

            def counting_loader(bd, **kwargs):
                calls.append(bd)
                return original(bd, **kwargs)

            with patch.object(xorq_loading, "load_expr_build_dir", side_effect=counting_loader):
                await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path})
                self.assertEqual(len(calls), 1)
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path, "stats_delivery": "deferred"})
                self.assertEqual(resp.code, 200)
                self.assertEqual(len(calls), 2, "a changed delivery must rebuild")
                self.assertEqual(self._session(sid).xorq_dataflow.stats_tier, "schema")
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path,
                     "stats_tier": "schema", "stats_delivery": "deferred"})
                self.assertEqual(len(calls), 3, "a changed tier must rebuild")
                resp = await _post(self.get_http_port(), "/load_expr",
                    {"session": sid, "build_dir": build_path,
                     "stats_tier": "full", "stats_delivery": "inline"})
                self.assertEqual(len(calls), 4, "returning to the defaults must rebuild")
            session = self._session(sid)
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "inline"))
            self.assertEqual(session.xorq_dataflow.stats_tier, "full")
            self.assertIn("mean", session.xorq_dataflow.merged_sd["a"])
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_reload_expr_replays_the_stored_pair(self):
        builds_root = tempfile.mkdtemp()
        project_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "sp-reload"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path, "project_root": project_root,
                 "stats_delivery": "deferred"})
            before = self._session(sid).xorq_dataflow
            resp = await _post(self.get_http_port(), f"/reload_expr/{sid}", {})
            self.assertEqual(resp.code, 200)
            session = self._session(sid)
            self.assertIsNot(session.xorq_dataflow, before)
            self.assertEqual(session.xorq_dataflow.stats_tier, "schema")
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "deferred"))
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(project_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_reload_expr_accepts_a_new_pair_and_stores_it(self):
        builds_root = tempfile.mkdtemp()
        project_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            sid = "sp-reload-new"
            await _post(self.get_http_port(), "/load_expr",
                {"session": sid, "build_dir": build_path, "project_root": project_root,
                 "stats_delivery": "deferred"})
            resp = await _post(self.get_http_port(), f"/reload_expr/{sid}",
                {"stats_delivery": "inline"})
            self.assertEqual(resp.code, 200)
            session = self._session(sid)
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "inline"))
            self.assertEqual(session.xorq_dataflow.stats_tier, "full")
            bad = await _post(self.get_http_port(), f"/reload_expr/{sid}",
                {"stats_tier": "sometimes"})
            self.assertEqual(bad.code, 400)
            self.assertEqual(json.loads(bad.body)["error_code"], "invalid_stats_tier")
            self.assertEqual((session.stats_tier, session.stats_delivery), ("full", "inline"))
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
            shutil.rmtree(project_root, ignore_errors=True)


def _build_stats_wire_dir(builds_root):
    """Build the ``_stats_tier_expr`` table to ``builds_root``. Its float column
    has a 1e9 maximum, so full stats change that column's ``minWidth`` and a
    message built from the schema tier differs from a complete one there."""
    expr = xo.memtable({
        "price": [12.5, 18.9, 7.4, 22.1, 1e9],
        "qty": [1, 2, 1, 3, 2],
        "category": ["a", "b", "a", "c", "b"]}, name="t")
    return str(xo.build_expr(expr, builds_dir=builds_root))


def _state_change(**changes):
    new_state = {"post_processing": "", "cleaning_method": "", "quick_command_args": {},
        "df_display": "main", "show_commands": False, "sampled": False, "search_string": ""}
    return json.dumps({"type": "buckaroo_state_change", "new_state": {**new_state, **changes}})


def _stats_request(stats_gen, **fields):
    return json.dumps({"type": "stats_request", "stats_gen": stats_gen, "scope": "raw", **fields})


async def _read_json(ws, timeout=3.0):
    """The next frame on ``ws``, decoded. Raises AssertionError, not a hang,
    when none arrives."""
    try:
        frame = await tornado.gen.with_timeout(
            datetime.timedelta(seconds=timeout), ws.read_message())
    except tornado.gen.TimeoutError:
        raise AssertionError(f"no frame within {timeout}s") from None
    assert frame is not None, "the connection closed"
    return json.loads(frame)


def _rows_by_stat(payload):
    """The decoded ``all_stats`` rows of a payload, keyed by stat name."""
    return {row["index"]: row for row in resolve_summary_stats_payload(payload)}


def _comparable(frame):
    """An ``initial_state`` frame as a JSON string, for comparing a legacy
    client's frame with what an inline session sends: ``all_stats`` decoded
    (its parquet bytes follow column order) and ``df_meta.stats`` dropped."""
    frame = json.loads(json.dumps(frame))
    frame["df_data_dict"]["all_stats"] = _rows_by_stat(frame["df_data_dict"]["all_stats"])
    frame["df_meta"].pop("stats", None)
    return _as_json(frame)


@contextmanager
def _count_stat_queries():
    """Record every query ``XorqStatPipeline`` sends while the block runs."""
    queries = []
    original = XorqStatPipeline._execute

    def spy(pipeline, query):
        queries.append(query)
        return original(pipeline, query)

    with patch.object(XorqStatPipeline, "_execute", spy):
        yield queries


def _merge_stat_payloads(payloads):
    """What a client holds after key-merging ``stats_update`` payloads into
    ``all_stats``, as ``StatsChannel`` does: a cell a payload carries replaces
    the held one, and a null (the wide pivot's fill for a stat a column did not
    carry) never replaces a value."""
    merged = {}
    for payload in payloads:
        for stat, row in _rows_by_stat(payload).items():
            cells = merged.setdefault(stat, {})
            for column, value in row.items():
                if column == "index" or (value is None and cells.get(column) is not None):
                    continue
                cells[column] = value
    return merged


class _SlowStats:
    """A stats class whose units run for real, each after ``delay`` seconds, as
    a slow query would. ``fail_on`` names a unit that raises instead."""

    def __init__(self, stats, delay=0.0, fail_on=None):
        self._stats, self._delay, self._fail_on = stats, delay, fail_on
        self.state = stats.state

    def plan(self, state):
        return self._stats.plan(state)

    def new_accumulator(self, state):
        return self._stats.new_accumulator(state)

    def run(self, unit, acc):
        time.sleep(self._delay)
        if unit.id == self._fail_on:
            raise RuntimeError(f"{unit.id} failed")
        return self._stats.run(unit, acc)


class TestStatsWire(tornado.testing.AsyncHTTPTestCase):
    """``stats_request``, ``stats_update`` and ``stats_aborted`` on a deferred
    ``/load_expr`` session, the ``stats_gen`` counter and ``df_meta.stats``, and
    the per-connection capability (``?caps=stats_update``) that keeps a client
    without it on complete messages (rows-first s3)."""

    def get_app(self):
        return make_app()

    def setUp(self):
        super().setUp()
        self.builds_root = tempfile.mkdtemp()
        self.project_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.builds_root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.project_root, ignore_errors=True)
        pp_dir = os.path.join(self.project_root, "post_processing")
        os.makedirs(pp_dir)
        with open(os.path.join(pp_dir, "first_three.py"), "w") as f:
            f.write("def process(expr):\n    return expr.limit(3)\n")
        self.build_path = _build_stats_wire_dir(self.builds_root)
        self.clients = []

    def tearDown(self):
        for ws in self.clients:
            ws.close()
        super().tearDown()

    def _session(self, sid):
        return self._app.settings["sessions"].get(sid)

    async def _load(self, sid, **body):
        resp = await _post(self.get_http_port(), "/load_expr",
            {"session": sid, "build_dir": self.build_path, "project_root": self.project_root, **body})
        self.assertEqual(resp.code, 200, resp.body)

    async def _connect(self, sid, caps=None):
        """Open a WebSocket, with ``caps`` as ``?caps=``. Returns it with its
        first ``initial_state``."""
        suffix = f"?caps={caps}" if caps else ""
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/{sid}{suffix}")
        self.clients.append(ws)
        return ws, await _read_json(ws)

    def _stats(self, frame):
        stats = frame["df_meta"].get("stats")
        self.assertIsNotNone(stats, "initial_state carries no df_meta.stats")
        return stats

    async def _inline_frame(self, sid, **changes):
        """What an inline session of the same build sends a client: the complete
        message every complete message here must match. ``changes`` are sent as
        a state change first, and the broadcast that follows is returned."""
        await self._load(sid)
        ws, frame = await self._connect(sid)
        if changes:
            ws.write_message(_state_change(**changes))
            frame = await _read_json(ws)
        return frame

    def _assert_pending(self, frame, gen):
        stats = self._stats(frame)
        self.assertEqual((stats["status"], stats["tier"], stats["gen"]), ("pending", "schema", gen))
        self.assertEqual(list(_rows_by_stat(frame["df_data_dict"]["all_stats"])), ["dtype"],
            "a pending frame must carry the schema tier only")

    def _assert_complete(self, frame, gen, inline_frame):
        stats = self._stats(frame)
        self.assertEqual((stats["status"], stats["tier"], stats["gen"]), ("complete", "full", gen))
        self.assertIn("histogram_bins", _rows_by_stat(frame["df_data_dict"]["all_stats"]))
        self.assertEqual(_comparable(frame), _comparable(inline_frame))

    async def _pair(self, sid):
        """A caps client, then a legacy client, on a deferred session. The
        legacy client's connect completes the stats, so a later push is the
        first thing to put the session back to pending."""
        await self._load(sid, stats_delivery="deferred")
        a, a_open = await self._connect(sid, caps="stats_update")
        b, b_open = await self._connect(sid)
        return a, a_open, b, b_open

    @tornado.testing.gen_test
    async def test_stats_request_returns_a_stats_update_that_completes_the_stats(self):
        await self._load("sw-complete", stats_delivery="deferred")
        inline = await self._inline_frame("sw-complete-inline")
        ws, first = await self._connect("sw-complete", caps="stats_update")
        gen = self._stats(first)["gen"]
        self._assert_pending(first, gen)
        self.assertEqual(first["protocol_version"], 1)

        ws.write_message(_stats_request(gen))
        update = await _read_json(ws)

        self.assertEqual(update["type"], "stats_update")
        self.assertEqual(update["stats_gen"], gen)
        self.assertEqual((update["scope"], update["tier"], update["final"]), ("raw", "full", True))
        self.assertEqual((update["payload"]["format"], update["payload"]["layout"]),
            ("parquet_b64", "wide"), "the payload must be inline, so binary pairing stays single-slot")
        self.assertEqual(_rows_by_stat(update["payload"]),
            _rows_by_stat(inline["df_data_dict"]["all_stats"]))
        self.assertIsInstance(update["elapsed_ms"], (int, float))

    @tornado.testing.gen_test
    async def test_rows_are_served_before_and_after_the_stats_request(self):
        await self._load("sw-rows", stats_delivery="deferred")
        ws, first = await self._connect("sw-rows", caps="stats_update")
        window = {"start": 0, "end": 5, "sourceName": "default", "origEnd": 5}
        ws.write_message(json.dumps({"type": "infinite_request", "payload_args": window}))
        self.assertEqual((await _read_json(ws))["length"], 5)
        pq.read_table(io.BytesIO(await ws.read_message()))
        ws.write_message(_stats_request(self._stats(first)["gen"]))
        self.assertEqual((await _read_json(ws))["type"], "stats_update")
        ws.write_message(json.dumps({"type": "infinite_request", "payload_args": window}))
        self.assertEqual((await _read_json(ws))["type"], "infinite_resp",
            "a stats_update must leave no stray binary frame in the stream")

    @tornado.testing.gen_test
    async def test_a_stale_stats_gen_gets_stats_aborted_and_runs_nothing(self):
        await self._load("sw-stale", stats_delivery="deferred")
        ws, first = await self._connect("sw-stale", caps="stats_update")
        gen = self._stats(first)["gen"]

        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen - 1))
            aborted = await _read_json(ws)
        self.assertEqual(aborted["type"], "stats_aborted")
        self.assertEqual((aborted["stats_gen"], aborted["current_gen"], aborted["reason"]),
            (gen - 1, gen, "stale"))
        self.assertEqual(queries, [], "a stale request must run no stat query")

        ws.write_message(_stats_request(gen))
        self.assertEqual((await _read_json(ws))["type"], "stats_update",
            "the stale request must not have consumed or failed the session's stats")

    @tornado.testing.gen_test
    async def test_an_unsupported_scope_gets_stats_aborted(self):
        await self._load("sw-scope", stats_delivery="deferred")
        ws, first = await self._connect("sw-scope", caps="stats_update")
        ws.write_message(_stats_request(self._stats(first)["gen"], scope="filt"))
        aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["reason"], aborted["scope"]),
            ("stats_aborted", "unsupported_scope", "filt"))

    @tornado.testing.gen_test
    async def test_load_expr_and_reload_expr_bump_stats_gen(self):
        await self._load("sw-gen", stats_delivery="deferred")
        ws, first = await self._connect("sw-gen", caps="stats_update")
        gen = self._stats(first)["gen"]

        await self._load("sw-gen", stats_delivery="deferred", force_reload=True)
        pushed = await _read_json(ws)
        self.assertGreater(self._stats(pushed)["gen"], gen, "/load_expr must bump stats_gen")
        gen = self._stats(pushed)["gen"]

        resp = await _post(self.get_http_port(), "/reload_expr/sw-gen", {})
        self.assertEqual(resp.code, 200, resp.body)
        pushed = await _read_json(ws)
        self.assertGreater(self._stats(pushed)["gen"], gen, "/reload_expr must bump stats_gen")

    @tornado.testing.gen_test
    async def test_df_meta_stats_survives_a_dataflow_field_change(self):
        await self._load("sw-change", stats_delivery="deferred")
        ws, first = await self._connect("sw-change", caps="stats_update")
        gen = self._stats(first)["gen"]
        ws.write_message(_stats_request(gen))
        self.assertEqual((await _read_json(ws))["type"], "stats_update")

        with _count_stat_queries() as queries:
            ws.write_message(_state_change(quick_command_args={"search": ["a"]}))
            changed = await _read_json(ws)
        self._assert_pending(changed, gen + 1)
        self.assertEqual(queries, [], "a dataflow-field change on a deferred session must run no stats")
        # The dataflow rebuilt df_meta for the filtered state; its keys are still there.
        self.assertEqual((changed["df_meta"]["total_rows"], changed["df_meta"]["filtered_rows"]), (5, 2))

        ws.write_message(_stats_request(gen))
        aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["current_gen"], aborted["reason"]),
            ("stats_aborted", gen + 1, "stale"))
        ws.write_message(_stats_request(gen + 1))
        update = await _read_json(ws)
        self.assertEqual((update["type"], update["stats_gen"], update["final"]),
            ("stats_update", gen + 1, True))

    @tornado.testing.gen_test
    async def test_a_legacy_client_stays_complete_while_a_caps_client_gets_a_stats_free_frame(self):
        sid = "sw-ab"
        inline = await self._inline_frame("sw-ab-inline", post_processing="first_three")
        await self._load(sid, stats_delivery="deferred")
        a1, a1_open = await self._connect(sid, caps="other,stats_update")
        a2, _ = await self._connect(sid, caps="stats_update")
        # Connecting runs the missing stats for a legacy client, so the session
        # is complete when B1 changes it.
        b1, b1_open = await self._connect(sid, caps="unknown")
        b2, _ = await self._connect(sid)
        gen = self._stats(a1_open)["gen"]
        self.assertEqual(self._stats(b1_open)["status"], "complete")

        with _count_stat_queries() as queries:
            b1.write_message(_state_change(post_processing="first_three"))
            frames = {name: await _read_json(ws)
                for name, ws in (("a1", a1), ("a2", a2), ("b1", b1), ("b2", b2))}
            for name in ("a1", "a2"):
                self._assert_pending(frames[name], gen + 1)
            for name in ("b1", "b2"):
                self._assert_complete(frames[name], gen + 1, inline)
            ran = len(queries)
            self.assertGreater(ran, 0, "B's frame must have run the stats it carries")

            a1.write_message(_stats_request(gen + 1))
            update = await _read_json(a1)
            self.assertEqual((update["type"], update["stats_gen"]), ("stats_update", gen + 1))
            self.assertEqual(_rows_by_stat(update["payload"]),
                _rows_by_stat(frames["b1"]["df_data_dict"]["all_stats"]))
            self.assertEqual(len(queries), ran,
                "A's request must be answered from the stats B's frame computed")

    @tornado.testing.gen_test
    async def test_load_expr_push_keeps_a_legacy_client_complete(self):
        sid = "sw-push-load-expr"
        inline = await self._inline_frame("sw-push-load-expr-inline")
        a, a_open, b, _ = await self._pair(sid)
        gen = self._stats(a_open)["gen"]
        await self._load(sid, stats_delivery="deferred", force_reload=True)
        self._assert_pending(await _read_json(a), gen + 1)
        self._assert_complete(await _read_json(b), gen + 1, inline)

    @tornado.testing.gen_test
    async def test_reload_expr_push_keeps_a_legacy_client_complete(self):
        sid = "sw-push-reload"
        inline = await self._inline_frame("sw-push-reload-inline")
        a, a_open, b, _ = await self._pair(sid)
        gen = self._stats(a_open)["gen"]
        resp = await _post(self.get_http_port(), f"/reload_expr/{sid}", {})
        self.assertEqual(resp.code, 200, resp.body)
        self._assert_pending(await _read_json(a), gen + 1)
        self._assert_complete(await _read_json(b), gen + 1, inline)

    @tornado.testing.gen_test
    async def test_load_push_leaves_both_clients_complete(self):
        """/load swaps the session to pandas, which has no deferred stats: the
        stored policy must not leave it looking pending."""
        sid = "sw-push-load"
        a, _, b, _ = await self._pair(sid)
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(csv_fd)
        try:
            pd.DataFrame({"x": [1, 2, 3], "y": ["p", "q", "r"]}).to_csv(csv_path, index=False)
            resp = await _post(self.get_http_port(), "/load",
                {"session": sid, "path": csv_path, "mode": "buckaroo"})
            self.assertEqual(resp.code, 200, resp.body)
        finally:
            os.unlink(csv_path)
        frames = [await _read_json(a), await _read_json(b)]
        for frame in frames:
            self.assertNotIn("stats", frame["df_meta"])
            self.assertIn("histogram_bins", _rows_by_stat(frame["df_data_dict"]["all_stats"]))
        self.assertEqual(_comparable(frames[0]), _comparable(frames[1]))

    @tornado.testing.gen_test
    async def test_load_compare_push_leaves_both_clients_complete(self):
        sid = "sw-push-compare"
        a, _, b, _ = await self._pair(sid)
        paths = []
        try:
            for frame in (pd.DataFrame({"id": [1, 2], "v": [10, 20]}),
                    pd.DataFrame({"id": [1, 3], "v": [10, 30]})):
                fd, path = tempfile.mkstemp(suffix=".csv")
                os.close(fd)
                frame.to_csv(path, index=False)
                paths.append(path)
            resp = await _post(self.get_http_port(), "/load_compare",
                {"session": sid, "path1": paths[0], "path2": paths[1], "join_columns": ["id"]})
            self.assertEqual(resp.code, 200, resp.body)
        finally:
            for path in paths:
                os.unlink(path)
        frames = [await _read_json(a), await _read_json(b)]
        for frame in frames:
            self.assertNotIn("stats", frame["df_meta"])
        self.assertEqual(_comparable(frames[0]), _comparable(frames[1]))

    @tornado.testing.gen_test
    async def test_highlight_overlay_is_complete_for_a_legacy_client_and_stats_free_for_a_caps_client(self):
        sid = "sw-overlay"
        await self._load(sid, stats_delivery="deferred")
        a, a_open = await self._connect(sid, caps="stats_update")
        gen = self._stats(a_open)["gen"]

        a.write_message(_state_change(search_string="ca"))
        a_overlay = await _read_json(a)
        self._assert_pending(a_overlay, gen)

        b, _ = await self._connect(sid)
        b.write_message(_state_change(search_string="ca"))
        b_overlay = await _read_json(b)
        self.assertEqual(self._stats(b_overlay)["status"], "complete")
        self.assertIn("histogram_bins", _rows_by_stat(b_overlay["df_data_dict"]["all_stats"]))
        # The overlay's display config is the complete one with the highlight on top.
        session_args = self._session(sid).df_display_args["main"]["df_viewer_config"]["column_config"]
        by_col = {cc["col_name"]: cc for cc in b_overlay["df_display_args"]["main"]["df_viewer_config"]["column_config"]}
        for expected in session_args:
            self.assertEqual(by_col[expected["col_name"]]["ag_grid_specs"], expected["ag_grid_specs"])
        highlighted = [cc for cc in by_col.values()
            if cc.get("displayer_args", {}).get("highlight_phrase") == ["ca"]]
        self.assertTrue(highlighted, "the overlay must still carry the highlight")

    @tornado.testing.gen_test
    async def test_overlay_for_a_legacy_client_is_built_after_its_stats_are_completed(self):
        """Completing the stats replaces the session's display config, so an
        overlay that copied it first would send a legacy client the schema
        tier's. Every send completes a session that has a legacy client
        connected, so only a direct call reaches a pending session here."""
        await self._load("sw-overlay-order", stats_delivery="deferred")
        session = self._session("sw-overlay-order")
        sent: list = []
        legacy = SimpleNamespace(search_string="ca", caps=frozenset(), session_id="sw-overlay-order",
            write_message=sent.append)
        self.assertEqual(getattr(session, "stats_status", None), "pending")

        DataStreamHandler._send_highlight_overlay(legacy, session)

        self.assertEqual(session.stats_status, "complete")
        overlay = json.loads(sent[0])["df_display_args"]["main"]["df_viewer_config"]["column_config"]
        complete = session.df_display_args["main"]["df_viewer_config"]["column_config"]
        self.assertEqual({cc["col_name"]: cc["ag_grid_specs"] for cc in overlay},
            {cc["col_name"]: cc["ag_grid_specs"] for cc in complete})

    @tornado.testing.gen_test
    async def test_a_client_connecting_after_completion_gets_the_complete_state(self):
        inline = await self._inline_frame("sw-late-inline")
        await self._load("sw-late", stats_delivery="deferred")
        a, a_open = await self._connect("sw-late", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        a.write_message(_stats_request(gen))
        self.assertEqual((await _read_json(a))["type"], "stats_update")

        with _count_stat_queries() as queries:
            _, late = await self._connect("sw-late", caps="stats_update")
            _, legacy = await self._connect("sw-late")
        self._assert_complete(late, gen, inline)
        self._assert_complete(legacy, gen, inline)
        self.assertEqual(queries, [], "stats computed once must not be computed again for a later client")

    @tornado.testing.gen_test
    async def test_a_legacy_client_connecting_to_a_pending_session_completes_it(self):
        inline = await self._inline_frame("sw-open-inline")
        await self._load("sw-open", stats_delivery="deferred")
        _, legacy = await self._connect("sw-open")
        self._assert_complete(legacy, self._stats(legacy)["gen"], inline)

    @tornado.testing.gen_test
    async def test_a_session_targeting_the_schema_tier_is_not_computed(self):
        await self._load("sw-schema", stats_tier="schema", stats_delivery="deferred")
        ws, first = await self._connect("sw-schema", caps="stats_update")
        stats = self._stats(first)
        self.assertEqual((stats["status"], stats["tier"], stats["reason"]), ("not_computed", "schema", "host"))
        ws.write_message(_stats_request(stats["gen"]))
        aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["reason"]), ("stats_aborted", "not_requestable"))
        # Nothing is missing relative to the schema tier, so a legacy client
        # gets the schema tier, as it does from an inline schema session.
        _, legacy = await self._connect("sw-schema")
        self.assertEqual(list(_rows_by_stat(legacy["df_data_dict"]["all_stats"])), ["dtype"])
        await self._load("sw-schema-inline", stats_tier="schema")
        _, inline_schema = await self._connect("sw-schema-inline")
        self.assertEqual(self._stats(inline_schema)["status"], "not_computed")

    @tornado.testing.gen_test
    async def test_a_failed_stats_run_reports_error_until_the_next_generation(self):
        await self._load("sw-error", stats_delivery="deferred")
        ws, first = await self._connect("sw-error", caps="stats_update")
        gen = self._stats(first)["gen"]

        with patch.object(xorq_loading.XorqServerDataflow, "_get_summary_sd",
            side_effect=RuntimeError("stats query failed")):
            ws.write_message(_stats_request(gen))
            aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["stats_gen"], aborted["reason"]), ("stats_aborted", gen, "error"))

        # The failure is the session's state for this generation: a client that
        # connects now is told so, and a legacy client still gets its frame.
        _, caps_frame = await self._connect("sw-error", caps="stats_update")
        stats = self._stats(caps_frame)
        self.assertEqual((stats["status"], stats["tier"], stats["gen"]), ("error", "schema", gen))
        self.assertIn("reason", stats)
        _, legacy = await self._connect("sw-error")
        self.assertEqual(legacy["type"], "initial_state")
        self.assertEqual(list(_rows_by_stat(legacy["df_data_dict"]["all_stats"])), ["dtype"])

        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen))
            self.assertEqual((await _read_json(ws))["reason"], "error")
        self.assertEqual(queries, [], "a failed generation must not be retried by every request")

        ws.write_message(_state_change(quick_command_args={"search": ["a"]}))
        self._assert_pending(await _read_json(ws), gen + 1)
        ws.write_message(_stats_request(gen + 1))
        self.assertEqual((await _read_json(ws))["type"], "stats_update")

    @tornado.testing.gen_test
    async def test_stats_request_emits_a_stats_request_span(self):
        captured: list = []
        with patch.object(telemetry, "make_http_sink", lambda url, **kw: captured.append):
            await self._load("sw-span", stats_delivery="deferred",
                telemetry_url="http://companion.invalid/internal/telemetry")
            ws, first = await self._connect("sw-span", caps="stats_update")
            gen = self._stats(first)["gen"]
            ws.write_message(_stats_request(gen - 1))
            await _read_json(ws)
            ws.write_message(_stats_request(gen, columns=["price"]))
            await _read_json(ws)

        stale, served = [r for r in captured if r["name"] == "stats.request"]
        self.assertEqual(served["trace"], "sw-span")
        self.assertEqual((served["attrs"]["stats_gen"], served["attrs"]["scope"], served["attrs"]["tier"]),
            (gen, "raw", "full"))
        self.assertEqual((served["attrs"]["outcome"], served["attrs"]["columns"]), ("update", 1))
        self.assertEqual((stale["attrs"]["outcome"], stale["attrs"]["stats_gen"]), ("stale", gen - 1))
        self.assertIn("firstpull.stats_total", [r["name"] for r in captured])

    @tornado.testing.gen_test
    async def test_returning_to_a_completed_state_is_answered_from_the_cache(self):
        await self._load("sw-revisit", stats_delivery="deferred")
        ws, first = await self._connect("sw-revisit", caps="stats_update")
        gen = self._stats(first)["gen"]
        ws.write_message(_stats_request(gen))
        original = await _read_json(ws)
        ws.write_message(_state_change(quick_command_args={"search": ["a"]}))
        self._assert_pending(await _read_json(ws), gen + 1)
        ws.write_message(_stats_request(gen + 1))
        self.assertEqual((await _read_json(ws))["type"], "stats_update")

        ws.write_message(_state_change(quick_command_args={}))
        self._assert_pending(await _read_json(ws), gen + 2)
        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen + 2))
            again = await _read_json(ws)
        self.assertEqual(queries, [], "the first state's stats are in summary_stats_cache")
        self.assertEqual(_rows_by_stat(again["payload"]), _rows_by_stat(original["payload"]))

    @tornado.testing.gen_test
    async def test_completing_the_stats_keeps_component_config(self):
        await self._load("sw-theme", stats_delivery="deferred", component_config={"className": "sw-themed"})
        ws, first = await self._connect("sw-theme", caps="stats_update")
        ws.write_message(_stats_request(self._stats(first)["gen"]))
        self.assertEqual((await _read_json(ws))["type"], "stats_update")
        _, late = await self._connect("sw-theme", caps="stats_update")
        dvc = late["df_display_args"]["main"]["df_viewer_config"]
        self.assertEqual(dvc["component_config"]["className"], "sw-themed")

    @tornado.testing.gen_test
    async def test_a_warm_load_expr_keeps_the_generation(self):
        await self._load("sw-warm", stats_delivery="deferred")
        _, first = await self._connect("sw-warm", caps="stats_update")
        gen = self._stats(first)["gen"]
        await self._load("sw-warm", stats_delivery="deferred")
        _, again = await self._connect("sw-warm", caps="stats_update")
        self.assertEqual(self._stats(again)["gen"], gen, "a warm exit rebuilds nothing, so the generation stands")

    @tornado.testing.gen_test
    async def test_a_stats_request_with_no_data_loaded_is_aborted(self):
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/sw-no-data?caps=stats_update")
        self.clients.append(ws)
        ws.write_message(_stats_request(1))
        aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["reason"]), ("stats_aborted", "no_data"))

    @tornado.testing.gen_test
    async def test_inline_sessions_send_no_df_meta_stats(self):
        """Default behaviour: a session with the default policy sends the
        message it always has, and a client reads the absence as complete."""
        await self._load("sw-inline")
        _, frame = await self._connect("sw-inline", caps="stats_update")
        self.assertNotIn("stats", frame["df_meta"])
        self.assertIn("histogram_bins", _rows_by_stat(frame["df_data_dict"]["all_stats"]))


    @tornado.testing.gen_test
    async def test_a_stat_run_is_started_on_the_session_for_the_current_generation(self):
        await self._load("sw-run", stats_delivery="deferred")
        session = self._session("sw-run")
        self.assertEqual(session.stat_runs, {})

        with _count_stat_queries() as queries:
            run = start_stat_run(session)
            self.assertIs(start_stat_run(session), run, "one run per generation and scope")

        self.assertEqual(queries, [], "planning a run runs no query")
        self.assertEqual(run.key, (session.stats_gen, "raw"))
        self.assertEqual(session.stat_runs, {run.key: run})
        self.assertEqual(run.remaining, 4, "the scalar batch and one histogram unit for each of three columns")
        self.assertEqual(run.units[0].id, "batch")

    @tornado.testing.gen_test
    async def test_a_run_ends_with_the_summary_sd_an_inline_session_computes(self):
        await self._load("sw-run-sd", stats_delivery="deferred")
        session = self._session("sw-run-sd")
        run = start_stat_run(session)
        while run.run_next() is not None:
            pass
        inline = xorq_loading.XorqServerDataflow(session.expr, skip_main_serial=True)
        self.assertEqual(run.status, "complete")
        self.assertEqual(_as_json(run.raw_sd()), _as_json(inline.summary_sd))

    @tornado.testing.gen_test
    async def test_a_dataflow_field_change_drops_the_run_and_a_search_term_change_keeps_it(self):
        await self._load("sw-drop", stats_delivery="deferred")
        ws, _first = await self._connect("sw-drop", caps="stats_update")
        session = self._session("sw-drop")
        run = start_stat_run(session)

        ws.write_message(_state_change(search_string="alp"))
        await _read_json(ws)  # this client's highlight overlay
        self.assertEqual(session.stat_runs, {run.key: run}, "a typed search term touches no stats")

        ws.write_message(_state_change(post_processing="first_three"))
        await _read_json(ws)
        self.assertEqual(session.stat_runs, {})
        self.assertEqual(session.stats_gen, run.stats_gen + 1)
        again = start_stat_run(session)
        self.assertEqual(again.key, (run.stats_gen + 1, "raw"))
        self.assertIsNot(again, run)

    @tornado.testing.gen_test
    async def test_reload_expr_drops_the_run(self):
        await self._load("sw-drop-reload", stats_delivery="deferred")
        session = self._session("sw-drop-reload")
        start_stat_run(session)
        resp = await _post(self.get_http_port(), "/reload_expr/sw-drop-reload", {})
        self.assertEqual(resp.code, 200, resp.body)
        self.assertEqual(session.stat_runs, {})

    @tornado.testing.gen_test
    async def test_each_connection_keeps_its_own_cursor_into_the_run(self):
        await self._load("sw-cursor", stats_delivery="deferred")
        await self._connect("sw-cursor", caps="stats_update")
        await self._connect("sw-cursor", caps="stats_update")
        session = self._session("sw-cursor")
        cursor_a, cursor_b = [handler.stats_cursor for handler in session.ws_clients]
        self.assertIsNot(cursor_a, cursor_b)
        self.assertEqual((cursor_a.position, cursor_b.position), (0, 0))

        run = start_stat_run(session)
        run.run_next()
        run.run_next()
        first = cursor_a.take(run)
        self.assertEqual((len(first), cursor_b.position), (2, 0))
        while run.run_next() is not None:
            pass
        rest, everything = cursor_a.take(run), cursor_b.take(run)

        self.assertEqual(merge_fragments(first + rest), merge_fragments(everything))
        self.assertEqual(len(set(run.ran)), len(run.units), "no unit ran twice")

    def _budget(self, seconds):
        """Set the time budget of an incremental request for the rest of the
        test. Zero runs exactly one unit per request, whatever it costs."""
        patcher = patch.object(stats_wire, "STATS_BUDGET_S", seconds, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def _pull_stats(self, ws, gen, limit=12, **fields):
        """Send incremental ``stats_request``s on ``ws`` until the final reply
        (or an abort) and return every reply."""
        replies = []
        for _ in range(limit):
            ws.write_message(_stats_request(gen, incremental=True, **fields))
            reply = await _read_json(ws)
            replies.append(reply)
            if reply["type"] != "stats_update" or reply["final"]:
                break
        return replies

    def _wrapped_run(self, sid, **kwargs):
        """Give the session a StatRun for its current generation whose units run
        for real but through ``_SlowStats``."""
        session = self._session(sid)
        dataflow = session.xorq_dataflow
        run = StatRun(session.stats_gen, "raw",
            _SlowStats(dataflow.build_stats(dataflow.processed_df, run=False), **kwargs))
        session.stat_runs[run.key] = run
        return run

    async def _infinite_window(self, ws, end=5):
        ws.write_message(json.dumps({"type": "infinite_request",
            "payload_args": {"start": 0, "end": end, "sourceName": "default", "origEnd": end}}))
        resp = await _read_json(ws)
        pq.read_table(io.BytesIO(await ws.read_message()))
        return resp

    @tornado.testing.gen_test
    async def test_incremental_requests_run_one_unit_each_and_end_with_the_complete_state(self):
        inline = await self._inline_frame("sw-inc-inline")
        await self._load("sw-inc", stats_delivery="deferred")
        ws, first = await self._connect("sw-inc", caps="stats_update")
        gen = self._stats(first)["gen"]
        self._budget(0)

        with _count_stat_queries() as queries:
            replies = await self._pull_stats(ws, gen)

        self.assertEqual([r["type"] for r in replies], ["stats_update"] * 4)
        self.assertEqual([r["final"] for r in replies], [False, False, False, True])
        self.assertEqual([r["remaining"] for r in replies], [3, 2, 1, 0])
        self.assertEqual(len(queries), 4, "one query for each unit, none repeated")
        for reply in replies:
            self.assertEqual((reply["stats_gen"], reply["scope"], reply["tier"]), (gen, "raw", "full"))
            self.assertIsInstance(reply["elapsed_ms"], (int, float))
        self.assertNotIn("histogram", _rows_by_stat(replies[0]["payload"]), "the scalar batch comes first")
        self.assertIn("histogram", _rows_by_stat(replies[1]["payload"]))
        self.assertEqual(_as_json(_merge_stat_payloads(r["payload"] for r in replies)),
            _as_json(_merge_stat_payloads([inline["df_data_dict"]["all_stats"]])))

    @tornado.testing.gen_test
    async def test_the_last_unit_assigns_the_stats_and_frees_the_run(self):
        await self._load("sw-assign", stats_delivery="deferred")
        ws, first = await self._connect("sw-assign", caps="stats_update")
        gen = self._stats(first)["gen"]
        session = self._session("sw-assign")
        dataflow = session.xorq_dataflow
        key = dataflow._scope_cache_key(split_chain_by_scope(dataflow.operations)["filt"], tier="full")
        self._budget(0)

        ws.write_message(_stats_request(gen, incremental=True))
        await _read_json(ws)
        self.assertEqual(len(session.stat_runs[(gen, "raw")].fragments), 1)
        self.assertEqual((session.stats_status, dataflow.stats_tier), ("pending", "schema"))
        self.assertNotIn(key, dataflow.summary_stats_cache, "a partial run writes nothing into the dataflow")

        await self._pull_stats(ws, gen)
        self.assertEqual(session.stat_runs, {}, "the accumulator is freed with the run")
        self.assertEqual((session.stats_status, dataflow.stats_tier), ("complete", "full"))
        self.assertIn(key, dataflow.summary_stats_cache)
        self.assertIn("histogram_bins", _rows_by_stat(session.df_data_dict["all_stats"]),
            "the session snapshot is refreshed in the same step")
        self.assertEqual(_as_json(dataflow.summary_sd), _as_json(dataflow.summary_stats_cache[key]))

    @tornado.testing.gen_test
    async def test_a_long_budget_runs_every_unit_in_one_request(self):
        await self._load("sw-warm-budget", stats_delivery="deferred")
        ws, first = await self._connect("sw-warm-budget", caps="stats_update")
        self._budget(3600)
        with _count_stat_queries() as queries:
            replies = await self._pull_stats(ws, self._stats(first)["gen"])
        self.assertEqual(len(replies), 1)
        self.assertEqual((replies[0]["final"], replies[0]["remaining"]), (True, 0))
        self.assertEqual(len(queries), 4)

    @tornado.testing.gen_test
    async def test_the_columns_hint_orders_the_units_of_a_request(self):
        await self._load("sw-hint", stats_delivery="deferred")
        ws, first = await self._connect("sw-hint", caps="stats_update")
        gen = self._stats(first)["gen"]
        self._budget(0)
        ws.write_message(_stats_request(gen, incremental=True, columns=["c"]))
        await _read_json(ws)
        ws.write_message(_stats_request(gen, incremental=True, columns=["c"]))
        reply = await _read_json(ws)
        run = self._session("sw-hint").stat_runs[(gen, "raw")]
        self.assertEqual(run.ran, ["batch", "histogram:category"],
            "the batch every histogram reads goes first, then the unit of the column named, c being category")
        columns = {name for row in _rows_by_stat(reply["payload"]).values() for name in row if name != "index"}
        self.assertEqual(columns, {"c"})

    @tornado.testing.gen_test
    async def test_a_stale_gen_mid_run_gets_stats_aborted_and_the_next_generation_starts_over(self):
        await self._load("sw-mid-stale", stats_delivery="deferred")
        ws, first = await self._connect("sw-mid-stale", caps="stats_update")
        gen = self._stats(first)["gen"]
        self._budget(0)
        ws.write_message(_stats_request(gen, incremental=True))
        self.assertFalse((await _read_json(ws))["final"])

        ws.write_message(_state_change(quick_command_args={"search": ["a"]}))
        self._assert_pending(await _read_json(ws), gen + 1)
        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen, incremental=True))
            aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["reason"], aborted["current_gen"]),
            ("stats_aborted", "stale", gen + 1))
        self.assertEqual(queries, [], "a stale request runs no unit")

        replies = await self._pull_stats(ws, gen + 1)
        self.assertEqual([r["remaining"] for r in replies], [3, 2, 1, 0], "the new generation runs every unit again")

    @tornado.testing.gen_test
    async def test_client_b_opening_after_client_a_finished_gets_the_complete_all_stats(self):
        inline = await self._inline_frame("sw-after-inline")
        await self._load("sw-after", stats_delivery="deferred")
        a, a_open = await self._connect("sw-after", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        self._budget(0)
        self.assertEqual(len(await self._pull_stats(a, gen)), 4)

        with _count_stat_queries() as queries:
            b, b_open = await self._connect("sw-after", caps="stats_update")
        self._assert_complete(b_open, gen, inline)
        self.assertEqual(queries, [], "the stats A's run produced are not computed again for B")

        b.write_message(_stats_request(gen, incremental=True))
        reply = await _read_json(b)
        self.assertEqual((reply["type"], reply["final"], reply["remaining"]), ("stats_update", True, 0))
        self.assertEqual(queries, [])

    @tornado.testing.gen_test
    async def test_two_interleaved_clients_each_end_with_full_stats_and_run_no_unit_twice(self):
        inline = await self._inline_frame("sw-inter-inline")
        await self._load("sw-inter", stats_delivery="deferred")
        a, a_open = await self._connect("sw-inter", caps="stats_update")
        b, _ = await self._connect("sw-inter", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        self._budget(0)
        received = {"a": [], "b": []}
        ran = []

        with _count_stat_queries() as queries:
            for _ in range(4):
                for name, ws in (("a", a), ("b", b)):
                    ws.write_message(_stats_request(gen, incremental=True))
                    received[name].append(await _read_json(ws))
                    ran.append(len(queries))

        self.assertEqual(ran, [1, 1, 2, 2, 3, 3, 4, 4],
            "each unit ran once, for whichever client asked first, and the other was caught up without a query")
        full = _as_json(_merge_stat_payloads([inline["df_data_dict"]["all_stats"]]))
        for name in ("a", "b"):
            replies = received[name]
            self.assertTrue(all(r["type"] == "stats_update" for r in replies))
            self.assertTrue(replies[-1]["final"])
            self.assertEqual(_as_json(_merge_stat_payloads(r["payload"] for r in replies)), full, name)

    @tornado.testing.gen_test
    async def test_the_final_reply_carries_the_rebuilt_display_args_when_its_hash_differs(self):
        await self._load("sw-dargs", stats_delivery="deferred")
        a, a_open = await self._connect("sw-dargs", caps="stats_update")
        b, _ = await self._connect("sw-dargs", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        session = self._session("sw-dargs")
        self._budget(0)

        replies = await self._pull_stats(a, gen)
        self.assertEqual(len(replies), 4)
        for reply in replies[:-1]:
            self.assertNotIn("df_display_args", reply)
        rebuilt = replies[-1]["df_display_args"]
        self.assertEqual(_as_json(rebuilt), _as_json(session.df_display_args))
        self.assertNotEqual(_as_json(rebuilt), _as_json(a_open["df_display_args"]),
            "full stats change the float column's minWidth")

        # B asked for nothing while A ran, and still holds the schema tier's config.
        b.write_message(_stats_request(gen, incremental=True))
        late = await _read_json(b)
        self.assertEqual((late["final"], late["remaining"]), (True, 0))
        self.assertEqual(_as_json(late["df_display_args"]), _as_json(session.df_display_args))
        b.write_message(_stats_request(gen, incremental=True))
        self.assertNotIn("df_display_args", await _read_json(b), "B holds it now")

    @tornado.testing.gen_test
    async def test_the_final_reply_carries_no_display_args_when_they_did_not_change(self):
        build = str(xo.build_expr(xo.memtable({"qty": [1, 2, 1, 3, 2], "category": ["a", "b", "a", "c", "b"]},
            name="t2"), builds_dir=self.builds_root))
        await self._load("sw-same-args", build_dir=build, stats_delivery="deferred")
        ws, first = await self._connect("sw-same-args", caps="stats_update")
        self._budget(0)
        replies = await self._pull_stats(ws, self._stats(first)["gen"])
        self.assertEqual(len(replies), 3, "the scalar batch and one histogram for each of two columns")
        self.assertTrue(replies[-1]["final"])
        self.assertNotIn("df_display_args", replies[-1], "int and string columns are styled the same at both tiers")

    @tornado.testing.gen_test
    async def test_the_final_display_args_keep_the_clients_search_highlight(self):
        await self._load("sw-highlight", stats_delivery="deferred")
        ws, first = await self._connect("sw-highlight", caps="stats_update")
        ws.write_message(_state_change(search_string="ca"))
        self._assert_pending(await _read_json(ws), self._stats(first)["gen"])
        self._budget(0)
        replies = await self._pull_stats(ws, self._stats(first)["gen"])
        self.assertEqual(len(replies), 4)
        columns = replies[-1]["df_display_args"]["main"]["df_viewer_config"]["column_config"]
        self.assertTrue([cc for cc in columns if cc.get("displayer_args", {}).get("highlight_phrase") == ["ca"]],
            "rebuilt config replaces the one with the highlight, so it must carry it")

    @tornado.testing.gen_test
    async def test_a_filtered_state_ends_as_complete_as_the_inline_session_s(self):
        search = {"search": ["a"]}
        inline = await self._inline_frame("sw-filt-inline", quick_command_args=search)
        await self._load("sw-filt", stats_delivery="deferred")
        ws, first = await self._connect("sw-filt", caps="stats_update")
        ws.write_message(_state_change(quick_command_args=search))
        gen = self._stats(await _read_json(ws))["gen"]
        self._budget(0)
        replies = await self._pull_stats(ws, gen)
        self.assertEqual(len(replies), 4)
        _, late = await self._connect("sw-filt", caps="stats_update")
        self._assert_complete(late, gen, inline)

    @tornado.testing.gen_test
    async def test_a_legacy_client_connecting_mid_run_gets_a_complete_state_from_the_remaining_units(self):
        inline = await self._inline_frame("sw-mid-inline")
        await self._load("sw-mid", stats_delivery="deferred")
        a, a_open = await self._connect("sw-mid", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        self._budget(0)

        with _count_stat_queries() as queries:
            for _ in range(2):
                a.write_message(_stats_request(gen, incremental=True))
                self.assertFalse((await _read_json(a))["final"])
            self.assertEqual(len(queries), 2)
            _, legacy = await self._connect("sw-mid")
            self.assertEqual(len(queries), 4, "the legacy client's frame ran the two units still to run")
            a.write_message(_stats_request(gen, incremental=True))
            reply = await _read_json(a)
            self.assertEqual(len(queries), 4, "A is answered from the stats the legacy client's frame completed")
        self._assert_complete(legacy, gen, inline)
        self.assertEqual((reply["final"], reply["remaining"]), (True, 0))
        self.assertEqual(_rows_by_stat(reply["payload"]), _rows_by_stat(inline["df_data_dict"]["all_stats"]))

    @tornado.testing.gen_test
    async def test_a_request_with_no_incremental_flag_finishes_a_run_that_has_progress(self):
        inline = await self._inline_frame("sw-finish-inline")
        await self._load("sw-finish", stats_delivery="deferred")
        ws, first = await self._connect("sw-finish", caps="stats_update")
        gen = self._stats(first)["gen"]
        self._budget(0)
        with _count_stat_queries() as queries:
            for _ in range(2):
                ws.write_message(_stats_request(gen, incremental=True))
                self.assertFalse((await _read_json(ws))["final"])
            ws.write_message(_stats_request(gen))
            update = await _read_json(ws)
        self.assertEqual((update["type"], update["final"], update["remaining"]), ("stats_update", True, 0))
        self.assertEqual(len(queries), 4, "the whole-run request ran the two units left, not all four")
        self.assertEqual(_rows_by_stat(update["payload"]), _rows_by_stat(inline["df_data_dict"]["all_stats"]))

    @tornado.testing.gen_test
    async def test_a_concurrent_infinite_request_is_served_between_units_within_the_stall_bound(self):
        await self._load("sw-stall", stats_delivery="deferred")
        a, a_open = await self._connect("sw-stall", caps="stats_update")
        b, _ = await self._connect("sw-stall", caps="stats_update")
        gen = self._stats(a_open)["gen"]
        self._wrapped_run("sw-stall", delay=0.04)

        a.write_message(_stats_request(gen, incremental=True))
        started = time.perf_counter()
        rows = await self._infinite_window(b)
        rows_latency = time.perf_counter() - started
        first = await _read_json(a)

        self.assertEqual((rows["type"], rows["length"]), ("infinite_resp", 5))
        self.assertFalse(first["final"], "rows came back while the stats were still running")
        self.assertEqual(self._session("sw-stall").stats_status, "pending")
        replies = [first] + await self._pull_stats(a, gen)
        self.assertTrue(replies[-1]["final"])
        # Plan 1's proposed ceiling on the longest single request.
        for reply in replies:
            self.assertLess(reply["elapsed_ms"], 250)
        self.assertLess(rows_latency, 0.25)

    @tornado.testing.gen_test
    async def test_the_first_initial_state_precedes_any_data_stat_query_and_rows_precede_the_stats(self):
        with _count_stat_queries() as queries:
            await self._load("sw-first", stats_delivery="deferred")
            ws, first = await self._connect("sw-first", caps="stats_update")
            gen = self._stats(first)["gen"]
            self._assert_pending(first, gen)
            self.assertEqual((await self._infinite_window(ws))["length"], 5)
            self.assertEqual(queries, [], "the first initial_state and the first rows precede every data stat query")

            self._budget(0)
            ws.write_message(_stats_request(gen, incremental=True))
            reply = await _read_json(ws)
            self.assertEqual((reply["type"], reply["final"]), ("stats_update", False))
            self.assertEqual(len(queries), 1)
            self.assertEqual((await self._infinite_window(ws))["type"], "infinite_resp")
            self.assertEqual(self._session("sw-first").stats_status, "pending", "rows are served before stats complete")

    @tornado.testing.gen_test
    async def test_reload_expr_mid_run_bumps_the_generation_and_drops_the_run(self):
        await self._load("sw-reload-run", stats_delivery="deferred")
        ws, first = await self._connect("sw-reload-run", caps="stats_update")
        gen = self._stats(first)["gen"]
        session = self._session("sw-reload-run")
        self._budget(0)
        ws.write_message(_stats_request(gen, incremental=True))
        self.assertFalse((await _read_json(ws))["final"])
        self.assertEqual(list(session.stat_runs), [(gen, "raw")])

        resp = await _post(self.get_http_port(), "/reload_expr/sw-reload-run", {})
        self.assertEqual(resp.code, 200, resp.body)
        self._assert_pending(await _read_json(ws), gen + 1)
        self.assertEqual(session.stat_runs, {})

        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen, incremental=True))
            aborted = await _read_json(ws)
            self.assertEqual((aborted["reason"], aborted["current_gen"]), ("stale", gen + 1))
            self.assertEqual(queries, [])
            ws.write_message(_stats_request(gen + 1, incremental=True))
            reply = await _read_json(ws)
        self.assertEqual((reply["remaining"], len(queries)), (3, 1), "the new generation starts from its first unit")

    @tornado.testing.gen_test
    async def test_stats_unit_and_completion_spans_are_emitted_on_the_session_sink(self):
        captured: list = []
        with patch.object(telemetry, "make_http_sink", lambda url, **kw: captured.append):
            await self._load("sw-spans", stats_delivery="deferred",
                telemetry_url="http://companion.invalid/internal/telemetry")
            ws, first = await self._connect("sw-spans", caps="stats_update")
            gen = self._stats(first)["gen"]
            self._budget(0)
            self.assertEqual(len(await self._pull_stats(ws, gen)), 4)

        units = [r for r in captured if r["name"] == "stats.unit"]
        self.assertEqual([r["attrs"]["unit"] for r in units],
            ["batch", "histogram:price", "histogram:qty", "histogram:category"])
        for record in units:
            self.assertEqual(record["trace"], "sw-spans")
            self.assertEqual((record["attrs"]["session"], record["attrs"]["stats_gen"]), ("sw-spans", gen))
        self.assertEqual([r["attrs"]["phase"] for r in units], ["batch", "histogram", "histogram", "histogram"])
        totals = [r for r in captured if r["name"] == "firstpull.stats_total"]
        self.assertEqual(len(totals), 1, "one completion span for the run, not one for each request")
        self.assertEqual((totals[0]["attrs"]["stats_gen"], totals[0]["attrs"]["units"]), (gen, 4))
        self.assertGreater(totals[0]["attrs"]["run_secs"], 0)
        requests = [r for r in captured if r["name"] == "stats.request"]
        self.assertEqual([r["attrs"]["outcome"] for r in requests], ["update"] * 4)
        self.assertEqual([r["attrs"]["units"] for r in requests], [1, 1, 1, 1])

    @tornado.testing.gen_test
    async def test_the_completion_span_reports_the_snapshot_cache_outcome_of_the_units(self):
        captured: list = []
        cache_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_root, ignore_errors=True)
        with patch.object(telemetry, "make_http_sink", lambda url, **kw: captured.append):
            await self._load("sw-cache", stats_delivery="deferred", cache_storage_path=cache_root,
                telemetry_url="http://companion.invalid/internal/telemetry")
            ws, first = await self._connect("sw-cache", caps="stats_update")
            gen = self._stats(first)["gen"]
            self._budget(3600)
            self.assertEqual(len(await self._pull_stats(ws, gen)), 1)
            # A reload builds a new dataflow with an empty in-process cache, so the
            # same state's units now read their snapshots.
            resp = await _post(self.get_http_port(), "/reload_expr/sw-cache", {})
            self.assertEqual(resp.code, 200, resp.body)
            await _read_json(ws)
            self.assertEqual(len(await self._pull_stats(ws, gen + 1)), 1)

        cold, warm = [r["attrs"] for r in captured if r["name"] == "firstpull.stats_total"]
        self.assertEqual((cold["cache_status"], cold["cache_hits"], cold["cache_misses"]), ("miss", 0, 4))
        self.assertEqual((warm["cache_status"], warm["cache_hits"], warm["cache_misses"]), ("hit", 4, 0))

    @tornado.testing.gen_test
    async def test_a_unit_that_raises_fails_the_generation_until_the_next(self):
        await self._load("sw-unit-fail", stats_delivery="deferred")
        ws, first = await self._connect("sw-unit-fail", caps="stats_update")
        gen = self._stats(first)["gen"]
        session = self._session("sw-unit-fail")
        self._wrapped_run("sw-unit-fail", fail_on="histogram:price")
        self._budget(0)

        ws.write_message(_stats_request(gen, incremental=True))
        self.assertFalse((await _read_json(ws))["final"])
        ws.write_message(_stats_request(gen, incremental=True))
        aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["stats_gen"], aborted["reason"]), ("stats_aborted", gen, "error"))
        self.assertEqual((session.stats_status, session.stats_reason), ("error", "stats_failed"))
        self.assertEqual(session.stat_runs, {})

        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen, incremental=True))
            self.assertEqual((await _read_json(ws))["reason"], "error")
        self.assertEqual(queries, [], "a failed generation is not retried by every request")
        _, legacy = await self._connect("sw-unit-fail")
        self.assertEqual(list(_rows_by_stat(legacy["df_data_dict"]["all_stats"])), ["dtype"])

        ws.write_message(_state_change(quick_command_args={"search": ["a"]}))
        self._assert_pending(await _read_json(ws), gen + 1)
        self.assertEqual(len(await self._pull_stats(ws, gen + 1)), 4)

    @tornado.testing.gen_test
    async def test_a_non_boolean_incremental_flag_is_aborted_as_a_bad_request(self):
        await self._load("sw-bad-flag", stats_delivery="deferred")
        ws, first = await self._connect("sw-bad-flag", caps="stats_update")
        gen = self._stats(first)["gen"]
        with _count_stat_queries() as queries:
            ws.write_message(_stats_request(gen, incremental="yes"))
            aborted = await _read_json(ws)
        self.assertEqual((aborted["type"], aborted["reason"], aborted["stats_gen"]),
            ("stats_aborted", "bad_request", gen))
        self.assertEqual(queries, [], "a malformed request must not fall back to the whole run")
        self._budget(0)
        self.assertFalse((await self._pull_stats(ws, gen, limit=1))[0]["final"],
            "the session still serves a good request")


def _wide_parquet_expr(tmp_path, name="wide"):
    """Twelve rows, six columns, read from parquet. Each string column has a
    different count per value, so a GROUP BY over it returns one order."""
    path = tmp_path / f"{name}.parquet"
    pd.DataFrame({
        "n0": [float(i) for i in range(12)], "n1": [i * 3 for i in range(12)],
        "n2": [float(i % 7) + 0.5 for i in range(12)], "word": list("aaaaabbbbccd"),
        "label": list("xxxxxyyyyzzw"), "flag": [True] * 7 + [False] * 5}).to_parquet(path)
    return xo.deferred_read_parquet(str(path))


def _batch_queries(queries):
    return [q for q in queries if type(q.op()).__name__ == "Aggregate"]


class TestStatUnits:
    """Resumable units on the xorq server dataflow (rows-first s4): the
    all-at-once constructor and a caller running ``plan``/``run`` one unit at a
    time compute the same stats."""

    def test_build_stats_without_running_issues_no_stat_query(self):
        dataflow = _build_dataflow()
        with _count_stat_queries() as queries:
            stats = dataflow.build_stats(dataflow.processed_df, run=False)
            stats.plan(stats.state)
            stats.new_accumulator(stats.state)
        assert queries == []
        assert stats.sdf == {} and stats.errs == {}

    def test_the_default_run_goes_through_the_units(self, monkeypatch):
        """Every stat query of the constructor is issued from inside a unit."""
        depth, inside, outside, units = [0], [], [], []
        original_run, original_execute = XorqStatPipeline.run, XorqStatPipeline._execute

        def spy_run(self, unit, acc):
            depth[0] += 1
            units.append(unit.id)
            try:
                return original_run(self, unit, acc)
            finally:
                depth[0] -= 1

        def spy_execute(self, query):
            (inside if depth[0] else outside).append(query)
            return original_execute(self, query)

        monkeypatch.setattr(XorqStatPipeline, "run", spy_run)
        monkeypatch.setattr(XorqStatPipeline, "_execute", spy_execute)
        _three_scope_dataflow()
        assert inside and outside == []
        assert units[0] == "batch" and "histogram:price" in units

    def test_units_assembled_equal_merged_sd_with_init_sd_cleaning_and_overrides(self):
        dataflow = _three_scope_dataflow(init_sd={
            "price": {"displayer_args": {"displayer": "string", "max_length": 99}, "init_only": 1}},
            column_config_overrides={"category": {"displayer_args": {"displayer": "string", "max_length": 5000}}})
        dataflow.add_analysis(_OverridingPostProcessing)
        dataflow.post_processing_method = "override_post"
        sd = dataflow.merged_sd
        assert sd["a"]["init_only"] == 1 and sd["b"]["from_post"] == 1 and sd["b"]["mean"] == 99.5
        assert "cleaned_length" in sd["a"] and "filtered_length" in sd["a"], "both layers must be active"

        sds = _scope_sds_by_units(dataflow)
        inputs = _scope_inputs(dataflow)
        assembled = assemble_merged_sd(init_sd=inputs["init_sd"], cleaned_sd=inputs["cleaned_sd"], raw_sd=sds["raw"],
            processed_sd=inputs["processed_sd"], processed_df=inputs["processed_df"], chains=inputs["chains"],
            clean_sd=sds["clean"], filt_sd=sds["filt"])

        assert _as_json(assembled) == _as_json(dataflow.merged_sd)

    def test_a_column_group_request_returns_only_those_columns(self):
        dataflow = _build_dataflow()
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        for names in (("qty", "category"), ("b", "c")):  # original or rewritten names
            state = dataclasses.replace(stats.state, columns=names)
            acc = stats.new_accumulator(state)
            fragments = [stats.run(unit, acc) for unit in stats.plan(state)]
            assert [u.id for u in stats.plan(state)] == ["batch", "histogram:qty", "histogram:category"]
            assert all(set(f) <= {"qty", "category"} for f in fragments)
            assert list(acc.sd()) == ["qty", "category"]

    def test_skip_stat_columns_get_no_unit(self):
        dataflow = _build_dataflow(skip_stat_columns=["qty"], init_sd={"qty": {"_type": "float"}})
        stats = dataflow.build_stats(dataflow.processed_df, run=False)
        assert stats.state.skip_columns == {"qty"}
        units = stats.plan(stats.state)
        assert [u.id for u in units] == ["batch", "histogram:price", "histogram:category"]
        assert all("qty" not in unit.columns for unit in units)

    def test_the_batch_is_one_query_by_default(self, tmp_path):
        expr = _wide_parquet_expr(tmp_path)
        with _count_stat_queries() as queries:
            xorq_loading.XorqServerDataflow(expr, skip_main_serial=True)
        assert len(_batch_queries(queries)) == 1

    def test_stat_chunk_cells_splits_the_batch_of_a_parquet_scan(self, tmp_path):
        expr = _wide_parquet_expr(tmp_path)
        whole = xorq_loading.XorqServerDataflow(expr, skip_main_serial=True)
        with _count_stat_queries() as queries:
            # 36 cells at 12 rows is three columns per chunk: two batch queries.
            split = xorq_loading.XorqServerDataflow(expr, skip_main_serial=True, stat_chunk_cells=36)
        assert len(_batch_queries(queries)) == 2
        assert _as_json(split.merged_sd) == _as_json(whole.merged_sd)

    def test_the_split_is_refused_for_a_join(self, tmp_path):
        left = _wide_parquet_expr(tmp_path, "left")
        pd.DataFrame({"n0": [float(i) for i in range(12)], "extra": list(range(12))}).to_parquet(
            tmp_path / "right.parquet")
        joined = left.join(xo.deferred_read_parquet(str(tmp_path / "right.parquet")), "n0")
        with _count_stat_queries() as queries:
            split = xorq_loading.XorqServerDataflow(joined, skip_main_serial=True, stat_chunk_cells=12)
        assert len(_batch_queries(queries)) == 1, "each chunk of a join would run the whole join again"
        whole = xorq_loading.XorqServerDataflow(joined, skip_main_serial=True)
        assert _as_json(split.merged_sd) == _as_json(whole.merged_sd)


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
        return sorted(Path(self.default_cache).rglob("*.parquet"))

    def test_load_expr_build_dir_redirects_nested_cache_nodes(self):
        """Every cache node, the one nested in the outer node's parent
        included, resolves under cache_dir and finds the baked snapshot."""
        build_path, host_cache, _ = _build_cached_expr_dir(self.root)
        expr = xorq_loading.load_expr_build_dir(build_path, cache_dir=str(host_cache))
        paths = _cache_node_paths(expr)
        self.assertEqual(len(paths), 2)
        for p in paths:
            self.assertIn(host_cache, p.parents)
            self.assertTrue(p.exists(), f"baked snapshot not found at {p}")

    def test_load_expr_build_dir_without_cache_dir_unchanged(self):
        """Unset cache_dir keeps xorq's default resolution."""
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
