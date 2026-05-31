import os
import time

import tornado.web

from buckaroo.server.handlers import HealthHandler, DiagnosticsHandler, LoadHandler, LoadExprHandler, LoadCompareHandler, ReloadExprHandler, SessionPageHandler, CacheHandler
from buckaroo.server.websocket_handler import DataStreamHandler
from buckaroo.server.session import SessionManager
from buckaroo.cache.store import InitialCacheStore

SERVER_START_TIME = time.time()


def make_app(sessions: SessionManager | None = None, port: int = 8888, open_browser: bool = True,
        datasets: list | None = None, initial_cache_store: InitialCacheStore | None = None,
        initial_cache_dir: str | None = None) -> tornado.web.Application:
    """Build the tornado app.

    ``datasets`` is the operator-supplied list of dropdown entries the
    demo page (/s/<id>) exposes — each a ``{"label", "kind", "target"}``
    dict, with ``kind`` in ``("pandas", "lazy", "xorq")``. ``None`` /
    ``[]`` means no datasets configured: the page omits the dropdown
    entirely rather than shipping the author's filesystem layout. See
    issue #811.

    ``initial_cache_store`` is the server-managed initial-load cache (the
    ``/load_expr`` hit path + ``/cache`` endpoint). Defaults to a memory-only
    store; pass ``initial_cache_dir`` for a persistent one (prewarmed eagerly at
    startup) or inject a prebuilt store directly."""
    if sessions is None:
        sessions = SessionManager()
    if initial_cache_store is None:
        initial_cache_store = InitialCacheStore(base_dir=initial_cache_dir)
    if initial_cache_dir:
        initial_cache_store.prewarm()

    static_path = os.path.join(os.path.dirname(__file__), "..", "static")

    return tornado.web.Application([
            (r"/health", HealthHandler),
            (r"/diagnostics", DiagnosticsHandler),
            (r"/load", LoadHandler),
            (r"/load_expr", LoadExprHandler),
            (r"/reload_expr/([^/]+)", ReloadExprHandler),
            (r"/load_compare", LoadCompareHandler),
            (r"/cache", CacheHandler),
            (r"/s/([^/]+)", SessionPageHandler),
            (r"/ws/([^/]+)", DataStreamHandler),
        ], sessions=sessions, port=port, open_browser=open_browser,
        static_path=os.path.abspath(static_path),
        server_start_time=SERVER_START_TIME, datasets=datasets or [],
        initial_cache_store=initial_cache_store)
