"""
Unit tests for batch planning system.

These tests use simulated execution results - no actual timeouts or multiprocessing.
"""
from datetime import timedelta

from buckaroo.file_cache.batch_planning import (
    ExecutionResult,
    PlanningContext,
    default_planning_function,
    smart_planning_function,
)


def test_baseline_measurement():
    """Test that baseline is handled via calibration module, not planning function.
    
    Since baseline measurement is now handled separately via mp_calibration module
    (runs once per process), the planning function should skip baseline phase and
    go directly to half_batch.
    """
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd'],
        baseline_overhead=timedelta(seconds=0.1),  # Already calibrated
        timeout_secs=30.0,
        execution_history=[],
        remaining_columns=['a', 'b', 'c', 'd']
    )
    
    result = default_planning_function(context)
    
    # Planning function should skip baseline (handled via calibration) and go to half_batch
    assert result.phase == "half_batch"
    assert len(result.batches) == 1
    assert len(result.batches[0].columns) == 2  # Half of 4


def test_half_batch_after_baseline():
    """Test that after baseline, planning tries half batch."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(
                columns=[],  # Baseline
                success=True,
                execution_time=timedelta(seconds=0.1),
                timed_out=False
            )
        ],
        remaining_columns=['a', 'b', 'c', 'd']
    )
    
    result = default_planning_function(context)
    
    assert result.phase == "half_batch"
    assert len(result.batches) == 1
    assert len(result.batches[0].columns) == 2  # Half of 4
    assert set(result.batches[0].columns) == {'a', 'b'}  # First half


def test_other_half_after_successful_half():
    """Test that after successful half batch, other half is processed."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=[], success=True, execution_time=timedelta(seconds=0.1), timed_out=False),
            ExecutionResult(columns=['a', 'b'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False)
        ],
        remaining_columns=['c', 'd']  # Other half
    )
    
    result = default_planning_function(context)
    
    assert result.phase == "other_half"
    assert len(result.batches) == 1
    assert set(result.batches[0].columns) == {'c', 'd'}


def test_single_column_after_timeout():
    """Test that after half batch timeout, single column is tried."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=[], success=True, execution_time=timedelta(seconds=0.1), timed_out=False),
            ExecutionResult(columns=['a', 'b'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True)
        ],
        remaining_columns=['a', 'b', 'c', 'd']  # Still all remaining (half batch timed out)
    )
    
    result = default_planning_function(context)
    
    assert result.phase == "single_column"
    assert len(result.batches) == 1
    assert len(result.batches[0].columns) == 1
    assert result.batches[0].columns[0] == 'a'  # First remaining


def test_binary_search_after_single_column():
    """Test that after single column succeeds, planner tries 2x size (binary search)."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=['a', 'b', 'c', 'd'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True),  # Half batch timeout
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False)  # Single column success
        ],
        remaining_columns=['b', 'c', 'd', 'e', 'f', 'g', 'h']  # After single column test
    )
    
    result = smart_planning_function(context)
    
    # Should try 2x the successful size (1 -> 2)
    assert result.phase == "binary_search"
    assert len(result.batches) == 1
    assert len(result.batches[0].columns) == 2  # 2x of 1
    assert set(result.batches[0].columns) == {'b', 'c'}  # Next 2 columns


def test_binary_search_continues_after_2x_success():
    """Test that binary search continues: 1 succeeds -> try 2, 2 succeeds -> try 4."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=['a', 'b', 'c', 'd'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True),  # Half batch timeout
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False),  # 1 column success
            ExecutionResult(columns=['b', 'c'], success=True, execution_time=timedelta(seconds=3.0), timed_out=False)  # 2 columns success
        ],
        remaining_columns=['d', 'e', 'f', 'g', 'h']  # After 1 and 2 column tests
    )
    
    result = smart_planning_function(context)
    
    # Should try 2x the largest successful (2 -> 4)
    # But half_batch_size is 4, so next_size = min(4, 5, 4) = 4
    # Since 4 >= half_batch_size (4), it should use optimized with max_successful (2)
    assert result.phase == "optimized"  # Because 4 >= half_batch_size (4)
    assert len(result.batches) > 0
    batch_sizes = [len(b.columns) for b in result.batches]
    # Should use size 2 (largest successful) for remaining columns
    assert all(size <= 2 for size in batch_sizes)  # All batches <= 2
    assert max(batch_sizes) == 2  # At least one batch should be size 2
    # Should cover all remaining columns
    all_batch_cols = [col for batch in result.batches for col in batch.columns]
    assert set(all_batch_cols) == {'d', 'e', 'f', 'g', 'h'}


def test_binary_search_stops_at_failure():
    """Test that binary search stops when 2x size fails, uses largest successful."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=['a', 'b', 'c', 'd'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True),  # Half batch timeout
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False),  # 1 column success
            ExecutionResult(columns=['b', 'c'], success=True, execution_time=timedelta(seconds=3.0), timed_out=False),  # 2 columns success
            ExecutionResult(columns=['d', 'e', 'f', 'g'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True)  # 4 columns timeout
        ],
        remaining_columns=['d', 'e', 'f', 'g', 'h']  # After tests, but 4 failed so d,e,f,g still remain
    )
    
    result = smart_planning_function(context)
    
    # Should use largest successful size (2) for remaining columns
    # Since 4 is in failed_sizes and next_size (4) is in tried_sizes, it should use optimized
    assert result.phase == "optimized"
    assert len(result.batches) > 0
    batch_sizes = [len(b.columns) for b in result.batches]
    # All batches should be size 2 (largest successful), except maybe last one
    assert all(size <= 2 for size in batch_sizes)  # All batches <= 2
    assert max(batch_sizes) == 2  # At least one batch should be size 2
    # Should cover all remaining columns
    all_batch_cols = [col for batch in result.batches for col in batch.columns]
    assert set(all_batch_cols) == {'d', 'e', 'f', 'g', 'h'}


def test_optimized_batching():
    """Test that optimal batch size is used after binary search finds limit."""
    context = PlanningContext(
        all_columns=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=['a', 'b', 'c', 'd'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True),
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False),
            ExecutionResult(columns=['b', 'c'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True)  # 2 columns failed
        ],
        remaining_columns=['b', 'c', 'd', 'e', 'f', 'g', 'h']  # After tests
    )
    
    result = smart_planning_function(context)
    
    # Should use size 1 (largest successful) for remaining
    assert result.phase == "optimized"
    assert len(result.batches) > 0
    batch_sizes = [len(b.columns) for b in result.batches]
    assert all(size == 1 for size in batch_sizes)  # All batches should be size 1
    assert sum(batch_sizes) == 7  # Should cover all remaining


def test_complete_when_no_remaining():
    """Test that planning returns complete when no columns remaining."""
    context = PlanningContext(
        all_columns=['a', 'b'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=[], success=True, execution_time=timedelta(seconds=0.1), timed_out=False),
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False),
            ExecutionResult(columns=['b'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False)
        ],
        remaining_columns=[]
    )
    
    result = default_planning_function(context)
    
    assert result.phase == "complete"
    assert len(result.batches) == 0


def test_single_column_timeout_error():
    """Test that single column timeout results in error phase."""
    context = PlanningContext(
        all_columns=['a', 'b'],
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=30.0,
        execution_history=[
            ExecutionResult(columns=[], success=True, execution_time=timedelta(seconds=0.1), timed_out=False),
            ExecutionResult(columns=['a', 'b'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True),
            ExecutionResult(columns=['a'], success=False, execution_time=timedelta(seconds=30.0), timed_out=True)
        ],
        remaining_columns=['a', 'b']
    )
    
    result = default_planning_function(context)
    
    assert result.phase == "error"
    assert "expression bisector" in result.notes.lower()
    assert len(result.batches) == 0


def test_binary_search_respects_half_batch_limit():
    """Test that binary search doesn't exceed half batch size."""
    context = PlanningContext(
        all_columns=['a'] * 20,  # 20 columns
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=10.0,
        execution_history=[
            ExecutionResult(columns=['a'] * 10, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # Half batch timeout
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=1.0), timed_out=False),  # 1 success
            ExecutionResult(columns=['a', 'a'], success=True, execution_time=timedelta(seconds=2.0), timed_out=False),  # 2 success
            ExecutionResult(columns=['a'] * 4, success=True, execution_time=timedelta(seconds=3.0), timed_out=False),  # 4 success
            ExecutionResult(columns=['a'] * 8, success=True, execution_time=timedelta(seconds=4.0), timed_out=False)  # 8 success
        ],
        remaining_columns=['a'] * 19  # 19 remaining
    )
    
    result = smart_planning_function(context)
    
    # Next would be 16 (2x of 8), but half_batch_size is 10, so should use 8
    assert result.phase == "optimized"
    batch_sizes = [len(b.columns) for b in result.batches]
    assert all(size == 8 for size in batch_sizes[:2])  # First batches should be 8
    assert sum(batch_sizes) == 19  # Should cover all remaining


def test_extract_execution_history_function():
    """Test extract_execution_history function."""
    # This would test the function with a real executor_log
    # For now, just verify the function exists and has correct signature
    from buckaroo.file_cache.batch_planning import extract_execution_history
    assert callable(extract_execution_history)
