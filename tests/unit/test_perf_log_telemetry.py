"""Tests for perf_log's telemetry span emission (#943).

``perf_span`` doubles as a telemetry span: when a sink is bound on the current
context (see ``telemetry_context``) it emits a flat, OTel-shaped record
``{trace, source, name, t_start_ms, t_end_ms, attrs}`` at span close. Emission
is decoupled from the ``BUCKAROO_PERF`` logging toggle — a sink is enough, so a
telemetry session never flips global perf logging on for everyone. These tests
run with perf logging *off* to lock that decoupling in.

They cover the transport-agnostic machinery only (the sink is an injected
callable). The server's real HTTP sink lives in ``buckaroo.server.telemetry``
and is covered by ``tests/unit/server/test_telemetry_sink.py``.
"""
import logging
from unittest.mock import patch

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


def test_telemetry_only_session_writes_no_perf_log_line(caplog):
    """Decoupling, the other direction: with BUCKAROO_PERF off, a bound sink
    still emits the record, but perf_span writes no ``perf span=`` log line.
    Wiring telemetry for one session must not turn perf logging on (the server's
    root logger sits at DEBUG, so an ungated log.info would leak perf lines into
    server.log for every telemetry session)."""
    records = []
    with caplog.at_level(logging.INFO, logger="buckaroo.perf"):
        with perf_log.telemetry_context("sess-quiet", records.append):
            with perf_log.perf_span("firstpull.load_expr"):
                pass

    assert len(records) == 1  # the record still emits
    perf_lines = [r for r in caplog.records if r.getMessage().startswith("perf span=")]
    assert perf_lines == [], (
        f"telemetry-only session must not log perf lines; got "
        f"{[r.getMessage() for r in perf_lines]}")


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


def test_emitted_timeline_derived_from_monotonic_duration():
    """t_end_ms is the wall-clock anchor plus the monotonic perf_counter delta,
    not a second time.time() read: the wall clock is read exactly once, so an
    NTP step mid-span can't make t_end_ms precede t_start_ms (and the record's
    duration always matches secs=)."""
    class _FakeClock:
        def __init__(self):
            self._perf = iter([100.0, 100.5])  # t0, then +0.5s at span close
            # Exactly one wall-clock value on purpose: a second read (the old
            # behaviour) would raise StopIteration and fail this test.
            self._time = iter([1000.0])

        def perf_counter(self):
            return next(self._perf)

        def time(self):
            return next(self._time)

    records = []
    with patch.object(perf_log, "time", _FakeClock()):
        with perf_log.telemetry_context("sess-clock", records.append):
            with perf_log.perf_span("firstpull.metadata"):
                pass

    r = records[0]
    assert r["t_start_ms"] == 1000.0 * 1000.0  # the single wall-clock anchor
    assert r["t_end_ms"] == r["t_start_ms"] + 0.5 * 1000.0  # anchor + duration
    assert r["t_end_ms"] >= r["t_start_ms"]
