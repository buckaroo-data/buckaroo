"""Handler-level tests for PR2 token auth, XSRF, origin allowlist and CSP.

A server built with a token refuses unauthenticated requests; ``/health``
stays exempt (and minimal); a ``?token=`` promotes to a cookie; the WS
origin policy is same-origin-plus-allowlist; ``/s/`` carries a
frame-ancestors CSP.
"""
import http.cookies
import json
import os
import sys
import tempfile

import pandas as pd
import pytest
import tornado.httpclient
import tornado.testing
import tornado.websocket

from buckaroo.server.app import make_app as _make_app

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="temp-file locking on Windows")

TOKEN = "test-token-abcdef0123456789"


def _write_csv(path):
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_csv(path, index=False)


def _cookies_from(resp):
    """Collapse a response's Set-Cookie headers into a name->value dict."""
    jar = {}
    for hdr in resp.headers.get_list("Set-Cookie"):
        c = http.cookies.SimpleCookie()
        c.load(hdr)
        for k, morsel in c.items():
            jar[k] = morsel.value
    return jar


def _cookie_header(jar):
    return "; ".join(f"{k}={v}" for k, v in jar.items())


class TestTokenAuth(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN)

    def test_diagnostics_refused_without_token(self):
        resp = self.fetch("/diagnostics")
        self.assertEqual(resp.code, 403)
        self.assertEqual(json.loads(resp.body)["error_code"], "forbidden")

    def test_diagnostics_allowed_with_header_token(self):
        resp = self.fetch("/diagnostics", headers={"Authorization": f"token {TOKEN}"})
        self.assertEqual(resp.code, 200)

    def test_session_page_refused_without_token(self):
        self.assertEqual(self.fetch("/s/sess-1").code, 403)

    def test_session_page_query_token_sets_cookie_then_cookie_auths(self):
        resp = self.fetch("/s/sess-1?token=" + TOKEN)
        self.assertEqual(resp.code, 200)
        jar = _cookies_from(resp)
        auth_cookies = [k for k in jar if k.startswith("buckaroo_token_")]
        self.assertTrue(auth_cookies, f"no auth cookie set; got {list(jar)}")
        # A follow-up request carrying only the cookie (no ?token=) authenticates.
        resp2 = self.fetch("/s/sess-1", headers={"Cookie": _cookie_header(jar)})
        self.assertEqual(resp2.code, 200)

    @tornado.testing.gen_test
    async def test_load_refused_without_token(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_csv(f.name)
            try:
                client = tornado.httpclient.AsyncHTTPClient()
                resp = await client.fetch(f"http://localhost:{self.get_http_port()}/load",
                    method="POST", body=json.dumps({"session": "s1", "path": f.name}),
                    headers={"Content-Type": "application/json"}, raise_error=False)
                self.assertEqual(resp.code, 403)
            finally:
                os.unlink(f.name)

    @tornado.testing.gen_test
    async def test_load_allowed_with_header_token(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_csv(f.name)
            try:
                client = tornado.httpclient.AsyncHTTPClient()
                resp = await client.fetch(f"http://localhost:{self.get_http_port()}/load",
                    method="POST", body=json.dumps({"session": "s1", "path": f.name}),
                    headers={"Content-Type": "application/json",
                        "Authorization": f"token {TOKEN}"}, raise_error=False)
                self.assertEqual(resp.code, 200)
            finally:
                os.unlink(f.name)


class TestHealthExemptAndMinimal(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN)

    def test_health_exempt_from_token(self):
        resp = self.fetch("/health")
        self.assertEqual(resp.code, 200)

    def test_health_body_is_minimal(self):
        body = json.loads(self.fetch("/health").body)
        self.assertEqual(body.get("status"), "ok")
        self.assertIn("version", body)
        # pid / static_files / paths must not leak from the unauthenticated endpoint.
        self.assertNotIn("pid", body)
        self.assertNotIn("static_files", body)


class TestAuthDisabled(tornado.testing.AsyncHTTPTestCase):
    """token=None (or '') disables auth — the default make_app used by the
    rest of the suite. POSTs work without a token or _xsrf."""

    def get_app(self):
        return _make_app(open_browser=False)

    def test_diagnostics_open_when_no_token(self):
        self.assertEqual(self.fetch("/diagnostics").code, 200)

    @tornado.testing.gen_test
    async def test_load_open_when_no_token(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_csv(f.name)
            try:
                client = tornado.httpclient.AsyncHTTPClient()
                resp = await client.fetch(f"http://localhost:{self.get_http_port()}/load",
                    method="POST", body=json.dumps({"session": "s1", "path": f.name}),
                    headers={"Content-Type": "application/json"}, raise_error=False)
                self.assertEqual(resp.code, 200)
            finally:
                os.unlink(f.name)


class TestXsrf(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN)

    @tornado.testing.gen_test
    async def test_cookie_post_without_xsrf_refused_but_header_token_exempt(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            _write_csv(f.name)
            try:
                port = self.get_http_port()
                client = tornado.httpclient.AsyncHTTPClient()
                # Authenticate via the page to collect the auth + _xsrf cookies.
                page = await client.fetch(f"http://localhost:{port}/s/s1?token={TOKEN}",
                    raise_error=False)
                jar = _cookies_from(page)
                self.assertIn("_xsrf", jar)
                # Cookie-authenticated POST with no X-XSRFToken -> refused.
                resp = await client.fetch(f"http://localhost:{port}/load", method="POST",
                    body=json.dumps({"session": "s1", "path": f.name}),
                    headers={"Content-Type": "application/json",
                        "Cookie": _cookie_header(jar)}, raise_error=False)
                self.assertEqual(resp.code, 403)
                # Same POST with the matching X-XSRFToken header -> allowed.
                resp2 = await client.fetch(f"http://localhost:{port}/load", method="POST",
                    body=json.dumps({"session": "s1", "path": f.name}),
                    headers={"Content-Type": "application/json",
                        "Cookie": _cookie_header(jar), "X-XSRFToken": jar["_xsrf"]},
                    raise_error=False)
                self.assertEqual(resp2.code, 200)
            finally:
                os.unlink(f.name)


class TestWsOriginPolicy(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN)

    @tornado.testing.gen_test(timeout=10)
    async def test_same_origin_with_token_connects(self):
        ws = await tornado.websocket.websocket_connect(
            f"ws://localhost:{self.get_http_port()}/ws/s1?token={TOKEN}")
        ws.close()

    @tornado.testing.gen_test(timeout=10)
    async def test_foreign_origin_refused_even_with_token(self):
        req = tornado.httpclient.HTTPRequest(
            f"ws://localhost:{self.get_http_port()}/ws/s1?token={TOKEN}",
            headers={"Origin": "http://evil.example"})
        with self.assertRaises(tornado.httpclient.HTTPClientError):
            await tornado.websocket.websocket_connect(req)

    @tornado.testing.gen_test(timeout=10)
    async def test_ws_refused_without_token(self):
        with self.assertRaises(tornado.httpclient.HTTPClientError):
            await tornado.websocket.websocket_connect(
                f"ws://localhost:{self.get_http_port()}/ws/s1")


class TestWsOriginAllowlist(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN,
            allow_origins=("http://embedder.example",))

    @tornado.testing.gen_test(timeout=10)
    async def test_allowlisted_origin_connects(self):
        req = tornado.httpclient.HTTPRequest(
            f"ws://localhost:{self.get_http_port()}/ws/s1?token={TOKEN}",
            headers={"Origin": "http://embedder.example"})
        ws = await tornado.websocket.websocket_connect(req)
        ws.close()


class TestSessionPageCSP(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return _make_app(open_browser=False, token=TOKEN)

    def test_frame_ancestors_present(self):
        resp = self.fetch("/s/s1?token=" + TOKEN)
        self.assertEqual(resp.code, 200)
        csp = resp.headers.get("Content-Security-Policy", "")
        self.assertIn("frame-ancestors", csp)
