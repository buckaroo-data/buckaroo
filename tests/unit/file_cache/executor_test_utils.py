import polars as pl
import polars.selectors as cs
import time
from pathlib import Path
from typing import Callable, Union, TYPE_CHECKING

from buckaroo.file_cache.base import (
    ColumnExecutor,
    ExecutorArgs,
    ColumnResults,
    ColumnResult,
    FileCache,
    ProgressNotification,
    Executor,
)

if TYPE_CHECKING:
    from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
    from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow


class SimpleColumnExecutor(ColumnExecutor[ExecutorArgs]):
    def get_execution_args(self, existing_stats:dict[str,dict[str,object]]) -> ExecutorArgs:
        columns = list(existing_stats.keys())
        return ExecutorArgs(
            columns=columns,
            column_specific_expressions=False,
            include_hash=True,
            expressions=[
                cs.numeric().sum().name.suffix("_sum"),
                pl.len().name.suffix("_len"),
            ],
            row_start=None,
            row_end=None,
            extra=None,
        )

    def execute(self, ldf:pl.LazyFrame, execution_args:ExecutorArgs) -> ColumnResults:
        cols = execution_args.columns
        only_cols_ldf = ldf.select(cols)
        res = only_cols_ldf.select(*execution_args.expressions).collect()

        col_results: ColumnResults = {}
        for col in cols:
            # Use a deterministic series_hash for tests without relying on pl_series_hash
            hash_: int = hash(col) & ((1 << 63) - 1)
            actual_result = {"len": res[col+"_len"][0] if col+"_len" in res.columns else 0}
            if col+"_sum" in res.columns:
                actual_result["sum"] = res[col+"_sum"][0]
            cr = ColumnResult(
                series_hash=hash_,
                column_name=col,
                expressions=[],
                result=actual_result,
            )
            col_results[col] = cr
        return col_results


class SlowColumnExecutor(SimpleColumnExecutor):
    def __init__(self, delay_sec: float) -> None:
        super().__init__()
        self.delay_sec = delay_sec
    def execute(self, ldf: pl.LazyFrame, execution_args: ExecutorArgs) -> ColumnResults:
        time.sleep(self.delay_sec)
        return super().execute(ldf, execution_args)


# Helper functions for PAFColumnExecutor tests
def create_listener(collected: list) -> Callable[[ProgressNotification], None]:
    """Create a listener that collects ProgressNotifications."""
    def listener(p: ProgressNotification) -> None:
        collected.append(p)
    return listener


def extract_results(notifications: list) -> dict:
    """Extract results from notifications into a dict keyed by column."""
    results = {}
    for note in notifications:
        if note.success and note.result:
            for col, col_result in note.result.items():
                if col not in results:
                    results[col] = {}
                results[col].update(col_result.result or {})
    return results


def get_cached_merged_sd(fc: FileCache, test_file: Path) -> dict:
    """Get cached merged_sd from file cache."""
    if fc.check_file(test_file):
        md = fc.get_file_metadata(test_file)
        if md and 'merged_sd' in md:
            return md.get('merged_sd', {})
    return {}


def build_existing_cached(fc: FileCache, test_file: Path, columns: list) -> dict:
    """Build existing_cached dict simulating what Executor does."""
    existing_cached = {}
    if fc.check_file(test_file):
        file_hashes = fc.get_file_series_hashes(test_file) or {}
        for col in columns:
            h = file_hashes.get(col)
            if h:
                cached_results = fc.get_series_results(h)
                existing_cached[col] = cached_results or {}
            else:
                existing_cached[col] = {'__missing_hash__': True}
    else:
        for col in columns:
            existing_cached[col] = {'__missing_hash__': True}
    return existing_cached


def has_stat(results: dict, column: str, stat_name: str) -> bool:
    """Check if a specific stat is present in results for a column."""
    return stat_name in results.get(column, {})


def assert_stats_present(results: dict, column: str, expected: list, unexpected: list = None) -> None:
    """Assert that expected stats are present and unexpected are not."""
    for stat in expected:
        assert has_stat(results, column, stat), f"{stat} missing for {column}"
    if unexpected:
        for stat in unexpected:
            assert not has_stat(results, column, stat), f"{stat} should not be present for {column}"


def wait_for_executor_finish(
    executor: Executor,
    timeout_secs: float = 30.0,
    check_interval_secs: float = 0.1,
) -> None:
    """
    Wait for an executor to finish running.
    
    Args:
        executor: The executor instance to wait for
        timeout_secs: Maximum time to wait in seconds (default: 30.0)
        check_interval_secs: How often to check if executor is done (default: 0.1)
    
    Raises:
        AssertionError: If run() has not been called on the executor
        TimeoutError: If executor doesn't finish within timeout
    """
    if not executor.has_run_been_called:
        raise AssertionError("Executor.run() has not been called yet - reconfigure your test")
    
    # For sync executors, run() blocks until complete, so if it's been called, we're done
    # For async executors (MultiprocessingExecutor with async_mode=True), check thread status
    from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor
    
    if isinstance(executor, MultiprocessingExecutor) and executor.async_mode:
        if executor._work_thread is None:
            raise AssertionError(
                "MultiprocessingExecutor with async_mode=True has run() called but _work_thread is None. "
                "This indicates the executor's run() method did not start the background thread as expected."
            )
        
        # Wait for thread to complete
        start_time = time.time()
        while executor._work_thread.is_alive():
            if time.time() - start_time > timeout_secs:
                raise TimeoutError(
                    f"Executor did not finish within {timeout_secs} seconds"
                )
            time.sleep(check_interval_secs)
        return
    
    # For sync executors, if run() has been called, execution is complete
    # (run() blocks until done)
    return


def wait_for_nested_executor_finish(
    obj: Union["LazyInfinitePolarsBuckarooWidget", "ColumnExecutorDataflow", Executor],
    timeout_secs: float = 30.0,
    check_interval_secs: float = 0.1,
) -> None:
    """
    Convenience function to wait for executor to finish from various object types.
    
    Args:
        obj: Can be:
            - LazyInfinitePolarsBuckarooWidget: waits for computation to appear complete
            - ColumnExecutorDataflow: waits for computation to appear complete
            - Executor: directly waits for executor to finish
        timeout_secs: Maximum time to wait in seconds (default: 30.0)
        check_interval_secs: How often to check if executor is done (default: 0.1)
    
    Note:
        For widgets/dataflows, this checks if merged_sd has content as a proxy
        for completion. For direct executor access, use wait_for_executor_finish.
    """
    # If it's an executor, use the direct function
    if isinstance(obj, Executor):
        return wait_for_executor_finish(obj, timeout_secs, check_interval_secs)
    
    # For widgets and dataflows, we can't access the executor directly
    # So we wait for computation to appear complete by checking merged_sd
    from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
    from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
    
    if isinstance(obj, LazyInfinitePolarsBuckarooWidget):
        # Wait for merged_sd to have expected number of columns
        expected_cols = obj.df_meta.get('columns', 0)
        start_time = time.time()
        
        while True:
            merged_sd = getattr(obj._df, 'merged_sd', {}) or {}
            if expected_cols == 0 or len(merged_sd) >= expected_cols:
                # Check if we have at least some content (not just defaults)
                if len(merged_sd) > 0:
                    # Verify at least one column has real stats (not just basic keys)
                    for col_stats in merged_sd.values():
                        if isinstance(col_stats, dict):
                            keys = set(col_stats.keys())
                            basic_keys = {'orig_col_name', 'rewritten_col_name'}
                            if keys > basic_keys:
                                return  # Found real stats, computation likely complete
            
            if time.time() - start_time > timeout_secs:
                raise TimeoutError(
                    f"Widget computation did not appear complete within {timeout_secs} seconds. "
                    f"Expected {expected_cols} columns, got {len(merged_sd)}"
                )
            time.sleep(check_interval_secs)
    
    elif isinstance(obj, ColumnExecutorDataflow):
        # Similar logic for dataflow
        expected_cols = obj.df_meta.get('columns', 0)
        start_time = time.time()
        
        while True:
            merged_sd = getattr(obj, 'merged_sd', {}) or {}
            if expected_cols == 0 or len(merged_sd) >= expected_cols:
                # Check if we have at least some content
                if len(merged_sd) > 0:
                    for col_stats in merged_sd.values():
                        if isinstance(col_stats, dict):
                            keys = set(col_stats.keys())
                            basic_keys = {'orig_col_name', 'rewritten_col_name'}
                            if keys > basic_keys:
                                return
            
            if time.time() - start_time > timeout_secs:
                raise TimeoutError(
                    f"Dataflow computation did not appear complete within {timeout_secs} seconds. "
                    f"Expected {expected_cols} columns, got {len(merged_sd)}"
                )
            time.sleep(check_interval_secs)
    
    else:
        raise TypeError(
            f"Object type {type(obj)} not supported. "
            f"Expected LazyInfinitePolarsBuckarooWidget, ColumnExecutorDataflow, or Executor"
        )

