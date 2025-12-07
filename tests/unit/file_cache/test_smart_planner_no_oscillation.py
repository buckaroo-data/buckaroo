"""
Test that smart planner doesn't oscillate after backing down.
"""
from datetime import timedelta

from buckaroo.file_cache.batch_planning import (
    ExecutionResult,
    PlanningContext,
    smart_planning_function,
)


def test_stays_at_backed_down_size():
    """Test that after backing down from 8 to 4, planner stays at 4."""
    # Scenario: 1, 2, 4, 8 all succeeded, then 8 started failing
    # After backing down to 4, it should stay at 4 for all remaining columns
    context = PlanningContext(
        all_columns=['a'] * 20,
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=10.0,
        execution_history=[
            ExecutionResult(columns=['a'] * 10, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # Half batch timeout
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=1.0), timed_out=False),  # 1 success
            ExecutionResult(columns=['a'] * 2, success=True, execution_time=timedelta(seconds=2.0), timed_out=False),  # 2 success
            ExecutionResult(columns=['a'] * 4, success=True, execution_time=timedelta(seconds=3.0), timed_out=False),  # 4 success
            ExecutionResult(columns=['a'] * 8, success=True, execution_time=timedelta(seconds=4.0), timed_out=False),  # 8 success (first time)
            ExecutionResult(columns=['a'] * 16, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # 16 failed
            ExecutionResult(columns=['a'] * 8, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # 8 now failing!
        ],
        remaining_columns=['a'] * 12
    )
    
    result = smart_planning_function(context)
    
    # Should back down to 4 and stay there
    assert result.phase == "optimized"
    assert len(result.batches) > 0
    batch_sizes = [len(b.columns) for b in result.batches]
    assert all(size == 4 for size in batch_sizes)  # All batches should be size 4
    assert sum(batch_sizes) == 12  # Should cover all remaining
    assert "staying at this size" in result.notes  # Should indicate staying at size to prevent oscillation


def test_stays_at_backed_down_size_on_subsequent_calls():
    """Test that subsequent calls after backdown also stay at backed-down size."""
    # First call: back down from 8 to 4
    context1 = PlanningContext(
        all_columns=['a'] * 20,
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=10.0,
        execution_history=[
            ExecutionResult(columns=['a'] * 10, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=1.0), timed_out=False),
            ExecutionResult(columns=['a'] * 2, success=True, execution_time=timedelta(seconds=2.0), timed_out=False),
            ExecutionResult(columns=['a'] * 4, success=True, execution_time=timedelta(seconds=3.0), timed_out=False),
            ExecutionResult(columns=['a'] * 8, success=True, execution_time=timedelta(seconds=4.0), timed_out=False),
            ExecutionResult(columns=['a'] * 16, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),
            ExecutionResult(columns=['a'] * 8, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # 8 failing
        ],
        remaining_columns=['a'] * 12
    )
    
    result1 = smart_planning_function(context1)
    assert result1.phase == "optimized"
    assert all(len(b.columns) == 4 for b in result1.batches)
    
    # Second call: after processing some columns with size 4, should still use 4
    # (simulate that 4 succeeded)
    context2 = PlanningContext(
        all_columns=['a'] * 20,
        baseline_overhead=timedelta(seconds=0.1),
        timeout_secs=10.0,
        execution_history=[
            ExecutionResult(columns=['a'] * 10, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),
            ExecutionResult(columns=['a'], success=True, execution_time=timedelta(seconds=1.0), timed_out=False),
            ExecutionResult(columns=['a'] * 2, success=True, execution_time=timedelta(seconds=2.0), timed_out=False),
            ExecutionResult(columns=['a'] * 4, success=True, execution_time=timedelta(seconds=3.0), timed_out=False),
            ExecutionResult(columns=['a'] * 8, success=True, execution_time=timedelta(seconds=4.0), timed_out=False),
            ExecutionResult(columns=['a'] * 16, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),
            ExecutionResult(columns=['a'] * 8, success=False, execution_time=timedelta(seconds=10.0), timed_out=True),  # 8 still failing
            ExecutionResult(columns=['a'] * 4, success=True, execution_time=timedelta(seconds=3.0), timed_out=False),  # 4 succeeded
        ],
        remaining_columns=['a'] * 8
    )
    
    result2 = smart_planning_function(context2)
    # Should still use 4, not try to grow to 8 again
    assert result2.phase == "optimized"
    assert all(len(b.columns) == 4 for b in result2.batches)
    assert sum(len(b.columns) for b in result2.batches) == 8
