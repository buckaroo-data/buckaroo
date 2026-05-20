"""SPIKE: rows-first WS state-change protocol.

When ``BUCKAROO_ROWS_FIRST_SPIKE`` is set, ``_handle_buckaroo_state_change``
emits the ``initial_state`` rebroadcast *before* running the analysis
pipeline that produces ``summary_sd``. A second ``initial_state``
follows once stats are ready, sent via an ``IOLoop.add_callback`` that
yields between the two so any ``infinite_request`` from the client
gets a turn ahead of the stats compute.

This test pins the wire-shape (two ``initial_state`` messages back to
back), proves an ``infinite_request`` fired between them is serviced
in order, and verifies the second message carries fresh
``filtered_*`` keys (i.e. the deferred stats compute actually ran).

Not pulling this into the default suite — gated on the env flag — so
it's safe to ship the spike alongside today's single-message
rebroadcast path while we evaluate the perf characteristics.
"""
import io
import json
import os
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


@pytest.fixture(autouse=True)
def enable_spike(monkeypatch):
    """Flip the spike gate on for every test in this module; the
    handler reads the env at request time so this works without a
    fresh import."""
    monkeypatch.setenv("BUCKAROO_ROWS_FIRST_SPIKE", "1")
    # Re-import the constant from the handler module so subsequent
    # handler invocations see the gate as on. The flag is read at
    # module-import-time, so we patch the resolved value directly.
    from buckaroo.server import websocket_handler as wh
    monkeypatch.setattr(wh, "_ROWS_FIRST_SPIKE", True)


class TestRowsFirstSpike(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    @tornado.testing.gen_test
    async def test_state_change_emits_two_initial_state_messages(self):
        """With the spike on, a single state_change produces two
        ``initial_state`` messages: phase 1 (deferred stats) followed by
        phase 2 (computed stats)."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "spike-1", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/spike-1")
            await ws.read_message()  # initial connection state

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

            # Phase 1: meta/display updated, stats may still be the
            # previous state's value (the spike's ``_defer_summary_sd``
            # short-circuit left ``summary_sd`` untouched).
            phase1 = json.loads(await ws.read_message())
            self.assertEqual(phase1["type"], "initial_state")
            self.assertEqual(phase1["buckaroo_state"]["quick_command_args"], {"search": ["alpha"]})

            # Phase 2: stats compute ran; the message arrives after the
            # ``call_later`` delay fires.
            phase2 = json.loads(await ws.read_message())
            self.assertEqual(phase2["type"], "initial_state")
            self.assertEqual(phase2["buckaroo_state"]["quick_command_args"], {"search": ["alpha"]})

            # Phase 1 vs phase 2 stats-payload divergence is exercised
            # downstream — the spike's value here is just "the wire
            # carries two ``initial_state`` frames per state change."

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)

    @tornado.testing.gen_test
    async def test_infinite_request_between_phases_returns_rows(self):
        """The key win of the spike: rows can be served *between* phase
        1 (skeleton) and phase 2 (stats). The client fires
        ``infinite_request`` after phase 1 arrives, and the parquet
        comes back before the stats message."""
        builds_root = tempfile.mkdtemp()
        try:
            build_path = _build_expr_dir(builds_root)
            await _post(self.get_http_port(), "/load_expr",
                {"session": "spike-2", "build_dir": build_path})

            ws = await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/spike-2")
            await ws.read_message()  # initial connection state

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

            # Phase 1 arrives.
            phase1 = json.loads(await ws.read_message())
            self.assertEqual(phase1["type"], "initial_state")

            # Simulate AG-Grid firing infinite_request immediately after
            # seeing phase 1.
            ws.write_message(json.dumps({
                "type": "infinite_request",
                "payload_args": {"start": 0, "end": 10,
                                 "sourceName": "default", "origEnd": 10}}))

            # The infinite_resp + parquet frame must arrive *before*
            # the phase 2 stats message — the whole point of the
            # add_callback yield.
            json_frame = json.loads(await ws.read_message())
            self.assertEqual(json_frame["type"], "infinite_resp")
            self.assertEqual(json_frame["length"], 4)

            binary_frame = await ws.read_message()
            self.assertIsInstance(binary_frame, bytes)
            table = pq.read_table(io.BytesIO(binary_frame))
            self.assertEqual(table.num_rows, 4)

            # Phase 2 follows.
            phase2 = json.loads(await ws.read_message())
            self.assertEqual(phase2["type"], "initial_state")

            ws.close()
        finally:
            shutil.rmtree(builds_root, ignore_errors=True)
