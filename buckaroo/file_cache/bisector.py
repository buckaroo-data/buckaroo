from __future__ import annotations

from abc import ABC, abstractmethod
import itertools
from typing import Any, Optional, Callable
import polars as pl

from .base import (
    ExecutorLogEvent,
    ExecutorLog,
    ColumnExecutor,
    ExecutorArgs,
    now,
    SimpleExecutorLog,
)


class BaseBisector(ABC):
    """
    Shared delta-debugging logic over a sequence of items (by index).

    Subclasses must provide how to build ExecutorArgs from selected indices and
    how many base items exist.
    """

    def __init__(self,
                 event: ExecutorLogEvent,
                 executor_log: ExecutorLog,
                 column_executor: ColumnExecutor[Any],
                 ldf: pl.LazyFrame) -> None:
        self.original_event = event
        self.executor_log = executor_log
        self.column_executor = column_executor
        self.ldf = ldf
        self.dfi = event.dfi

    @abstractmethod
    def base_size(self) -> int:
        ...

    @abstractmethod
    def build_args_from_indices(self, indices: list[int]) -> ExecutorArgs:
        ...

    def try_execute_by_indices(self, indices: list[int]) -> tuple[bool, ExecutorLogEvent]:
        args = self.build_args_from_indices(indices)
        self.executor_log.log_start_col_group(self.dfi, args)
        try:
            self.column_executor.execute(self.ldf, args)
        except Exception:  # noqa: BLE001
            ev = self.executor_log.find_event(self.dfi, args)
            if ev is None:
                ev = ExecutorLogEvent(dfi=self.dfi,
                                      args=args,
                                      start_time=now(),
                                      end_time=None,
                                      completed=False)
            return False, ev
        self.executor_log.log_end_col_group(self.dfi, args)
        ev = self.executor_log.find_event(self.dfi, args)
        if ev is None or not ev.completed:
            raise RuntimeError("Bisector expected a completed log event after successful execute")
        return True, ev

    def minimize_failing_indices(self, all_indices: list[int]) -> list[int]:
        overall_ok, _ = self.try_execute_by_indices(all_indices)
        if overall_ok:
            return []

        n = 2
        current = list(all_indices)
        while len(current) >= 2:
            # split into n chunks
            chunk_size = max(1, len(current) // n)
            subsets: list[list[int]] = [current[i:i + chunk_size] for i in range(0, len(current), chunk_size)]

            some_failure_found = False
            # Try each subset (reduce): if a subset fails, shrink to it
            for subset in subsets:
                subset_succeeds, _ = self.try_execute_by_indices(subset)
                if not subset_succeeds:
                    current = subset
                    n = 2
                    some_failure_found = True
                    break

            if some_failure_found:
                continue

            # Try complements
            for i in range(len(subsets)):
                complement: list[int] = list(itertools.chain.from_iterable(subsets[:i] + subsets[i + 1:]))
                if not complement:
                    continue
                complement_succeeds, _ = self.try_execute_by_indices(complement)
                if not complement_succeeds:
                    current = complement
                    n = max(n - 1, 2)
                    some_failure_found = True
                    break

            if some_failure_found:
                continue

            if n >= len(current):
                break
            n = min(len(current), n * 2)

        return current

    def run(self) -> tuple[ExecutorLogEvent, ExecutorLogEvent]:
        # If original event succeeded, nothing to bisect
        if self.original_event.completed:
            return self.original_event, self.original_event

        all_indices = list(range(self.base_size()))
        # Find minimal failing subset
        minimal_fail_idxs = self.minimize_failing_indices(all_indices)
        if not minimal_fail_idxs:
            # No failure induced by items; treat original as success and return it with itself
            _, success_ev = self.try_execute_by_indices(all_indices)
            return success_ev, success_ev

        # Build maximal success set as complement and verify; otherwise, greedy-build
        complement_idxs = [i for i in all_indices if i not in set(minimal_fail_idxs)]
        complement_succeeds, success_ev = self.try_execute_by_indices(complement_idxs)
        if not complement_succeeds:
            # Greedy build a large success set
            success_set: list[int] = []
            for i in all_indices:
                candidate = success_set + [i]
                candidate_succeeds, _ = self.try_execute_by_indices(candidate)
                if candidate_succeeds:
                    success_set.append(i)
            final_succeeds, success_ev = self.try_execute_by_indices(success_set)
            if not final_succeeds:
                # As a last resort, empty set (should always succeed)
                _, success_ev = self.try_execute_by_indices([])

        # Ensure we return the failing event corresponding to minimal failing subset
        minimal_subset_succeeds, fail_ev = self.try_execute_by_indices(minimal_fail_idxs)
        if minimal_subset_succeeds:
            raise RuntimeError("Bisector invariant violated: minimal failing subset unexpectedly succeeded")

        return fail_ev, success_ev


class ExpressionBisector(BaseBisector):
    """
    Delta-debug the expression list in ExecutorArgs to:
    - find the minimal subset that reproduces the original failure
    - find the maximal subset that still succeeds
    """

    def __init__(self,
                 event: ExecutorLogEvent,
                 executor_log: ExecutorLog,
                 column_executor: ColumnExecutor[Any],
                 ldf: pl.LazyFrame) -> None:
        super().__init__(event, executor_log, column_executor, ldf)
        self._base_expressions: list[pl.Expr] = list(event.args.expressions)

    def build_args_with_expressions(self, expressions: list[pl.Expr]) -> ExecutorArgs:
        src = self.original_event.args
        return ExecutorArgs(
            columns=list(src.columns),
            column_specific_expressions=src.column_specific_expressions,
            include_hash=src.include_hash,
            expressions=list(expressions),
            row_start=src.row_start,
            row_end=src.row_end,
            extra=src.extra,
        )

    def try_execute_with_expressions(self, expressions: list[pl.Expr]) -> tuple[bool, ExecutorLogEvent]:
        expr_to_index = {id(expr): idx for idx, expr in enumerate(self._base_expressions)}
        indices = [expr_to_index[id(e)] for e in expressions]
        return self.try_execute_by_indices(indices)

    def build_args_from_indices(self, indices: list[int]) -> ExecutorArgs:
        exprs = [self._base_expressions[i] for i in indices]
        return self.build_args_with_expressions(exprs)

    def base_size(self) -> int:
        return len(self._base_expressions)


class ColumnBisector(BaseBisector):
    """
    Delta-debug the columns in ExecutorArgs.columns to:
    - find the minimal subset of columns that reproduces the failure
    - find the maximal subset that still succeeds
    """

    def __init__(self,
                 event: ExecutorLogEvent,
                 executor_log: ExecutorLog,
                 column_executor: ColumnExecutor[Any],
                 ldf: pl.LazyFrame,
                 existing_stats_provider: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None) -> None:
        super().__init__(event, executor_log, column_executor, ldf)
        self._base_columns: list[str] = list(event.args.columns)
        self._existing_stats_provider = existing_stats_provider or (lambda cols: {c: {} for c in cols})

    def build_args_with_columns(self, columns: list[str]) -> ExecutorArgs:
        # Recompute execution args using the executor and provided priors for the selected columns
        existing_stats = self._existing_stats_provider(columns)
        return self.column_executor.get_execution_args(existing_stats)

    def try_execute_with_columns(self, columns: list[str]) -> tuple[bool, ExecutorLogEvent]:
        index_map = {col: idx for idx, col in enumerate(self._base_columns)}
        indices = [index_map[c] for c in columns]
        return self.try_execute_by_indices(indices)

    def build_args_from_indices(self, indices: list[int]) -> ExecutorArgs:
        cols = [self._base_columns[i] for i in indices]
        return self.build_args_with_columns(cols)

    def base_size(self) -> int:
        return len(self._base_columns)


class RowRangeBisector:
    """
    Find a minimal contiguous row range [row_start, row_end) that reproduces a failure,
    and a maximal contiguous row range that succeeds.
    """

    def __init__(self,
                 event: ExecutorLogEvent,
                 executor_log: ExecutorLog,
                 column_executor: ColumnExecutor[Any],
                 ldf: pl.LazyFrame) -> None:
        self.original_event = event
        self.executor_log = executor_log
        self.column_executor = column_executor
        self.ldf = ldf
        self.dfi = event.dfi

        # Determine total rows for this LazyFrame
        self._total_rows: int = self.ldf.collect().height

    def build_args_with_range(self, row_start: int | None, row_end: int | None) -> ExecutorArgs:
        src = self.original_event.args
        return ExecutorArgs(
            columns=list(src.columns),
            column_specific_expressions=src.column_specific_expressions,
            include_hash=src.include_hash,
            expressions=list(src.expressions),
            row_start=row_start,
            row_end=row_end,
            extra=src.extra,
        )

    def _try_execute(self, row_start: int | None, row_end: int | None) -> tuple[bool, ExecutorLogEvent]:
        args = self.build_args_with_range(row_start, row_end)
        self.executor_log.log_start_col_group(self.dfi, args)
        try:
            self.column_executor.execute(self.ldf, args)
        except Exception:  # noqa: BLE001
            ev = self.executor_log.find_event(self.dfi, args)
            if ev is None:
                ev = ExecutorLogEvent(dfi=self.dfi,
                                      args=args,
                                      start_time=now(),
                                      end_time=None,
                                      completed=False)
            return False, ev
        self.executor_log.log_end_col_group(self.dfi, args)
        ev = self.executor_log.find_event(self.dfi, args)
        if ev is None or not ev.completed:
            raise RuntimeError("RowRangeBisector expected a completed log event after successful execute")
        return True, ev

    def _find_minimal_failing_window(self) -> tuple[int, int]:
        # Brute-force increasing window size to guarantee finding a minimal contiguous window
        n = self._total_rows
        for window in range(1, n + 1):
            for start in range(0, n - window + 1):
                end = start + window
                ok, _ = self._try_execute(start, end)
                if not ok:
                    return start, end
        # If no window fails, raise
        raise RuntimeError("RowRangeBisector could not find a failing window; original event may not be a failure")

    def run(self) -> tuple[ExecutorLogEvent, ExecutorLogEvent]:
        # If original event succeeded, nothing to bisect
        if self.original_event.completed:
            return self.original_event, self.original_event

        # Verify that full range fails (or at least current args) and then find minimal failing
        full_ok, _ = self._try_execute(None, None)
        if full_ok:
            # If full succeeds, return success twice
            _, success_ev = self._try_execute(None, None)
            return success_ev, success_ev

        s, e = self._find_minimal_failing_window()
        # Failing event for minimal window
        _, fail_ev = self._try_execute(s, e)

        # Maximal success: choose the larger of the two success windows that avoid [s,e)
        left_size = s
        right_size = self._total_rows - e
        if left_size >= right_size:
            success_ok, success_ev = self._try_execute(0, s)
            if not success_ok:
                # If left unexpectedly fails, try right
                success_ok, success_ev = self._try_execute(e, self._total_rows)
                if not success_ok:
                    # As a safeguard, empty window should succeed
                    success_ok, success_ev = self._try_execute(0, 0)
            return fail_ev, success_ev
        else:
            success_ok, success_ev = self._try_execute(e, self._total_rows)
            if not success_ok:
                success_ok, success_ev = self._try_execute(0, s)
                if not success_ok:
                    success_ok, success_ev = self._try_execute(0, 0)
            return fail_ev, success_ev


class SamplingRowBisector(BaseBisector):
    """
    Delta-debug over arbitrary row indices (non-contiguous) to:
    - find a minimal set of row indices that reproduces the failure
    - find a maximal set of row indices that succeeds

    Selected rows are communicated via ExecutorArgs.extra['row_indices'].
    """

    def __init__(self,
                 event: ExecutorLogEvent,
                 executor_log: ExecutorLog,
                 column_executor: ColumnExecutor[Any],
                 ldf: pl.LazyFrame) -> None:
        super().__init__(event, executor_log, column_executor, ldf)
        self._total_rows: int = self.ldf.collect().height

    def build_args_with_row_indices(self, row_indices: list[int]) -> ExecutorArgs:
        
        src = self.original_event.args
        extra = dict(src.extra) if isinstance(src.extra, dict) else {}
        extra['row_indices'] = list(row_indices)
        return ExecutorArgs(
            columns=list(src.columns),
            column_specific_expressions=src.column_specific_expressions,
            include_hash=src.include_hash,
            expressions=list(src.expressions),
            row_start=None,
            row_end=None,
            extra=extra,
        )

    def build_args_from_indices(self, indices: list[int]) -> ExecutorArgs:
        return self.build_args_with_row_indices(indices)

    def base_size(self) -> int:
        return self._total_rows

    seeds = [42, 1337, 7, 99, 2025]
    fracs = [0.75, 0.5, 0.25, 0.125]
    min_size = 16
    def try_execute_by_indices(self, indices: list[int]) -> tuple[bool, ExecutorLogEvent]:
        args = self.build_args_from_indices(indices)
        # Filter rows by an identifier: prefer 'original_row' if present, else use a temporary row index
        if 'original_row' in self.ldf.columns:
            filtered_ldf = self.ldf.filter(pl.col('original_row').is_in(indices))
        else:
            # Keep the temporary index column so downstream executors can detect which original rows are present
            filtered_ldf = (
                self.ldf
                .with_row_index('_row_ix')
                .filter(pl.col('_row_ix').is_in(indices))
            )
        self.executor_log.log_start_col_group(self.dfi, args)
        try:
            self.column_executor.execute(filtered_ldf, args)
        except Exception:  # noqa: BLE001
            ev = self.executor_log.find_event(self.dfi, args)
            if ev is None:
                ev = ExecutorLogEvent(dfi=self.dfi,
                                      args=args,
                                      start_time=now(),
                                      end_time=None,
                                      completed=False)
            return False, ev
        self.executor_log.log_end_col_group(self.dfi, args)
        ev = self.executor_log.find_event(self.dfi, args)
        if ev is None or not ev.completed:
            raise RuntimeError("SamplingRowBisector expected a completed log event after successful execute")
        return True, ev

    def run(self) -> tuple[ExecutorLogEvent, ExecutorLogEvent]:
        if self.original_event.completed:
            return self.original_event, self.original_event

        # Initial downsampling using deterministic sampling to shrink the search space
        ldf_current = self.ldf

        for frac in self.fracs: 
            found = False
            for seed in self.seeds:
                # LazyFrame may not support sample; collect then sample deterministically using seed
                current_df = ldf_current.collect()
                candidate_df = current_df.sample(fraction=frac, with_replacement=False, shuffle=True, seed=seed)
                candidate = candidate_df.lazy()
                # If candidate still fails, accept and continue shrinking
                args = self.build_args_from_indices(list(range(self._total_rows)))
                self.executor_log.log_start_col_group(self.dfi, args)
                try:
                    self.column_executor.execute(candidate, args)
                except Exception:
                    ldf_current = candidate
                    found = True
                    break
                finally:
                    # We don't mark completion for this probe as it's not a real ddmin step
                    pass
            if found:
                # Update total rows based on the new sampled data
                self.ldf = ldf_current
                self._total_rows = self.ldf.collect().height
                if self._total_rows <= self.min_size:
                    break
            else:
                # Could not find a failing sample at this fraction; stop shrinking
                break

        # Prepare the set of available original_row indices from current ldf
        if 'original_row' in self.ldf.columns:
            rows_df = self.ldf.select(pl.col('original_row')).collect()
            all_indices = list(map(int, rows_df['original_row'].to_list()))
        else:
            rows_df = self.ldf.with_row_index('_row_ix').select(pl.col('_row_ix')).collect()
            all_indices = list(map(int, rows_df['_row_ix'].to_list()))

        # Use BaseBisector logic on the explicit row id set
        minimal_fail_idxs = self.minimize_failing_indices(all_indices)
        if not minimal_fail_idxs:
            # If nothing fails, consider full current set as success
            _, success_ev = self.try_execute_by_indices(all_indices)
            return success_ev, success_ev

        # Build maximal success as complement
        complement_idxs = [i for i in all_indices if i not in set(minimal_fail_idxs)]
        complement_succeeds, success_ev = self.try_execute_by_indices(complement_idxs)
        if not complement_succeeds:
            # Greedy build a large success set
            success_set: list[int] = []
            for i in all_indices:
                candidate = success_set + [i]
                candidate_succeeds, _ = self.try_execute_by_indices(candidate)
                if candidate_succeeds:
                    success_set.append(i)
            final_succeeds, success_ev = self.try_execute_by_indices(success_set)
            if not final_succeeds:
                _, success_ev = self.try_execute_by_indices([])

        minimal_subset_succeeds, fail_ev = self.try_execute_by_indices(minimal_fail_idxs)
        if minimal_subset_succeeds:
            raise RuntimeError("SamplingRowBisector invariant violated: minimal failing subset unexpectedly succeeded")

        return fail_ev, success_ev


def full_bisect_pipeline(ldf: pl.LazyFrame,
                         column_executor: ColumnExecutor[Any]) -> tuple[ExecutorLogEvent, ExecutorLogEvent]:
    """
    Orchestrate a multi-stage diagnosis to answer two questions when a large select fails:
    1) What is the largest successful set of expressions I can run on the original dataframe?
    2) What is the most reduced failure I can produce (minimal repro)?

    Approach:
    - Column stage: Use ColumnBisector to identify a minimal set of failing columns and a maximal set of successful columns.
    - Expression stage: On the failing column set, use ExpressionBisector to split failing and succeeding expressions.
    - Build success: Combine all successful columns plus the failing column set using only the successful expressions to form a maximal success args; execute on the original dataframe to get the success event.
    - Build minimal failure: Start with the minimal failing expressions on the failing columns, then reduce rows using RowRangeBisector and finally SamplingRowBisector to produce a minimal failure event.

    Notes and caveats:
    - If multiple columns interact to cause the failure, ColumnBisector may return multiple columns in the minimal failing set. This pipeline will use that set as the failing group for the expression bisect. If truly higher-order interactions exist, the expression-level split may not isolate a single expression.
    - Expressions can be column-global in some executors (applied to all columns). To avoid expressions that reference removed columns, ColumnBisector recomputes execution args via get_execution_args for each candidate column set; this pipeline uses the successful expression subset from the expression stage for the final success run.
    - LazyFrame.sample is not available; row sampling is handled by DataFrame.sample with deterministic seeds in SamplingRowBisector.

    """
    # Initial executor log and starting args constructed from current columns
    log = SimpleExecutorLog()
    all_columns = list(ldf.columns)
    # Recompute args via get_execution_args for the full set
    existing_stats_full = {col: {} for col in all_columns}
    starting_args = column_executor.get_execution_args(existing_stats_full)
    starting_event = ExecutorLogEvent(dfi=(id(ldf), ''), args=starting_args, start_time=now(), end_time=None, completed=False)

    # 1) Split columns
    cb = ColumnBisector(starting_event, log, column_executor, ldf)
    col_fail_ev, col_success_ev = cb.run()

    failing_columns = col_fail_ev.args.columns
    success_columns = col_success_ev.args.columns

    # 2) Split expressions on the failing columns set
    failing_stats = {col: {} for col in failing_columns}
    failing_args = column_executor.get_execution_args(failing_stats)
    expr_start_event = ExecutorLogEvent(dfi=(id(ldf), ''), args=failing_args, start_time=now(), end_time=None, completed=False)
    eb = ExpressionBisector(expr_start_event, log, column_executor, ldf)
    expr_fail_ev, expr_success_ev = eb.run()

    # Build maximal success event: run on original dataframe with (success_columns + failing_columns) and success expressions
    combined_columns = list(dict.fromkeys(success_columns + failing_columns))
    total_rows = ldf.collect().height
    success_args = ExecutorArgs(
        columns=combined_columns,
        column_specific_expressions=False,
        include_hash=starting_args.include_hash,
        expressions=list(expr_success_ev.args.expressions),
        row_start=0,
        row_end=total_rows,
        extra={},
    )
    log.log_start_col_group((id(ldf), ''), success_args)
    try:
        column_executor.execute(ldf, success_args)
        log.log_end_col_group((id(ldf), ''), success_args)
        success_event = log.find_event((id(ldf), ''), success_args)
        if success_event is None or not success_event.completed:
            raise RuntimeError("Expected success event after executing maximal success args")
    except Exception:
        # Likely a row-dependent failure: compute minimal failing window first, then
        # execute success on the larger of the two complementary success windows.
        failing_expr_args = ExecutorArgs(
            columns=list(failing_columns),
            column_specific_expressions=False,
            include_hash=starting_args.include_hash,
            expressions=list(expr_fail_ev.args.expressions),
            row_start=None,
            row_end=None,
            extra={},
        )
        row_event_for_success = ExecutorLogEvent(dfi=(id(ldf), ''), args=failing_expr_args, start_time=now(), end_time=None, completed=False)
        rrb0 = RowRangeBisector(row_event_for_success, log, column_executor, ldf)
        rr_fail_ev0, _ = rrb0.run()
        s0, e0 = rr_fail_ev0.args.row_start or 0, rr_fail_ev0.args.row_end or total_rows
        left_size = s0
        right_size = total_rows - e0
        if left_size >= right_size:
            success_args.row_start, success_args.row_end = 0, s0
        else:
            success_args.row_start, success_args.row_end = e0, total_rows
        try:
            column_executor.execute(ldf, success_args)
            log.log_end_col_group((id(ldf), ''), success_args)
            success_event = log.find_event((id(ldf), ''), success_args)
            if success_event is None or not success_event.completed:
                success_event = col_success_ev
        except Exception:
            success_event = col_success_ev
    # If success_event still not set for any reason, fall back to column-level success
    if success_event is None:
        success_event = col_success_ev

    # Build minimal failure: reduce rows via RowRangeBisector then SamplingRowBisector
    minimal_fail_expr_args = ExecutorArgs(
        columns=list(failing_columns),
        column_specific_expressions=False,
        include_hash=starting_args.include_hash,
        expressions=list(expr_fail_ev.args.expressions),
        row_start=None,
        row_end=None,
        extra={},
    )
    row_event = ExecutorLogEvent(dfi=(id(ldf), ''), args=minimal_fail_expr_args, start_time=now(), end_time=None, completed=False)
    rrb = RowRangeBisector(row_event, log, column_executor, ldf)
    rr_fail_ev, _ = rrb.run()

    srb = SamplingRowBisector(rr_fail_ev, log, column_executor, ldf)
    final_fail_ev, _ = srb.run()

    return success_event, final_fail_ev


