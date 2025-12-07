from __future__ import annotations

from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import polars as pl

from .base import (
    Executor as BaseExecutor,
    ColumnExecutor,
    ColumnGroup,
    FileCache,
    ProgressNotification,
    ProgressListener,
    SimpleExecutorLog,
    MaybeFilepathLike,
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
        file_path: MaybeFilepathLike = None,
        max_workers: Optional[int] = None,
        cached_merged_sd: dict[str, dict[str, Any]] | None = None,
        orig_to_rw_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__(ldf, column_executor, listener, fc, executor_log, file_path=file_path, cached_merged_sd=cached_merged_sd, orig_to_rw_map=orig_to_rw_map)
        self.max_workers = max_workers

    def run(self) -> None:
        # Collect all column groups first (threaded executor needs them all upfront)
        # Use a set to avoid duplicates in case of planning issues
        seen_groups: set[tuple[str, ...]] = set()
        groups: list[ColumnGroup] = []
        max_iterations = 1000  # Safety limit to prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            group = self.get_next_column_chunk()
            if group is None:
                break
            # Avoid duplicates
            group_key = tuple(sorted(group))
            if group_key in seen_groups:
                # Planning returned duplicate - update state and break to avoid infinite loop
                self._update_planning_state_after_execution(list(group))
                break
            seen_groups.add(group_key)
            groups.append(group)
        
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
                        execution_args=ex_args,
                        result=res,
                        execution_time=0,
                        failure_message=None
                    ))
                    self.executor_log.log_end_col_group(self.dfi, ex_args)
                except Exception as e:
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=ex_args,
                        result=None,
                        execution_time=0,
                        failure_message=str(e)
                    ))
                    continue


