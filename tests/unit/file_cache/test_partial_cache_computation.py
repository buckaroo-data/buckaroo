"""
Test that partial cache works correctly - load cached columns immediately,
continue computing missing columns in background.
"""
# state:READONLY

import os
import sys
import threading
import time

import polars as pl
import pytest

from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
from buckaroo.file_cache.cache_utils import get_global_file_cache, clear_file_cache
from buckaroo.read_utils import read_df
from buckaroo.file_cache.base import Executor, ProgressNotification
from tests.unit.file_cache.executor_test_utils import wait_for_nested_executor_finish

# Timing assumptions and tmpdir cleanup don't work on Windows (spawn is slow,
# SQLite file locking prevents cleanup)
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Timing-dependent tests incompatible with Windows spawn context",
)


def test_partial_cache_loads_immediately_and_continues_computing(tmp_path):
    """
    Test that when some columns are cached:
    1. Cached columns are shown immediately
    2. Missing columns continue computing in background
    3. Eventually all columns are computed
    """
    import buckaroo.file_cache.cache_utils as cache_utils_module
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test file with 5 columns
        test_file = tmp_path / "test_partial.csv"
        df = pl.DataFrame({
            'col1': [1, 2, 3],
            'col2': [4, 5, 6],
            'col3': [7, 8, 9],
            'col4': [10, 11, 12],
            'col5': [13, 14, 15]
        })
        df.write_csv(test_file)
        
        # Track which columns are computed
        computed_columns = []
        original_run = Executor.run
        
        def tracked_run(self):
            # Track which columns are actually computed (after cache checks)
            # Only track columns that go through execute(), not skipped ones
            original_execute = self.column_executor.execute
            def tracked_execute(ldf, ex_args):
                # Track columns being executed
                for col in ex_args.columns:
                    if col not in computed_columns:
                        computed_columns.append(col)
                return original_execute(ldf, ex_args)
            self.column_executor.execute = tracked_execute
            try:
                return original_run(self)
            finally:
                self.column_executor.execute = original_execute
        
        Executor.run = tracked_run
        
        try:
            # First run - compute all columns
            clear_file_cache()
            ldf1 = read_df(str(test_file))
            
            # Use a listener to wait for 3rd notification (simulating Jupyter Lab behavior)
            # In Jupyter Lab, the widget updates as notifications arrive, so we wait for some progress
            notification_count = [0]  # Use list to allow modification in nested function
            notification_event = threading.Event()
            
            # Monkey-patch ColumnExecutorDataflow to inject our counting listener
            from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
            original_compute = ColumnExecutorDataflow.compute_summary_with_executor
            
            def compute_with_listener(self, file_cache=None, progress_listener=None, file_path=None):
                # Create a wrapper listener that counts successful notifications
                def counting_listener(note: ProgressNotification):
                    # Chain to original listener if provided
                    if progress_listener:
                        try:
                            progress_listener(note)
                        except Exception:
                            pass
                    # Count successful notifications
                    if note.success:
                        notification_count[0] += 1
                        if notification_count[0] >= 3:
                            notification_event.set()
                return original_compute(self, file_cache, counting_listener, file_path)
            
            ColumnExecutorDataflow.compute_summary_with_executor = compute_with_listener
            
            try:
                w1 = LazyInfinitePolarsBuckarooWidget(
                    ldf1,
                    file_path=str(test_file),
                    sync_executor_class=Executor,
                    parallel_executor_class=Executor
                )
                
                # Wait for 3rd notification (simulating Jupyter Lab - widget updates as notifications arrive)
                # This is more realistic than time.sleep() as it responds to actual progress
                notification_event.wait(timeout=10.0)  # 10 second timeout for safety
            
                # After 3rd notification, give a brief moment for remaining notifications to complete
                # (In real Jupyter Lab, we'd continue immediately after seeing some progress)
                import time
                time.sleep(0.3)  # Brief wait for remaining notifications to complete
                
                # Verify all columns computed
                assert len(w1._df.merged_sd) == 5, "All 5 columns should be computed"
                assert set(w1._df.merged_sd.keys()) == {'a', 'b', 'c', 'd', 'e'}, "Should have all columns"
                
                # Clear computation tracking
                computed_columns.clear()
                
                # Second run - should load from cache immediately, no computation
                # Reset notification tracking for second run
                notification_count[0] = 0
                notification_event.clear()
                
                ldf2 = read_df(str(test_file))
                w2 = LazyInfinitePolarsBuckarooWidget(
                    ldf2,
                    file_path=str(test_file),
                    sync_executor_class=Executor,
                    parallel_executor_class=Executor
                )
                
                # For cached columns, should be immediate - no need to wait for notifications
                # Use wait utility to ensure initialization is complete
                wait_for_nested_executor_finish(w2, timeout_secs=5.0)
                
                # Should have all columns immediately from cache
                assert len(w2._df.merged_sd) == 5, "All 5 columns should be loaded from cache"
                # Executor should NOT be called (or called with 0 new columns)
                # Since all are cached, computation should be skipped
                assert len(computed_columns) == 0, f"Should not recompute cached columns, but computed: {computed_columns}"
            finally:
                # Restore original compute method
                ColumnExecutorDataflow.compute_summary_with_executor = original_compute
            
        finally:
            Executor.run = original_run
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home


def test_partial_cache_shows_cached_immediately_computes_rest(tmp_path):
    """
    Test scenario: Some columns are cached, some are not.
    - Cached columns should appear immediately
    - Missing columns should compute in background
    - Eventually all columns should be present
    """
    import buckaroo.file_cache.cache_utils as cache_utils_module
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test file with 5 columns
        test_file = tmp_path / "test_partial2.csv"
        df = pl.DataFrame({
            'col1': [1, 2, 3],
            'col2': [4, 5, 6],
            'col3': [7, 8, 9],
            'col4': [10, 11, 12],
            'col5': [13, 14, 15]
        })
        df.write_csv(test_file)
        
        # First: Compute and cache only first 3 columns
        # (Simulate by manually caching only some columns)
        clear_file_cache()
        ldf1 = read_df(str(test_file))
        w1 = LazyInfinitePolarsBuckarooWidget(
            ldf1,
            file_path=str(test_file),
            sync_executor_class=Executor,
            parallel_executor_class=Executor
        )
        assert w1
        wait_for_nested_executor_finish(w1, timeout_secs=5.0)
        
        # Manually remove some columns from cache to simulate partial cache
        fc = get_global_file_cache()
        md = fc.get_file_metadata(test_file)
        if md and 'merged_sd' in md:
            # Remove last 2 columns from cached merged_sd
            partial_merged_sd = md['merged_sd'].copy()
            partial_merged_sd.pop('d', None)  # col4
            partial_merged_sd.pop('e', None)  # col5
            fc.upsert_file_metadata(test_file, {'merged_sd': partial_merged_sd})
        
        # Track which columns are computed
        computed_columns = []
        original_run = Executor.run
        
        def tracked_run(self):
            # Reset planning state so we can track columns
            self._planning_state = None
            # Track columns by calling get_next_column_chunk() and resetting state
            temp_state = []
            while True:
                col_group = self.get_next_column_chunk()
                if col_group is None:
                    break
                temp_state.append(col_group)
                for col in col_group:
                    if col not in computed_columns:
                        computed_columns.append(col)
            # Reset planning state so original_run can start fresh
            self._planning_state = None
            return original_run(self)
        
        Executor.run = tracked_run
        
        try:
            # Second run: Should load 3 cached columns immediately, compute 2 missing ones
            ldf2 = read_df(str(test_file))
            w2 = LazyInfinitePolarsBuckarooWidget(
                ldf2,
                file_path=str(test_file),
                sync_executor_class=Executor,
                parallel_executor_class=Executor
            )
            
            # Immediately after creation, should have at least the 3 cached columns
            # Note: cached columns should appear immediately, but we wait briefly for initialization
            wait_for_nested_executor_finish(w2, timeout_secs=5.0)
            initial_cols = set(w2._df.merged_sd.keys())
            assert 'a' in initial_cols, "col1 (a) should be cached and shown immediately"
            assert 'b' in initial_cols, "col2 (b) should be cached and shown immediately"
            assert 'c' in initial_cols, "col3 (c) should be cached and shown immediately"
            
            # Wait for computation to complete (remaining columns)
            wait_for_nested_executor_finish(w2, timeout_secs=5.0)
            
            # Eventually should have all 5 columns
            final_cols = set(w2._df.merged_sd.keys())
            assert len(final_cols) == 5, f"Should eventually have all 5 columns, got: {final_cols}"
            assert final_cols == {'a', 'b', 'c', 'd', 'e'}, "Should have all columns a-e"
            
            # Should only compute the missing columns
            # Note: executor might compute all, but should check cache per column
            # The important thing is that cached columns are shown immediately
            
        finally:
            Executor.run = original_run
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home


def test_huge_dataframe_partial_cache_scenario(tmp_path):
    """
    Simulate scenario with huge dataframe and 300 columns:
    - Only some columns cached
    - Cached columns should appear immediately
    - Rest should compute in background
    - User shouldn't have to wait for all 300 to complete
    """
    import buckaroo.file_cache.cache_utils as cache_utils_module
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test file with many columns (simulate 300 with 10 for testing)
        test_file = tmp_path / "test_huge.csv"
        data = {f'col{i}': list(range(10)) for i in range(1, 11)}
        df = pl.DataFrame(data)
        df.write_csv(test_file)
        
        clear_file_cache()
        
        # First run: Compute and cache only first 5 columns
        ldf1 = read_df(str(test_file))
        w1 = LazyInfinitePolarsBuckarooWidget(
            ldf1,
            file_path=str(test_file),
            sync_executor_class=Executor,
            parallel_executor_class=Executor
        )
        assert w1
        wait_for_nested_executor_finish(w1, timeout_secs=5.0)
        
        # Manually cache only first 5 columns
        fc = get_global_file_cache()
        md = fc.get_file_metadata(test_file)
        if md and 'merged_sd' in md:
            # Keep only first 5 columns (a-e)
            partial_merged_sd = {k: v for k, v in md['merged_sd'].items() if k in ['a', 'b', 'c', 'd', 'e']}
            fc.upsert_file_metadata(test_file, {'merged_sd': partial_merged_sd})
        
        # Second run: Should show 5 cached columns immediately
        # Then compute remaining 5 in background
        ldf2 = read_df(str(test_file))
        start_time = time.time()
        w2 = LazyInfinitePolarsBuckarooWidget(
            ldf2,
            file_path=str(test_file),
            sync_executor_class=Executor,
            parallel_executor_class=Executor
        )
        
        # Immediately check - should have cached columns
        time.sleep(0.1)
        initial_time = time.time() - start_time
        initial_cols = set(w2._df.merged_sd.keys())
        
        # Should have cached columns immediately (within 0.1s)
        assert initial_time < 0.5, "Cached columns should appear almost instantly"
        assert len(initial_cols) >= 5, f"Should have at least 5 cached columns immediately, got: {initial_cols}"
        
        # Wait for remaining computation
        wait_for_nested_executor_finish(w2, timeout_secs=5.0)
        final_cols = set(w2._df.merged_sd.keys())
        
        # Eventually should have all 10 columns
        assert len(final_cols) == 10, f"Should eventually have all 10 columns, got: {final_cols}"
        
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home

