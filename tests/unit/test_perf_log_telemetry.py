"""Tests for the perf_log telemetry sink (#943).

``perf_span`` doubles as a telemetry span: when a sink is bound on the current
context (see ``telemetry_context``) it emits a flat, OTel-shaped record
``{trace, source, name, t_start_ms, t_end_ms, attrs}`` at span close. Emission
is decoupled from the ``BUCKAROO_PERF`` logging toggle — a sink is enough, so a
telemetry session never flips global perf logging on for everyone. These tests
run with perf logging *off* to lock that decoupling in.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from buckaroo.pluggable_analysis_framework import perf_log


@pytest.fixture(autouse=True)
def _perf_logging_off():
    """Force the BUCKAROO_PERF toggle off so these tests exercise the
    sink-only path, then restore whatever the env/process had set."""
    saved = perf_log._ENABLED
    perf_log._ENABLED = False
    try:
        yield
    finally:
        perf_log._ENABLED = saved


def test_perf_span_emits_record_to_sink():
    records = []
    with perf_log.telemetry_context("sess-1", records.append):
        with perf_log.perf_span("firstpull.load_expr", build_dir="/x"):
            pass

    assert len(records) == 1
    r = records[0]
    assert set(r) == {"trace", "source", "name", "t_start_ms", "t_end_ms", "attrs"}
    assert r["trace"] == "sess-1"
    assert r["source"] == "server"
    assert r["name"] == "firstpull.load_expr"
    assert r["attrs"]["build_dir"] == "/x"
    assert r["t_end_ms"] >= r["t_start_ms"]


def test_set_attr_inside_block_lands_in_record():
    """Attributes discovered *inside* the timed block (e.g. cache hit/miss,
    known only after the stats run) must reach the emitted record."""
    records = []
    with perf_log.telemetry_context("sess-2", records.append):
        with perf_log.perf_span("firstpull.summary_stats", n_columns=3) as span:
            span.set_attr(cache_status="miss", cache_hits=0, cache_misses=5)

    attrs = records[0]["attrs"]
    assert attrs["n_columns"] == 3
    assert attrs["cache_status"] == "miss"
    assert attrs["cache_hits"] == 0
    assert attrs["cache_misses"] == 5


def test_sink_scoped_to_context():
    """A sink only captures spans run *within* its telemetry_context — the
    contextvar is reset on exit, so later spans don't leak into it."""
    records = []
    with perf_log.telemetry_context("sess-3", records.append):
        with perf_log.perf_span("inside"):
            pass
    # Outside the context: no sink bound, perf logging off → pure no-op.
    with perf_log.perf_span("outside") as span:
        span.set_attr(should_not="emit")

    assert [r["name"] for r in records] == ["inside"]


def test_errored_span_still_emits_tagged():
    """A span whose block raises still emits (partial timing), tagged
    errored=true, and the exception propagates."""
    records = []
    with pytest.raises(ValueError):
        with perf_log.telemetry_context("sess-4", records.append):
            with perf_log.perf_span("boom"):
                raise ValueError("kaboom")

    assert len(records) == 1
    assert records[0]["attrs"].get("errored") == "true"


def test_no_sink_is_a_noop():
    """telemetry_context with sink=None runs spans but emits nothing, and the
    yielded handle still accepts set_attr (callers don't branch)."""
    with perf_log.telemetry_context("sess-5", None):
        with perf_log.perf_span("quiet") as span:
            span.set_attr(x=1)  # must not raise


def test_sink_exception_does_not_propagate():
    """A sink that raises must not break the instrumented request."""
    def _boom(_record):
        raise RuntimeError("sink down")

    with perf_log.telemetry_context("sess-6", _boom):
        with perf_log.perf_span("resilient"):
            pass  # no exception escapes


class _Receiver(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        _Receiver.received.append(json.loads(self.rfile.read(n)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_a):  # silence stderr access logs
        pass


def test_http_sink_posts_json_record():
    """http_sink fire-and-forget POSTs each record as JSON; flush_telemetry
    blocks until the in-flight POST lands."""
    _Receiver.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Receiver)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        sink = perf_log.http_sink(f"http://127.0.0.1:{port}/internal/telemetry")
        with perf_log.telemetry_context("sess-http", sink):
            with perf_log.perf_span("firstpull.metadata"):
                pass
        perf_log.flush_telemetry(5.0)
    finally:
        srv.shutdown()
        srv.server_close()

    assert len(_Receiver.received) == 1
    r = _Receiver.received[0]
    assert r["name"] == "firstpull.metadata"
    assert r["trace"] == "sess-http"
    assert r["source"] == "server"
