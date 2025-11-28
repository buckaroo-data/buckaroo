from __future__ import annotations

from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import polars as pl

from .base import (
    Executor as BaseExecutor,
    ColumnExecutor,
    FileCache,
    ProgressNotification,
    ProgressListener,
    SimpleExecutorLog,
)


class ThreadedExecutor(BaseExecutor):
    """
    Minimal threaded Executor that runs column groups concurrently.
    This keeps ColumnExecutor simple; parallelism is handled here.
    """
    def __init__(
        self,
        ldf: pl.LazyFrame,
        column_executor: ColumnExecutor,
        listener: ProgressListener,
        fc: FileCache,
        executor_log: Optional[SimpleExecutorLog] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        super().__init__(ldf, column_executor, listener, fc, executor_log)
        self.max_workers = max_workers

    def run(self) -> None:
        groups = self.get_column_chunks()
        if not groups:
            return
        workers = self.max_workers or min(8, len(groups))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut_to_args: Dict = {}
            for group in groups:
                ex_args = self.get_executor_args(group)
                self.executor_log.log_start_col_group(self.dfi, ex_args)
                fut = pool.submit(self.column_executor.execute, self.ldf, ex_args)
                fut_to_args[fut] = (group, ex_args)

            for fut in as_completed(fut_to_args):
                group, ex_args = fut_to_args[fut]
                try:
                    res = fut.result()
                    for _col, col_result in res.items():
                        self.fc.upsert_key(col_result.series_hash, col_result.result)
                    self.listener(ProgressNotification(
                        success=True,
                        col_group=group,
                        execution_args=[],
                        result=res,
                        execution_time=0,
                        failure_message=None
                    ))
                    self.executor_log.log_end_col_group(self.dfi, ex_args)
                except Exception as e:
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=[],
                        result=None,
                        execution_time=0,
                        failure_message=str(e)
                    ))
                    continue


