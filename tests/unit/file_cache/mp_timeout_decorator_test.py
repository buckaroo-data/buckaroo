"""
mp_timeout_decorator pytest tests.

Most tests that exercise the multiprocessing decorator are slow due to process
spawning overhead. They have been moved to a standalone script that runs them
all in a single process-startup cycle:

    python tests/unit/file_cache/run_mp_timeout_tests.py

Each skipped test below documents which script check covers it.
"""
import pytest


def test_mp_timeout_pass():
    """Covered by run_mp_timeout_tests.py  check 1 (basic_pass)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_timeout_fail():
    """Covered by run_mp_timeout_tests.py  check 2 (timeout_fail)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_crash_exit():
    """Covered by run_mp_timeout_tests.py  check 3 (crash_exit). Flaky in CI."""
    pytest.skip(
        "Diagnostic + slow. Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_polars_crash():
    """Covered by run_mp_timeout_tests.py  check 4 (polars_crash). Flaky in CI."""
    pytest.skip(
        "Diagnostic + slow. Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_polars_timeout():
    """Covered by run_mp_timeout_tests.py  check 5 (polars_timeout)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_fail_then_normal():
    """Covered by run_mp_timeout_tests.py  check 6 (fail_then_normal)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_normal_exception():
    """Pure Python, no mp_timeout involved -- kept inline."""
    with pytest.raises(ZeroDivisionError):
        1 / 0


def test_mp_exception():
    """Covered by run_mp_timeout_tests.py  check 7 (mp_exception)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_polars_rename_unserializable_raises_execution_failed():
    """Covered by run_mp_timeout_tests.py  check 8 (polars_unserializable). Flaky in CI."""
    pytest.skip(
        "Diagnostic + slow. Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_mp_polars_simple_len():
    """Covered by run_mp_timeout_tests.py  check 9 (polars_simple_len)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_jupyter_simulate():
    """Covered by run_mp_timeout_tests.py  check 10 (jupyter_simulate)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_unpicklable_return_raises_execution_failed():
    """Covered by run_mp_timeout_tests.py  check 11 (unpicklable_return)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_unpicklable_exception_raises_execution_failed():
    """Covered by run_mp_timeout_tests.py  check 12 (unpicklable_exception). Flaky in CI."""
    pytest.skip(
        "Diagnostic + slow. Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_sys_exit_is_execution_failed():
    """Covered by run_mp_timeout_tests.py  check 13 (sys_exit). Flaky in CI."""
    pytest.skip(
        "Diagnostic + slow. Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )


def test_is_running_in_mp_timeout():
    """Covered by run_mp_timeout_tests.py  check 14 (is_running_in_mp_timeout)."""
    pytest.skip(
        "Slow (process spawn). Run: python tests/unit/file_cache/run_mp_timeout_tests.py"
    )
