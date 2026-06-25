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
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop

log = logging.getLogger("buckaroo.perf")


def make_http_sink(url: str, timeout: float = 2.0) -> Callable[[Dict[str, Any]], None]:
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
