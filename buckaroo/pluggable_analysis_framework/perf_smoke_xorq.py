"""Xorq runner for the perf/memory smoke harness.

The xorq pipeline doesn't call one python function per stat, so the pandas
harness's wrap-the-func approach can't time it alone. Batched aggregate stats
(``XorqColumn -> ibis.Expr``) only *build* expressions; ``XorqStatPipeline``
folds them into a single ``table.aggregate`` and the engine executes them
together. ``run_xorq_perf_smoke`` therefore measures in two passes per frame:

1. each batch stat's expression executed as its own single-expression
   aggregate — per-stat engine time and memory attribution, and
2. the full ``XorqStatPipeline`` per column with wrapped funcs, which times
   post-batch stats — including expression stats like ``histogram`` that run
   real queries through their injected ``execute``.

Frames are the pandas ``SMOKE_FRAME_MAKERS`` wrapped as ``xo.memtable``.
Engine allocations (DataFusion/Arrow) live in native memory; the RSS tracker
in ``perf_smoke`` is the signal that sees them, tracemalloc cannot.
"""
import time
import tracemalloc
from typing import Callable, Dict, Optional

import xorq.api as xo

from .perf_smoke import (DEFAULT_ROWS, MEMORY_FLOOR_BYTES, SMOKE_FRAME_MAKERS, SmokeResult,
    _frame_bytes, _measure, _Recorder, _wrap)
from .stat_pipeline import _normalize_inputs
from .xorq_stat_pipeline import XorqStatPipeline, XorqColumn, _is_batch_func


def _xorq_baseline_seconds(table) -> float:
    """Time canonical engine work on the memtable: a row count plus min/max
    aggregates per column. Plays the role ``_baseline_seconds`` plays for
    pandas — the time limit is a multiple of this on the same machine.
    Columns whose dtype can't build min/max are skipped; the absolute floor
    keeps the limit sane when most skip."""
    def work():
        try:
            table.count().execute()
        except Exception:
            pass
        for col in table.columns:
            try:
                table.aggregate([table[col].max().name('mx'),
                    table[col].min().name('mn')]).execute()
            except Exception:
                pass

    work()  # warm caches so the measured pass isn't paying first-call cost
    t0 = time.perf_counter()
    work()
    return time.perf_counter() - t0


def run_xorq_perf_smoke(stat_funcs: list, rows: int = DEFAULT_ROWS,
        frames: Optional[Dict[str, Callable]] = None,
        max_time_ratio: float = 20.0, time_floor_seconds: float = 0.25,
        max_memory_ratio: float = 20.0,
        memory_floor_bytes: float = MEMORY_FLOOR_BYTES) -> SmokeResult:
    """Smoke-test a xorq stat list for perf/memory pathologies.

    ``frames`` maps frame name to a ``maker(rows) -> pandas.DataFrame``
    callable (the frame is wrapped as a memtable); defaults to
    SMOKE_FRAME_MAKERS. Limits and return shape match ``run_perf_smoke``.
    Engine errors are tolerated — that's ``unit_test()``'s job.
    """
    frame_makers = SMOKE_FRAME_MAKERS if frames is None else frames
    recorder = _Recorder()
    normalized = _normalize_inputs(stat_funcs)
    batch_funcs = [sf for sf in normalized if _is_batch_func(sf)]
    wrapped = [_wrap(sf, recorder) for sf in normalized]
    pipeline = XorqStatPipeline(wrapped, unit_test=False)

    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    try:
        small = max(500, rows // 10)
        scales = [small, rows] if small < rows else [rows]
        for n in scales:
            for frame_name, maker in frame_makers.items():
                try:
                    pdf = maker(n)
                    table = xo.memtable(pdf)
                    table.count().execute()
                except Exception:
                    continue  # frame shape not representable in arrow (e.g. Period, #799)
                recorder.frame = frame_name
                baseline = _xorq_baseline_seconds(table)
                recorder.configure(
                    rows=n,
                    time_limit=max(time_floor_seconds, max_time_ratio * baseline),
                    memory_limit=max(memory_floor_bytes,
                                     max_memory_ratio * _frame_bytes(pdf)))
                schema = table.schema()
                # Pass 1: batch aggregates, one engine round-trip per stat
                for sf in batch_funcs:
                    param = next(r.name for r in sf.requires if r.type is XorqColumn)
                    for col in table.columns:
                        if sf.name in recorder.flagged:
                            continue
                        if sf.column_filter is not None and not sf.column_filter(schema[col]):
                            continue
                        recorder.column = col
                        try:
                            expr = sf.func(**{param: table[col]})
                        except Exception:
                            continue
                        if expr is None:
                            continue
                        query = table.aggregate([expr.name('v')])
                        try:
                            _measure(recorder, sf.name, query.execute)
                        except Exception:
                            pass
                # Pass 2: full pipeline per column — post-batch stats
                for col in table.columns:
                    recorder.column = col
                    try:
                        pipeline.process_table(xo.memtable(pdf[[col]]))
                    except Exception:
                        pass
    finally:
        if not was_tracing:
            tracemalloc.stop()

    return SmokeResult(passed=(not recorder.findings), findings=recorder.findings,
        measurements=recorder.measurements)
