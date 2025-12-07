from __future__ import annotations

from datetime import datetime as dtdt
from typing import Optional, Any
import os
import threading
import logging

import polars as pl

from .base import (
    Executor as BaseExecutor,
    ColumnExecutor,
    ExecutorArgs,
    FileCache,
    ProgressNotification,
    ProgressListener,
    SimpleExecutorLog,
    MaybeFilepathLike,
)
from .mp_timeout_decorator import mp_timeout, TimeoutException, ExecutionFailed
from .batch_planning import PlanningFunction, simple_one_column_planning


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
        file_path: MaybeFilepathLike = None,
        timeout_secs: float = 30.0,
        async_mode: bool = True,
        cached_merged_sd: dict[str, dict[str, Any]] | None = None,
        orig_to_rw_map: dict[str, str] | None = None,
        planning_function: Optional[PlanningFunction] = None,
    ) -> None:
        # Use simple_one_column_planning by default for backward compatibility
        # Can be overridden with default_planning_function for batch optimization
        planning_func = planning_function or simple_one_column_planning
        super().__init__(ldf, column_executor, listener, fc, executor_log, file_path=file_path, 
                        cached_merged_sd=cached_merged_sd, orig_to_rw_map=orig_to_rw_map,
                        planning_function=planning_func)
        self.timeout_secs = timeout_secs
        self.async_mode = async_mode
        # Track thread for async mode (for testing utilities)
        self._work_thread: Optional[threading.Thread] = None

    def run(self) -> None:
        logger = logging.getLogger("buckaroo.multiprocessing_executor")
        executor_id = id(self)
        executor_pid = os.getpid()
        log_msg = f"MultiprocessingExecutor.run() START - executor_id={executor_id}, pid={executor_pid}, async_mode={self.async_mode}"
        logger.info(log_msg)
        
        def _work():
            worker_pid = os.getpid()
            worker_thread_id = threading.get_ident()
            log_msg = f"MultiprocessingExecutor._work() START - executor_id={executor_id}, original_pid={executor_pid}, worker_pid={worker_pid}, worker_thread_id={worker_thread_id}"
            logger.info(log_msg)
            
            iteration_count = 0
            # Use get_next_column_chunk() to get batches one at a time
            while True:
                iteration_count += 1
                log_msg_iter = f"MultiprocessingExecutor._work() ITERATION {iteration_count} - executor_id={executor_id}, worker_thread_id={worker_thread_id}, calling get_next_column_chunk()"
                logger.info(log_msg_iter)
                
                group = self.get_next_column_chunk()
                log_msg_group = f"MultiprocessingExecutor._work() got group - executor_id={executor_id}, worker_thread_id={worker_thread_id}, group={group}, iteration={iteration_count}"
                logger.info(log_msg_group)
                
                if group is None:
                    log_msg_done = f"MultiprocessingExecutor._work() DONE - executor_id={executor_id}, worker_thread_id={worker_thread_id}, iterations={iteration_count}, no more groups"
                    logger.info(log_msg_done)
                    break
                log_msg_args = f"MultiprocessingExecutor._work() getting executor args - executor_id={executor_id}, worker_thread_id={worker_thread_id}, group={group}"
                logger.info(log_msg_args)
                
                ex_args = self.get_executor_args(group)
                
                log_msg_args_result = f"MultiprocessingExecutor._work() got executor args - executor_id={executor_id}, worker_thread_id={worker_thread_id}, columns={ex_args.columns}, no_exec={ex_args.no_exec}, expressions_count={len(ex_args.expressions) if ex_args.expressions else 0}"
                logger.info(log_msg_args_result)
                
                # Check if already failed (don't retry)
                if self.executor_log.check_log_for_previous_failure(self.dfi, ex_args):
                    log_msg = f"MultiprocessingExecutor._work() SKIPPING group {group} - previous failure detected"
                    logger.info(log_msg)
                    # DON'T remove columns from remaining - planner needs to retry with smaller batches
                    # The planner will detect the timeout from executor log history and transition to smaller batches
                    continue
                
                # Check if already completed
                original_group_args = ExecutorArgs(
                    columns=list(group),
                    column_specific_expressions=ex_args.column_specific_expressions,
                    include_hash=ex_args.include_hash,
                    expressions=ex_args.expressions,
                    row_start=ex_args.row_start,
                    row_end=ex_args.row_end,
                    extra=ex_args.extra,
                    no_exec=False
                )
                
                if self.executor_log.check_log_for_completed(self.dfi, original_group_args):
                    log_msg = f"MultiprocessingExecutor._work() SKIPPING group {group} - already completed (found in executor log)"
                    logger.info(log_msg)
                    self._update_planning_state_after_execution(list(group))
                    continue
                
                # Check if no_exec (all columns cached via merged_sd)
                if ex_args.no_exec:
                    log_msg = f"MultiprocessingExecutor._work() SKIPPING group {group} - no_exec=True (all columns cached)"
                    logger.info(log_msg)
                    self._update_planning_state_after_execution(list(group))
                    continue
                
                # No columns to execute
                if not ex_args.columns:
                    log_msg = f"MultiprocessingExecutor._work() SKIPPING group {group} - no columns to execute"
                    logger.info(log_msg)
                    self._update_planning_state_after_execution(list(group))
                    continue
                
                log_msg_exec = f"MultiprocessingExecutor._work() EXECUTING group {group} - executor_id={executor_id}, worker_thread_id={worker_thread_id}, columns={ex_args.columns}"
                logger.info(log_msg_exec)
                
                log_msg_dfi = f"MultiprocessingExecutor._work() LOGGING START - dfi={self.dfi}, columns={len(ex_args.columns)}"
                logger.debug(log_msg_dfi)
                self.executor_log.log_start_col_group(self.dfi, ex_args, self.executor_class_name)
                t1 = dtdt.now()
                try:
                    timed_exec = mp_timeout(self.timeout_secs)(_execute_column)
                    log_msg_before_exec = f"MultiprocessingExecutor._work() calling timed_exec - executor_id={executor_id}, worker_thread_id={worker_thread_id}, columns={ex_args.columns}"
                    logger.info(log_msg_before_exec)
                    
                    res = timed_exec(self.column_executor, self.ldf, ex_args)
                    
                    log_msg_after_exec = f"MultiprocessingExecutor._work() timed_exec returned - executor_id={executor_id}, worker_thread_id={worker_thread_id}, result_keys={list(res.keys()) if res else None}"
                    logger.info(log_msg_after_exec)
                    # persist results
                    for _col, col_result in res.items():
                        self.fc.upsert_key(col_result.series_hash, col_result.result)
                    t2 = dtdt.now()

                    listener_id = id(self.listener)
                    log_msg = f"MultiprocessingExecutor._work() CALLING LISTENER - executor_id={executor_id}, worker_pid={worker_pid}, listener_id={listener_id}, col_group={group}, columns_computed={len(res)}"
                    logger.info(log_msg)
                    self.listener(ProgressNotification(
                        success=True,
                        col_group=group,
                        execution_args=ex_args,
                        result=res,
                        execution_time=t2-t1,  # timedelta
                        failure_message=None
                    ))
                    self.executor_log.log_end_col_group(self.dfi, ex_args)
                    # Update planning state after successful execution
                    executed_columns = list(res.keys())
                    self._update_planning_state_after_execution(executed_columns)
                except TimeoutException:
                    t2 = dtdt.now()
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=ex_args,
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message=f"timeout after {self.timeout_secs}s",
                    ))
                    # DON'T remove columns from remaining on timeout - planner needs to retry with smaller batches
                    # The planner will detect the timeout from executor log history and transition to smaller batches
                    continue
                except ExecutionFailed:
                    t2 = dtdt.now()
                    # ExecutionFailed means the worker process exited abnormally (non-zero exit,
                    # crash/SystemExit, or failed to serialize/return a result). Other exceptions
                    # caught below are raised in the parent process during orchestration.
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=ex_args,
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message="execution failed in worker",
                    ))
                    # DON'T remove columns from remaining on ExecutionFailed - planner may retry with smaller batches
                    # For now, remove to prevent infinite loop, but this could be improved
                    self._update_planning_state_after_execution(list(group))
                    continue
                except Exception as e:
                    t2 = dtdt.now()
                    self.listener(ProgressNotification(
                        success=False,
                        col_group=group,
                        execution_args=ex_args,
                        result=None,
                        execution_time=t2-t1,  # timedelta
                        failure_message=str(e),
                    ))
                    # Update planning state to prevent infinite loop
                    self._update_planning_state_after_execution(list(group))
                    continue

        if self.async_mode:
            listener_id = id(self.listener)
            log_msg = f"MultiprocessingExecutor.run() STARTING BACKGROUND THREAD - executor_id={executor_id}, pid={executor_pid}, listener_id={listener_id}, async_mode=True"
            logger.info(log_msg)
            t = threading.Thread(target=_work, daemon=True)
            self._work_thread = t  # Store thread reference for testing utilities
            t.start()
            thread_id = t.ident
            log_msg = f"MultiprocessingExecutor.run() THREAD STARTED - executor_id={executor_id}, thread_id={thread_id}, listener_id={listener_id}, returning immediately (async_mode=True)"
            logger.info(log_msg)
            return
        else:
            _work()


