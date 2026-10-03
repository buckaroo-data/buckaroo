"""Telemetry sink for the buckaroo server (#943).

``perf_log`` stays transport-agnostic: a span emits by calling whatever sink is
bound on the current context (see ``perf_log.telemetry_context``). This module
supplies the *server's* sink — a fire-and-forget POST of each span record to the
companion's telemetry endpoint.

The POST runs on the Tornado IOLoop via ``AsyncHTTPClient`` + ``spawn_callback``,
never on a background thread. A span closes synchronously on the IOLoop thread,
schedules the POST for the next loop iteration, and returns immediately, so a
slow or absent companion can't stall the grid load that produced the span — the
same non-blocking guarantee the old thread pool gave, but with no threads to
create, bound, or shut down. ``AsyncHTTPClient``'s own ``max_clients`` caps
in-flight requests, so a dead companion can't grow an unbounded backlog.

It lives here, not in the leaf ``perf_log`` module, because tornado is in the
``[server]`` extra: the threadless widget/stats path imports ``perf_log`` without
tornado installed, so ``perf_log`` must never import it.

The load handlers (``/load``, ``/load_expr``, ``/load_compare``) share the same
wiring (#996): build the sink from the request's ``telemetry_url``, bind it for
the load's ``firstpull.*`` spans, and store it on the session with first-pull
telemetry re-armed so the WS handler's time-to-first-rows span reaches it.
``sink_for_url``, ``firstpull_load`` and ``arm_session`` are those three steps.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop

from buckaroo.pluggable_analysis_framework import perf_log

log = logging.getLogger("buckaroo.perf")

Sink = Callable[[Dict[str, Any]], None]


def make_http_sink(url: str, timeout: float = 2.0) -> Sink:
    """Return a sink that fire-and-forget POSTs each span record as JSON to ``url``.

    Build it on the IOLoop thread — the ``/load_expr`` POST and the WS handler
    both do — so the captured ``IOLoop.current()`` is the server loop. Each
    record is handed to ``spawn_callback`` (non-blocking, and safe to call from
    any thread), and the POST's own failures are swallowed: telemetry is
    best-effort and must never surface as a request error.
    """
    loop = IOLoop.current()
    client = AsyncHTTPClient()

    async def _post(record: Dict[str, Any]) -> None:
        try:
            await client.fetch(
                url, method="POST",
                body=json.dumps(record).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                connect_timeout=timeout, request_timeout=timeout)
        except Exception:
            log.debug("telemetry POST to %s failed", url, exc_info=True)

    def _sink(record: Dict[str, Any]) -> None:
        loop.spawn_callback(_post, record)

    return _sink


def sink_for_url(telemetry_url: Optional[str]) -> Optional[Sink]:
    """The sink for a load request's ``telemetry_url``, or None when it is absent.

    Call it on the IOLoop, in the handler, before any early exit: a warm
    re-POST that skips the pipeline still re-arms telemetry for its fresh WS
    pull (#944). None leaves ``telemetry_context`` a no-op, so normal buckaroo
    usage emits nothing.
    """
    return make_http_sink(telemetry_url) if telemetry_url else None


def arm_session(session: Any, tele_sink: Optional[Sink]) -> None:
    """Bind ``tele_sink`` on ``session`` and re-arm its first-pull telemetry.

    Every load POST into a session does this, a full load and a warm re-POST
    alike: the refreshed page opens a new WS and pulls a fresh
    time-to-first-rows, which the WS handler only spans while
    ``_perf_first_payload_seen`` is False (#944). Binding the sink
    unconditionally means a load without ``telemetry_url`` also unbinds the
    one an earlier load left behind.
    """
    session.tele_sink = tele_sink
    session._perf_first_payload_seen = False


@contextmanager
def firstpull_load(session_id: str, tele_sink: Optional[Sink], label: str, **fields: Any) -> Iterator[None]:
    """Bind telemetry for one load POST and time it as the outer ``firstpull.<label>`` span.

    The steps inside open their own ``perf_span("firstpull.<step>",
    session=session_id)`` and nest under this total. ``session=`` is on every
    span so concurrent loads can be told apart in the log: the handlers are
    async, so two POSTs can interleave even though no await sits inside a
    single span.
    """
    with (
        perf_log.telemetry_context(session_id, tele_sink),
        perf_log.perf_span(f"firstpull.{label}", session=session_id, **fields),
    ):
        yield
