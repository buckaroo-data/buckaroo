import socket
import sys
import ctypes
import time
from buckaroo.file_cache.mp_timeout_decorator import mp_timeout

"""
multiprocessing  an behave differently when a function is defined in an imported module vs defined in the smae module or in an interpreter.

  This module provides examples of functions that are defined in a module
  """


LOCAL_TIMEOUT = 1
CI_TIMEOUT = 5


IS_RUNNING_LOCAL = "Paddy" in socket.gethostname()
#print(socket.gethostname())
TIMEOUT = LOCAL_TIMEOUT if IS_RUNNING_LOCAL else CI_TIMEOUT



@mp_timeout(TIMEOUT)
def mp_polars_longread(i=0):
    # Simulate a long-running polars operation that will timeout
    # Sleep for longer than TIMEOUT to ensure it times out
    time.sleep(TIMEOUT * 1.5)
    return 5


@mp_timeout(TIMEOUT)
def mp_simple():
    return 5


@mp_timeout(TIMEOUT)
def mp_sleep1():
    time.sleep(TIMEOUT*3)
    return 5


@mp_timeout(TIMEOUT * 3)
def mp_crash_exit():
    # intentionally crash the process
    ctypes.string_at(0)


@mp_timeout(TIMEOUT)
def mp_sys_exit():
    sys.exit()


@mp_timeout(TIMEOUT * 3)
def mp_polars_crash():
    try:
        import polars as pl  # type: ignore
        from pl_series_hash import crash  # type: ignore
        df_1 = pl.DataFrame({"u64": pl.Series([5, 3, 20], dtype=pl.UInt64)})
        df_1.select(hash_col=crash("u64"))
    except Exception:
        raise
