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

With a ``StatCache`` (ADR-001), both phases first look each cell up by
``(scope_id, col, stat_id)``. Only missing cells are computed: the batch
aggregate is restricted to the missing ``(column, stat)`` pairs, and a
per-column query stat runs only where its cell is missing. A full hit builds
no expressions and runs no queries. Newly computed cells go to one new part.

Errors are captured into ``StatError`` via the standard Ok/Err mechanism;
nothing is silently swallowed. Construction validates the DAG up front and
raises ``DAGConfigError`` on bad configurations.

Optional dependency: install with ``buckaroo[xorq]``.
"""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from . import perf_log
from .col_analysis import SDType
from .safe_summary_df import output_full_reproduce
from .stat_cache import (CachedScope, CachedStatError, StatCache, length_stat_id, make_scope_id,
    stat_hashes)
from .stat_func import XorqColumn, XorqExpr, XorqExecute, RAW_MARKER_TYPES, StatFunc
from .stat_pipeline import _execute_stat_func, _normalize_inputs, errors_to_errdict
from .stat_result import Err, Ok, StatError, StatResult, resolve_accumulator
from .typed_dag import build_column_dag, build_typed_dag
from .utils import PERVERSE_DF

# Re-export marker types so users only need to import from this module.
__all__ = ["XorqStatPipeline", "XorqDfStatsV2", "XorqColumn", "XorqExpr", "XorqExecute"]

try:
    import xorq.api as xo
    from xorq.caching import SnapshotStrategy

    HAS_XORQ = True
except ImportError:
    xo = None
    SnapshotStrategy = None
    HAS_XORQ = False

log = logging.getLogger(__name__)

TOTAL_LENGTH_KEY = "__total_length__"


def _new_cache_run_stats() -> Dict[str, Any]:
    """Per-``process_table``-run counters for the stat cache.

    Reset at the start of every run and summarised in one log line at the
    end (see ``_log_cache_stats``). ``hits`` and ``misses`` count cells;
    ``snapshots`` is the number of parts written (same as ``parts_written``,
    kept for existing telemetry consumers)."""
    return {"hits": 0, "misses": 0, "snapshots": 0, "bytes": 0,
        "write_errors": 0, "secs": 0.0, "parts_read": 0, "parts_written": 0,
        "errors_cached": 0}


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


def _is_query_func(sf: StatFunc) -> bool:
    """A per-column stat that runs its own query (e.g. histogram)."""
    return any(r.type is XorqExpr or r.type is XorqExecute for r in sf.requires)


# How an engine reports a failure of its environment rather than of the query:
# DataFusion's resource, IO and object-store errors, and a Rust io::Error,
# which renders as "... (os error N)".
_ENVIRONMENTAL_MESSAGES = ("resources exhausted", "out of memory", "timed out", "timeout", "io error:",
    "object store error", "(os error ")


def _is_environmental(e: Optional[BaseException]) -> bool:
    """A failure that says nothing about the stat: the backend was down,
    slow, out of memory, or couldn't read its files. Any OSError counts
    (connection, timeout, a missing file, no file handles left), and so does
    an error one caused, since an engine or a stat may wrap it. Never cached
    (ADR-001 D11)."""
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, (MemoryError, OSError)):
            return True
        msg = str(e).lower()
        if any(s in msg for s in _ENVIRONMENTAL_MESSAGES):
            return True
        e = e.__cause__ or e.__context__
    return False


def fallback_data_id(table) -> str:
    """The data identity of an expression when the caller supplies none: the
    hash xorq's snapshot cache gives it, computed once per load."""
    return SnapshotStrategy().calc_key(table)


def _as_stat_cache(cache_storage):
    """Accept a ``StatCache`` or, for older callers, a xorq
    ``ParquetSnapshotCache``, whose ``base_path`` then holds the stat cache."""
    if cache_storage is None or isinstance(cache_storage, StatCache):
        return cache_storage
    return StatCache.for_cache_storage_path(cache_storage.storage.base_path)


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
        self.cache_storage = _as_stat_cache(cache_storage)

        # Per-run cache counters, (re)initialised in process_table. Set here so
        # the attribute always exists (e.g. for the unit_test() run kicked off
        # below, which disables the cache).
        self._cache_stats = _new_cache_run_stats()
        # Successful queries in the current run. A stat's failure is cached
        # only when a query succeeded after it, which shows the backend was
        # up (D11).
        self._queries_ok = 0
        # Row count of the last process_table run (cached or counted), or None.
        self.last_length: Optional[int] = None
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
        result = self.backend.execute(query) if self.backend is not None else query.execute()
        self._queries_ok += 1
        return result

    def _log_cache_stats(self, span=None):
        """Surface the per-run cache outcome (#910, #951).

        Two channels, so the write side is never invisible:

        * ``span`` — attach the hit/miss/part/byte/write-error counts to the
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
                cache_write_errors=cs["write_errors"], cache_parts_read=cs["parts_read"],
                cache_parts_written=cs["parts_written"], cache_errors_cached=cs["errors_cached"])
        log.info(
            "xorq stat cache [%s]: %d hit(s), %d miss(es), %d part(s) read, %d snapshot(s) "
            "written (%d bytes), %d error(s) cached, %d write error(s) in %.3fs",
            self.cache_storage.base_path, s["hits"], s["misses"], s["parts_read"], s["snapshots"],
            s["bytes"], s["errors_cached"], s["write_errors"], s.get("secs", 0.0))

    def cache_run_stats(self) -> Dict[str, Any]:
        """Public snapshot of the last ``process_table`` run's summary-stat
        cache outcome — the structured signal a telemetry consumer wants (#943).

        ``{hits, misses, snapshots, bytes, write_errors, secs, parts_read,
        parts_written, errors_cached, cached, status}``. ``hits`` and
        ``misses`` count cells. ``status`` is ``hit`` / ``miss`` / ``mixed`` /
        ``none`` for a run that used the cache, and ``uncached`` when no cache
        was configured. ``secs`` is the wall-clock of the whole stats run.
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

    def process_table(self, table, skip_columns=None, stat_columns=None,
            scope_id=None) -> Tuple[SDType, List[StatError]]:
        """Run the stats over ``table``.

        ``skip_columns`` keep their structural metadata but get no stats (their
        stats come from ``init_sd``). ``stat_columns``, when given, restricts
        stats to those columns, so a caller can fill a wide table in batches;
        every other column is treated as skipped. ``scope_id`` keys the cache
        (see ``stat_cache.make_scope_id``); with a cache and no ``scope_id``
        it is derived from ``table`` itself."""
        self._cache_stats = _new_cache_run_stats()
        self._queries_ok = 0
        self.last_length = None
        self._perf = (perf_log.PerfRecorder()
                      if perf_log.enabled() and not self._suppress_perf_summary else None)
        _t0 = time.perf_counter()
        with self._span("stat.xorq.total") as span:
            try:
                return self._process_table_impl(
                    table, skip_columns=skip_columns, stat_columns=stat_columns, scope_id=scope_id)
            finally:
                self._cache_stats["secs"] = round(time.perf_counter() - _t0, 4)
                self._log_cache_stats(span)
                if self._perf is not None:
                    self._perf.label = (
                        f"xorq cols={len(table.columns)} "
                        f"cache_hits={self._cache_stats['hits']} "
                        f"misses={self._cache_stats['misses']}")
                    self._perf.summary()

    def _read_cache(self, table, scope_id) -> Tuple[Optional[str], CachedScope]:
        if self.cache_storage is None:
            return None, CachedScope()
        if scope_id is None:
            scope_id = make_scope_id(fallback_data_id(table))
        try:
            with self._span("stat.xorq.cache_read"):
                cached = self.cache_storage.read(scope_id)
        except Exception as e:
            log.warning("stat cache read failed for %s: %s", scope_id, e)
            cached = CachedScope()
        self._cache_stats["parts_read"] = cached.parts_read
        return scope_id, cached

    def _process_table_impl(self, table, skip_columns=None, stat_columns=None,
            scope_id=None) -> Tuple[SDType, List[StatError]]:
        schema = table.schema()
        columns = list(table.columns)
        # Columns whose stats are supplied externally (via init_sd) keep their
        # structural metadata (name/dtype/length) but get no stat expressions
        # built — so the column's data is never scanned.
        skip = set(skip_columns or ())
        if stat_columns is not None:
            wanted = set(stat_columns)
            skip |= {c for c in columns if c not in wanted}

        scope_id, cached = self._read_cache(table, scope_id)
        hashes = stat_hashes(self.ordered_stat_funcs) if self.cache_storage is not None else {}
        cells = _CellLedger(cached, hashes)

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
                if cells.serve(col, sf, accumulators[col], self._cache_stats):
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

        total_length = cells.cached_length()
        if batch_items or total_length is None:
            with self._span("stat.xorq.batch_aggregate", n_stats=len(batch_items)):
                values, failures, length = self._run_batch(table, batch_items, need_length=total_length is None)
            if total_length is None and length is not None:
                total_length = length
                cells.computed_length(length)
            for i, (col, sf, _) in enumerate(batch_items):
                self._cache_stats["misses"] += len(sf.provides)
                stat_name = sf.provides[0].name
                if i in failures:
                    err, ok_before = failures[i]
                    accumulators[col][stat_name] = Err(error=err, stat_func_name=sf.name, column_name=col, inputs={})
                    cells.failed(col, sf, err, ok_before)
                else:
                    accumulators[col][stat_name] = Ok(values[i])
                    cells.computed(col, sf, {stat_name: values[i]})
        if total_length is not None:
            self.last_length = total_length
            for col in columns:
                accumulators[col]["length"] = Ok(total_length)

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
                query_func = _is_query_func(sf)
                if query_func and cells.serve(col, sf, col_accum, self._cache_stats):
                    continue
                if self._perf is not None:
                    t0 = time.perf_counter()
                raised = _execute_stat_func(sf, col_accum, col, raw_series=None, sampled_series=None,
                    raw_dataframe=None, xorq_expr=table, xorq_execute=self._execute)
                if self._perf is not None:
                    self._perf.record("xorq/per-column", col, sf.name, time.perf_counter() - t0)
                if query_func:
                    cells.ran_query_func(col, sf, col_accum, raised, self._queries_ok, self._cache_stats)

            col_key_to_func: Dict[str, StatFunc] = {}
            for sf in col_funcs:
                for sk in sf.provides:
                    col_key_to_func[sk.name] = sf

            plain, errors = resolve_accumulator(col_accum, col, col_key_to_func)
            summary[col] = plain
            all_errors.extend(errors)

        if self.cache_storage is not None:
            self._write_cells(scope_id, cells)
        return summary, all_errors

    def _run_batch(self, table, items, need_length: bool):
        """Run the batch aggregate over ``items``; returns ``(values, failures,
        length)`` keyed by item index. A failure is ``(error, ok_before)``:
        the count of queries that had succeeded when it failed, or None when
        the backend was down (see ``_CellLedger.failed``).

        One query when it succeeds. When it fails, the failure is isolated
        (ADR-001 D11) so one bad expression can't take down every stat on
        every column: a ``count()`` canary first (a failing canary means the
        backend is down, so every item fails), then one aggregate per stat,
        then one per cell for a stat whose aggregate still fails. Failures are
        reported at the finest level reached."""
        values: Dict[int, Any] = {}
        failures: Dict[int, Tuple[BaseException, Optional[int]]] = {}

        def run(idxs, with_length=False):
            exprs = [table.count().name(TOTAL_LENGTH_KEY)] if with_length else []
            exprs += [items[i][2] for i in idxs]
            df = self._execute(table.aggregate(exprs))
            for i in idxs:
                col, sf, _ = items[i]
                name = f"{col}|{sf.provides[0].name}"
                if name in df.columns:
                    values[i] = _to_python_scalar(df[name].iloc[0])
                else:
                    failures[i] = (KeyError(f"missing aggregate column {name!r} in result"), self._queries_ok)
            if with_length:
                length = _to_python_scalar(df[TOTAL_LENGTH_KEY].iloc[0])
                return 0 if length is None else length
            return None

        all_idxs = list(range(len(items)))
        first_ok = self._queries_ok
        try:
            return values, failures, run(all_idxs, with_length=need_length)
        except Exception as batch_err:
            log.warning("xorq stat batch aggregate failed, isolating: %s", batch_err)
            first_err = batch_err

        try:
            length = run([], with_length=True)
        except Exception as canary_err:
            for i in all_idxs:
                failures[i] = (canary_err, None)
            return values, failures, None
        if len(items) == 1:
            failures[0] = (first_err, first_ok)
            return values, failures, length

        by_stat: Dict[str, List[int]] = {}
        for i, (_, sf, _) in enumerate(items):
            by_stat.setdefault(sf.name, []).append(i)
        for idxs in by_stat.values():
            if len(by_stat) > 1:
                try:
                    run(idxs)
                    continue
                except Exception as stat_err:
                    if len(idxs) == 1:
                        failures[idxs[0]] = (stat_err, self._queries_ok)
                        continue
            for i in idxs:
                try:
                    run([i])
                except Exception as cell_err:
                    failures[i] = (cell_err, self._queries_ok)
        return values, failures, length

    def _write_cells(self, scope_id, cells: "_CellLedger") -> None:
        errors, fallback_values = cells.settled(self._queries_ok)
        values = {col: {**fallback_values.get(col, {}), **cells.new_values.get(col, {})}
            for col in set(cells.new_values) | set(fallback_values)}
        live = cells.live_stat_ids(self.ordered_stat_funcs)
        try:
            path = self.cache_storage.write(scope_id, values, errors, keep=live.__contains__)
        except Exception as e:
            self._cache_stats["write_errors"] += 1
            log.warning("stat cache write failed for %s: %s", scope_id, e)
            return
        if path is not None:
            self._cache_stats["snapshots"] += 1
            self._cache_stats["parts_written"] += 1
            self._cache_stats["bytes"] += path.stat().st_size
            self._cache_stats["errors_cached"] = sum(len(v) for v in errors.values())

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


class _CellLedger:
    """One run's view of the cache: which cells it served and which it
    computed. Inert when the pipeline has no cache (``hashes`` empty)."""

    def __init__(self, cached: CachedScope, hashes: Dict[str, str]):
        self.cached = cached
        self.hashes = hashes
        self.new_values: Dict[Any, Dict[str, Any]] = {}
        # Stat errors, and values a stat's ``default`` substituted for an
        # exception, each with the count of queries that had succeeded when
        # it failed. Cached only when a query succeeded after it (D11), see
        # ``settled``.
        self.new_errors: Dict[Any, Dict[str, Tuple[str, int]]] = {}
        self.fallback_values: Dict[Any, Dict[str, Tuple[Any, int]]] = {}

    def _sid(self, sf: StatFunc, key: str) -> Optional[str]:
        h = self.hashes.get(sf.name)
        return f"{key}@{h}" if h else None

    def serve(self, col, sf: StatFunc, accum: Dict[str, StatResult], counters) -> bool:
        """Fill ``accum`` with ``sf``'s cached cells for ``col`` if all of them
        are cached; returns whether it did."""
        if sf.name not in self.hashes:
            return False
        results = {}
        for sk in sf.provides:
            sid = self._sid(sf, sk.name)
            if sid in self.cached.values.get(col, {}):
                results[sk.name] = Ok(self.cached.values[col][sid])
            elif sid in self.cached.errors.get(col, {}):
                results[sk.name] = Err(error=CachedStatError(self.cached.errors[col][sid]),
                    stat_func_name=sf.name, column_name=col, inputs={})
            else:
                return False
        accum.update(results)
        counters["hits"] += len(results)
        return True

    def cached_length(self) -> Optional[int]:
        if not self.hashes:
            return None
        return self.cached.values.get(None, {}).get(length_stat_id())

    def computed_length(self, length: int) -> None:
        if self.hashes:
            self.new_values.setdefault(None, {})[length_stat_id()] = length

    def computed(self, col, sf: StatFunc, values: Dict[str, Any]) -> None:
        if sf.name in self.hashes:
            col_values = self.new_values.setdefault(col, {})
            for key, v in values.items():
                col_values[self._sid(sf, key)] = v

    def failed(self, col, sf: StatFunc, error: BaseException, ok_before: Optional[int]) -> None:
        """Record ``sf`` failing on ``col``. ``ok_before`` is the count of
        queries that had succeeded when it failed, None when the backend was
        down."""
        if sf.name in self.hashes and ok_before is not None and not _is_environmental(error):
            col_errors = self.new_errors.setdefault(col, {})
            for sk in sf.provides:
                col_errors[self._sid(sf, sk.name)] = (f"{type(error).__name__}: {error}", ok_before)

    def ran_query_func(self, col, sf: StatFunc, accum: Dict[str, StatResult],
            raised: Optional[BaseException], ok_before: int, counters) -> None:
        """Record a per-column query stat that was asked to run. One that
        didn't run (an upstream error) records nothing. A value its
        ``default`` substituted for an exception is cached like an error."""
        results = [accum.get(sk.name) for sk in sf.provides]
        if raised is None and any(not isinstance(r, Ok) for r in results):
            return
        counters["misses"] += len(sf.provides)
        if raised is not None and _is_environmental(raised):
            return
        if raised is not None and all(isinstance(r, Err) for r in results):
            self.failed(col, sf, raised, ok_before)
            return
        values = {sk.name: r.value for sk, r in zip(sf.provides, results)}
        if sf.name not in self.hashes:
            return
        if raised is not None:
            # A default stood in for the exception: cached under the same
            # rule as an error.
            col_values = self.fallback_values.setdefault(col, {})
            for key, v in values.items():
                col_values[self._sid(sf, key)] = (v, ok_before)
            return
        self.computed(col, sf, values)

    def settled(self, queries_ok: int) -> Tuple[Dict[Any, Dict[str, str]], Dict[Any, Dict[str, Any]]]:
        """``(errors, fallback values)`` with a successful query after them,
        given the run's final count of successful queries. The backend
        answered after each of these failed, so it was up and the stat failed
        on its own. Succeeding before a failure doesn't show that: the
        backend can go away partway through a run."""
        def after(recorded):
            out: Dict[Any, Dict[str, Any]] = {}
            for col, cells in recorded.items():
                kept = {sid: v for sid, (v, ok_before) in cells.items() if ok_before < queries_ok}
                if kept:
                    out[col] = kept
            return out
        return after(self.new_errors), after(self.fallback_values)

    def live_stat_ids(self, stat_funcs: List[StatFunc]) -> Set[str]:
        live = {length_stat_id()}
        for sf in stat_funcs:
            if (_is_batch_func(sf) or _is_query_func(sf)) and sf.name in self.hashes:
                live |= {self._sid(sf, sk.name) for sk in sf.provides}
        return live


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
                 cache_storage=None, skip_columns=None, scope_id=None):
        self.table = table
        # Skip the unit_test PERVERSE_DF run on each widget construction —
        # it doubles the SQL query count (issue #709). The DAG-validation
        # cost is already paid by verify_analysis_objects on first set up
        # and by the test suite. Mirrors PlDfStatsV2.
        self.ap = XorqStatPipeline(col_analysis_objs, unit_test=False,
            cache_storage=cache_storage)
        self.operating_df_name = operating_df_name
        self.debug = debug
        # Kept for add_analysis, which reruns the pipeline over the same
        # columns and cache scope.
        self.skip_columns = skip_columns
        self.scope_id = scope_id
        self.sdf, errors = self.ap.process_table(self.table, skip_columns=skip_columns, scope_id=scope_id)
        # The table's row count, from the cache or the batch count(); None if
        # it couldn't be counted.
        self.length = self.ap.last_length
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
        self.sdf, self.stat_errors = self.ap.process_table(
            self.table, skip_columns=self.skip_columns, scope_id=self.scope_id)
        self.length = self.ap.last_length
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("DAG validation failed")
        if self.errs:
            print("Errors on original table")
        if errors or self.stat_errors:
            for err in errors + self.stat_errors:
                if err.stat_func is not None:
                    print(err.reproduce_code())
