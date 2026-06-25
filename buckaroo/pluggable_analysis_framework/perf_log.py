"""Opt-in perf instrumentation for the stats pipeline and the first data pull.

Default off — zero behavioural change and a single bool check at each call
site. Turn on with ``BUCKAROO_PERF=1`` in the environment, or
programmatically with :func:`enable` (handy in a notebook investigation)::

    from buckaroo.pluggable_analysis_framework import perf_log
    perf_log.enable()
    BuckarooWidget(df)          # spans + summary printed to the buckaroo.perf logger
    perf_log.disable()

When enabled, two things happen:

* :func:`perf_span` context managers emit one ``key=value`` line per span to
  the ``buckaroo.perf`` logger (greppable; in the server these land in
  ``~/.buckaroo/logs/server.log``).
* The stat pipelines feed a :class:`PerfRecorder` with one row per
  ``(phase, column, stat, seconds)`` and print a top-N-slowest summary at the
  end of a run.

Enabling (env var or :func:`enable`) raises the ``buckaroo.perf`` logger to
INFO so spans and summaries are emitted. When the root logger is already
configured (the server, or a notebook that called ``logging.basicConfig``)
the lines propagate to that existing handler — the server log file, stderr,
etc. When nothing upstream has a handler (the common ``BUCKAROO_PERF=1
python script.py`` / bare-notebook case, where root sits at WARNING and would
drop INFO), a plain stderr handler is attached so the spans still show. It
stays quiet unless enabled, regardless of how noisy other loggers are.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("buckaroo.perf")


def _env_enabled() -> bool:
    return os.environ.get("BUCKAROO_PERF", "").lower() in ("1", "true", "yes", "on")


# Computed once from the environment; flip at runtime with enable()/disable().
_ENABLED: bool = _env_enabled()


def _ensure_logging() -> None:
    """Make INFO spans visible whenever perf is enabled.

    A bare notebook/script leaves the root logger at WARNING with only the
    lastResort handler, so our INFO lines would be dropped. Bump this logger to
    INFO and, when nothing upstream has a handler, attach a plain stderr handler
    of our own. When root is already configured (the server) we add nothing and
    let propagation deliver the lines to the existing log. Idempotent — safe to
    call on every enable().
    """
    log.setLevel(logging.INFO)
    if not logging.getLogger().hasHandlers() and not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)


def enabled() -> bool:
    """True when perf instrumentation should run. Cheap; safe in hot paths."""
    return _ENABLED


def enable() -> None:
    """Turn perf instrumentation on for this process (overrides the env var)."""
    global _ENABLED
    _ENABLED = True
    _ensure_logging()


def disable() -> None:
    """Turn perf instrumentation off for this process."""
    global _ENABLED
    _ENABLED = False


# When enabled from the environment, configure logging at import so spans are
# visible without a separate enable() call.
if _ENABLED:
    _ensure_logging()


# ---------------------------------------------------------------------------
# Telemetry sink (#943)
# ---------------------------------------------------------------------------
# A perf span doubles as a telemetry span: when a *sink* is bound on the current
# context, ``perf_span`` emits a flat, OTel-shaped record
# ``{trace, source, name, t_start_ms, t_end_ms, attrs}`` at span close. The sink
# and the correlation key (``trace`` = buckaroo session id) ride ContextVars so
# concurrent requests on the single IOLoop don't clobber each other, and a
# non-telemetry request stays a pure no-op (no sink → no emit).
#
# Emission is decoupled from the BUCKAROO_PERF logging toggle: a span is live
# when perf logging is enabled *or* a sink is present. So enabling telemetry for
# one session never flips global perf logging on for everyone.

_session_var: ContextVar[Optional[str]] = ContextVar(
    "buckaroo_perf_session", default=None)
_source_var: ContextVar[str] = ContextVar(
    "buckaroo_perf_source", default="server")
_sink_var: ContextVar[Optional[Callable[[Dict[str, Any]], None]]] = ContextVar(
    "buckaroo_perf_sink", default=None)

# Lazily-created pool for fire-and-forget POSTs — telemetry must never block the
# Tornado IOLoop (a hung/absent companion would otherwise stall every grid load).
_telemetry_executor: Optional[ThreadPoolExecutor] = None
_pending_posts: "set[Future]" = set()


@contextmanager
def telemetry_context(session_id: Optional[str],
                      sink: Optional[Callable[[Dict[str, Any]], None]],
                      source: str = "server"):
    """Bind the telemetry ``trace`` / ``source`` / sink for the enclosed block.

    Set at each entry point that owns a session id (the ``/load_expr`` POST and
    the WS handler). ``sink=None`` is a valid no-op binding — spans run but emit
    nothing — so callers don't have to branch on whether telemetry is wired.
    """
    t_sess = _session_var.set(session_id)
    t_src = _source_var.set(source)
    t_sink = _sink_var.set(sink)
    try:
        yield
    finally:
        _session_var.reset(t_sess)
        _source_var.reset(t_src)
        _sink_var.reset(t_sink)


def _get_executor() -> ThreadPoolExecutor:
    global _telemetry_executor
    if _telemetry_executor is None:
        _telemetry_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="buckaroo-telemetry")
    return _telemetry_executor


def _post_record(url: str, record: Dict[str, Any], timeout: float) -> None:
    """POST one span record as JSON. Failures are swallowed — telemetry is
    best-effort and must never surface as a request error."""
    try:
        data = json.dumps(record).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout).close()
    except Exception:
        log.debug("telemetry POST to %s failed", url, exc_info=True)


def http_sink(url: str, timeout: float = 2.0) -> Callable[[Dict[str, Any]], None]:
    """Return a sink that fire-and-forget POSTs each record to ``url``.

    The POST runs on a background thread so a slow or absent companion can't
    block the request that produced the span. Use :func:`flush_telemetry`
    (tests, shutdown) to wait for in-flight POSTs.
    """
    def _sink(record: Dict[str, Any]) -> None:
        fut = _get_executor().submit(_post_record, url, record, timeout)
        _pending_posts.add(fut)
        fut.add_done_callback(_pending_posts.discard)
    return _sink


def flush_telemetry(timeout: float = 5.0) -> None:
    """Block until in-flight telemetry POSTs finish. For tests and shutdown."""
    for fut in list(_pending_posts):
        try:
            fut.result(timeout)
        except Exception:
            pass


def _emit_record(sink: Callable[[Dict[str, Any]], None], label: str,
                 t_start_ms: float, t_end_ms: float, attrs: Dict[str, Any]) -> None:
    record = {"trace": _session_var.get(), "source": _source_var.get(), "name": label,
        "t_start_ms": round(t_start_ms, 3), "t_end_ms": round(t_end_ms, 3), "attrs": dict(attrs)}
    try:
        sink(record)
    except Exception:
        log.debug("telemetry sink raised for span=%s", label, exc_info=True)


class _Span:
    """Mutable handle yielded by :func:`perf_span`.

    ``set_attr`` attaches attributes discovered *inside* the timed block (e.g.
    cache hit/miss, known only after the stats run) so they land in the log line
    and the emitted record at span close."""
    __slots__ = ("attrs",)

    def __init__(self, attrs: Dict[str, Any]):
        self.attrs = attrs

    def set_attr(self, **kw: Any) -> None:
        self.attrs.update(kw)


class _NullSpan:
    """No-op handle yielded when a span is inactive, so ``set_attr`` callers
    don't need to branch on whether instrumentation is on."""
    __slots__ = ()

    def set_attr(self, **kw: Any) -> None:
        pass


_NULL_SPAN = _NullSpan()


def _fmt_fields(fields: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in fields.items())


@contextmanager
def perf_span(label: str, **fields):
    """Time a block, log one ``perf span=<label> secs=<n> ...`` line, and — when
    a telemetry sink is bound (see :func:`telemetry_context`) — emit a span
    record to it.

    Yields a span handle whose :meth:`_Span.set_attr` attaches attributes
    discovered inside the block (e.g. cache hit/miss). No-op (a couple of cheap
    lookups, no timing) when neither perf logging nor a sink is active.
    ``fields`` are appended as ``key=value`` pairs for grepping/parsing.

    If the block raises, the line/record still emit (the timing of the partial
    work) but are tagged ``errored=true`` so a parser keying on ``secs=``
    doesn't mistake a failed run's partial timing for a clean one.
    """
    sink = _sink_var.get()
    if not _ENABLED and sink is None:
        yield _NULL_SPAN
        return
    span = _Span(dict(fields))
    t0 = time.perf_counter()
    t_start_ms = time.time() * 1000.0
    errored = False
    try:
        yield span
    except BaseException:
        errored = True
        raise
    finally:
        secs = time.perf_counter() - t0
        t_end_ms = time.time() * 1000.0
        attrs = span.attrs
        if errored:
            attrs = {**attrs, "errored": "true"}
        suffix = _fmt_fields(attrs)
        log.info("perf span=%s secs=%.4f%s", label, secs,
            f" {suffix}" if suffix else "")
        if sink is not None:
            _emit_record(sink, label, t_start_ms, t_end_ms, attrs)


class PerfRecorder:
    """Accumulates ``(phase, column, stat, seconds)`` rows for one pipeline run.

    Shared schema across the pandas, polars and xorq pipelines so their output
    reads identically. ``summary()`` logs per-phase totals and the slowest
    individual stats.
    """

    def __init__(self, label: str = ""):
        self.label = label
        self.rows: List[Tuple[str, str, str, float]] = []

    def record(self, phase: str, column: str, stat: str, seconds: float) -> None:
        self.rows.append((phase, column, stat, seconds))

    def extend_timings(self, phase: str, timings) -> None:
        """Absorb ``(column, stat, seconds)`` tuples (StatPipeline.timings shape)."""
        for column, stat, seconds in timings:
            self.rows.append((phase, column, stat, seconds))

    def summary(self, top_n: int = 15) -> None:
        if not _ENABLED or not self.rows:
            return
        total = sum(r[3] for r in self.rows)
        by_phase: dict = {}
        for phase, _col, _stat, secs in self.rows:
            by_phase[phase] = by_phase.get(phase, 0.0) + secs
        label = f" {self.label}" if self.label else ""
        log.info("perf summary%s: total=%.4fs stats=%d", label, total, len(self.rows))
        for phase, secs in sorted(by_phase.items(), key=lambda kv: -kv[1]):
            log.info("perf   phase=%s secs=%.4f", phase, secs)
        slowest = sorted(self.rows, key=lambda r: -r[3])[:top_n]
        for phase, column, stat, secs in slowest:
            log.info("perf   slow phase=%s col=%s stat=%s secs=%.4f",
                phase, column, stat, secs)
