"""Session-scoped warm-up for the mp_timeout multiprocessing context.

The first call to ``ctx.Process().start()`` (forkserver on POSIX, spawn on
Windows) pays a one-time bootstrap cost — starting the forkserver helper or
spinning up a fresh interpreter. On a slow CI runner that bootstrap can
exceed the 1-second ``CI_TIMEOUT`` used by these tests, so the *first* test
that calls a normal ``@mp_timeout``-wrapped function (``test_mp_timeout_pass``
in particular) intermittently flakes with ``TimeoutException``. Subsequent
calls reuse the warm pool and finish in milliseconds.

This fixture forces one no-op invocation per session before any test runs,
amortising the bootstrap cost so per-test timeouts only need to cover the
work itself.
"""

from __future__ import annotations

import pytest

from buckaroo.file_cache.mp_timeout_decorator import mp_timeout


@pytest.fixture(scope="session", autouse=True)
def _warm_mp_context():
    @mp_timeout(30.0)
    def _noop():
        return None

    try:
        _noop()
    except Exception:
        # Never block the test session if warm-up itself can't run — the
        # individual tests will surface any real defect.
        pass
