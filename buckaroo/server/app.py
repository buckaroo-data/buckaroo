import os
import secrets
import time

import tornado.web

from buckaroo.server.handlers import HealthHandler, DiagnosticsHandler, LoadHandler, LoadExprHandler, LoadCompareHandler, ReloadExprHandler, SessionPageHandler
from buckaroo.server.websocket_handler import DataStreamHandler
from buckaroo.server.session import SessionManager

SERVER_START_TIME = time.time()


def make_app(sessions: SessionManager | None = None, port: int = 8888, open_browser: bool = False,
        datasets: list | None = None, token: str | None = None,
        allow_origins=()) -> tornado.web.Application:
    """Build the tornado app.

    ``datasets`` is the operator-supplied list of dropdown entries the
    demo page (/s/<id>) exposes — each a ``{"label", "kind", "target"}``
    dict, with ``kind`` in ``("pandas", "lazy", "xorq")``. ``None`` /
    ``[]`` means no datasets configured: the page omits the dropdown
    entirely rather than shipping the author's filesystem layout. See
    issue #811.

    ``open_browser`` is off unless asked for: the CLI passes it from
    ``--no-browser``, and a test or script building a throwaway server
    shouldn't open a window per ``/load``.

    ``token`` is the auth token every request must present (header, query
    or cookie). ``None`` / ``""`` disables auth — the default here so tests
    and scripts build an open server; ``buckaroo.server.__main__`` resolves
    a real token (default-on) and passes it in. ``allow_origins`` lists the
    extra browser origins (beyond same-origin) allowed to open a WebSocket,
    for embedders; ``"*"`` allows all. XSRF cookies are enabled only when a
    token is set — a token-authenticated request is XSRF-exempt, so the
    cookie protects only the browser's own same-origin POSTs."""
    if sessions is None:
        sessions = SessionManager()

    static_path = os.path.join(os.path.dirname(__file__), "..", "static")

    return tornado.web.Application([
            (r"/health", HealthHandler),
            (r"/diagnostics", DiagnosticsHandler),
            (r"/load", LoadHandler),
            (r"/load_expr", LoadExprHandler),
            (r"/reload_expr/([^/]+)", ReloadExprHandler),
            (r"/load_compare", LoadCompareHandler),
            (r"/s/([^/]+)", SessionPageHandler),
            (r"/ws/([^/]+)", DataStreamHandler),
        ], sessions=sessions, port=port, open_browser=open_browser,
        static_path=os.path.abspath(static_path),
        server_start_time=SERVER_START_TIME, datasets=datasets or [],
        token=token or "", allow_origins=tuple(allow_origins),
        cookie_secret=secrets.token_hex(32), xsrf_cookies=bool(token))
