"""Regression test for the ``--port=0`` (OS-assigned) → app settings path.

When the server is launched with ``--port=0``, ``tornado.netutil.bind_sockets``
binds an OS-assigned port. The Application's ``settings['port']`` must reflect
that bound port — not the requested ``0`` — because
``LoadHandler._handle_browser_window`` reads ``settings['port']`` to build the
``http://localhost:<port>/s/<session>`` URL it asks the OS to focus.

Pre-fix, ``__main__.main()`` did ``make_app(port=args.port)`` first (with 0),
then bound sockets afterwards, so settings captured the stale 0 and any
browser-focus call opened ``http://localhost:0/s/<id>``.

This test pins the fix by exercising the extracted ``bind_and_make_app`` helper
that ``main()`` now uses.
"""

import socket
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Uses POSIX bind_sockets semantics")


def _close_all(sockets):
    for s in sockets:
        try:
            s.close()
        except OSError:
            pass


def test_bind_and_make_app_propagates_bound_port_to_settings():
    """``--port=0`` path: settings['port'] must be the OS-assigned port."""
    from buckaroo.server.__main__ import bind_and_make_app

    sockets, bound_port, app = bind_and_make_app(port=0, open_browser=False)
    try:
        assert bound_port != 0, "bind_sockets(0) should return a non-zero OS-assigned port"
        assert app.settings["port"] == bound_port, (
            f"Application settings['port'] must reflect bound port {bound_port}, "
            f"got {app.settings['port']!r}. LoadHandler._handle_browser_window would "
            f"open http://localhost:{app.settings['port']}/s/<session> — bogus."
        )
    finally:
        _close_all(sockets)


def test_bind_and_make_app_explicit_port_round_trips():
    """When a concrete port is requested, settings should match exactly."""
    from buckaroo.server.__main__ import bind_and_make_app

    # Grab a known-free high port to bind, then close before re-binding.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    sockets, bound_port, app = bind_and_make_app(port=free_port, open_browser=False)
    try:
        assert bound_port == free_port
        assert app.settings["port"] == free_port
    finally:
        _close_all(sockets)
