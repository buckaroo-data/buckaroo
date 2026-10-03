"""Polars-backed stat pipeline for the v2 framework.

Two-phase execution, the polars twin of ``XorqStatPipeline`` (#999):
  1. Batch select — every @stat with a ``PlColumn`` parameter contributes
     one ``pl.Expr`` per column its column_filter accepts. All of them run
     in a single ``frame.select(...)``, so polars evaluates every column in
     parallel, and a ``LazyFrame`` (``pl.scan_parquet``) works unchanged.
  2. Per-column — ``RawSeries`` stats and computed stats run through the
     standard typed-DAG executor with the batch values already in the
     accumulator (via ``initial_stats``).

A ``@stat(max_rows=N)`` stat is skipped on a frame with more than N rows,
in either phase, and its dependents cascade out; ``StatPipeline.process_column``
reports the keys as ``NOT_COMPUTED`` and ``gated_keys`` lists them per run.

Optional dependency: install with ``buckaroo[polars]``.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from buckaroo.df_util import to_chars

from .col_analysis import SDType
from .stat_func import PlColumn, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import StatPipeline, collect_gated_keys
from .stat_result import Err, Ok, StatError, StatResult
from .typed_dag import DAGConfigError, row_gated
from .utils import PERVERSE_DF

__all__ = ["PolarsStatPipeline", "PlColumn"]

try:
    import polars as pl

    HAS_POLARS = True
except ImportError:
    pl = None
    HAS_POLARS = False


def _is_batch_func(sf: StatFunc) -> bool:
    """A batch-phase func has a PlColumn parameter and only raw/external deps.

    Such a function returns a ``pl.Expr`` the pipeline can fold into the one
    ``select``; a non-raw dep would need another stat's value first.
    """
    if not any(r.type is PlColumn for r in sf.requires):
        return False
    return all(r.type in RAW_MARKER_TYPES for r in sf.requires)


class PolarsStatPipeline(StatPipeline):
    """``StatPipeline`` for polars frames, with the batch-select phase.

    Accepts the same inputs as ``StatPipeline``. ``process_df`` takes a
    ``pl.DataFrame`` or a ``pl.LazyFrame``.
    """

    def __init__(self, stat_funcs: list, unit_test: bool = True, record_timings: Optional[bool] = None):
        if not HAS_POLARS:
            raise ImportError(
                "polars is required for PolarsStatPipeline. "
                "Install with: pip install buckaroo[polars]")
        super().__init__(stat_funcs, unit_test=unit_test, record_timings=record_timings)
        for sf in self._batch_funcs():
            if len(sf.provides) != 1:
                raise DAGConfigError(
                    f"'{sf.name}' takes a PlColumn and must provide exactly one key, "
                    f"got {[sk.name for sk in sf.provides]}")

    def _batch_funcs(self) -> List[StatFunc]:
        # Not cached: add_stat replaces ordered_stat_funcs.
        return [sf for sf in self.ordered_stat_funcs if _is_batch_func(sf)]

    def unit_test(self) -> Tuple[bool, List[StatError]]:
        """Test the pipeline against PERVERSE_DF as a polars frame."""
        self._suppress_perf_summary = True
        try:
            _, errors = self.process_df(pl.from_pandas(PERVERSE_DF))
            if not errors:
                return True, []
            return False, errors
        except Exception:
            return False, []
        finally:
            self._suppress_perf_summary = False

    # ---- Phase 1: batch select ----------------------------------------

    def _run_batch(self, lf, schema, columns: List[str], row_count: int,
            funcs: Optional[List[StatFunc]] = None) -> Dict[str, Dict[str, StatResult]]:
        """Evaluate every batch stat for every column in one select.

        Returns ``{column: {stat_key: Ok | Err}}``; a column_filter'd or
        row-gated stat leaves no key. If the one select fails, each column's
        expressions are retried on their own, so one bad column doesn't blank
        the rest.
        """
        results: Dict[str, Dict[str, StatResult]] = {col: {} for col in columns}
        items: List[Tuple[str, StatFunc, Any]] = []
        for sf in (funcs if funcs is not None else self._batch_funcs()):
            if row_gated(sf, row_count):
                continue
            param = next(r.name for r in sf.requires if r.type is PlColumn)
            key = sf.provides[0].name
            for col in columns:
                dtype = schema[col]
                if sf.column_filter is not None and not sf.column_filter(dtype):
                    continue
                try:
                    expr = sf.func(**{param: PlColumn(col, dtype, pl.col(col))})
                    if expr is None:
                        continue
                    expr = expr.alias(f"{len(items)}")
                except Exception as e:
                    results[col][key] = Err(error=e, stat_func_name=sf.name, column_name=col, inputs={'col': col})
                    continue
                items.append((col, sf, expr))
        if not items:
            return results

        t0 = time.perf_counter()
        try:
            self._assign(results, items, lf.select([e for _, _, e in items]).collect().row(0))
        except Exception:
            for col in columns:
                col_items = [it for it in items if it[0] == col]
                if not col_items:
                    continue
                try:
                    self._assign(results, col_items, lf.select([e for _, _, e in col_items]).collect().row(0))
                except Exception as e:
                    for _, sf, _ in col_items:
                        results[col][sf.provides[0].name] = Err(error=e, stat_func_name=sf.name, column_name=col,
                            inputs={'col': col})
        if self.record_timings:
            self.timings.append(('<batch>', 'pl_batch_select', time.perf_counter() - t0))
        return results

    @staticmethod
    def _assign(results, items, row) -> None:
        for (col, sf, _), val in zip(items, row):
            results[col][sf.provides[0].name] = Ok(val)

    # ---- Phase 2: per column -------------------------------------------

    @staticmethod
    def _series(df, lf, name: str):
        if isinstance(df, pl.DataFrame):
            return df.get_column(name)
        return lf.select(name).collect().to_series()

    def process_column(self, column_name: str, column_dtype, raw_series=None, sampled_series=None, raw_dataframe=None,
            initial_stats: Optional[Dict[str, Any]] = None, row_count: Optional[int] = None) -> Tuple[Dict[str, Any], List[StatError]]:
        """Process one column. A batch stat whose key isn't in
        ``initial_stats`` is evaluated on ``raw_series`` first, so a single
        ``pl.Series`` can be run through the whole DAG."""
        initial = dict(initial_stats or {})
        if raw_series is not None and isinstance(raw_series, pl.Series):
            if row_count is None:
                row_count = len(raw_series)
            missing = [sf for sf in self._batch_funcs() if sf.provides[0].name not in initial]
            if missing:
                lf = raw_series.to_frame().lazy()
                batch = self._run_batch(lf, lf.collect_schema(), [raw_series.name], row_count, funcs=missing)
                initial.update(batch[raw_series.name])
        return super().process_column(column_name, column_dtype, raw_series=raw_series, sampled_series=sampled_series,
            raw_dataframe=raw_dataframe, initial_stats=initial, row_count=row_count)

    def process_df(self, df, debug: bool = False, skip_columns=None) -> Tuple[SDType, List[StatError]]:
        """Process all columns of a ``pl.DataFrame`` or ``pl.LazyFrame``.

        ``skip_columns`` as in ``StatPipeline.process_df``: those columns get
        structural metadata only, and no batch expression is built for them.

        A pandas frame (DataFlow's error frames are pandas on every backend)
        is converted; one polars can't convert takes the per-series path.
        """
        if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
            try:
                df = pl.from_pandas(df)
            except Exception:
                return super().process_df(df, debug=debug, skip_columns=skip_columns)
        lf = df.lazy()
        schema = lf.collect_schema()
        if len(schema) == 0:
            return {}, []
        row_count = df.height if isinstance(df, pl.DataFrame) else lf.select(pl.len()).collect().item()
        if row_count == 0:
            return {}, []

        if self.record_timings:
            self.timings = []

        skip = set(skip_columns or ())
        columns = [(name, to_chars(i)) for i, name in enumerate(schema.names())]
        batch_cols = [orig for orig, rewritten in columns if orig not in skip and rewritten not in skip]
        batch = self._run_batch(lf, schema, batch_cols, row_count)

        summary: SDType = {}
        all_errors: List[StatError] = []
        for orig_col_name, rewritten_col_name in columns:
            if orig_col_name not in batch:
                summary[rewritten_col_name] = {
                    'orig_col_name': orig_col_name, 'rewritten_col_name': rewritten_col_name}
                continue
            ser = self._series(df, lf, orig_col_name)
            initial: Dict[str, Any] = {'orig_col_name': orig_col_name, 'rewritten_col_name': rewritten_col_name}
            initial.update(batch[orig_col_name])
            # StatPipeline.process_column directly: the batch is done, and the
            # override would rebuild it for any column_filter'd key.
            col_result, col_errors = StatPipeline.process_column(self, column_name=rewritten_col_name,
                column_dtype=schema[orig_col_name], raw_series=ser, sampled_series=ser, raw_dataframe=df,
                initial_stats=initial, row_count=row_count)
            summary[rewritten_col_name] = col_result
            all_errors.extend(col_errors)

        self.gated_keys = collect_gated_keys(summary)
        self._perf_summary(row_count, summary)
        return summary, all_errors
