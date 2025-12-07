"""
Batch planning system for multiprocessing executor.

This module provides a pluggable planning system that determines optimal column batch sizes
for multiprocessing execution, balancing overhead vs. timeout risk.

The planning algorithm:
1. Measures baseline mp_timeout overhead (no-op call)
2. Tries half the columns as first batch
3. If succeeds before timeout, processes other half
4. If fails due to timeout, tries single column to measure per-column time
5. Uses this data to determine optimal batch size for remaining columns
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from buckaroo.file_cache.base import ExecutorLog, DFIdentifier


@dataclass
class ExecutionResult:
    """Result of executing a batch of columns."""
    columns: list[str]
    success: bool
    execution_time: timedelta
    timed_out: bool
    error: str | None = None


@dataclass
class PlanningContext:
    """Context for planning column batches."""
    all_columns: list[str]
    baseline_overhead: timedelta  # Time for no-op mp_timeout call
    timeout_secs: float  # Timeout in seconds (like mp_timeout expects)
    execution_history: list[ExecutionResult]
    remaining_columns: list[str]  # Columns not yet executed


@dataclass
class ColumnBatch:
    """A planned batch of columns to execute."""
    columns: list[str]
    expected_duration: Optional[timedelta] = None  # Optional estimate


@dataclass
class PlanningResult:
    """Result of planning step."""
    batches: list[ColumnBatch]
    phase: str  # "baseline", "half_batch", "single_column", "optimized", "complete", "error"
    notes: str = ""  # Optional notes about planning decisions


PlanningFunction = Callable[[PlanningContext], PlanningResult]


def extract_execution_history(executor_log: 'ExecutorLog', dfi: 'DFIdentifier') -> list[ExecutionResult]:
    """
    Extract execution history from executor log.
    
    Converts ExecutorLogEvent objects to ExecutionResult objects for planning.
    Filters to events matching the dfi.
    
    Args:
        executor_log: ExecutorLog instance
        dfi: DFIdentifier tuple (id(ldf), file_path_str)
    
    Returns:
        List of ExecutionResult objects, ordered by execution time.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Import at runtime to avoid circular import
    
    try:
        events = executor_log.get_log_events()
    except Exception:
        return []
    
    log_msg = f"extract_execution_history: dfi={dfi}, total_events={len(events)}"
    logger.info(log_msg)
    
    results = []
    # dfi is (id(ldf), file_path_str)
    # Note: SQLite stores dfi as JSON, so integers become strings when reconstructed
    # We need to handle both int and string comparisons
    def dfi_matches(event_dfi, target_dfi):
        """Compare dfi tuples, handling string/int conversion for IDs."""
        if len(event_dfi) != len(target_dfi):
            return False
        # Compare IDs (first element) - handle int/string conversion
        event_id = event_dfi[0]
        target_id = target_dfi[0]
        if str(event_id) != str(target_id):
            return False
        # Compare file paths (second element)
        if len(event_dfi) > 1 and len(target_dfi) > 1:
            return event_dfi[1] == target_dfi[1]
        return len(event_dfi) == len(target_dfi)
    
    matched_count = 0
    for i, event in enumerate(events):
        # Filter to matching dfi
        if not dfi_matches(event.dfi, dfi):
            continue
        matched_count += 1
        if matched_count <= 3:  # Log first few matches
            log_msg = f"extract_execution_history: event {i} MATCHED - dfi={event.dfi}, columns={len(event.args.columns) if hasattr(event, 'args') and event.args else 'N/A'}"
            logger.info(log_msg)
        
        # Determine if timed out (started but not completed, and end_time is None)
        timed_out = not event.completed and event.end_time is None
        
        # Calculate execution time
        if event.end_time:
            execution_time = event.end_time - event.start_time
        else:
            # If not completed, use a default timeout duration
            # For planning purposes, we'll use a large time if timed out
            execution_time = timedelta(seconds=30.0)  # Default timeout
        
        result = ExecutionResult(
            columns=list(event.args.columns),
            success=event.completed,
            execution_time=execution_time,
            timed_out=timed_out,
            error=None  # ExecutorLogEvent doesn't store error messages
        )
        
        log_msg = f"extract_execution_history: event columns={len(result.columns)}, success={result.success}, timed_out={result.timed_out}"
        logger.info(log_msg)
        
        results.append(result)
    
    log_msg = f"extract_execution_history: matched {matched_count} events, returning {len(results)} results"
    logger.info(log_msg)
    
    if matched_count > 0 and len(results) == 0:
        log_msg = f"extract_execution_history: WARNING - matched {matched_count} events but created 0 results. This should not happen!"
        logger.warning(log_msg)
    
    return results


def simple_one_column_planning(context: PlanningContext) -> PlanningResult:
    """
    Simple planning function that returns one column at a time.
    
    This is the default for backward compatibility - it maintains
    the original behavior of one column per batch.
    """
    remaining = context.remaining_columns
    
    if not remaining:
        return PlanningResult(batches=[], phase="complete", notes="No columns remaining")
    
    # Return first column as a single batch
    return PlanningResult(
        batches=[ColumnBatch(columns=[remaining[0]])],
        phase="simple",
        notes="One column at a time (simple planning)"
    )


def smart_planning_function(context: PlanningContext) -> PlanningResult:
    """
    Smart planning function implementing the tuning algorithm.
    
    Algorithm:
    1. Baseline overhead is measured via mp_calibration module (once per process)
    2. If no batch history, try half the columns
    3. If half batch timed out, start with 1 column
    4. After first failure, work up by 2x (1, 2, 4, 8, ...) until finding optimal size
    5. Once optimal size found, process remaining columns in that batch size
    
    Returns:
        PlanningResult with batches to execute next
    """
    import logging
    logger = logging.getLogger(__name__)
    
    remaining = context.remaining_columns
    history = context.execution_history
    
    log_msg = f"smart_planning_function: all_columns={len(context.all_columns)}, remaining={len(remaining)}, history_size={len(history)}"
    logger.info(log_msg)
    
    if history:
        log_msg = f"smart_planning_function: history details: {[(len(r.columns), r.success, r.timed_out) for r in history]}"
        logger.info(log_msg)
    
    if not remaining:
        return PlanningResult(batches=[], phase="complete", notes="No columns remaining")
    
    # Phase 1: Baseline overhead is now handled via mp_calibration module (runs once per process)
    # No need to return empty batch - baseline is calibrated separately
    # The executor will update planning state with calibrated baseline before calling this function
    
    # Phase 2: Try half batch if not done
    # Look for half batch results in history
    # IMPORTANT: half_batch_size is based on ALL columns, not remaining
    half_batch_size = len(context.all_columns) // 2
    half_batch_results = [r for r in history if len(r.columns) == half_batch_size]
    
    log_msg = f"smart_planning_function: half_batch_size={half_batch_size}, half_batch_results={len(half_batch_results)}"
    logger.info(log_msg)
    
    if not half_batch_results:
        # Haven't tried half batch yet - try it now
        half_size = half_batch_size
        # But don't exceed remaining columns
        half_size = min(half_size, len(remaining))
        if half_size == 0:
            return PlanningResult(batches=[], phase="complete", notes="No columns remaining")
        log_msg = f"smart_planning_function: No half batch in history, trying {half_size} columns"
        logger.info(log_msg)
        return PlanningResult(
            batches=[ColumnBatch(columns=remaining[:half_size])],
            phase="half_batch",
            notes=f"Trying half batch ({half_size} columns)"
        )
    
    half_result = half_batch_results[0]
    log_msg = f"smart_planning_function: Found half batch result: success={half_result.success}, timed_out={half_result.timed_out}, columns={len(half_result.columns)}"
    logger.info(log_msg)
    
    # Phase 3: If half batch succeeded, process other half
    if half_result.success and not half_result.timed_out:
        # Find which columns were in the half batch
        half_batch_cols = set(half_result.columns)
        # Get remaining columns that weren't in the half batch
        other_half = [c for c in remaining if c not in half_batch_cols]
        if other_half:
            return PlanningResult(
                batches=[ColumnBatch(columns=other_half)],
                phase="other_half",
                notes="Half batch succeeded, processing other half"
            )
        # All done
        return PlanningResult(batches=[], phase="complete", notes="All columns processed")
    
    # Phase 4: Half batch timed out - start with 1 column, then work up by 2x
    log_msg = "smart_planning_function: Half batch timed out or failed, transitioning to binary search"
    logger.info(log_msg)
    
    # Find all successful batch sizes in history (sorted by size)
    successful_batches = [r for r in history if r.success and not r.timed_out and len(r.columns) > 0]
    successful_sizes = sorted(set(len(r.columns) for r in successful_batches))
    
    # Find all failed batch sizes
    failed_batches = [r for r in history if (r.timed_out or not r.success) and len(r.columns) > 0]
    failed_sizes = set(len(r.columns) for r in failed_batches)
    
    log_msg = f"smart_planning_function: successful_sizes={successful_sizes}, failed_sizes={failed_sizes}"
    logger.info(log_msg)
    
    # If we have no successful batches yet, start with 1 column
    if not successful_sizes:
        # Check if we already tried 1 column
        single_col_results = [r for r in history if len(r.columns) == 1]
        if not single_col_results:
            return PlanningResult(
                batches=[ColumnBatch(columns=[remaining[0]])],
                phase="single_column",
                notes="Half batch timed out, starting with 1 column"
            )
        
        single_result = single_col_results[0]
        if not single_result.success or single_result.timed_out:
            # Single column also timed out
            return PlanningResult(
                batches=[],
                phase="error",
                notes="Single column timed out - should use expression bisector"
            )
        # Single column succeeded, now we can start binary search
        successful_sizes = [1]
    
    # Phase 5: Binary search - work up by 2x until we find the limit
    # First, check if the current "optimal" size (max_successful) is now failing
    # If it is, back down to the next smaller successful size
    max_successful = max(successful_sizes)
    if max_successful in failed_sizes:
        # The "optimal" size is now failing - back down to next smaller size
        log_msg = f"smart_planning_function: Optimal size {max_successful} is now failing, backing down"
        logger.info(log_msg)
        # Remove failed sizes from successful_sizes
        successful_sizes = [s for s in successful_sizes if s not in failed_sizes]
        if not successful_sizes:
            # All sizes failed - start over with 1
            log_msg = "smart_planning_function: All sizes failed, restarting with 1 column"
            logger.warning(log_msg)
            return PlanningResult(
                batches=[ColumnBatch(columns=[remaining[0]])],
                phase="single_column",
                notes="All batch sizes failed, restarting with 1 column"
            )
        max_successful = max(successful_sizes)
        log_msg = f"smart_planning_function: Backed down to size {max_successful}"
        logger.info(log_msg)
    
    # Check if we've found the limit during binary search and should prevent oscillation
    # The limit is found when: during binary search, we tried a size (e.g., 8), it succeeded,
    # then we tried 2x (16) and it failed, then we tried 8 again and it failed
    # In this case, we should stay at the backed-down size to prevent oscillation
    # This prevents: 8 (fail) -> 4 -> 8 (fail) -> 4... instead of 8 (fail) -> 4 -> 4 -> 4...
    # 
    # We only prevent oscillation if:
    # 1. We've backed down (max_successful was in failed_sizes), OR
    # 2. We've tried 2x max_successful and it failed (found limit via binary search)
    # But we exclude the half_batch_size failure from this check (that's a different phase)
    if failed_sizes and max_successful not in [half_batch_size]:
        max_failed = max(failed_sizes)
        # Check if we've found the limit via binary search:
        # - max_successful itself failed (we backed down), OR
        # - we tried 2x max_successful and it failed
        expected_next = max_successful * 2
        found_limit = (max_successful in failed_sizes) or (max_failed >= expected_next and max_failed != half_batch_size)
        
        if found_limit:
            # We've found the limit - stay at max_successful to prevent oscillation
            optimal_batch_size = max_successful
            
            # Create batches for remaining columns using this size
            batches = []
            for i in range(0, len(remaining), optimal_batch_size):
                batch_cols = remaining[i:i + optimal_batch_size]
                batches.append(ColumnBatch(columns=batch_cols))
            
            log_msg = f"smart_planning_function: Found limit at {max_failed}, staying at {optimal_batch_size} to prevent oscillation"
            logger.info(log_msg)
            
            return PlanningResult(
                batches=batches,
                phase="optimized",
                notes=f"Using batch size: {optimal_batch_size} columns (staying at this size after finding limit at {max_failed})"
            )
    
    # Start from the largest successful size, double it
    next_size = max_successful * 2
    
    # But don't exceed remaining columns or go above half batch size
    next_size = min(next_size, len(remaining), half_batch_size)
    
    # Check if we've already tried next_size
    tried_sizes = successful_sizes + list(failed_sizes)
    if next_size in tried_sizes:
        # We've already tried this size - if it failed, use optimal; if it succeeded, we'd have it in successful_sizes
        if next_size in failed_sizes:
            # We've found the limit - use the largest successful size for remaining columns
            optimal_batch_size = max_successful
            
            # Create batches for remaining columns using optimal size
            batches = []
            for i in range(0, len(remaining), optimal_batch_size):
                batch_cols = remaining[i:i + optimal_batch_size]
                batches.append(ColumnBatch(columns=batch_cols))
            
            return PlanningResult(
                batches=batches,
                phase="optimized",
                notes=f"Using optimal batch size: {optimal_batch_size} columns (found via binary search)"
            )
        # If next_size succeeded, it should be in successful_sizes, so this shouldn't happen
        # But handle it anyway - use next_size as optimal
        optimal_batch_size = next_size
        batches = []
        for i in range(0, len(remaining), optimal_batch_size):
            batch_cols = remaining[i:i + optimal_batch_size]
            batches.append(ColumnBatch(columns=batch_cols))
        
        return PlanningResult(
            batches=batches,
            phase="optimized",
            notes=f"Using optimal batch size: {optimal_batch_size} columns"
        )
    
    # Check if next_size would exceed limits
    if next_size >= half_batch_size:
        # We've reached half batch limit, use largest successful size
        optimal_batch_size = max_successful
        
        # Create batches for remaining columns using optimal size
        batches = []
        for i in range(0, len(remaining), optimal_batch_size):
            batch_cols = remaining[i:i + optimal_batch_size]
            batches.append(ColumnBatch(columns=batch_cols))
        
        return PlanningResult(
            batches=batches,
            phase="optimized",
            notes=f"Using optimal batch size: {optimal_batch_size} columns (reached half batch limit)"
        )
    
    # Try the next size (2x the largest successful)
    return PlanningResult(
        batches=[ColumnBatch(columns=remaining[:next_size])],
        phase="binary_search",
        notes=f"Testing batch size {next_size} (2x {max_successful})"
    )


# Alias for backward compatibility
default_planning_function = smart_planning_function
