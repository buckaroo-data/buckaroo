"""Unit tests for ``buckaroo.server.security``.

Pure functions — fast, deterministic, no server. The handler-level
enforcement (which status codes come back) lives in ``test_server.py`` and
``test_server_auth.py``.
"""
import os
import stat
from unittest import mock

import pytest

from buckaroo.server import security as S


class TestIsValidSessionId:
    @pytest.mark.parametrize("sid", [
        "a" * 32,                                   # buckaroo uuid4().hex
        "deadbeefcafebabedeadbeefcafebabe",
        "entry-restaurants-" + "a" * 64,            # tallyman entry-<project>-<sha256hex>
        "diff-abc123abc123-def456def456",           # pydata diff ids
        "test-session", "sess_plain", "x", "A.B_c-1",
        "a" * 128,                                  # exactly the cap
    ])
    def test_accepts_real_caller_ids(self, sid):
        assert S.is_valid_session_id(sid)

    @pytest.mark.parametrize("sid", [
        "",                                         # empty
        "a" * 129,                                  # one over the cap
        '";alert(document.domain);"',               # JS-string breakout
        "</title><script>alert(1)</script>",        # HTML/title breakout
        'x" & (do shell script "touch /tmp/pwned") & "',  # AppleScript breakout
        "a/b", "../etc/passwd", "a\\b",             # path-ish
        "a b", "a\tb", "a\nb",                      # whitespace / control
        "sess#1", "a%2e", "café",                   # other non-charset
    ])
    def test_rejects_dangerous_ids(self, sid):
        assert not S.is_valid_session_id(sid)

    @pytest.mark.parametrize("sid", [None, 123, b"abc", ["a"]])
    def test_rejects_non_str(self, sid):
        assert not S.is_valid_session_id(sid)


class TestHostIsLocal:
    @pytest.mark.parametrize("host", [
        "localhost", "localhost:8700", "LOCALHOST:8700",
        "127.0.0.1", "127.0.0.1:8700", "127.5.6.7:8700",   # whole 127/8 is loopback
        "[::1]", "[::1]:8700", "::1"])
    def test_loopback_hosts_allowed(self, host):
        assert S.host_is_local(host)

    @pytest.mark.parametrize("host", [
        "evil.example", "evil.example:8700",
        "192.168.1.5:8700", "10.0.0.1:8700",
        "0.0.0.0:8700",                                    # bind-all is not loopback
        "buckaroo.attacker.com", ""])
    def test_non_loopback_hosts_refused(self, host):
        assert not S.host_is_local(host)


# ---------------------------------------------------------------------------
# PR2: token auth + connection file + origin allowlist
# ---------------------------------------------------------------------------


class TestResolveToken:
    def test_generates_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            tok = S.resolve_token()
        assert isinstance(tok, str) and len(tok) >= 32

    def test_two_generated_tokens_differ(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert S.resolve_token() != S.resolve_token()

    def test_uses_env_value(self):
        with mock.patch.dict(os.environ, {"BUCKAROO_TOKEN": "sekret123"}):
            assert S.resolve_token() == "sekret123"

    def test_empty_env_disables_auth(self):
        # Explicit empty string means "no token" (auth off), distinct from unset.
        with mock.patch.dict(os.environ, {"BUCKAROO_TOKEN": ""}):
            assert S.resolve_token() == ""


class TestConnectionFile:
    def test_round_trips(self, tmp_path):
        S.write_connection_file(60123, 4242, "tok-abc", "9.9.9", runtime_dir=str(tmp_path))
        got = S.read_connection_file(60123, runtime_dir=str(tmp_path))
        assert got["port"] == 60123
        assert got["pid"] == 4242
        assert got["token"] == "tok-abc"
        assert got["version"] == "9.9.9"

    def test_is_owner_only(self, tmp_path):
        p = S.write_connection_file(60124, 1, "t", "0", runtime_dir=str(tmp_path))
        mode = stat.S_IMODE(os.stat(p).st_mode)
        assert mode == 0o600, f"connection file mode {oct(mode)} is not 0600"

    def test_missing_returns_none(self, tmp_path):
        assert S.read_connection_file(59999, runtime_dir=str(tmp_path)) is None

    def test_remove(self, tmp_path):
        S.write_connection_file(60125, 1, "t", "0", runtime_dir=str(tmp_path))
        S.remove_connection_file(60125, runtime_dir=str(tmp_path))
        assert S.read_connection_file(60125, runtime_dir=str(tmp_path)) is None


class TestTokensMatch:
    def test_equal(self):
        assert S.tokens_match("abc", "abc")

    @pytest.mark.parametrize("a,b", [("abc", "abd"), ("", "abc"), ("abc", ""), (None, "abc"), ("abc", None)])
    def test_unequal_or_empty(self, a, b):
        assert not S.tokens_match(a, b)


class TestOriginIsAllowed:
    PORT = 8700

    @pytest.mark.parametrize("origin",
        [f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}", f"https://localhost:{PORT}"])
    def test_same_origin_loopback_allowed(self, origin):
        assert S.origin_is_allowed(origin, self.PORT, ())

    def test_empty_origin_allowed(self):
        # Non-browser clients send no Origin; the token still gates them.
        assert S.origin_is_allowed("", self.PORT, ())
        assert S.origin_is_allowed(None, self.PORT, ())

    @pytest.mark.parametrize("origin",
        ["http://evil.example", "http://localhost:1420", "tauri://localhost", f"http://evil.example:{PORT}"])
    def test_foreign_origin_refused_without_allowlist(self, origin):
        assert not S.origin_is_allowed(origin, self.PORT, ())

    def test_allowlisted_origin_allowed(self):
        assert S.origin_is_allowed("tauri://localhost", self.PORT, ("tauri://localhost",))
        assert S.origin_is_allowed("http://localhost:1420", self.PORT, ("http://localhost:1420",))

    def test_wildcard_allows_all(self):
        assert S.origin_is_allowed("http://evil.example", self.PORT, ("*",))
