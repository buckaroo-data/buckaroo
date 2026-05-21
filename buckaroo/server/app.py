import os
import time

import tornado.web

from buckaroo.server.handlers import HealthHandler, DiagnosticsHandler, LoadHandler, LoadExprHandler, LoadCompareHandler, SessionPageHandler
from buckaroo.server.websocket_handler import DataStreamHandler
from buckaroo.server.session import SessionManager

SERVER_START_TIME = time.time()


def make_app(sessions: SessionManager | None = None, port: int = 8888, open_browser: bool = True,
        datasets: list | None = None) -> tornado.web.Application:
    """Build the tornado app.

    ``datasets`` is the operator-supplied list of dropdown entries the
    demo page (/s/<id>) exposes — each a ``{"label", "kind", "target"}``
    dict, with ``kind`` in ``("pandas", "lazy", "xorq")``. ``None`` /
    ``[]`` means no datasets configured: the page omits the dropdown
    entirely rather than shipping the author's filesystem layout. See
    issue #811."""
    if sessions is None:
        sessions = SessionManager()

    static_path = os.path.join(os.path.dirname(__file__), "..", "static")

    return tornado.web.Application([
            (r"/health", HealthHandler),
            (r"/diagnostics", DiagnosticsHandler),
            (r"/load", LoadHandler),
            (r"/load_expr", LoadExprHandler),
            (r"/load_compare", LoadCompareHandler),
            (r"/s/([^/]+)", SessionPageHandler),
            (r"/ws/([^/]+)", DataStreamHandler),
        ], sessions=sessions, port=port, open_browser=open_browser,
        static_path=os.path.abspath(static_path),
        server_start_time=SERVER_START_TIME, datasets=datasets or [])
