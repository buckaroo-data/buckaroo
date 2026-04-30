"""Ibis-backed stat pipeline for the v2 framework.

Two-phase execution:
  1. Batch aggregate — every @stat with an IbisColumn parameter contributes
     one ibis scalar expression. All such expressions across all columns
     are folded into a single ``table.aggregate(...)`` query and executed
     once.
  2. Per-column post-batch — computed stats (deps only on other stats) and
     IbisTable-param stats (e.g. histograms that need their own query)
     run through the standard typed-DAG executor with results written into
     the per-column accumulator.

Errors are captured into ``StatError`` via the standard Ok/Err mechanism;
nothing is silently swallowed. Construction validates the DAG up front and
raises ``DAGConfigError`` on bad configurations.

Optional dependency: install with ``buckaroo[xorq]``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .col_analysis import SDType
from .stat_func import IbisColumn, IbisTable, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import _execute_stat_func, _normalize_inputs
from .stat_result import Err, Ok, StatError, StatResult, resolve_accumulator
from .typed_dag import build_column_dag, build_typed_dag

# Re-export marker types so users only need to import from this module.
__all__ = ["IbisStatPipeline", "IbisColumn", "IbisTable"]

try:
    import ibis  # noqa: F401

    HAS_IBIS = True
except ImportError:
    HAS_IBIS = False


def _to_python_scalar(val):
    """Coerce numpy/pandas scalars to native Python types.

    The DAG runs strict ``isinstance`` checks against the declared StatKey
    type. ``numpy.int64`` is not a subclass of ``int`` on NumPy >= 2, so
    aggregate results need coercion before they enter the accumulator.
    """
    if val is None:
        return None
    item = getattr(val, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            return val
    return val


def _is_batch_func(sf: StatFunc) -> bool:
    """A batch-phase func has an IbisColumn parameter and only raw/external deps.

    Such a function returns an ibis.Expr that the pipeline can fold into a
    single ``table.aggregate(...)`` call.
    """
    has_ibis_col = any(r.type is IbisColumn for r in sf.requires)
    if not has_ibis_col:
        return False
    for r in sf.requires:
        if r.type in RAW_MARKER_TYPES:
            continue
        # Any non-raw dep means we cannot run this in the pre-aggregate phase.
        return False
    return True


class IbisStatPipeline:
    """v2 stat pipeline for ``ibis.Table`` inputs.

    Accepts the same kinds of inputs as ``StatPipeline``:
      - ``StatFunc`` objects
      - ``@stat``-decorated functions
      - Stat-group classes
      - ``ColAnalysis`` subclasses (via v1 adapter)

    Use ``process_table(table)`` to run the pipeline; returns
    ``(SDType, List[StatError])``.
    """

    EXTERNAL_KEYS = frozenset({"orig_col_name", "rewritten_col_name", "dtype"})

    def __init__(self, stat_funcs: list, backend: Any = None):
        if not HAS_IBIS:
            raise ImportError(
                "ibis-framework is required for IbisStatPipeline. "
                "Install with: pip install buckaroo[xorq]"
            )

        self.all_stat_funcs = _normalize_inputs(stat_funcs)
        self._original_inputs = list(stat_funcs)
        self.backend = backend

        # Validate the full DAG up front (raises DAGConfigError on misconfig).
        self.ordered_stat_funcs = build_typed_dag(
            self.all_stat_funcs, external_keys=self.EXTERNAL_KEYS
        )

        self._key_to_func: Dict[str, StatFunc] = {}
        for sf in self.ordered_stat_funcs:
            for sk in sf.provides:
                self._key_to_func[sk.name] = sf

    def _execute(self, query):
        if self.backend is not None:
            return self.backend.execute(query)
        return query.execute()

    def process_table(self, table) -> Tuple[SDType, List[StatError]]:
        schema = table.schema()
        columns = list(table.columns)

        accumulators: Dict[str, Dict[str, StatResult]] = {}
        for col in columns:
            accumulators[col] = {
                "orig_col_name": Ok(col),
                "rewritten_col_name": Ok(col),
                "dtype": Ok(str(schema[col])),
            }

        # ---- Phase 1: batch aggregate ----------------------------------
        batch_items: List[Tuple[str, StatFunc, Any]] = []
        for sf in self.ordered_stat_funcs:
            if not _is_batch_func(sf):
                continue
            ibis_col_param = next(r.name for r in sf.requires if r.type is IbisColumn)
            for col in columns:
                col_dtype = schema[col]
                if sf.column_filter is not None and not sf.column_filter(col_dtype):
                    continue
                try:
                    expr = sf.func(**{ibis_col_param: table[col]})
                except Exception as e:
                    for sk in sf.provides:
                        accumulators[col][sk.name] = Err(
                            error=e,
                            stat_func_name=sf.name,
                            column_name=col,
                            inputs={"col": col},
                        )
                    continue
                if expr is None:
                    continue
                stat_name = sf.provides[0].name
                try:
                    expr = expr.name(f"{col}|{stat_name}")
                except Exception as e:
                    for sk in sf.provides:
                        accumulators[col][sk.name] = Err(
                            error=e,
                            stat_func_name=sf.name,
                            column_name=col,
                            inputs={"col": col},
                        )
                    continue
                batch_items.append((col, sf, expr))

        if batch_items:
            agg_exprs = [e for _, _, e in batch_items]
            try:
                result_df = self._execute(table.aggregate(agg_exprs))
            except Exception as e:
                # Whole batch query failed — every batched stat reports the same root cause.
                for col, sf, _ in batch_items:
                    for sk in sf.provides:
                        accumulators[col][sk.name] = Err(
                            error=e,
                            stat_func_name=sf.name,
                            column_name=col,
                            inputs={},
                        )
            else:
                for col, sf, _ in batch_items:
                    stat_name = sf.provides[0].name
                    col_stat = f"{col}|{stat_name}"
                    if col_stat in result_df.columns:
                        raw_val = result_df[col_stat].iloc[0]
                        accumulators[col][stat_name] = Ok(_to_python_scalar(raw_val))
                    else:
                        accumulators[col][stat_name] = Err(
                            error=KeyError(
                                f"missing aggregate column {col_stat!r} in result"
                            ),
                            stat_func_name=sf.name,
                            column_name=col,
                            inputs={},
                        )

        # ---- Phase 2: per-column post-batch ----------------------------
        all_errors: List[StatError] = []
        summary: SDType = {}

        for col in columns:
            col_accum = accumulators[col]
            col_dtype = schema[col]
            col_funcs = build_column_dag(
                self.all_stat_funcs,
                col_dtype,
                external_keys=self.EXTERNAL_KEYS,
            )

            for sf in col_funcs:
                # Skip stats whose results are already in the accumulator
                # (typically the batch-phase stats).
                if sf.provides and all(sk.name in col_accum for sk in sf.provides):
                    continue
                _execute_stat_func(
                    sf,
                    col_accum,
                    col,
                    raw_series=None,
                    sampled_series=None,
                    raw_dataframe=None,
                    ibis_table=table,
                )

            col_key_to_func: Dict[str, StatFunc] = {}
            for sf in col_funcs:
                for sk in sf.provides:
                    col_key_to_func[sk.name] = sf

            plain, errors = resolve_accumulator(col_accum, col, col_key_to_func)
            summary[col] = plain
            all_errors.extend(errors)

        return summary, all_errors
