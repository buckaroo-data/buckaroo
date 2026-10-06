"""Request-level security gates for the buckaroo server.

The server binds ``127.0.0.1`` and is meant for local use, but two things
still reach it from a hostile context: a page open in any browser tab can
drive it cross-origin, and DNS rebinding can make a remote page look
same-origin. These helpers are the request-time gates against the subset
of that which does not need the token machinery (that lands separately):

- ``is_valid_session_id`` constrains the session id that gets interpolated
  into the ``/s/`` page (HTML + inline JS) and into the AppleScript in
  ``focus.py``, so a crafted id cannot break out of any of those contexts.
- ``host_is_local`` / ``LocalHostCheckMixin`` reject requests whose ``Host``
  header is not a loopback name — the DNS-rebinding defense Jupyter ships
  as ``allow_remote_access=False``.
- ``resolve_token`` / the connection-file helpers / ``AuthMixin`` are the
  token gate, modelled on Jupyter: a per-server token (header, query or
  cookie) is the trust boundary, and a 0600 connection file lets the
  parent process (the MCP tool) find the running server's port, pid and
  token without an unauthenticated endpoint.
- ``origin_is_allowed`` is the WebSocket origin policy: same-origin plus a
  configured allowlist, replacing the previously permissive check.
"""
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("buckaroo.server.security")

# Session ids are only ever dict keys in ``SessionManager`` — never
# filesystem paths — so the single risk is interpolation into the ``/s/``
# page (HTML text + a double-quoted inline JS string) and into the
# double-quoted AppleScript strings in ``focus.py``. No character in this
# class is significant in any of those contexts. 128 chars fits every real
# caller: buckaroo's own ``uuid4().hex`` (32), tallyman's
# ``entry-<project>-<sha256hex>`` (~103), pydata's ``diff-<12>-<12>``.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def is_valid_session_id(session_id) -> bool:
    """True when *session_id* is a non-empty string of at most 128
    ``[A-Za-z0-9._-]`` characters. Everything else is rejected at the edge
    so no handler interpolates an attacker-chosen id into HTML, JS or
    AppleScript."""
    return isinstance(session_id, str) and SESSION_ID_RE.match(session_id) is not None


def _hostname_from_host_header(host: str) -> str:
    """Return the hostname portion of a ``Host`` header, port stripped.

    Handles the bracketed IPv6 form (``[::1]:8700`` -> ``::1``). A bare
    ``host:port`` splits on the last colon only, so a malformed unbracketed
    IPv6 literal fails the loopback test below rather than silently losing
    octets.
    """
    if not host:
        return ""
    if host.startswith("["):
        # Bracketed IPv6: [::1] or [::1]:8700
        return host[1:].split("]", 1)[0]
    if host.count(":") > 1:
        # Bare IPv6 literal with no port (a port would require brackets);
        # splitting on the last colon would mistake a hextet for a port.
        return host
    return host.rsplit(":", 1)[0] if ":" in host else host


def host_is_local(host: str) -> bool:
    """True when a ``Host`` header names the loopback interface.

    Mirrors Jupyter's ``allow_remote_access=False`` default: a Host that is
    not ``localhost`` or a loopback IP is refused. This is the DNS-rebinding
    defense — an attacker's page can rebind its name to the victim's address,
    but the ``Host`` header the browser then sends is still the attacker's
    name, not a loopback one.
    """
    hostname = _hostname_from_host_header(host).strip().lower()
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def remote_access_allowed() -> bool:
    """``BUCKAROO_ALLOW_REMOTE_ACCESS=1`` turns the Host check off, the
    parallel of Jupyter's ``allow_remote_access``. Off by default."""
    return os.environ.get("BUCKAROO_ALLOW_REMOTE_ACCESS", "").lower() in ("1", "true", "yes")


class LocalHostCheckMixin:
    """Mixin that rejects requests with a non-loopback ``Host`` header.

    Mixed in ahead of ``tornado.web.RequestHandler`` (and the WebSocket
    handler) so its ``prepare`` runs before any ``get``/``post`` or the WS
    upgrade. ``BUCKAROO_ALLOW_REMOTE_ACCESS=1`` disables it.
    """

    def prepare(self):
        if not remote_access_allowed() and not host_is_local(self.request.host or ""):
            log.warning("refused non-local Host header: %r (path=%s)",
                self.request.host, self.request.path)
            self.set_status(403)
            self.set_header("Content-Type", "application/json")
            self.finish({"error_code": "forbidden_host",
                "message": "Refusing request with a non-local Host header "
                "(DNS-rebinding protection). Set BUCKAROO_ALLOW_REMOTE_ACCESS=1 "
                "on the server to allow remote access."})
            return
        super().prepare()


# ---------------------------------------------------------------------------
# Token auth + connection file (Jupyter-style)
# ---------------------------------------------------------------------------

_RUNTIME_DIR = Path(os.path.expanduser("~")) / ".buckaroo" / "runtime"


def resolve_token(env=None) -> str:
    """The token a server authenticates with.

    ``BUCKAROO_TOKEN`` wins when set — including an explicit empty string,
    which disables auth (the escape hatch, with a warning at startup). When
    the variable is unset a fresh 48-hex token is minted. Mirrors Jupyter's
    default-on token.
    """
    env = os.environ if env is None else env
    tok = env.get("BUCKAROO_TOKEN")
    if tok is None:
        return secrets.token_hex(24)
    return tok


def tokens_match(a, b) -> bool:
    """Constant-time compare of two non-empty tokens."""
    if not a or not b:
        return False
    return hmac.compare_digest(str(a), str(b))


def connection_file_path(port: int, runtime_dir=None) -> Path:
    base = Path(runtime_dir) if runtime_dir else _RUNTIME_DIR
    return base / f"buckaroo-{port}.json"


def write_connection_file(port: int, pid: int, token: str, version: str,
        runtime_dir=None) -> Path:
    """Write ``~/.buckaroo/runtime/buckaroo-<port>.json`` at mode 0600.

    The parent process (the MCP tool) reads it to learn the running
    server's pid and token — so it never has to take a pid from an
    unauthenticated HTTP endpoint, and never kills a process it can't
    confirm is ours.
    """
    path = connection_file_path(port, runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "url": f"http://127.0.0.1:{port}/", "port": port, "pid": pid,
        "token": token, "version": version})
    # O_CREAT with 0600 and O_TRUNC — never world-readable even briefly.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(payload)
    os.chmod(path, 0o600)
    return path


def read_connection_file(port: int, runtime_dir=None) -> dict | None:
    try:
        return json.loads(connection_file_path(port, runtime_dir).read_text())
    except (OSError, ValueError):
        return None


def remove_connection_file(port: int, runtime_dir=None) -> None:
    try:
        connection_file_path(port, runtime_dir).unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Origin policy (WebSocket + browser)
# ---------------------------------------------------------------------------


def origin_is_allowed(origin, port: int, allow_origins=()) -> bool:
    """Whether a browser ``Origin`` may open a WebSocket / drive the server.

    - No ``Origin`` (non-browser client) is allowed; the token still gates it.
    - The server's own origin — an ``http(s)`` loopback host on *port* — is
      same-origin and allowed (the standalone ``/s/`` page).
    - Anything else must be listed in *allow_origins* (an embedder's origin,
      e.g. ``tauri://localhost`` or ``http://localhost:7860``). ``"*"`` in the
      list allows every origin (the old permissive behavior, opt-in).
    """
    if not origin:
        return True
    allow = {o.rstrip("/").lower() for o in allow_origins}
    if "*" in allow:
        return True
    try:
        u = urlparse(origin)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme in ("http", "https") and host_is_local(host) and u.port == port:
        return True
    return origin.rstrip("/").lower() in allow


# ---------------------------------------------------------------------------
# Auth enforcement mixin
# ---------------------------------------------------------------------------


class AuthMixin:
    """Mixin that requires the server token on every request.

    Mixed in ahead of ``LocalHostCheckMixin`` so the Host check runs first
    (via ``super().prepare()``), then the token check. A handler sets
    ``_auth_exempt = True`` to opt out (``/health``). When the app has no
    token configured (``settings['token']`` falsy) auth is disabled and
    every request passes — that is the explicit opt-out.

    A token presented in the ``Authorization: token <t>`` header or the
    ``?token=`` query is promoted to a signed, HttpOnly cookie so the
    follow-up same-origin requests (the WS, row fetches, the engine-bar
    POST) authenticate without re-passing it.
    """

    _auth_exempt = False

    def check_xsrf_cookie(self):
        # A request carrying the token in the header or query is a
        # programmatic client (or the first authenticated page load); it is
        # exempt from XSRF, exactly as in Jupyter. Cookie-only requests —
        # a browser POST — still need the _xsrf token.
        presented, from_cookie = self._presented_token()
        if presented and not from_cookie and tokens_match(presented, self.settings.get("token")):
            return
        super().check_xsrf_cookie()

    def prepare(self):
        super().prepare()  # Host check; may finish() with 403.
        if self._finished:
            return
        token = self.settings.get("token")
        if not token or self._auth_exempt:
            return
        presented, from_cookie = self._presented_token()
        if presented and tokens_match(presented, token):
            # Promote a header/query token to a cookie so the page's
            # follow-up same-origin requests authenticate on their own.
            # Not on a WebSocket upgrade — the page already holds the
            # cookie there, and Set-Cookie on a 101 is unreliable.
            is_ws = self.request.headers.get("Upgrade", "").lower() == "websocket"
            if not from_cookie and not is_ws:
                self.set_signed_cookie(self._auth_cookie_name(), token,
                    httponly=True, samesite="Lax")
            return
        log.warning("refused request with missing/invalid token (path=%s)", self.request.path)
        self.set_status(403)
        self.set_header("Content-Type", "application/json")
        self.finish({"error_code": "forbidden",
            "message": "Missing or invalid token. Pass ?token=<t>, an "
            "'Authorization: token <t>' header, or load the page the server "
            "opened (which carries the token)."})

    def _auth_cookie_name(self) -> str:
        return f"buckaroo_token_{self.settings.get('port', '')}"

    def _presented_token(self):
        """Return ``(token, from_cookie)``; token is None when absent."""
        auth = self.request.headers.get("Authorization", "")
        if auth.startswith("token "):
            return auth[len("token "):].strip(), False
        qtok = self.get_query_argument("token", None)
        if qtok:
            return qtok, False
        cookie = self.get_signed_cookie(self._auth_cookie_name(), max_age_days=30)
        if cookie:
            return (cookie.decode() if isinstance(cookie, bytes) else cookie), True
        return None, False
