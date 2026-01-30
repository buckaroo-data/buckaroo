#!/usr/bin/env python
"""
Standalone mp_timeout_decorator test script.

Runs all mp_timeout checks in a single invocation, avoiding the overhead of
pytest spinning up a fresh forkserver per test.  Each check mirrors a skipped
pytest test in mp_timeout_decorator_test.py.

The forkserver context means every mp_timeout call pays the cost of forking a
fresh Python interpreter.  Under pytest the child inherits a large memory image
(all test fixtures, plugins, collected items, etc.) which makes each fork
significantly slower.  Running the same checks from a lean standalone script
cuts that overhead.  pytest-xdist has been tried and does not help here because
the bottleneck is per-fork overhead, not test parallelism.

Usage:
    python tests/unit/file_cache/run_mp_timeout_tests.py

To run the original pytest versions instead:
    pytest tests/unit/file_cache/mp_timeout_decorator_test.py --no-header -rN
"""
import sys
import textwrap
import threading

from buckaroo.file_cache.mp_timeout_decorator import (
    TimeoutException, ExecutionFailed, mp_timeout, is_running_in_mp_timeout,
)
from tests.unit.file_cache.mp_test_utils import (
    mp_simple, mp_sleep1, mp_polars_longread,
    TIMEOUT,
)

passed = 0
failed = 0
errors: list[str] = []


def run_check(name: str, pytest_test: str, fn):
    """Run a check function, print PASS/FAIL, and record results."""
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except Exception as exc:
        msg = str(exc).split("\n")[0]
        print(f"  FAIL  {name}: {msg}")
        print(f"         pytest -xvs tests/unit/file_cache/mp_timeout_decorator_test.py::{pytest_test}")
        failed += 1
        errors.append(name)


# ── check functions (defined at module level for pickling) ────────────────────

def check_basic_pass():
    result = mp_simple()
    assert result == 5, f"expected 5, got {result}"


def check_timeout_fail():
    try:
        mp_sleep1()
    except TimeoutException:
        return
    raise AssertionError("TimeoutException not raised")


def check_normal_exception():
    try:
        1 / 0
    except ZeroDivisionError:
        return
    raise AssertionError("ZeroDivisionError not raised")


def check_polars_timeout():
    try:
        mp_polars_longread()
    except TimeoutException:
        return
    raise AssertionError("TimeoutException not raised")


def check_fail_then_normal():
    try:
        mp_sleep1()
    except TimeoutException:
        pass
    result = mp_simple()
    assert result == 5, f"expected 5 after recovery, got {result}"


def check_mp_exception():
    @mp_timeout(TIMEOUT * 3)
    def zero_div():
        5 / 0
    try:
        zero_div()
    except ZeroDivisionError:
        return
    raise AssertionError("ZeroDivisionError not raised")


def check_polars_simple_len():
    import polars as pl  # type: ignore

    @mp_timeout(TIMEOUT * 2)
    def polars_len():
        df = pl.DataFrame({'a': [1, 2, 3]})
        return int(df.select(pl.len()).item())

    result = polars_len()
    assert result == 3, f"expected 3, got {result}"


def check_jupyter_simulate():
    ipython_cell_source = """
        def f(x):
            return x
        """
    ipython_cell_id = "<ipython-input-0-000000000000>"
    my_locals = {}
    exec(
        compile(
            textwrap.dedent(ipython_cell_source),
            filename=ipython_cell_id,
            mode="exec",
        ),
        None,
        my_locals,
    )
    f = my_locals["f"]
    f.__module__ = "__main__"
    assert f(1) == 1
    wrapped_f = mp_timeout(TIMEOUT * 3)(f)
    result = wrapped_f(1)
    assert result == 1, f"expected 1, got {result}"


def check_unpicklable_return():
    @mp_timeout(TIMEOUT * 3)
    def return_unpicklable():
        return threading.Lock()

    try:
        return_unpicklable()
    except ExecutionFailed:
        return
    raise AssertionError("ExecutionFailed not raised for unpicklable return")


def check_is_running_in_mp_timeout():
    assert is_running_in_mp_timeout() is False, "should be False outside mp_timeout"

    @mp_timeout(TIMEOUT * 3)
    def check_inside():
        return is_running_in_mp_timeout()

    result = check_inside()
    assert result is True, "should be True inside mp_timeout"


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    run_check("1  basic_pass",            "test_mp_timeout_pass",             check_basic_pass)
    run_check("2  timeout_fail",          "test_mp_timeout_fail",             check_timeout_fail)
    run_check("3  polars_timeout",        "test_mp_polars_timeout",           check_polars_timeout)
    run_check("4  fail_then_normal",      "test_mp_fail_then_normal",         check_fail_then_normal)
    run_check("5  normal_exception",      "test_normal_exception",            check_normal_exception)
    run_check("6  mp_exception",          "test_mp_exception",                check_mp_exception)
    run_check("7  polars_simple_len",     "test_mp_polars_simple_len",        check_polars_simple_len)
    run_check("8  jupyter_simulate",      "test_jupyter_simulate",            check_jupyter_simulate)
    run_check("9  unpicklable_return",    "test_unpicklable_return_raises_execution_failed", check_unpicklable_return)
    run_check("10 is_running_in_mp_timeout", "test_is_running_in_mp_timeout", check_is_running_in_mp_timeout)

    print()
    print(f"  {passed} passed, {failed} failed")
    if errors:
        print(f"  FAILED: {', '.join(errors)}")
        sys.exit(1)
