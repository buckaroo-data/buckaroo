"""
mp_timeout_decorator pytest tests.

Most tests that exercise the multiprocessing decorator are slow due to process
spawning overhead. They have been moved to a standalone script that runs them
all in a single process-startup cycle:

    python tests/unit/file_cache/run_mp_timeout_tests.py

Each skipped test below documents which script check covers it.
"""
import pytest

SKIP_MSG = "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"


def test_mp_timeout_pass():
    """Covered by run_mp_timeout_tests.py  check 1 (basic_pass)."""
    pytest.skip(SKIP_MSG)


def test_mp_timeout_fail():
    """Covered by run_mp_timeout_tests.py  check 2 (timeout_fail)."""
    pytest.skip(SKIP_MSG)


def test_mp_polars_timeout():
    """Covered by run_mp_timeout_tests.py  check 3 (polars_timeout)."""
    pytest.skip(SKIP_MSG)


def test_mp_fail_then_normal():
    """Covered by run_mp_timeout_tests.py  check 4 (fail_then_normal)."""
    pytest.skip(SKIP_MSG)


def test_normal_exception():
    """Covered by run_mp_timeout_tests.py  check 5 (normal_exception). Also kept inline."""
    with pytest.raises(ZeroDivisionError):
        1 / 0


def test_mp_exception():
    """Covered by run_mp_timeout_tests.py  check 6 (mp_exception)."""
    pytest.skip(SKIP_MSG)


def test_mp_polars_simple_len():
    """Covered by run_mp_timeout_tests.py  check 7 (polars_simple_len)."""
    pytest.skip(SKIP_MSG)


def test_jupyter_simulate():
    """Covered by run_mp_timeout_tests.py  check 8 (jupyter_simulate)."""
    pytest.skip(SKIP_MSG)


def test_unpicklable_return_raises_execution_failed():
    """Covered by run_mp_timeout_tests.py  check 9 (unpicklable_return)."""
    pytest.skip(SKIP_MSG)


def test_is_running_in_mp_timeout():
    """Covered by run_mp_timeout_tests.py  check 10 (is_running_in_mp_timeout)."""
    pytest.skip(SKIP_MSG)
