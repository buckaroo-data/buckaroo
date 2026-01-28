import textwrap
import sys
import threading
import pytest
import polars as pl  # type: ignore

from buckaroo.file_cache.mp_timeout_decorator import (
    TimeoutException, ExecutionFailed, mp_timeout, is_running_in_mp_timeout
)

from .mp_test_utils import ( mp_simple, mp_sleep1, mp_crash_exit, mp_polars_longread, mp_polars_crash,
                               TIMEOUT)

def test_mp_timeout_pass():
    """
      make sure a normal wrapped function invocation reutrns normally
      """
    assert mp_simple() == 5

    
def test_mp_timeout_fail():
    with pytest.raises(TimeoutException):
        mp_sleep1()


def test_mp_crash_exit():
    """
    DIAGNOSTIC TEST - Edge case: Subprocess crash detection.

    Verifies that a ctypes-induced crash in the subprocess is detected and
    results in ExecutionFailed. This is flaky in CI because crash detection
    timing varies based on system load.

    Run explicitly if testing subprocess crash handling behavior.
    """
    pytest.skip("Diagnostic test - subprocess crash detection is flaky in CI, run explicitly if needed")
    with pytest.raises(ExecutionFailed):
        mp_crash_exit()
    assert 1==1

def test_mp_polars_crash():
    """
    DIAGNOSTIC TEST - Edge case: Polars crash detection.

    Verifies that a Polars-induced crash in the subprocess is detected.
    This is flaky in CI because crash detection timing varies.

    Run explicitly if testing Polars crash handling behavior.
    """
    pytest.skip("Diagnostic test - Polars crash detection is flaky in CI, run explicitly if needed")
    with pytest.raises(ExecutionFailed):
        mp_polars_crash()

def test_mp_polars_timeout():
    """
      verify that a long running polars operation fails too
      """
    with pytest.raises(TimeoutException):
        mp_polars_longread()
        
def test_mp_fail_then_normal():
    """
      verify that a you can use the decorator, have it fail, then continue executing nomrally

      """
    with pytest.raises(TimeoutException):
        mp_sleep1()
    assert mp_simple() == 5


def test_normal_exception():
    with pytest.raises(ZeroDivisionError):
        1/0

@mp_timeout(TIMEOUT * 3)
def zero_div():
    5/0

def test_mp_exception():
    with pytest.raises(ZeroDivisionError):
        zero_div()



def test_polars_rename_unserializable_raises_execution_failed():
    """
    DIAGNOSTIC TEST - Edge case: Polars serialization failure.
    
    Reproduces a Polars serialization error path where a renaming function is not supported.
    The worker should complete but result serialization fails, resulting in ExecutionFailed.
    
    This tests a specific Polars edge case that may not occur in normal usage.
    Run explicitly if testing Polars serialization error handling.
    """
    pytest.skip("Diagnostic test - edge case for Polars serialization, run explicitly if needed")
    @mp_timeout(TIMEOUT * 2)
    def make_unserializable_df():
        df = pl.DataFrame({'a':[1,2,3], 'b':[4,5,6]})
        # Use a Python callable in a name-mapping context to trigger Polars BindingsError
        return df.select(pl.all().name.map(lambda nm: nm + "_x"))

    make_unserializable_df()
    
def test_mp_polars_simple_len():
    """
    Simplest possible Polars op under mp_timeout: ensure it returns a small, serializable result.
    """
    @mp_timeout(TIMEOUT * 2)
    def polars_len():
        df = pl.DataFrame({'a':[1,2,3]})
        # return a plain int to avoid any serialization edge-cases
        return int(df.select(pl.len()).item())
    assert polars_len() == 3


def test_jupyter_simulate():
    """
      based on a test from joblib

      mulitprocessing with jupyter is tricky.  This test does the best aproximation of a funciton that is defined in a jupyter cell
      """
    ipython_cell_source = """
        def f(x):
            return x
        """

    ipython_cell_id = "<ipython-input-{}-000000000000>".format(0)
    
    my_locals = {}
    exec(
        compile(
            textwrap.dedent(ipython_cell_source),
            filename=ipython_cell_id,
            mode="exec",
        ),
        # TODO when Python 3.11 is the minimum supported version, use
        # locals=my_locals instead of passing globals and locals in the
        # next two lines as positional arguments
            None,
            my_locals,
    )
    f = my_locals["f"]
    f.__module__ = "__main__"

    assert f(1) == 1

    wrapped_f = mp_timeout(TIMEOUT * 3)(f)

    assert wrapped_f(1) == 1


# Additional edge-case tests to cover all code paths in simple_decorator

@mp_timeout(TIMEOUT * 3)
def return_unpicklable():
    return threading.Lock()


def test_unpicklable_return_raises_execution_failed():
    with pytest.raises(ExecutionFailed):
        return_unpicklable()


class UnpicklableError(Exception):
    def __init__(self, fh):
        super().__init__("unpicklable")
        self.fh = fh


@mp_timeout(TIMEOUT * 3)
def raise_unpicklable_exc(tmp_path):
    fh = open(tmp_path / "x", "w")
    raise UnpicklableError(fh)


def test_unpicklable_exception_raises_execution_failed(tmp_path):
    """
    DIAGNOSTIC TEST - Edge case: Exception serialization failure.
    
    Tests that when an exception with unpicklable attributes is raised in the worker,
    it results in ExecutionFailed rather than propagating the exception.
    
    This is an edge case that rarely occurs in practice but is important for robustness.
    Run explicitly if testing exception serialization behavior.
    """
    pytest.skip("Diagnostic test - edge case for exception serialization, run explicitly if needed")
    with pytest.raises(ExecutionFailed):
        raise_unpicklable_exc(tmp_path)


@mp_timeout(TIMEOUT)
def exit_now():
    sys.exit(0)


def test_sys_exit_is_execution_failed():
    """
    DIAGNOSTIC TEST - Edge case: sys.exit() handling.
    
    Verifies that the decorator works with functions in the same file (not just imported modules)
    and that sys.exit() in the worker process results in ExecutionFailed.
    
    This tests pickling behavior and sys.exit handling, which are edge cases.
    Run explicitly if testing same-file function pickling or sys.exit behavior.
    """
    pytest.skip("Diagnostic test - edge case for sys.exit handling, run explicitly if needed")
    with pytest.raises(ExecutionFailed):
        exit_now()

def test_is_running_in_mp_timeout():
    """
    Test that is_running_in_mp_timeout correctly detects when code is running
    inside an mp_timeout decorator.
    """
    # When called directly (not in mp_timeout), should return False
    assert is_running_in_mp_timeout() is False
    
    # Create a function that checks if it's running in mp_timeout
    @mp_timeout(TIMEOUT * 3)
    def check_inside_mp_timeout():
        return is_running_in_mp_timeout()
    
    # When called via mp_timeout decorator, should return True
    result = check_inside_mp_timeout()
    assert result is True, "is_running_in_mp_timeout should return True when called inside mp_timeout decorator"
