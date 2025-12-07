import os
import polars as pl
from polars import functions as F

import buckaroo.file_cache.cache_utils as cache_utils_module
from buckaroo.file_cache.base import Executor, FileCache, ProgressNotification
from buckaroo.file_cache.cache_utils import clear_file_cache, get_global_file_cache
from buckaroo.dataflow.styling_core import merge_sds
from buckaroo.file_cache.paf_column_executor import PAFColumnExecutor
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.utils import json_postfix
from buckaroo.file_cache.batch_planning import simple_one_column_planning
from tests.unit.file_cache.executor_test_utils import (
    build_existing_cached,
    create_listener,
    extract_results,
    get_cached_merged_sd,
    assert_stats_present
)

class SelectOnlyAnalysis(PolarsAnalysis):
    provides_defaults = {'null_count':0}
    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
    ]


def test_paf_column_executor_basic():
    df = pl.DataFrame({'a1': [1,2,3], 'b2': [10, None, 30]})
    ldf = df.lazy()
    fc = FileCache()
    collected: list[ProgressNotification] = []
    def listener(p:ProgressNotification) -> None:
        collected.append(p)

    exec_ = PAFColumnExecutor([SelectOnlyAnalysis])
    ex = Executor(ldf, exec_, listener, fc, planning_function=simple_one_column_planning)
    ex.run()

    # Should have produced two notifications and cached per-series results
    assert len(collected) == 2

    # Validate we got notifications per column (success or failure)
    assert all(p.col_group in [['a1'], ['b2']] for p in collected)


class ComputedOnlyAnalysis(PolarsAnalysis):
    """
    Minimal analysis that only provides a default and a computed_summary
    value, with no select_clauses or column_ops. This is used to verify
    that PAFColumnExecutor (via polars_series_stats_from_select_result)
    actually invokes computed_summary for each column.
    """

    provides_defaults = {'foo': 0}
    select_clauses: list[pl.Expr] = []

    @staticmethod
    def computed_summary(summary_dict):
        # Increment foo to a non-default value so we can assert it was called.
        return {'foo': summary_dict.get('foo', 0) + 1}


def test_paf_column_executor_runs_computed_summary():
    """
    Ensure that PAFColumnExecutor results include values produced by
    computed_summary, not just raw select_clauses/column_ops output.
    """
    df = pl.DataFrame({'a1': [1, 2, 3], 'b2': [10, 20, 30]})
    ldf = df.lazy()
    fc = FileCache()
    collected: list[ProgressNotification] = []

    def listener(p: ProgressNotification) -> None:
        collected.append(p)

    exec_ = PAFColumnExecutor([ComputedOnlyAnalysis])
    ex = Executor(ldf, exec_, listener, fc, planning_function=simple_one_column_planning)
    ex.run()

    # One notification per column, and each should contain ColumnResults
    assert len(collected) == 2
    for note in collected:
        assert note.success
        assert isinstance(note.result, dict)
        # Each ColumnResult.result should contain foo==1 (default 0 + 1)
        for col, col_result in note.result.items():
            assert col in ('a1', 'b2')
            assert col_result.result.get('foo') == 1


# Analysis classes that produce unique stat keys to track execution
class AnalysisA(PolarsAnalysis):
    """Analysis A produces a unique stat key 'analysis_a_stat'"""
    provides_defaults = {'analysis_a_stat': 0}
    select_clauses = [
        F.all().mean().name.map(json_postfix('analysis_a_stat')),
    ]


class AnalysisB(PolarsAnalysis):
    """Analysis B produces a unique stat key 'analysis_b_stat'"""
    provides_defaults = {'analysis_b_stat': 0}
    select_clauses = [
        F.all().sum().name.map(json_postfix('analysis_b_stat')),
    ]


class AnalysisC(PolarsAnalysis):
    """Analysis C produces a unique stat key 'analysis_c_stat'"""
    provides_defaults = {'analysis_c_stat': 0}
    select_clauses = [
        F.all().min().name.map(json_postfix('analysis_c_stat')),
    ]


class AnalysisD(PolarsAnalysis):
    """Analysis D produces a unique stat key 'analysis_d_stat'"""
    provides_defaults = {'analysis_d_stat': 0}
    select_clauses = [
        F.all().max().name.map(json_postfix('analysis_d_stat')),
    ]


def test_paf_column_executor_with_different_analysis_sets(tmp_path):
    """
    Test caching behavior when running PAFColumnExecutor with different analysis sets.
    
    Scenario:
    1. Run with analyses a,b,c through an executor, verify the results
    2. Run with analyses b,c,d - verify that only d is run, and b and c are not run,
       but that the results are available
    3. Run a,b,c again - verify that no analysis is run
    
    Expected behavior based on codebase descriptions:
    
    SECOND RUN (b,c,d):
    - Based on ColumnExecutorDataflow.compute_summary_with_executor (lines 163-169, 198-205):
      It initializes aggregated_summary with cached_merged_sd, then updates with newly computed results.
      This means it merges cached data with newly computed data.
    - Therefore, run 2 should return a,b,c,d (all cached from run 1 + newly computed d)
    
    THIRD RUN (a,b,c):
    - Based on PAFColumnExecutor.get_execution_args (lines 29-91), it checks if columns are cached.
      If all columns are cached, it sets no_exec=True.
    - Based on ColumnExecutorDataflow behavior, when no execution occurs, it should return
      all cached stats from merged_sd, not just the requested ones.
    - Therefore, run 3 should return a,b,c,d (all cached from previous runs)
    
    The key issue being tested:
    - PAFColumnExecutor.get_execution_args() currently checks if a column has ANY stats in cache,
      not whether it has the specific stats needed for the requested analyses.
    - This means it might incorrectly mark a column as cached even when some requested analyses are missing.
    - However, when it does execute, it runs ALL analyses in the list, not just missing ones.
    """
    # Set up isolated cache
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test data
        df = pl.DataFrame({'test_col': [1, 2, 3, 4, 5]})
        test_file = tmp_path / "test_data.csv"
        df.write_csv(test_file)
        
        fc = get_global_file_cache()
        clear_file_cache()
        ldf = df.lazy()
        test_column = 'test_col'
        orig_to_rw_map = {test_column: test_column}
        
        # STEP 1: Run with analyses a,b,c
        collected1 = []
        exec1 = PAFColumnExecutor([AnalysisA, AnalysisB, AnalysisC])
        ex1 = Executor(ldf, exec1, create_listener(collected1), fc, file_path=test_file, planning_function=simple_one_column_planning)
        ex1.run()
        
        results_1 = extract_results(collected1)
        assert len(results_1) > 0, "Run 1 should produce results"
        assert_stats_present(results_1, test_column, 
                           ['analysis_a_stat', 'analysis_b_stat', 'analysis_c_stat'],
                           ['analysis_d_stat'])
        
        # Build and save merged_sd from run 1 (simulating ColumnExecutorDataflow)
        aggregated_summary_1 = {}
        for note in collected1:
            if note.success and note.result:
                for orig_col, col_res in note.result.items():
                    stats = col_res.result or {}
                    rw = orig_to_rw_map.get(orig_col, orig_col)
                    entry = aggregated_summary_1.get(rw)
                    if entry is None:
                        entry = {'orig_col_name': orig_col, 'rewritten_col_name': rw}
                        aggregated_summary_1[rw] = entry
                    entry.update(stats)
        
        # Save merged_sd to cache (simulating what ColumnExecutorDataflow does)
        if aggregated_summary_1:
            merged_sd_1 = merge_sds({}, aggregated_summary_1, {})
            fc.upsert_file_metadata(test_file, {'merged_sd': merged_sd_1})
        
        # STEP 2: Run with analyses b,c,d
        cached_merged_sd_2 = get_cached_merged_sd(fc, test_file)
        existing_cached = build_existing_cached(fc, test_file, [test_column])
        
        exec2 = PAFColumnExecutor(
            [AnalysisB, AnalysisC, AnalysisD],
            cached_merged_sd=cached_merged_sd_2,
            orig_to_rw_map=orig_to_rw_map
        )
        
        # Check which columns will be executed
        exec_args_2 = exec2.get_execution_args(existing_cached)
        columns_to_execute_2 = exec_args_2.columns
        
        # Verify that test_column should be executed because analysis_d_stat doesn't exist in cache
        rw_col = orig_to_rw_map.get(test_column, test_column)
        cached_stats_2 = cached_merged_sd_2.get(rw_col, {})
        assert 'analysis_d_stat' not in cached_stats_2, "analysis_d_stat should not exist in cache before run 2"
        
        # BUG DEMONSTRATION: The current implementation checks if the column has ANY stats,
        # not whether it has the specific stats needed for the requested analyses.
        # Since the column has stats from a,b,c, it incorrectly marks it as cached,
        # even though analysis_d_stat is missing.
        # 
        # EXPECTED BEHAVIOR: Since analysis_d_stat doesn't exist, the column should be executed
        # (even though it has stats for a,b,c, it doesn't have stats for d)
        # 
        # This assertion will fail, demonstrating the bug:
        assert test_column in columns_to_execute_2, (
            f"BUG: test_column should be in columns_to_execute because analysis_d_stat is not cached. "
            f"Got: {columns_to_execute_2}. "
            f"The column has stats from a,b,c but is missing d, so it should be executed."
        )
        assert not exec_args_2.no_exec, "no_exec should be False because analysis_d_stat needs to be computed"
        
        collected2 = []
        ex2 = Executor(ldf, exec2, create_listener(collected2), fc, file_path=test_file, planning_function=simple_one_column_planning)
        ex2.run()
        
        # Verify that execution occurred (column was in columns_to_execute)
        # When PAFColumnExecutor executes, it runs ALL analyses in the list
        # So b, c, d will all be executed, but b and c should already be in cache
        results_2 = extract_results(collected2)
        
        # Verify that analysis_d_stat was executed (should be in notifications)
        assert 'analysis_d_stat' in results_2.get(test_column, {}), "Run 2 should have executed and produced analysis_d_stat"
        
        # Check which stats are in the newly computed results (from notifications)
        # These are the stats that were actually executed in run 2
        newly_computed_stats_2 = set()
        for note in collected2:
            if note.success and note.result:
                for orig_col, col_res in note.result.items():
                    stats = col_res.result or {}
                    newly_computed_stats_2.update(stats.keys())
        
        # When PAFColumnExecutor executes, it runs ALL analyses in the list
        # So b, c, d will all be executed (all three analyses run)
        # But we want to verify that b and c were already cached and didn't need to run
        # The fact that they appear in results_2 means they were executed, but they should
        # have been available from cache
        assert 'analysis_d_stat' in newly_computed_stats_2, "analysis_d_stat should be in newly computed stats"
        # Note: b and c will also be in newly_computed_stats_2 because PAFColumnExecutor
        # executes all analyses in the list, not just missing ones. This is the current behavior.
        
        # Build aggregated_summary for run 2 (simulating ColumnExecutorDataflow)
        # Start with cached data
        aggregated_summary_2 = {}
        if cached_merged_sd_2:
            for rw_col_iter, cached_stats in cached_merged_sd_2.items():
                if isinstance(cached_stats, dict):
                    aggregated_summary_2[rw_col_iter] = cached_stats.copy()
        
        # Add newly computed results
        for note in collected2:
            if note.success and note.result:
                for orig_col, col_res in note.result.items():
                    stats = col_res.result or {}
                    rw = orig_to_rw_map.get(orig_col, orig_col)
                    entry = aggregated_summary_2.get(rw)
                    if entry is None:
                        entry = {'orig_col_name': orig_col, 'rewritten_col_name': rw}
                        aggregated_summary_2[rw] = entry
                    entry.update(stats)
        
        # Save merged_sd after run 2
        if aggregated_summary_2:
            merged_sd_2 = merge_sds({}, aggregated_summary_2, {})
            fc.upsert_file_metadata(test_file, {'merged_sd': merged_sd_2})
        
        # Verify results: should have a,b,c (from cache) + d (newly computed)
        # Based on ColumnExecutorDataflow behavior (lines 163-169, 198-205), it merges
        # cached data with newly computed data, so run 2 should return a,b,c,d
        merged_stats_2 = aggregated_summary_2.get(rw_col, {})
        assert 'analysis_a_stat' in merged_stats_2, "Run 2 should preserve analysis_a_stat from run 1"
        assert 'analysis_b_stat' in merged_stats_2, "Run 2 should preserve analysis_b_stat from run 1"
        assert 'analysis_c_stat' in merged_stats_2, "Run 2 should preserve analysis_c_stat from run 1"
        assert 'analysis_d_stat' in merged_stats_2, "Run 2 should add analysis_d_stat (was executed and merged)"
        
        # STEP 3: Run with analyses a,b,c again
        cached_merged_sd_3 = get_cached_merged_sd(fc, test_file)
        existing_cached_3 = build_existing_cached(fc, test_file, [test_column])
        
        exec3 = PAFColumnExecutor(
            [AnalysisA, AnalysisB, AnalysisC],
            cached_merged_sd=cached_merged_sd_3,
            orig_to_rw_map=orig_to_rw_map
        )
        
        # All requested analyses (a,b,c) should be cached, so no execution needed
        exec_args_3 = exec3.get_execution_args(existing_cached_3)
        # Verify that no_exec is True - this is the key check
        assert exec_args_3.no_exec, "Run 3 should set no_exec=True since all requested analyses (a,b,c) are cached"
        assert len(exec_args_3.columns) == 0, "Run 3 should have no columns to execute"
        
        collected3 = []
        ex3 = Executor(ldf, exec3, create_listener(collected3), fc, file_path=test_file, planning_function=simple_one_column_planning)
        ex3.run()
        
        # Verify no execution occurred (all cached)
        assert len(collected3) == 0, "Run 3 should produce no notifications since all analyses are cached"
        
        # Build final aggregated_summary (all from cache)
        # Based on ColumnExecutorDataflow behavior, when no execution occurs, it should
        # return all cached stats, not just the requested ones
        aggregated_summary_3 = {}
        if cached_merged_sd_3:
            for rw_col, cached_stats in cached_merged_sd_3.items():
                if isinstance(cached_stats, dict):
                    aggregated_summary_3[rw_col] = cached_stats.copy()
        
        # Verify final state - should have a,b,c,d (all from previous runs)
        # The cache contains all stats from previous runs, so all should be available
        merged_stats_3 = aggregated_summary_3.get(rw_col, {})
        assert 'analysis_a_stat' in merged_stats_3, "Final state should have analysis_a_stat"
        assert 'analysis_b_stat' in merged_stats_3, "Final state should have analysis_b_stat"
        assert 'analysis_c_stat' in merged_stats_3, "Final state should have analysis_c_stat"
        assert 'analysis_d_stat' in merged_stats_3, "Final state should have analysis_d_stat (from run 2)"
        
        # ========================================================================
        # ANSWERS TO QUESTIONS:
        # ========================================================================
        # 
        # Q1: What should the second run (b,c,d) return - b,c,d or a,b,c,d?
        # A1: Based on ColumnExecutorDataflow.compute_summary_with_executor (lines 163-169, 198-205):
        #     - It initializes aggregated_summary with cached_merged_sd (which has a,b,c)
        #     - Then it updates with newly computed results (which has b,c,d)
        #     - The update() call merges the dictionaries, so all stats are preserved
        #     - Therefore, run 2 should return a,b,c,d (all cached from run 1 + newly computed d)
        # 
        # Q2: What should the last run (a,b,c) return - a,b,c or a,b,c,d?
        # A2: Based on ColumnExecutorDataflow behavior when no execution occurs:
        #     - When no_exec=True, Executor.run() returns early (line 545-546 in base.py)
        #     - ColumnExecutorDataflow still has access to cached_merged_sd (line 163-169)
        #     - The aggregated_summary is initialized from cached_merged_sd, which contains all stats
        #     - Therefore, run 3 should return a,b,c,d (all cached from previous runs)
        # 
        # Q3: Should run 3 have no_exec=True?
        # A3: YES. Based on PAFColumnExecutor.get_execution_args (lines 29-91):
        #     - It should check if all requested analyses (a,b,c) are present in cache
        #     - If they are, it should set no_exec=True
        #     - However, the current implementation only checks if the column has ANY stats,
        #       not whether it has the specific stats needed for the requested analyses
        #     - This is the bug being demonstrated by this test
        # 
        # ========================================================================
        
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home




class SimpleAnalysis(PolarsAnalysis):
    """Simple analysis that produces a stat key"""
    provides_defaults = {}
    select_clauses = [
        F.all().mean().name.map(json_postfix('mean_stat')),
    ]


def test_no_exec_per_column_group(tmp_path):
    """
    Test that no_exec works per column group, not for the entire executor run.
    
    Scenario:
    1. Create a dataframe with two columns: col1 and col2
    2. Run executor with both columns - both get computed and cached
    3. Manually set up cache so that col1 is fully cached but col2 is not
    4. Run executor again - col1 should have no_exec=True, col2 should have no_exec=False
    5. Verify that Executor skips execution for col1 (no_exec=True) but executes col2 (no_exec=False)
    
    Current behavior analysis:
    - Executor.run() first pass (lines 513-546): 
      * Calls get_execution_args() for each column group
      * Checks if ALL groups have empty columns list (line 543)
      * If all have empty columns, returns early (line 545-546)
      * NOTE: It doesn't check no_exec flag here, only checks if columns list is empty
    - Executor.run() second pass (lines 551-655):
      * For each column group, calls get_execution_args() again
      * Checks if columns list is empty (line 591) - if so, skips that group
      * NOTE: It doesn't explicitly check no_exec flag, but if no_exec=True, 
        columns list should be empty, so it would be skipped
    - The issue: no_exec flag is not explicitly checked per group in Executor.run()
      * It relies on empty columns list as a proxy for no_exec=True
      * But no_exec is a more explicit signal that should be checked directly
    
    Intended behavior (CORRECT):
    - Executor should check no_exec flag for each column group individually
    - Groups with no_exec=True should be skipped
    - Groups with no_exec=False should be executed
    - The executor should continue processing even if some groups have no_exec=True
    """
    # Set up isolated cache
    cache_utils_module._file_cache = None
    cache_utils_module._executor_log = None
    
    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(tmp_path)
    
    try:
        # Create test data with two columns
        df = pl.DataFrame({
            'col1': [1, 2, 3, 4, 5],
            'col2': [10, 20, 30, 40, 50]
        })
        test_file = tmp_path / "test_data.csv"
        df.write_csv(test_file)
        
        fc = get_global_file_cache()
        clear_file_cache()
        ldf = df.lazy()
        orig_to_rw_map = {'col1': 'col1', 'col2': 'col2'}
        
        # STEP 1: Run with both columns to populate cache
        collected1 = []
        exec1 = PAFColumnExecutor([SimpleAnalysis])
        ex1 = Executor(ldf, exec1, create_listener(collected1), fc, file_path=test_file, planning_function=simple_one_column_planning)
        ex1.run()
        
        # Verify both columns were executed
        results_1 = extract_results(collected1)
        assert 'col1' in results_1, "col1 should have been executed in run 1"
        assert 'col2' in results_1, "col2 should have been executed in run 1"
        assert 'mean_stat' in results_1.get('col1', {}), "col1 should have mean_stat"
        assert 'mean_stat' in results_1.get('col2', {}), "col2 should have mean_stat"
        
        # Build and save merged_sd from run 1
        aggregated_summary_1 = {}
        for note in collected1:
            if note.success and note.result:
                for orig_col, col_res in note.result.items():
                    stats = col_res.result or {}
                    rw = orig_to_rw_map.get(orig_col, orig_col)
                    entry = aggregated_summary_1.get(rw)
                    if entry is None:
                        entry = {'orig_col_name': orig_col, 'rewritten_col_name': rw}
                        aggregated_summary_1[rw] = entry
                    entry.update(stats)
        
        if aggregated_summary_1:
            merged_sd_1 = merge_sds({}, aggregated_summary_1, {})
            fc.upsert_file_metadata(test_file, {'merged_sd': merged_sd_1})
        
        # STEP 2: Set up cache so col1 is fully cached but col2 is missing from merged_sd
        # This simulates a scenario where one column group is cached, another is not
        cached_merged_sd_2 = get_cached_merged_sd(fc, test_file)
        
        # Remove col2 from cached_merged_sd to simulate it not being cached
        # Keep col1 in cache (fully cached)
        cached_merged_sd_partial = {'col1': cached_merged_sd_2.get('col1', {})}
        # col2 is intentionally missing from cached_merged_sd_partial
        
        # STEP 3: Run executor again and check no_exec per column group
        existing_cached = build_existing_cached(fc, test_file, ['col1', 'col2'])
        
        exec2 = PAFColumnExecutor(
            [SimpleAnalysis],
            cached_merged_sd=cached_merged_sd_partial,  # Only col1 is in cache
            orig_to_rw_map=orig_to_rw_map
        )
        
        # Check execution args for each column individually
        # col1 should have no_exec=True (fully cached)
        existing_cached_col1 = {'col1': existing_cached.get('col1', {})}
        exec_args_col1 = exec2.get_execution_args(existing_cached_col1)
        assert exec_args_col1.no_exec, (
            f"col1 should have no_exec=True because it's fully cached. "
            f"Got no_exec={exec_args_col1.no_exec}, columns={exec_args_col1.columns}"
        )
        assert len(exec_args_col1.columns) == 0, (
            f"col1 should have no columns to execute. Got: {exec_args_col1.columns}"
        )
        
        # col2 should have no_exec=False (not in cached_merged_sd)
        existing_cached_col2 = {'col2': existing_cached.get('col2', {})}
        exec_args_col2 = exec2.get_execution_args(existing_cached_col2)
        assert not exec_args_col2.no_exec, (
            f"col2 should have no_exec=False because it's not in cached_merged_sd. "
            f"Got no_exec={exec_args_col2.no_exec}, columns={exec_args_col2.columns}"
        )
        assert 'col2' in exec_args_col2.columns, (
            f"col2 should be in columns to execute. Got: {exec_args_col2.columns}"
        )
        
        # STEP 4: Run executor and verify behavior
        collected2 = []
        ex2 = Executor(
            ldf,
            exec2,
            create_listener(collected2),
            fc,
            file_path=test_file,
            cached_merged_sd=cached_merged_sd_partial,
            planning_function=simple_one_column_planning
        )
        ex2.run()
        
        # INTENDED BEHAVIOR (what we want):
        # - Executor should explicitly check no_exec flag for each column group
        # - col1 group should be skipped because no_exec=True
        # - col2 group should be executed because no_exec=False
        # - Therefore, we should get notifications only for col2
        
        # Verify that col2 was executed (should have notification)
        results_2 = extract_results(collected2)
        
        # col2 should have been executed
        assert 'col2' in results_2, (
            f"col2 should have been executed (no_exec=False). "
            f"Got results for: {list(results_2.keys())}"
        )
        assert 'mean_stat' in results_2.get('col2', {}), (
            "col2 should have mean_stat from execution"
        )
        
        # col1 should NOT have been executed (no_exec=True)
        # The Executor should explicitly check no_exec flag and skip col1
        # Currently, Executor.run() doesn't check no_exec explicitly - it only checks
        # if columns list is empty. Since no_exec=True means columns list is empty,
        # it might work by accident, but we want explicit no_exec checking.
        if 'col1' in results_2:
            # This means col1 was executed even though it had no_exec=True
            # This would indicate Executor is not properly checking no_exec per group
            assert False, (
                f"BUG: col1 should NOT have been executed because no_exec=True, "
                f"but got results: {results_2.get('col1', {})}. "
                f"Executor should explicitly check no_exec flag and skip groups with no_exec=True."
            )
        
        # Verify that we got exactly one notification (for col2)
        # If Executor properly checks no_exec per group, we should get 1 notification
        # If it doesn't, we might get 2 notifications (both col1 and col2)
        assert len(collected2) == 1, (
            f"Should get exactly 1 notification (for col2), but got {len(collected2)}. "
            f"Notifications: {[n.col_group for n in collected2]}. "
            f"This indicates Executor is not properly checking no_exec per column group. "
            f"Expected: col1 skipped (no_exec=True), col2 executed (no_exec=False)."
        )
        
        # Verify the notification is for col2
        assert collected2[0].col_group == ['col2'], (
            f"Notification should be for col2, but got: {collected2[0].col_group}"
        )
        
        # ADDITIONAL CHECK: Document intended behavior
        # Currently, Executor.run() second pass (line 591) only checks if columns list is empty,
        # not if no_exec flag is True. 
        # 
        # INTENDED BEHAVIOR: Executor should explicitly check ex_args.no_exec for each group
        # and skip groups where no_exec=True, regardless of whether columns list is empty or not.
        # 
        # The current implementation happens to work because when no_exec=True, columns list
        # is empty, so the check on line 591 catches it. But this is indirect - we want
        # explicit no_exec checking for clarity and correctness.
        #
        # TODO: Update Executor.run() second pass to check ex_args.no_exec explicitly:
        #   if ex_args.no_exec:
        #       logger.debug(f"  Skipping column group {col_group} - no_exec=True")
        #       continue
        #   if not ex_args.columns:
        #       logger.debug(f"  Skipping column group {col_group} - all columns cached")
        #       continue
        
    finally:
        cache_utils_module._file_cache = None
        cache_utils_module._executor_log = None
        if original_home:
            os.environ['HOME'] = original_home
