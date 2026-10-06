import pytest


@pytest.fixture(scope="session", autouse=True)
def _pyarrow_honours_timezones():
    """pandera sets ``PYARROW_IGNORE_TIMEZONE=1`` when it is imported, and
    collecting ``contrib/test_buckaroo_pandera.py`` imports it. Left set, every
    test in the session would run with pyarrow storing an aware datetime's wall
    time as UTC (#1058)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("PYARROW_IGNORE_TIMEZONE", raising=False)
        yield
