"""Unit tests for ``buckaroo.server.security``.

Pure functions — fast, deterministic, no server. The handler-level
enforcement (which status codes come back) lives in ``test_server.py``.
"""
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
