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

import logging
import os
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Tuple

import pandas as pd

from . import perf_log
from .col_analysis import SDType
from .safe_summary_df import output_full_reproduce
from .stat_func import XorqColumn, XorqExpr, XorqExecute, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import _execute_stat_func, _normalize_inputs, errors_to_errdict
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

log = logging.getLogger(__name__)


def _new_cache_run_stats() -> Dict[str, Any]:
    """Per-``process_table``-run counters for the snapshot cache.

    Reset at the start of every run and summarised in one log line at the
    end (see ``_log_cache_stats``)."""
    return {"hits": 0, "misses": 0, "snapshots": 0, "bytes": 0,
        "write_errors": 0, "secs": 0.0}


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

        # Per-run snapshot-cache counters, (re)initialised in process_table.
        # Set here so the attribute always exists (e.g. for the unit_test()
        # run kicked off below, which disables the cache).
        self._cache_stats = _new_cache_run_stats()
        # Per-run perf recorder, (re)initialised in process_table when the
        # BUCKAROO_PERF toggle is on; None otherwise.
        self._perf = None
        # Set during the unit_test() DAG self-check so its PERVERSE_DF run
        # stays out of the perf log.
        self._suppress_perf_summary = False

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
            return self._execute_cached(query)
        return query.execute()

    def _execute_cached(self, query):
        """Serve ``query`` from the per-expression snapshot cache.

        HIT: read the snapshot parquet directly rather than routing the query
        back through ``cache().execute()``. The latter re-plans and re-executes
        the whole expression through DataFusion just to reach the cached node —
        ~30ms for a single-table expr and ~125ms for a join, versus ~1-3ms to
        read the result parquet. The win compounds across the per-column
        histogram queries.

        MISS: execute ``query`` and write the snapshot ourselves. The cache key
        is content-addressed on ``query`` as built against the source expression
        (the same key the next process gets), so warm loads stay portable. The
        result is written with pandas (the same reader the HIT path uses); these
        stat-result snapshots are read back only via ``pd.read_parquet`` here,
        never through xorq's cache layer.
        """
        key = self.cache_storage.calc_key(query)
        path = self.cache_storage.storage.get_path(key)
        if os.path.exists(path):
            try:
                result = pd.read_parquet(path)
                self._cache_stats["hits"] += 1
                return result
            except Exception:
                pass  # corrupt/partial cache file — fall back to recompute
        self._cache_stats["misses"] += 1
        result = query.execute()
        self._write_snapshot(path, result)
        return result

    def _write_snapshot(self, path, result_df):
        """Write a stat result to its snapshot path, atomically.

        Writes a temp file and renames so a crash mid-write can't leave a
        truncated parquet the HIT path would later read as a corrupt cache.
        Write failures are counted and logged — never silent (#910)."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            result_df.to_parquet(tmp, index=False)
            tmp.rename(path)
            self._cache_stats["snapshots"] += 1
            self._cache_stats["bytes"] += path.stat().st_size
        except Exception as e:
            self._cache_stats["write_errors"] += 1
            log.warning("xorq stat snapshot write failed for %s: %s", path, e)

    def _log_cache_stats(self, span=None):
        """Surface the per-run snapshot-cache outcome (#910, #951).

        Two channels, so the write side is never invisible:

        * ``span`` — attach the hit/miss/snapshot/byte/write-error counts to the
          run's ``stat.xorq.total`` telemetry span. A bound telemetry sink then
          carries the cache outcome (including ``write_errors``) to the operator
          without a debug log build — the ``log.info`` line below lands in a
          server log file no deployment reads (#951).
        * ``log`` — one summary line per run for a local perf/debug session."""
        if self.cache_storage is None:
            return
        s = self._cache_stats
        if span is not None:
            cs = self.cache_run_stats()
            span.set_attr(
                cache_status=cs["status"], cache_hits=cs["hits"],
                cache_misses=cs["misses"], cache_secs=cs["secs"],
                cache_snapshots=cs["snapshots"], cache_bytes=cs["bytes"],
                cache_write_errors=cs["write_errors"])
        base_path = getattr(getattr(self.cache_storage, "storage", None), "base_path", "?")
        log.info(
            "xorq stat cache [%s]: %d hit(s), %d miss(es), %d snapshot(s) "
            "written (%d bytes), %d write error(s) in %.3fs",
            base_path, s["hits"], s["misses"], s["snapshots"], s["bytes"],
            s["write_errors"], s.get("secs", 0.0))

    def cache_run_stats(self) -> Dict[str, Any]:
        """Public snapshot of the last ``process_table`` run's summary-stat
        cache outcome — the structured signal a telemetry consumer wants (#943).

        ``{hits, misses, snapshots, bytes, write_errors, secs, cached, status}``
        where ``status`` is ``hit`` / ``miss`` / ``mixed`` / ``none`` for a run
        that used the snapshot cache, and ``uncached`` when no cache was
        configured. ``secs`` is the wall-clock of the whole stats run.
        """
        s = dict(self._cache_stats)
        cached = self.cache_storage is not None
        hits, misses = s.get("hits", 0), s.get("misses", 0)
        if not cached:
            status = "uncached"
        elif hits and misses:
            status = "mixed"
        elif hits:
            status = "hit"
        elif misses:
            status = "miss"
        else:
            status = "none"
        s["cached"] = cached
        s["status"] = status
        return s

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
        # The PERVERSE_DF self-check is not a real data pull — keep it out of
        # the perf log (spans and summary).
        self._suppress_perf_summary = True
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
            self._suppress_perf_summary = False

    def _span(self, label, **fields):
        """perf_span for this run unless it's a unit-test validation run.

        perf_span itself decides whether to time and emit (perf logging on *or* a
        telemetry sink bound — see ``perf_log.perf_span``); this only adds the
        unit-test suppression. Deferring the gate keeps ``stat.xorq.*`` spans on
        the same enabled-OR-sink footing as the ``firstpull.*`` spans, so a
        telemetry-only run (BUCKAROO_PERF off, sink bound) still emits the stats
        timeline (#944)."""
        if self._suppress_perf_summary:
            return nullcontext()
        return perf_log.perf_span(label, **fields)

    def process_table(self, table, skip_columns=None) -> Tuple[SDType, List[StatError]]:
        # Each per-column query runs directly against ``table`` (the source
        # expression). When a snapshot cache is set, queries are keyed against
        # that source so the content-addressed key is stable across processes;
        # ``_execute_cached`` serves a hit from the snapshot parquet or executes
        # and writes one on a miss.
        self._cache_stats = _new_cache_run_stats()
        self._perf = (perf_log.PerfRecorder()
                      if perf_log.enabled() and not self._suppress_perf_summary else None)
        _t0 = time.perf_counter()
        with self._span("stat.xorq.total") as span:
            try:
                return self._process_table_impl(table, skip_columns=skip_columns)
            finally:
                self._cache_stats["secs"] = round(time.perf_counter() - _t0, 4)
                self._log_cache_stats(span)
                if self._perf is not None:
                    self._perf.label = (
                        f"xorq cols={len(table.columns)} "
                        f"cache_hits={self._cache_stats['hits']} "
                        f"misses={self._cache_stats['misses']}")
                    self._perf.summary()

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
            with self._span("stat.xorq.batch_aggregate", n_stats=len(batch_items)):
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
                if self._perf is not None:
                    t0 = time.perf_counter()
                _execute_stat_func(sf, col_accum, col, raw_series=None, sampled_series=None, raw_dataframe=None,
                    xorq_expr=table, xorq_execute=self._execute)
                if self._perf is not None:
                    self._perf.record("xorq/per-column", col, sf.name, time.perf_counter() - t0)

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

        Mirrors ``StatPipeline.add_stat`` for parity with the stats-wrapper
        surface, but skips the PERVERSE_DF unit-test (no ibis
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

class XorqDfStatsV2:
    """Stats wrapper for xorq table inputs.

    Mirrors the ``DfStatsV2`` / ``PlDfStatsV2`` surface (``.sdf``, ``.errs``,
    ``.ap.ordered_a_objs``, ``verify_analysis_objects``) so DataFlow,
    ``CustomizableDataflow`` and any other stats consumer can run
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
        self.sdf, errors = self.ap.process_table(self.table, skip_columns=skip_columns)
        self.errs = errors_to_errdict(errors)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def cache_run_stats(self) -> dict:
        """The summary-stat cache outcome of the last pipeline run (#943) —
        the structured hit/miss/timing signal, delegating to
        ``XorqStatPipeline.cache_run_stats`` for a consumer reading from the
        stats wrapper."""
        return self.ap.cache_run_stats()

    def add_analysis(self, a_obj):
        """Add an analysis class/stat func and reprocess the table.

        Matches the contract of DfStatsV2.add_analysis / PlDfStatsV2.add_analysis
        so DataFlow.add_analysis works against a xorq-backed stats wrapper.
        """
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.stat_errors = self.ap.process_table(self.table)
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("DAG validation failed")
        if self.errs:
            print("Errors on original table")
        if errors or self.stat_errors:
            for err in errors + self.stat_errors:
                if err.stat_func is not None:
                    print(err.reproduce_code())
