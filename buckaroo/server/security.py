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
"""
import ipaddress
import logging
import os
import re

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
