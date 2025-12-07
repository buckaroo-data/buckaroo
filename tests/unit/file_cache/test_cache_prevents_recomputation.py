"""
Test that cache prevents recomputation on re-execution.
"""
# state:READONLY

import polars as pl
from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.file_cache.cache_utils import get_global_file_cache, clear_file_cache
from buckaroo.read_utils import read_df
from buckaroo.file_cache.base import Executor
import os
# Reset global instances to use temp directory
import buckaroo.file_cache.cache_utils as cache_utils_module
from tests.unit.file_cache.executor_test_utils import wait_for_nested_executor_finish

def test_cache_prevents_recomputation_on_second_execution(tmp_path):
    """Test that when a file is cached, second execution doesn't recompute stats."""
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test file
        test_file = tmp_path / "test.csv"
        df = pl.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        df.write_csv(test_file)
        
        # Track if executor.run was called and if execution actually happened
        executor_run_calls = []
        executor_execute_calls = []
        original_run = Executor.run
        
        def tracked_run(self):
            executor_run_calls.append('run')
            # Track if column_executor.execute is called (actual computation)
            original_execute = self.column_executor.execute
            def tracked_execute(ldf, ex_args):
                executor_execute_calls.append(('execute', ex_args.columns))
                return original_execute(ldf, ex_args)
            self.column_executor.execute = tracked_execute
            try:
                return original_run(self)
            finally:
                self.column_executor.execute = original_execute
        
        Executor.run = tracked_run
        
        try:
            # First execution - should compute
            clear_file_cache()
            ldf1 = read_df(str(test_file))
            w1 = LazyInfinitePolarsBuckarooWidget(
                ldf1,
                file_path=str(test_file),
                sync_executor_class=Executor,
                parallel_executor_class=Executor
            )
            
            # Wait for computation to complete (sync executor is blocking)
            wait_for_nested_executor_finish(w1, timeout_secs=5.0)
            
            first_run_calls = len(executor_run_calls)
            first_execute_calls = len(executor_execute_calls)
            print(f"First run - executor.run called {first_run_calls} times, execute called {first_execute_calls} times")
            assert first_run_calls  == 1, "Executor.run should have been called on first run"
            # With 2 columns, we get 2 execute calls (one per column group)
            assert first_execute_calls == 2, f"Executor should have executed computation for 2 columns, got {first_execute_calls}"
            
            # Verify stats were computed (2 columns = 2 entries in merged_sd)
            assert len(w1._df.merged_sd) == 2, f"Stats should be computed for 2 columns on first run, got {len(w1._df.merged_sd)}"
            
            # Verify cache was populated
            fc = get_global_file_cache()
            assert fc.check_file(test_file), "File should be in cache after first run"
            md = fc.get_file_metadata(test_file)
            assert md is not None and 'merged_sd' in md, "merged_sd should be in cache"
            
            # Reset executor call counters
            executor_run_calls.clear()
            executor_execute_calls.clear()
            
            # Second execution - should use cache, NOT recompute
            ldf2 = read_df(str(test_file))
            w2 = LazyInfinitePolarsBuckarooWidget(
                ldf2,
                file_path=str(test_file),
                sync_executor_class=Executor,
                parallel_executor_class=Executor
            )
            
            # Wait for initialization (sync executor is blocking)
            wait_for_nested_executor_finish(w2, timeout_secs=5.0)
            
            second_run_calls = len(executor_run_calls)
            second_execute_calls = len(executor_execute_calls)
            print(f"Second run - executor.run called {second_run_calls} times, execute called {second_execute_calls} times")
            
            # Executor.run() may be called but should return early without executing
            # The important thing is that execute() should NOT be called (no actual computation)
            assert second_execute_calls == 0, f"Executor should NOT execute computation on second run (cache should be used), but execute was called {second_execute_calls} times: {executor_execute_calls}"
            
            # Verify stats are still available (from cache)
            assert len(w2._df.merged_sd) > 0, "Stats should be available from cache on second run"
            
        finally:
            # Restore original run method
            Executor.run = original_run
    finally:
        # Reset global instances
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home
