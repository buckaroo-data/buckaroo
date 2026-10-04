"""Xorq-backed stat pipeline for the v2 framework.

Two-phase execution, each phase a kind of resumable unit (see ``stat_units``):
  1. Batch aggregate — every @stat with an XorqColumn parameter contributes
     one ibis scalar expression. All such expressions across all columns
     are folded into a single ``table.aggregate(...)`` query and executed
     once. This is the ``batch`` unit, and it also computes the stats that
     are pure functions of its results (``histogram_bins``, ``nan_per``...).
     Behind a host's opt-in the batch can be cut into one aggregate per chunk
     of columns (``chunk_cells``), for a plain parquet scan only.
  2. Per-column post-batch — XorqExpr-param stats (e.g. histograms that need
     their own query), and any stat reading one, run through the standard
     typed-DAG executor with results written into the per-column
     accumulator. One ``histogram:<col>`` unit per column.

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from . import perf_log
from .col_analysis import SDType
from .safe_summary_df import output_full_reproduce
from .stat_func import XorqColumn, XorqExpr, XorqExecute, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import _execute_stat_func, _normalize_inputs, errors_to_errdict
from .stat_result import Err, Ok, StatError, StatResult, resolve_accumulator
from .stat_units import (Fragment, StatAccumulator, StatState, StatUnit, UnitPipeline, UnitStats, columns_in_scope,
    prioritized)
from .typed_dag import build_column_dag, build_typed_dag
from .utils import PERVERSE_DF

# Re-export marker types so users only need to import from this module.
__all__ = ["XorqStatPipeline", "XorqDfStatsV2", "XorqColumn", "XorqExpr", "XorqExecute"]

try:
    import xorq.api as xo
    from xorq.expr.relations import Read
    from xorq.vendor.ibis.expr import operations as ops

    HAS_XORQ = True
except ImportError:
    xo = Read = ops = None
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


class XorqAccumulator(StatAccumulator):
    """``StatAccumulator`` for a xorq run. ``working`` holds each column's
    Ok/Err accumulator, which the units read and write; ``emitted`` the keys of
    it already returned in a fragment, so each stat is returned and any error in
    it reported once; ``phases`` caches how each dtype's stats split (see
    ``XorqStatPipeline._column_phases``). ``sd()`` is every column's stats so
    far in accumulator order, a failed stat as None."""

    def __init__(self, state: StatState, columns: Sequence[Any] = (), rewritten: Optional[Dict[Any, str]] = None,
            skipped: Sequence[Any] = ()):
        super().__init__(state, columns, rewritten)
        self.skipped: Tuple[Any, ...] = tuple(skipped)
        self.working: Dict[Any, Dict[str, StatResult]] = {}
        self.emitted: Dict[Any, set] = {}
        self.phases: Dict[Any, Any] = {}
        self.schema: Any = None

    def sd(self) -> Dict[Any, Dict[str, Any]]:
        return {col: {key: (result.value if isinstance(result, Ok) else None if isinstance(result, Err) else result)
            for key, result in self.working[col].items()} for col in self.order}


class XorqStatPipeline(UnitPipeline):
    """v2 stat pipeline for ``ibis.Table`` inputs.

    Accepts the same kinds of inputs as ``StatPipeline``:
      - ``StatFunc`` objects
      - ``@stat``-decorated functions
      - Stat-group classes
      - ``ColAnalysis`` subclasses (via v1 adapter)

    Use ``process_table(table)`` to run the pipeline; returns
    ``(SDType, List[StatError])``. ``plan(state)``, ``new_accumulator(state)``
    and ``run(unit, acc)`` are the same run one unit at a time.

    ``chunk_cells`` (off when ``None``) cuts the batch aggregate into one
    aggregate per chunk of columns holding about that many cells, when the
    caller gives the row count and the source is a plain parquet scan
    (``chunk_refusal``).
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
                 cache_storage=None, chunk_cells: Optional[int] = None):
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
        self.chunk_cells = chunk_cells

        # Per-run snapshot-cache counters, (re)initialised in new_accumulator.
        # Set here so the attribute always exists (e.g. for the unit_test()
        # run kicked off below, which disables the cache).
        self._cache_stats = _new_cache_run_stats()
        # Per-run perf recorder, (re)initialised in new_accumulator when the
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

    def process_table(self, table, skip_columns=None, rows=None) -> Tuple[SDType, List[StatError]]:
        # Each per-column query runs directly against ``table`` (the source
        # expression). When a snapshot cache is set, queries are keyed against
        # that source so the content-addressed key is stable across processes;
        # ``_execute_cached`` serves a hit from the snapshot parquet or executes
        # and writes one on a miss. ``rows`` is the row count when the caller
        # has it; only the column-chunk split reads it.
        state = StatState(table, frozenset(skip_columns or ()), rows=rows)
        acc = self.new_accumulator(state)
        _t0 = time.perf_counter()
        with self._span("stat.xorq.total") as span:
            try:
                for _unit, _fragment in self.iter_units(state, acc):
                    pass
                return acc.sd(), acc.errors
            finally:
                self._cache_stats["secs"] = round(time.perf_counter() - _t0, 4)
                self._log_cache_stats(span)
                if self._perf is not None:
                    self._perf.label = (
                        f"xorq cols={len(table.columns)} "
                        f"cache_hits={self._cache_stats['hits']} "
                        f"misses={self._cache_stats['misses']}")
                    self._perf.summary()

    @staticmethod
    def chunk_refusal(table) -> Optional[str]:
        """Why ``table`` may not have its batch split by column chunk, or
        ``None`` when it may.

        Each chunk is its own aggregate over the source. On a parquet scan a
        chunk reads only its columns, so the chunks cost about what one batch
        does (0.90-1.16x at 10-12M rows) and each needs less memory. On
        anything else a chunk runs the plan again: a join or an aggregate
        executes in full per chunk, and a CSV read reparses the file (2.1-2.2x).
        So the split is allowed for a parquet ``Read``, or a projection of
        plain columns of one, and refused for everything else, including an
        expression this does not recognise. A refusal can only keep the single
        batch; it never turns the split on.
        """
        op = table.op()
        if isinstance(op, ops.Project):
            if not all(isinstance(value, ops.Field) for value in op.values.values()):
                return "it computes columns instead of reading them"
            op = op.parent
        if not isinstance(op, Read):
            return f"not a parquet scan ({type(op).__name__})"
        if op.method_name != "read_parquet":
            return f"not a parquet scan ({op.method_name})"
        return None

    def _batch_chunks(self, state: StatState, columns: List[Any]) -> List[List[Any]]:
        """``columns`` cut into the chunks the batch runs in: one, unless the
        split is on, the row count is known and the source allows it."""
        if not self.chunk_cells:
            return [columns]
        if state.rows is None:
            log.debug("xorq stat column chunking needs the row count; running one batch")
            return [columns]
        refusal = self.chunk_refusal(state.data)
        if refusal is not None:
            log.info("xorq stat column chunking refused: %s", refusal)
            return [columns]
        per_chunk = max(1, self.chunk_cells // max(state.rows, 1))
        return [columns[i:i + per_chunk] for i in range(0, len(columns), per_chunk)] or [columns]

    def _column_phases(self, cache: Dict[Any, Any], dtype) -> Tuple[List[StatFunc], List[StatFunc], Dict[str, StatFunc]]:
        """A column's stat funcs split into those that need no further query
        once the batch has run (``pure``) and those that run one or read the
        result of one that does (``query``), each in dependency order, plus the
        stat key -> func map errors are reported against."""
        if dtype not in cache:
            col_funcs = build_column_dag(self.all_stat_funcs, dtype, external_keys=self.EXTERNAL_KEYS)
            pure: List[StatFunc] = []
            query: List[StatFunc] = []
            query_keys: set = set()
            for sf in col_funcs:
                if any(r.type in (XorqExpr, XorqExecute) or r.name in query_keys for r in sf.requires):
                    query.append(sf)
                    query_keys.update(sk.name for sk in sf.provides)
                else:
                    pure.append(sf)
            key_to_func = {sk.name: sf for sf in col_funcs for sk in sf.provides}
            cache[dtype] = (pure, query, key_to_func)
        return cache[dtype]

    def plan(self, state: StatState) -> List[StatUnit]:
        """The scalar batch first, then one histogram GROUP BY per column that
        has one, columns named in ``state.priority`` first. The batch is cut
        into chunks only as ``_batch_chunks`` allows, and every chunk precedes
        every histogram, since a histogram reads what its chunk computes.
        Skipped columns get no unit. Nothing is computed: no query is sent."""
        table = state.data
        pairs = columns_in_scope(state)
        if not pairs:
            return []
        schema = table.schema()
        # xorq has always matched skip_columns on the column's own name only.
        skip = {orig for orig, _rewritten in pairs if orig in state.skip_columns}
        active = [orig for orig, _rewritten in prioritized(state, [p for p in pairs if p[0] not in skip])]
        chunks = self._batch_chunks(state, active)
        units: List[StatUnit] = []
        batch_of: Dict[Any, str] = {}
        for i, chunk in enumerate(chunks):
            unit_id = "batch" if len(chunks) == 1 else f"batch:{i}"
            units.append(StatUnit(id=unit_id, columns=tuple(chunk), phase="batch", cost="scan"))
            batch_of.update({col: unit_id for col in chunk})
        phases: Dict[Any, Any] = {}
        for col in active:
            if self._column_phases(phases, schema[col])[1]:
                units.append(StatUnit(id=f"histogram:{col}", columns=(col,), phase="histogram",
                    after=(batch_of[col],), cost="query"))
        return units

    def new_accumulator(self, state: StatState) -> "XorqAccumulator":
        """The accumulator for a run of ``state``, and the start of the run's
        counters: the snapshot-cache hit/miss counts and the perf recorder.

        Pre-populate every column accumulator with the externally-provided
        keys. ``length`` is filled in by the batch query. ``min`` / ``max``
        start as None so dependents (histogram) don't cascade-exclude on
        non-numeric columns; ``min`` / ``max`` overwrite for numeric cols.
        ``distinct_count`` likewise starts as None so float columns (where the
        stat is column_filtered out) keep their dependents (histogram,
        histogram_bins, distinct_per) runnable. A skipped column keeps these
        (its stats are supplied via init_sd and its data is never scanned)."""
        self._cache_stats = _new_cache_run_stats()
        self._perf = (perf_log.PerfRecorder()
                      if perf_log.enabled() and not self._suppress_perf_summary else None)
        schema = state.data.schema()
        pairs = columns_in_scope(state)
        acc = XorqAccumulator(state, columns=[orig for orig, _rewritten in pairs], rewritten=dict(pairs),
            skipped=[orig for orig, _rewritten in pairs if orig in state.skip_columns])
        for col in acc.order:
            acc.working[col] = {"orig_col_name": Ok(col), "rewritten_col_name": Ok(col), "dtype": Ok(str(schema[col])),
                "length": Ok(0), "min": Ok(None), "max": Ok(None), "distinct_count": Ok(None)}
            acc.emitted[col] = set()
        acc.schema = schema
        return acc

    def run(self, unit: StatUnit, acc: StatAccumulator) -> Fragment:
        """Run one unit and return the stats it produced, ``{col: {stat: value}}``
        for its columns. A stat that fails is recorded on ``acc.errors`` once
        and the run goes on."""
        assert isinstance(acc, XorqAccumulator)
        if unit.phase == "batch":
            return self._run_batch(unit, acc)
        return self._run_histogram(unit, acc)

    def _run_funcs(self, funcs: List[StatFunc], col: Any, acc: "XorqAccumulator") -> None:
        """Run ``funcs`` (in dependency order) for one column against its
        accumulator, skipping stats whose results are already there (typically
        the batch-phase stats)."""
        col_accum = acc.working[col]
        for sf in funcs:
            if sf.provides and all(sk.name in col_accum for sk in sf.provides):
                continue
            if self._perf is not None:
                t0 = time.perf_counter()
            _execute_stat_func(sf, col_accum, col, raw_series=None, sampled_series=None, raw_dataframe=None,
                xorq_expr=acc.state.data, xorq_execute=self._execute)
            if self._perf is not None:
                self._perf.record("xorq/per-column", col, sf.name, time.perf_counter() - t0)

    def _emit(self, acc: "XorqAccumulator", col: Any, key_to_func: Dict[str, StatFunc]) -> Dict[str, Any]:
        """The stats of ``col`` that no earlier unit has returned, as plain
        values (a failed stat as None), recorded on ``acc`` with their errors."""
        working = acc.working[col]
        fresh = {key: result for key, result in working.items() if key not in acc.emitted[col]}
        plain, errors = resolve_accumulator(fresh, col, key_to_func)
        acc.emitted[col].update(fresh)
        acc.record({col: plain}, errors)
        return plain

    def _run_batch(self, unit: StatUnit, acc: "XorqAccumulator") -> Fragment:
        table = acc.state.data
        schema = acc.schema
        columns = list(unit.columns)
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
                col_dtype = schema[col]
                if sf.column_filter is not None and not sf.column_filter(col_dtype):
                    continue
                try:
                    expr = sf.func(**{xorq_col_param: table[col]})
                except Exception as e:
                    for sk in sf.provides:
                        acc.working[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col,
                            inputs={"col": col})
                    continue
                if expr is None:
                    continue
                stat_name = sf.provides[0].name
                try:
                    expr = expr.name(f"{col}|{stat_name}")
                except Exception as e:
                    for sk in sf.provides:
                        acc.working[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col,
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
                    acc.working[col][sk.name] = Err(error=e, stat_func_name=sf.name, column_name=col, inputs={})
        else:
            total_length = _to_python_scalar(result_df[TOTAL_LENGTH_KEY].iloc[0])
            if total_length is None:
                total_length = 0
            # A skipped column has no unit but has always been given the length.
            for col in [*columns, *acc.skipped]:
                acc.working[col]["length"] = Ok(total_length)
            for col, sf, _ in batch_items:
                stat_name = sf.provides[0].name
                col_stat = f"{col}|{stat_name}"
                if col_stat in result_df.columns:
                    raw_val = result_df[col_stat].iloc[0]
                    acc.working[col][stat_name] = Ok(_to_python_scalar(raw_val))
                else:
                    acc.working[col][stat_name] = Err(error=KeyError(
                        f"missing aggregate column {col_stat!r} in result"), stat_func_name=sf.name, column_name=col, inputs={})

        # The stats that are pure functions of the ones just computed, so that
        # histogram_bins (and with it color_map) needs no histogram query.
        fragment: Fragment = {}
        for col in columns:
            pure, _query, key_to_func = self._column_phases(acc.phases, schema[col])
            self._run_funcs(pure, col, acc)
            fragment[col] = self._emit(acc, col, key_to_func)
        return fragment

    def _run_histogram(self, unit: StatUnit, acc: "XorqAccumulator") -> Fragment:
        fragment: Fragment = {}
        for col in unit.columns:
            _pure, query, key_to_func = self._column_phases(acc.phases, acc.schema[col])
            self._run_funcs(query, col, acc)
            fragment[col] = self._emit(acc, col, key_to_func)
        return fragment

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

class XorqDfStatsV2(UnitStats):
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
    entire table. ``run=False`` builds the wrapper without running anything,
    for a caller that drives ``plan`` / ``run`` itself. ``chunk_cells`` and
    ``rows`` are the column-chunk split's size and the row count it needs.
    """

    @classmethod
    def verify_analysis_objects(cls, objs):
        # unit_test=False to skip the per-widget PERVERSE_DF pipeline run
        # (issue #709). DAG validation still runs as part of __init__.
        XorqStatPipeline(objs, unit_test=False)

    def __init__(self, table, col_analysis_objs, operating_df_name=None, debug=False,
                 cache_storage=None, skip_columns=None, chunk_cells=None, rows=None, run=True):
        self.table = table
        # Skip the unit_test PERVERSE_DF run on each widget construction —
        # it doubles the SQL query count (issue #709). The DAG-validation
        # cost is already paid by verify_analysis_objects on first set up
        # and by the test suite. Mirrors PlDfStatsV2.
        self.ap = XorqStatPipeline(col_analysis_objs, unit_test=False,
            cache_storage=cache_storage, chunk_cells=chunk_cells)
        self.operating_df_name = operating_df_name
        self.debug = debug
        self.rows = rows
        self.state = StatState(table, frozenset(skip_columns or ()), rows=rows)
        self.sdf: SDType = {}
        self.errs = {}
        self.stat_errors = []
        if run:
            self.sdf, errors = self.ap.process_table(self.table, skip_columns=skip_columns, rows=rows)
            self.errs = errors_to_errdict(errors)
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
        self.sdf, self.stat_errors = self.ap.process_table(self.table, rows=self.rows)
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("DAG validation failed")
        if self.errs:
            print("Errors on original table")
        if errors or self.stat_errors:
            for err in errors + self.stat_errors:
                if err.stat_func is not None:
                    print(err.reproduce_code())
