"""Perf/memory smoke testing for summary stats.

``StatPipeline.unit_test()`` runs stats against the 10-row PERVERSE_DF and
catches raised errors. Nothing catches a stat that is *correct but
pathological* — a per-row python loop, an O(n^2) algorithm, a huge
intermediate allocation. Those sail through a 10-row unit test and only
surface as a hung widget or an OOM on real data. User- and LLM/MCP-authored
stats (``add_analysis``, project stat dirs) are the usual source.

``perf_smoke_test()`` runs each stat against a seeded synthetic frame and
flags per-stat wall-time and peak-memory blowups::

    from buckaroo.pluggable_analysis_framework.perf_smoke import perf_smoke_test

    passed, findings = perf_smoke_test([MyStatClass, my_stat_func])
    for f in findings:
        print(f.message)

Pass the same stat list you would hand to a widget or pipeline — stats that
``require`` keys from other stats need their providers in the list.

Design notes:

- Limits are machine-relative: the time limit is a ratio against canonical
  pandas ops timed on the same frame on the same machine (plus an absolute
  floor), so the check behaves the same on a fast laptop and a slow CI
  runner. The memory limit is a ratio against the input frame's size, also
  floored.
- Stats run at a small scale first, then full scale, and a flagged stat is
  never run again — a quadratic stat can't make the smoke test itself run
  away.
- Errors raised by stats are ignored here; that's ``unit_test()``'s job.
- Peak memory is measured with ``tracemalloc``, which sees numpy/pandas
  allocations. Polars/Arrow-native allocations are invisible to it; this
  harness targets the pandas pipeline.
"""
from __future__ import annotations

import dataclasses
import time
import tracemalloc
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd

from .stat_pipeline import StatPipeline, _normalize_inputs
from .stat_func import StatFunc

DEFAULT_ROWS = 10_000
MEMORY_FLOOR_BYTES = 20_000_000


def make_smoke_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    """Seeded synthetic frame exercising the shapes stats commonly choke on:
    plain ints, floats with nans, low-cardinality strings (categorical-ish),
    and all-distinct strings (worst case for value_counts-style work)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({'int_col': rng.integers(0, 1_000, rows),
        'float_col': np.where(rng.random(rows) < 0.05, np.nan, rng.random(rows)),
        'str_low_card': pd.Series(rng.integers(0, 20, rows)).map('cat_{}'.format),
        'str_high_card': [f'id_{i:08d}' for i in range(rows)]})


@dataclass
class SmokeFinding:
    stat_name: str
    column: str
    kind: str  # 'time' | 'memory'
    measured: float  # seconds for 'time', bytes for 'memory'
    limit: float
    rows: int
    message: str


class _SmokeSkip(Exception):
    """Raised inside a wrapped stat that was already flagged, so the pipeline
    records an Err instead of running the pathological code again."""


def _baseline_seconds(df: pd.DataFrame) -> float:
    """Time canonical per-column pandas work on the smoke frame. A reasonable
    stat does far less than this; the time limit is a multiple of it."""
    def work():
        for col in df.columns:
            ser = df[col]
            ser.value_counts()
            ser.sort_values()
            ser.nunique()

    work()  # warm caches so the measured pass isn't paying first-call cost
    t0 = time.perf_counter()
    work()
    return time.perf_counter() - t0


class _Recorder:
    """Shared state between perf_smoke_test and the wrapped stat funcs:
    current column/scale/limits going in, findings and flagged stats out."""

    def __init__(self):
        self.findings: List[SmokeFinding] = []
        self.flagged: set = set()
        self.column = '<unknown>'
        self.rows = 0
        self.time_limit = float('inf')
        self.memory_limit = float('inf')

    def configure(self, rows: int, time_limit: float, memory_limit: float) -> None:
        self.rows = rows
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def record(self, stat_name: str, seconds: float, peak_bytes: float) -> None:
        if seconds > self.time_limit:
            self.flagged.add(stat_name)
            self.findings.append(SmokeFinding(
                stat_name=stat_name, column=self.column, kind='time', measured=seconds,
                limit=self.time_limit, rows=self.rows,
                message=(
                    f"stat '{stat_name}' took {seconds:.2f}s on column '{self.column}' "
                    f"of a {self.rows}-row frame (limit {self.time_limit:.2f}s). "
                    f"Likely a per-row python loop or an O(n^2) algorithm — "
                    f"vectorize with pandas/numpy operations.")))
        if peak_bytes > self.memory_limit:
            self.flagged.add(stat_name)
            self.findings.append(SmokeFinding(
                stat_name=stat_name, column=self.column, kind='memory', measured=peak_bytes,
                limit=self.memory_limit, rows=self.rows,
                message=(
                    f"stat '{stat_name}' allocated a peak of {peak_bytes / 1e6:.0f}MB on column "
                    f"'{self.column}' of a {self.rows}-row frame (limit {self.memory_limit / 1e6:.0f}MB). "
                    f"Avoid materializing large intermediates (pairwise matrices, "
                    f"cross joins, full copies per row).")))


def _wrap(sf: StatFunc, recorder: _Recorder) -> StatFunc:
    inner = sf.func

    def measured(*args, **kwargs):
        if sf.name in recorder.flagged:
            raise _SmokeSkip(f"'{sf.name}' skipped after an earlier perf finding")
        before_bytes = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        t0 = time.perf_counter()
        try:
            return inner(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - t0
            peak = tracemalloc.get_traced_memory()[1] - before_bytes
            recorder.record(sf.name, elapsed, peak)

    return dataclasses.replace(sf, func=measured)


def perf_smoke_test(stat_funcs: list, rows: int = DEFAULT_ROWS, max_time_ratio: float = 20.0,
        time_floor_seconds: float = 0.25, max_memory_ratio: float = 20.0,
        memory_floor_bytes: float = MEMORY_FLOOR_BYTES) -> Tuple[bool, List[SmokeFinding]]:
    """Smoke-test stats for perf/memory pathologies on synthetic data.

    Accepts the same mixed input as StatPipeline (StatFunc, @stat functions,
    stat group classes, ColAnalysis subclasses). Returns
    ``(passed, findings)`` mirroring ``unit_test()``'s shape.

    A stat is flagged when a single per-column call exceeds
    ``max(time_floor_seconds, max_time_ratio * baseline)`` wall-time or
    ``max(memory_floor_bytes, max_memory_ratio * frame_bytes)`` peak traced
    memory. Defaults are deliberately loose — this catches
    order-of-magnitude blowups, not 2x regressions.
    """
    recorder = _Recorder()
    wrapped = [_wrap(sf, recorder) for sf in _normalize_inputs(stat_funcs)]
    pipeline = StatPipeline(wrapped, unit_test=False)

    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    try:
        small = max(500, rows // 10)
        scales = [small, rows] if small < rows else [rows]
        for n in scales:
            df = make_smoke_df(n)
            baseline = _baseline_seconds(df)
            recorder.configure(
                rows=n,
                time_limit=max(time_floor_seconds, max_time_ratio * baseline),
                memory_limit=max(memory_floor_bytes,
                                 max_memory_ratio * float(df.memory_usage(deep=True).sum())))
            for col in df.columns:
                recorder.column = col
                pipeline.process_df(df[[col]])
    finally:
        if not was_tracing:
            tracemalloc.stop()

    return (not recorder.findings), recorder.findings
