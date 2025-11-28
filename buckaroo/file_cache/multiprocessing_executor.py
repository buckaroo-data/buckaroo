from __future__ import annotations

from datetime import datetime as dtdt
from typing import Optional, Dict
import threading
import time

import polars as pl

from .base import (
    Executor as BaseExecutor,
    ColumnExecutor,
    FileCache,
    ProgressNotification,
    ProgressListener,
    SimpleExecutorLog,
)
from .mp_timeout_decorator import mp_timeout, TimeoutException, ExecutionFailed


def _execute_column(column_executor: ColumnExecutor, ldf: pl.LazyFrame, ex_args):
    return column_executor.execute(ldf, ex_args)


class MultiprocessingExecutor(BaseExecutor):
    """
    Executor that runs each column group in a separate process with a timeout.
    Uses mp_timeout (cloudpickle + multiprocessing) to isolate crashes and cap runtime.
    """
    def __init__(
        self,
        ldf: pl.LazyFrame,
        column_executor: ColumnExecutor,
        listener: ProgressListener,
        fc: FileCache,
        executor_log: Optional[SimpleExecutorLog] = None,
        timeout_secs: float = 30.0,
        async_mode: bool = True,
    ) -> None:
        super().__init__(ldf, column_executor, listener, fc, executor_log)
        self.timeout_secs = timeout_secs
        self.async_mode = async_mode

    def run(self) -> None:
        def _work():
            groups = self.get_column_chunks()
            if not groups:
                return
            for group in groups:
                ex_args = self.get_executor_args(group)
                if self.executor_log.check_log_for_previous_failure(self.dfi, ex_args):
                    return
                self.executor_log.log_start_col_group(self.dfi, ex_args, self.executor_class_name)
                t1 = dtdt.now()
                try:
                    timed_exec = mp_timeout(self.timeout_secs)(_execute_column)
                    res = timed_exec(self.column_executor, self.ldf, ex_args)
                    # persist results
                    for _col, col_result in res.items():
                        self.fc.upsert_key(col_result.series_hash, col_result.result)
                    t2 = dtdt.now()

                    self.listener(ProgressNotification(
                        success=True,
                        col_group=group,
                        execution_args=[],
                        result=res,
                        execution_time=t2-t1,  # timedelta
                        failure_message=None
                    ))
                    self.executor_log.log_end_col_group(self.dfi, ex_args)
                except TimeoutException as e:
                    t2 = dtdt.now()
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=[],
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message=f"timeout after {self.timeout_secs}s",
                    ))
                    continue
                except ExecutionFailed as e:
                    t2 = dtdt.now()
                    # ExecutionFailed means the worker process exited abnormally (non-zero exit,
                    # crash/SystemExit, or failed to serialize/return a result). Other exceptions
                    # caught below are raised in the parent process during orchestration.
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=[],
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message="execution failed in worker",
                    ))
                    continue
                except Exception as e:
                    t2 = dtdt.now()
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=[],
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message=str(e),
                    ))
                    continue

        if self.async_mode:
            t = threading.Thread(target=_work, daemon=True)
            t.start()
            return
        else:
            _work()


