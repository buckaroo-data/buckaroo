"""Xorq-backed stat pipeline for the v2 framework.

Two-phase execution:
  1. Batch aggregate — every @stat with an XorqColumn parameter contributes
     one ibis scalar expression. All such expressions across all columns
     are folded into a single ``table.aggregate(...)`` query and executed
     once.
  2. Per-column post-batch — computed stats (deps only on other stats) and
     XorqExpr-param stats (e.g. histograms that need their own query)
     run through the standard typed-DAG executor with results written into
     the per-column accumulator.

Errors are captured into ``StatError`` via the standard Ok/Err mechanism;
nothing is silently swallowed. Construction validates the DAG up front and
raises ``DAGConfigError`` on bad configurations.

Optional dependency: install with ``buckaroo[xorq]``.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from .col_analysis import ErrDict, SDType
from .safe_summary_df import output_full_reproduce
from .stat_func import XorqColumn, XorqExpr, XorqExecute, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import _execute_stat_func, _find_v1_class, _normalize_inputs
from .stat_result import Err, Ok, StatError, StatResult, resolve_accumulator
from .typed_dag import build_column_dag, build_typed_dag
from .utils import PERVERSE_DF

# Re-export marker types so users only need to import from this module.
__all__ = ["XorqStatPipeline", "XorqDfStatsV2", "XorqColumn", "XorqExpr", "XorqExecute"]

try:
    import xorq.api as xo

    HAS_XORQ = True
except ImportError:
    xo = None
    HAS_XORQ = False


def _to_python_scalar(val):
    """Coerce numpy/pandas scalars to native Python types.

    The DAG runs strict ``isinstance`` checks against the declared StatKey
    type. ``numpy.int64`` is not a subclass of ``int`` on NumPy >= 2, so
    aggregate results need coercion before they enter the accumulator.

    Also coalesces pandas missing-data singletons (``pd.NA``, ``pd.NaT``)
    to ``None`` — they don't have ``.item()`` and aren't valid scalar
    types, so without this they'd pass through unchanged and fail the
    isinstance check later. ``np.nan`` is left alone since it's a valid
    float and ``isinstance(np.nan, float)`` is True.
    """
    if val is None or val is pd.NA or val is pd.NaT:
        return None
    item = getattr(val, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            return val
    return val


def _is_batch_func(sf: StatFunc) -> bool:
    """A batch-phase func has an XorqColumn parameter and only raw/external deps.

    Such a function returns an ibis.Expr that the pipeline can fold into a
    single ``table.aggregate(...)`` call.
    """
    has_xorq_col = any(r.type is XorqColumn for r in sf.requires)
    if not has_xorq_col:
        return False
    for r in sf.requires:
        if r.type in RAW_MARKER_TYPES:
            continue
        # Any non-raw dep means we cannot run this in the pre-aggregate phase.
        return False
    return True


class XorqStatPipeline:
    """v2 stat pipeline for ``ibis.Table`` inputs.

    Accepts the same kinds of inputs as ``StatPipeline``:
      - ``StatFunc`` objects
      - ``@stat``-decorated functions
      - Stat-group classes
      - ``ColAnalysis`` subclasses (via v1 adapter)

    Use ``process_table(table)`` to run the pipeline; returns
    ``(SDType, List[StatError])``.
    """

    # Keys that the pipeline pre-populates per column. Listed as external
    # so the DAG validator doesn't require a stat to provide them, and so
    # that build_column_dag treats dependents as satisfied even when the
    # actual provider stat (e.g. ``min`` for numeric cols) is filtered
    # out by column_filter.
    EXTERNAL_KEYS = frozenset(
        {"orig_col_name", "rewritten_col_name", "dtype", "length", "min", "max",
         "distinct_count"})

    def __init__(self, stat_funcs: list, backend: Any = None, unit_test: bool = True,
                 cache_storage=None):
        if not HAS_XORQ:
            raise ImportError(
                "xorq is required for XorqStatPipeline. "
                "Install with: pip install buckaroo[xorq]")

        if backend is not None and cache_storage is not None:
            raise ValueError(
                "backend and cache_storage are mutually exclusive: "
                "pass one or the other, not both")

        self.all_stat_funcs = _normalize_inputs(stat_funcs)
        self._original_inputs = list(stat_funcs)
        self.backend = backend
        self.cache_storage = cache_storage

        # Validate the full DAG up front (raises DAGConfigError on misconfig).
        self.ordered_stat_funcs = build_typed_dag(
            self.all_stat_funcs, external_keys=self.EXTERNAL_KEYS)

        self._key_to_func: Dict[str, StatFunc] = {}
        for sf in self.ordered_stat_funcs:
            for sk in sf.provides:
                self._key_to_func[sk.name] = sf

        # Smoke-test against an ibis.memtable wrapping PERVERSE_DF — catches
        # dumb stat bugs (typos, wrong dtype assumptions) at construction
        # time. Result is captured, never raised, mirroring StatPipeline.
        if unit_test:
            self._unit_test_result = self.unit_test()

    @property
    def ordered_a_objs(self):
        """The original input list, preserved for DataFlow.add_analysis."""
        return list(self._original_inputs)

    def _execute(self, query):
        if self.backend is not None:
            return self.backend.execute(query)
        if self.cache_storage is not None:
            # On a cache HIT, read the snapshot parquet directly instead of
            # routing the query back through ``cache().execute()``. The latter
            # re-plans and re-executes the whole expression through DataFusion
            # just to reach the cached node — ~30ms for a single-table expr and
            # ~125ms for a join, versus ~1-3ms to read the result parquet. The
            # win compounds across the per-column histogram queries. calc_key /
            # storage.get_path are the same ParquetSnapshotCache API used by
            # ``_resolve_cached_nodes`` below.
            key = self.cache_storage.calc_key(query)
            path = self.cache_storage.storage.get_path(key)
            if os.path.exists(path):
                try:
                    return pd.read_parquet(path)
                except Exception:
                    pass  # corrupt/partial cache file — fall back to recompute
            return query.cache(cache=self.cache_storage).execute()
        return query.execute()

    def _maybe_materialize(self, table):
        """Materialize a lazy expression to a fresh base table.

        Lazy filter/clean chains (filt/clean scopes in the buckaroo
        dataflow) re-execute on every per-column query. With N columns
        and a histogram per column, that's N+1 filter evaluations.
        Materializing once turns each subsequent query into a simple
        table scan against an in-memory base table.

        Only runs for in-process xorq-datafusion backends. Remote
        backends would pay the cost of pulling all data over the wire.
        Returns (table_to_use, cleanup) where cleanup is (backend, name)
        for later drop, or None if no materialization happened.

        Skipped when a ``cache_storage`` is set: stat queries are then served
        from the per-expression snapshot cache, so the per-column filter
        re-evaluation this avoids never happens — and materializing would inject
        a ``__buckaroo_histo_mat_<uuid>`` table name into the expression token,
        breaking the content-addressed cache key on every load.
        """
        if self.cache_storage is not None:
            return table, None
        try:
            underlying = table._find_backend()
        except Exception:
            return table, None
        if "xorq_datafusion" not in type(underlying).__module__:
            return table, None
        # Skip when the table is already a base table on the backend —
        # materializing it again is pure overhead (full table read +
        # re-register) with no filter chain to amortize.
        try:
            from xorq.vendor.ibis.expr import operations as _ibis_ops
            if isinstance(table.op(), (_ibis_ops.DatabaseTable, _ibis_ops.InMemoryTable)):
                return table, None
        except Exception:
            pass
        # If no per-column work follows the batch aggregate (i.e. nothing
        # would re-execute the filter chain), materialization is just
        # wasted work — skip it.
        if not any(not _is_batch_func(sf) for sf in self.ordered_stat_funcs):
            return table, None
        name = f"__buckaroo_histo_mat_{uuid.uuid4().hex[:12]}"
        new_table = self._create_base_table(underlying, name, table)
        if new_table is None:
            return table, None
        return new_table, (underlying, name)

    def _create_base_table(self, underlying, name, table):
        """Land ``table`` as a base table on ``underlying``, or None on failure.

        Prefers the in-engine ``create_table(expr)`` path, which materialises
        in DataFusion without a pandas round-trip (~3-4× cheaper than
        ``execute()`` + ``create_table(df)``). That path compiles the
        expression to SQL, so an op with no translation rule — notably
        ``CachedNode`` from ``expr.cache()`` (the shape every catalog-diff
        comparison carries) — makes it raise. Two fallbacks recover that:

          1. Rewrite each ``CachedNode`` to a read of its on-disk cache file
             and retry in-engine — no transport, the join still runs once.
          2. Last resort, ``execute()`` to pandas and register the result.
             Correct for any expression but pays a full transport.
        """
        try:
            return underlying.create_table(name, table, overwrite=True)
        except Exception:
            pass
        rewritten = self._resolve_cached_nodes(table, underlying)
        if rewritten is not None:
            try:
                return underlying.create_table(name, rewritten, overwrite=True)
            except Exception:
                pass
        try:
            return underlying.create_table(name, table.execute(), overwrite=True)
        except Exception:
            return None

    @staticmethod
    def _resolve_cached_nodes(table, underlying):
        """Rewrite ``CachedNode``s in ``table`` to reads of their cache files.

        ``CachedNode`` has no SQL translation, but its cached result is a
        parquet on disk once materialised. Swapping each node for a
        ``read_parquet`` of that file yields an equivalent expression the SQL
        compiler can handle, keeping materialisation in-engine. Returns the
        rewritten expression, or None if there are no cached nodes or any
        cache file is missing (so the caller falls back to ``execute()``,
        which populates the cache).
        """
        try:
            from xorq.expr.relations import CachedNode
        except Exception:
            return None
        nodes = list(table.op().find(CachedNode))
        if not nodes:
            return None
        subs = {}
        for cn in nodes:
            try:
                path = cn.cache.storage.get_path(cn.cache.calc_key(cn.parent))
                if not Path(path).exists():
                    return None
                subs[cn] = underlying.read_parquet(str(path)).op()
            except Exception:
                return None
        try:
            return table.op().replace(subs).to_expr()
        except Exception:
            return None

    def unit_test(self) -> Tuple[bool, List[StatError]]:
        """Run pipeline against PERVERSE_DF wrapped as a xorq memtable.

        Mirrors ``StatPipeline.unit_test``. Returns ``(True, [])`` on a clean
        run; ``(False, errors)`` if any stat raised. A construction-time
        check that catches typos / wrong-dtype assumptions before real data
        hits the pipeline.

        Internal validation runs against the in-memory backend bound to
        ``xo.memtable`` regardless of whatever ``backend=`` the caller
        passed in — the user's backend is for their queries, not ours.
        """
        saved_backend = self.backend
        saved_cache = self.cache_storage
        self.backend = None
        self.cache_storage = None
        try:
            table = xo.memtable(PERVERSE_DF)
            _, errors = self.process_table(table)
            if not errors:
                return True, []
            return False, errors
        except Exception:
            return False, []
        finally:
            self.backend = saved_backend
            self.cache_storage = saved_cache

    def process_table(self, table, skip_columns=None) -> Tuple[SDType, List[StatError]]:
        materialized, cleanup = self._maybe_materialize(table)
        try:
            return self._process_table_impl(materialized, skip_columns=skip_columns)
        finally:
            if cleanup is not None:
                backend, name = cleanup
                try:
                    backend.drop_table(name)
                except Exception:
                    pass

    def _process_table_impl(self, table, skip_columns=None) -> Tuple[SDType, List[StatError]]:
        schema = table.schema()
        columns = list(table.columns)
        # Columns whose stats are supplied externally (via init_sd) keep their
        # structural metadata (name/dtype/length) but get no stat expressions
        # built — so the column's data is never scanned.
        skip = set(skip_columns or ())

        # Pre-populate every column accumulator with the externally-provided
        # keys. ``length`` is filled in by the batch query below. ``min`` /
        # ``max`` start as None so dependents (histogram) don't cascade-
        # exclude on non-numeric columns; ``min`` / ``max`` overwrite for
        # numeric cols. ``distinct_count`` likewise starts as None so float
        # columns (where the stat is column_filtered out) keep their
        # dependents (histogram, histogram_bins, distinct_per) runnable.
        accumulators: Dict[str, Dict[str, StatResult]] = {}
        for col in columns:
            accumulators[col] = {"orig_col_name": Ok(col), "rewritten_col_name": Ok(col), "dtype": Ok(str(schema[col])),
                "length": Ok(0), "min": Ok(None), "max": Ok(None), "distinct_count": Ok(None)}

        # ---- Phase 1: batch aggregate ----------------------------------
        # ``length`` is a table-level scalar (same value for every column),
        # so it goes in once as ``__total_length__`` rather than as N
        # per-column expressions.
        TOTAL_LENGTH_KEY = "__total_length__"
        batch_items: List[Tuple[str, StatFunc, Any]] = []
        for sf in self.ordered_stat_funcs:
            if not _is_batch_func(sf):
                continue
            xorq_col_param = next(r.name for r in sf.requires if r.type is XorqColumn)
            for col in columns:
                if col in skip:
                    continue
                col_dtype = schema[col]
                if sf.column_filter is not None and not sf.column_filter(col_dtype):
                    continue
                try:
                    expr = sf.func(**{xorq_col_param: table[col]})
                except Exception as e:
                    for sk in sf.provides:
                        accumulators[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col,
                            inputs={"col": col})
                    continue
                if expr is None:
                    continue
                stat_name = sf.provides[0].name
                try:
                    expr = expr.name(f"{col}|{stat_name}")
                except Exception as e:
                    for sk in sf.provides:
                        accumulators[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col,
                            inputs={"col": col})
                    continue
                batch_items.append((col, sf, expr))

        agg_exprs = [table.count().name(TOTAL_LENGTH_KEY)]
        agg_exprs.extend(e for _, _, e in batch_items)

        try:
            result_df = self._execute(table.aggregate(agg_exprs))
        except Exception as e:
            # Whole batch query failed — every batched stat reports the same root cause.
            # length stays at the prepopulated 0 so consumers still see something.
            for col, sf, _ in batch_items:
                for sk in sf.provides:
                    accumulators[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col, inputs={})
        else:
            total_length = _to_python_scalar(result_df[TOTAL_LENGTH_KEY].iloc[0])
            if total_length is None:
                total_length = 0
            for col in columns:
                accumulators[col]["length"] = Ok(total_length)
            for col, sf, _ in batch_items:
                stat_name = sf.provides[0].name
                col_stat = f"{col}|{stat_name}"
                if col_stat in result_df.columns:
                    raw_val = result_df[col_stat].iloc[0]
                    accumulators[col][stat_name] = Ok(_to_python_scalar(raw_val))
                else:
                    accumulators[col][stat_name] = Err(error=KeyError(
                        f"missing aggregate column {col_stat!r} in result"), stat_func_name=sf.name, column_name=col, inputs={})

        # ---- Phase 2: per-column post-batch ----------------------------
        all_errors: List[StatError] = []
        summary: SDType = {}

        for col in columns:
            col_accum = accumulators[col]
            col_dtype = schema[col]
            col_funcs = build_column_dag(self.all_stat_funcs, col_dtype, external_keys=self.EXTERNAL_KEYS)

            for sf in col_funcs if col not in skip else []:
                # Skip stats whose results are already in the accumulator
                # (typically the batch-phase stats).
                if sf.provides and all(sk.name in col_accum for sk in sf.provides):
                    continue
                _execute_stat_func(sf, col_accum, col, raw_series=None, sampled_series=None, raw_dataframe=None,
                    xorq_expr=table, xorq_execute=self._execute)

            col_key_to_func: Dict[str, StatFunc] = {}
            for sf in col_funcs:
                for sk in sf.provides:
                    col_key_to_func[sk.name] = sf

            plain, errors = resolve_accumulator(col_accum, col, col_key_to_func)
            summary[col] = plain
            all_errors.extend(errors)

        return summary, all_errors

    def add_stat(self, stat_func_or_class) -> Tuple[bool, List[StatError]]:
        """Add a stat function or ColAnalysis class interactively.

        Mirrors ``StatPipeline.add_stat`` for parity with the v1-compat
        DfStats surface, but skips the PERVERSE_DF unit-test (no ibis
        equivalent yet — there's no perverse ibis.Table to validate
        against). Validates the DAG; returns ``(True, [])`` on success
        or ``(False, [config_error])`` if the DAG can't be built.
        """
        new_inputs = list(self._original_inputs)

        if isinstance(stat_func_or_class, type):
            new_inputs = [
                inp
                for inp in new_inputs
                if not (
                    isinstance(inp, type)
                    and inp.__name__ == stat_func_or_class.__name__
                )
            ]
        new_inputs.append(stat_func_or_class)

        try:
            new_funcs = _normalize_inputs(new_inputs)
            new_ordered = build_typed_dag(new_funcs, external_keys=self.EXTERNAL_KEYS)
        except Exception as e:
            return False, [
                StatError(column="<dag>", stat_key="<config>", error=e, stat_func=None)]

        self.all_stat_funcs = new_funcs
        self.ordered_stat_funcs = new_ordered
        self._original_inputs = new_inputs
        self._key_to_func = {}
        for sf in self.ordered_stat_funcs:
            for sk in sf.provides:
                self._key_to_func[sk.name] = sf

        return True, []

    def process_table_v1_compat(self, table, skip_columns=None) -> Tuple[SDType, ErrDict]:
        """Run process_table and convert errors to v1 ErrDict shape.

        Used by XorqDfStatsV2 / DataFlow consumers expecting the same
        ``{(col, stat): (Exception, kls)}`` shape that AnalysisPipeline
        produced.
        """
        summary, errors = self.process_table(table, skip_columns=skip_columns)
        errs: ErrDict = {}
        for se in errors:
            kls = _find_v1_class(se.stat_func, self._original_inputs) if se.stat_func else None
            err_key = (se.column, se.stat_func.name if se.stat_func else "unknown")
            errs[err_key] = (se.error, kls)
        return summary, errs


class XorqDfStatsV2:
    """Drop-in DfStats wrapper for xorq table inputs.

    Mirrors the ``DfStatsV2`` / ``PlDfStatsV2`` surface (``.sdf``, ``.errs``,
    ``.ap.ordered_a_objs``, ``verify_analysis_objects``) so DataFlow,
    ``CustomizableDataflow`` and any other DfStats consumer can run
    against a xorq table without changes.

    Lives in this module (not ``df_stats_v2``) so importing
    ``buckaroo.pluggable_analysis_framework.df_stats_v2`` doesn't transitively
    require xorq — installs without ``buckaroo[xorq]`` keep working.

    Stats execute through ``XorqStatPipeline`` — a single batched
    ``table.aggregate(...)`` query plus per-column histogram queries —
    pushing computation to the backend instead of materialising the
    entire table.
    """

    @classmethod
    def verify_analysis_objects(cls, objs):
        # unit_test=False to skip the per-widget PERVERSE_DF pipeline run
        # (issue #709). DAG validation still runs as part of __init__.
        XorqStatPipeline(objs, unit_test=False)

    def __init__(self, table, col_analysis_objs, operating_df_name=None, debug=False,
                 cache_storage=None, skip_columns=None):
        self.table = table
        # Skip the unit_test PERVERSE_DF run on each widget construction —
        # it doubles the SQL query count (issue #709). The DAG-validation
        # cost is already paid by verify_analysis_objects on first set up
        # and by the test suite. Mirrors PlDfStatsV2.
        self.ap = XorqStatPipeline(col_analysis_objs, unit_test=False,
            cache_storage=cache_storage)
        self.operating_df_name = operating_df_name
        self.debug = debug
        self.sdf, self.errs = self.ap.process_table_v1_compat(self.table, skip_columns=skip_columns)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        """Add an analysis class/stat func and reprocess the table.

        Matches the contract of DfStatsV2.add_analysis / PlDfStatsV2.add_analysis
        so DataFlow.add_analysis works against a xorq-backed stats wrapper.
        """
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.errs = self.ap.process_table_v1_compat(self.table)
        _, self.stat_errors = self.ap.process_table(self.table)
        if not passed:
            print("DAG validation failed")
        if self.errs:
            print("Errors on original table")
        if errors or self.stat_errors:
            for err in errors + self.stat_errors:
                if err.stat_func is not None:
                    print(err.reproduce_code())
