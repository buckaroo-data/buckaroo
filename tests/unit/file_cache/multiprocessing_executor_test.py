import sys

import polars as pl
import pytest
import time

from buckaroo.file_cache.base import FileCache, ProgressNotification
from buckaroo.file_cache.multiprocessing_executor import MultiprocessingExecutor
from buckaroo.file_cache.batch_planning import default_planning_function
from .executor_test_utils import SimpleColumnExecutor, SlowColumnExecutor


def test_multiprocessing_executor_success():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10,20,30]})
    ldf = df.lazy()
    fc = FileCache()
    notes: list[ProgressNotification] = []
    def listener(p: ProgressNotification):
        notes.append(p)
    #FIXME this should be able to work without async_mode=False, but it doesn't .  maybe there is a pytest config
    exc = MultiprocessingExecutor(ldf, SimpleColumnExecutor(), listener, fc, timeout_secs=5.0, async_mode=False)
    exc.run()
    # one notification per column
    assert len(notes) == len(df.columns)
    assert all(n.success for n in notes)
    # cache populated for each col (cannot assert exact keys)
    assert len(fc.summary_stats_cache.keys()) >= len(df.columns)


def test_multiprocessing_executor_with_default_planning_function_processes_columns():
    """
    Test that MultiprocessingExecutor with default_planning_function actually processes columns.
    
    This test captures a bug where default_planning_function returns an empty batch
    for baseline measurement, but the executor skips empty batches, causing it to
    never process any actual columns.
    
    Expected behavior:
    - Executor should handle empty baseline batch and then process actual columns
    - All columns should eventually be processed
    - Listener should receive notifications for all columns
    - Cache should be populated with summary stats
    """
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10,20,30], 'c3': [100,200,300]})
    ldf = df.lazy()
    fc = FileCache()
    notes: list[ProgressNotification] = []
    
    def listener(p: ProgressNotification):
        notes.append(p)
    
    # Use default_planning_function (smart planner) which returns empty batch for baseline
    exc = MultiprocessingExecutor(
        ldf, 
        SimpleColumnExecutor(), 
        listener, 
        fc, 
        timeout_secs=5.0, 
        async_mode=False,  # Use sync mode for test determinism
        planning_function=default_planning_function  # This is the key - uses smart planner
    )
    exc.run()
    
    # The bug: executor skips empty baseline batch, so it never processes columns
    # Expected: all 3 columns should be processed
    # Actual (with bug): 0 columns processed because baseline batch is skipped
    
    # More generic check: After allowing time for processing, verify summary_stats_cache has entries
    # This is a time-based assertion that should pass even if execution is async or delayed
    time.sleep(3.0)
    assert len(fc.summary_stats_cache.keys()) > 0, (
        f"Expected summary_stats_cache to have at least 1 entry after 3 seconds, "
        f"but got {len(fc.summary_stats_cache.keys())}. This indicates columns are not being "
        f"processed and cached, likely because the executor is skipping the empty baseline batch."
    )
    
    # Verify we got notifications (may be fewer than columns due to batching)
    assert len(notes) > 0, (
        f"Expected at least 1 notification, but got {len(notes)}. This indicates the executor "
        f"is not processing columns because it's skipping the empty baseline batch from "
        f"default_planning_function."
    )
    
    # Verify all notifications are successful
    successful_notes = [n for n in notes if n.success and n.result]
    assert len(successful_notes) > 0, (
        f"Expected at least 1 successful notification, but got {len(successful_notes)}. "
        f"Total notes: {len(notes)}"
    )
    
    # Verify all columns were processed by checking result keys across all notifications
    processed_columns = set()
    for note in successful_notes:
        if note.result:
            processed_columns.update(note.result.keys())
    
    assert len(processed_columns) == len(df.columns), (
        f"Expected all {len(df.columns)} columns to be processed, but only got "
        f"{len(processed_columns)}: {processed_columns}. Expected: {set(df.columns)}"
    )
    
    # Verify cache is populated with expected number of entries
    assert len(fc.summary_stats_cache.keys()) >= len(df.columns), (
        f"Expected cache to have at least {len(df.columns)} entries, "
        f"but got {len(fc.summary_stats_cache.keys())}"
    )
    
    # More generic check: After allowing time for processing, verify summary_stats_cache has entries
    # This is a time-based assertion that should pass even if execution is async
    time.sleep(3.0)
    assert len(fc.summary_stats_cache.keys()) > 0, (
        f"Expected summary_stats_cache to have at least 1 entry after 3 seconds, "
        f"but got {len(fc.summary_stats_cache.keys())}. This indicates columns are not being "
        f"processed and cached, likely because the executor is skipping the empty baseline batch."
    )
    
    # More generic check: After a reasonable wait time, summary_stats should be populated
    # This catches cases where execution might be delayed or async
    start_time = time.time()
    max_wait = 3.0
    while time.time() - start_time < max_wait:
        if len(fc.summary_stats_cache.keys()) > 0:
            break
        time.sleep(0.1)
    
    assert len(fc.summary_stats_cache.keys()) > 0, (
        f"Expected summary_stats_cache to be populated after {max_wait} seconds, "
        f"but got {len(fc.summary_stats_cache.keys())} entries. "
        f"This indicates the executor is not processing columns or not caching results."
    )


def test_multiprocessing_executor_timeout():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10,20,30]})
    ldf = df.lazy()
    fc = FileCache()
    notes: list[ProgressNotification] = []
    def listener(p: ProgressNotification):
        notes.append(p)

    # Make each column execute longer than the timeout
    #FIXME we should have a test that exercises async_mode=True verifying that the right callbacks are called 
    exc = MultiprocessingExecutor(ldf, SlowColumnExecutor(2.5), listener, fc, timeout_secs=2.0, async_mode=False)
    exc.run()
    # With the new planning system and infinite loop detection:
    # - When a column times out repeatedly, it may be retried multiple times
    # - If it keeps timing out, infinite loop detection will remove it
    # - So we might get multiple notifications for the same column before it's removed
    # - We should get at least one timeout notification
    assert len(notes) > 0, "Expected at least one timeout notification"
    assert all((not n.success) for n in notes), "All notifications should be failures"
    assert all("timeout" in (n.failure_message or "").lower() for n in notes), "All failures should be timeouts"
    
    # Verify that at least one column was attempted (may be fewer than all columns
    # if infinite loop detection removes them)
    attempted_columns = set()
    for note in notes:
        if note.col_group:
            attempted_columns.update(note.col_group)
    assert len(attempted_columns) > 0, (
        f"Expected at least one column to be attempted, "
        f"but got {len(attempted_columns)}: {attempted_columns}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="multiprocessing spawn + SQLite file locking unreliable on Windows")
def test_multiprocessing_executor_skips_cached_columns(tmp_path):
    """
    Test that MultiprocessingExecutor skips already-computed columns on re-execution.
    
    This verifies the behavior shown in logs where all column groups are skipped
    with "SKIPPING group [...] - no_exec=True (all columns cached)" on re-execution.
    """
    import os
    from buckaroo.file_cache.cache_utils import clear_file_cache
    from buckaroo.file_cache.sqlite_file_cache import SQLiteFileCache
    from buckaroo.file_cache.sqlite_log import SQLiteExecutorLog
    
    # Reset global instances to use temp directory
    import buckaroo.file_cache.cache_utils as cache_utils_module
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test file
        test_file = tmp_path / "test.csv"
        df = pl.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        df.write_csv(test_file)
        
        # Use SQLite cache and log (matching production)
        fc = SQLiteFileCache(str(tmp_path / "file_cache.sqlite"))
        executor_log = SQLiteExecutorLog(str(tmp_path / "executor_log.sqlite"))
        
        cache_utils_module._file_cache = fc
        cache_utils_module._executor_log = executor_log
        
        clear_file_cache()
        
        ldf = df.lazy()
        
        notes: list[ProgressNotification] = []
        def listener(p: ProgressNotification):
            notes.append(p)
        
        # First execution - should compute and send notifications
        column_executor = SimpleColumnExecutor()
        exc1 = MultiprocessingExecutor(
            ldf, column_executor, listener, fc,
            executor_log=executor_log,
            file_path=test_file,
            timeout_secs=5.0,
            async_mode=False
        )
        exc1.run()
        
        # First execution should send notifications for both columns
        assert len(notes) == 2, f"First execution should send 2 notifications, got {len(notes)}"
        assert all(n.success for n in notes), "All notifications should be successful"
        
        # Verify series results are in cache (executor caches by series hash)
        # We can't easily check file_cache directly, but we know results were cached
        # because they were upserted during execution
        
        # Reset for second execution
        notes.clear()
        
        # Second execution - should skip all columns (no_exec=True)
        column_executor2 = SimpleColumnExecutor()
        
        notes2: list[ProgressNotification] = []
        def listener2(p: ProgressNotification):
            notes2.append(p)
        
        exc2 = MultiprocessingExecutor(
            ldf, column_executor2, listener2, fc,
            executor_log=executor_log,
            file_path=test_file,
            timeout_secs=5.0,
            async_mode=False
        )
        exc2.run()
        
        # Second execution should NOT send notifications (columns are cached and skipped)
        # The executor should skip execution entirely when all columns are cached
        assert len(notes2) == 0, (
            f"Second execution should skip all columns (no_exec=True), "
            f"but got {len(notes2)} notifications: {notes2}"
        )
        
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home


            
