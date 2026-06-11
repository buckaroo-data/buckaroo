"""Perf/memory smoke testing for summary stats.

``StatPipeline.unit_test()`` runs stats against the 10-row PERVERSE_DF and
catches raised errors. Nothing catches a stat that is *correct but
pathological* — a per-row python loop, an O(n^2) algorithm, a huge
intermediate allocation. Those sail through a 10-row unit test and only
surface as a hung widget or an OOM on real data. User- and LLM/MCP-authored
stats (``add_analysis``, project stat dirs) are the usual source.

``perf_smoke_test()`` runs each stat against a suite of seeded synthetic
frames and flags per-stat wall-time and peak-memory blowups::

    from buckaroo.pluggable_analysis_framework.perf_smoke import perf_smoke_test

    passed, findings = perf_smoke_test([MyStatClass, my_stat_func])
    for f in findings:
        print(f.message)

Pass the same stat list you would hand to a widget or pipeline — stats that
``require`` keys from other stats need their providers in the list.

The frame suite (``SMOKE_FRAME_MAKERS``) covers shapes with bug history:
unhashable object cells (#843), int64 beyond 2^53 (#800, #632), Decimal
columns (#801), tz-aware datetimes (#277), all-null columns, and categorical
dtype. Findings name the frame that triggered them.

``run_perf_smoke()`` additionally returns every per-call measurement, and
``measurements_markdown()`` renders them as a per-stat worst-case table —
used by ``scripts/perf_smoke_report.py`` to write a CI job summary.

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
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

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


def _make_unhashable_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 843: cells holding lists/dicts break hash-based ops (nunique raises) and
    # make others crawl (value_counts succeeds but takes seconds at 10k rows)
    return pd.DataFrame({'list_cells': [[i, i + 1] for i in range(rows)],
        'dict_cells': [{'k': i} for i in range(rows)]})


def _make_big_int64_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 800/632: int64 beyond 2^53 silently loses precision through float casts
    return pd.DataFrame({'beyond_2_53': np.arange(rows, dtype=np.int64) + 2**53 + 1,
        'int64_extremes': np.where(np.arange(rows) % 2 == 0,
                                   np.int64(2**63 - 1), np.int64(-(2**63) + 1))})


def _make_decimal_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 801: Decimal cells are object dtype and break numeric fast paths
    return pd.DataFrame({'decimal_col': [Decimal(i) / Decimal(7) for i in range(rows)]})


def _make_tz_datetime_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 277: tz-aware datetimes break naive datetime arithmetic/serialization
    return pd.DataFrame({
        'utc_ts': pd.date_range('2020-01-01', periods=rows, freq='min', tz='UTC'),
        'ny_ts': pd.date_range('2020-01-01', periods=rows, freq='min',
                               tz='America/New_York')})


def _make_all_null_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    return pd.DataFrame({'none_obj': pd.Series([None] * rows, dtype='object'),
        'nan_float': pd.Series(np.full(rows, np.nan)),
        'nat_ts': pd.Series([pd.NaT] * rows)})


def _make_categorical_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        'cat_col': pd.Categorical.from_codes(rng.integers(0, 5, rows),
                                             categories=[f'c{i}' for i in range(5)]),
        'ordered_cat': pd.Categorical.from_codes(rng.integers(0, 3, rows),
                                                 categories=['low', 'mid', 'high'],
                                                 ordered=True)})


SMOKE_FRAME_MAKERS: Dict[str, Callable[..., pd.DataFrame]] = {'base': make_smoke_df, 'unhashable': _make_unhashable_df,
    'big_int64': _make_big_int64_df, 'decimal': _make_decimal_df, 'tz_datetime': _make_tz_datetime_df,
    'all_null': _make_all_null_df, 'categorical': _make_categorical_df}


@dataclass
class SmokeFinding:
    stat_name: str
    frame: str
    column: str
    kind: str  # 'time' | 'memory'
    measured: float  # seconds for 'time', bytes for 'memory'
    limit: float
    rows: int
    message: str


@dataclass
class SmokeMeasurement:
    """One instrumented stat call: which stat, on which frame/column/scale,
    and what it cost. Collected for every call, not just limit exceedances."""
    stat_name: str
    frame: str
    column: str
    rows: int
    seconds: float
    peak_bytes: float


@dataclass
class SmokeResult:
    passed: bool
    findings: List[SmokeFinding]
    measurements: List[SmokeMeasurement]


class _SmokeSkip(Exception):
    """Raised inside a wrapped stat that was already flagged, so the pipeline
    records an Err instead of running the pathological code again."""


def _baseline_seconds(df: pd.DataFrame) -> float:
    """Time canonical per-column pandas work on a smoke frame. A reasonable
    stat does far less than this; the time limit is a multiple of it. Ops that
    raise on a shape (value_counts on unhashable cells) are skipped — the
    absolute floor keeps the limit sane when most ops skip."""
    def work():
        for col in df.columns:
            ser = df[col]
            for op in (ser.value_counts, ser.sort_values, ser.nunique):
                try:
                    op()
                except Exception:
                    pass

    work()  # warm caches so the measured pass isn't paying first-call cost
    t0 = time.perf_counter()
    work()
    return time.perf_counter() - t0


class _Recorder:
    """Shared state between run_perf_smoke and the wrapped stat funcs:
    current frame/column/scale/limits going in, measurements, findings and
    flagged stats out."""

    def __init__(self):
        self.findings: List[SmokeFinding] = []
        self.measurements: List[SmokeMeasurement] = []
        self.flagged: set = set()
        self.frame = '<unknown>'
        self.column = '<unknown>'
        self.rows = 0
        self.time_limit = float('inf')
        self.memory_limit = float('inf')

    def configure(self, rows: int, time_limit: float, memory_limit: float) -> None:
        self.rows = rows
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def record(self, stat_name: str, seconds: float, peak_bytes: float) -> None:
        self.measurements.append(SmokeMeasurement(
            stat_name=stat_name, frame=self.frame, column=self.column,
            rows=self.rows, seconds=seconds, peak_bytes=peak_bytes))
        if seconds > self.time_limit:
            self.flagged.add(stat_name)
            self.findings.append(SmokeFinding(
                stat_name=stat_name, frame=self.frame, column=self.column,
                kind='time', measured=seconds, limit=self.time_limit, rows=self.rows,
                message=(
                    f"stat '{stat_name}' took {seconds:.2f}s on column '{self.column}' "
                    f"of the {self.rows}-row '{self.frame}' frame (limit {self.time_limit:.2f}s). "
                    f"Likely a per-row python loop or an O(n^2) algorithm — "
                    f"vectorize with pandas/numpy operations.")))
        if peak_bytes > self.memory_limit:
            self.flagged.add(stat_name)
            self.findings.append(SmokeFinding(
                stat_name=stat_name, frame=self.frame, column=self.column,
                kind='memory', measured=peak_bytes, limit=self.memory_limit, rows=self.rows,
                message=(
                    f"stat '{stat_name}' allocated a peak of {peak_bytes / 1e6:.0f}MB on column "
                    f"'{self.column}' of the {self.rows}-row '{self.frame}' frame "
                    f"(limit {self.memory_limit / 1e6:.0f}MB). "
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


def run_perf_smoke(stat_funcs: list, rows: int = DEFAULT_ROWS,
        frames: Optional[Dict[str, Callable[..., pd.DataFrame]]] = None,
        max_time_ratio: float = 20.0, time_floor_seconds: float = 0.25,
        max_memory_ratio: float = 20.0,
        memory_floor_bytes: float = MEMORY_FLOOR_BYTES) -> SmokeResult:
    """Smoke-test stats for perf/memory pathologies on synthetic data.

    Accepts the same mixed input as StatPipeline (StatFunc, @stat functions,
    stat group classes, ColAnalysis subclasses). ``frames`` maps frame name to
    a ``maker(rows) -> DataFrame`` callable; defaults to SMOKE_FRAME_MAKERS.

    A stat is flagged when a single per-column call exceeds
    ``max(time_floor_seconds, max_time_ratio * baseline)`` wall-time or
    ``max(memory_floor_bytes, max_memory_ratio * frame_bytes)`` peak traced
    memory. Defaults are deliberately loose — this catches
    order-of-magnitude blowups, not 2x regressions.
    """
    frame_makers = SMOKE_FRAME_MAKERS if frames is None else frames
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
            for frame_name, maker in frame_makers.items():
                df = maker(n)
                recorder.frame = frame_name
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

    return SmokeResult(passed=(not recorder.findings), findings=recorder.findings,
        measurements=recorder.measurements)


def perf_smoke_test(stat_funcs: list, rows: int = DEFAULT_ROWS,
        frames: Optional[Dict[str, Callable[..., pd.DataFrame]]] = None,
        max_time_ratio: float = 20.0, time_floor_seconds: float = 0.25,
        max_memory_ratio: float = 20.0,
        memory_floor_bytes: float = MEMORY_FLOOR_BYTES) -> Tuple[bool, List[SmokeFinding]]:
    """``run_perf_smoke`` returning just ``(passed, findings)``, mirroring
    ``unit_test()``'s shape."""
    result = run_perf_smoke(stat_funcs, rows=rows, frames=frames,
        max_time_ratio=max_time_ratio, time_floor_seconds=time_floor_seconds,
        max_memory_ratio=max_memory_ratio, memory_floor_bytes=memory_floor_bytes)
    return result.passed, result.findings


def measurements_markdown(measurements: List[SmokeMeasurement]) -> str:
    """Per-stat markdown table: worst wall-time and worst peak memory across
    all frames/columns/scales, naming where each worst case happened."""
    worst_time: Dict[str, SmokeMeasurement] = {}
    worst_mem: Dict[str, SmokeMeasurement] = {}
    for m in measurements:
        if m.stat_name not in worst_time or m.seconds > worst_time[m.stat_name].seconds:
            worst_time[m.stat_name] = m
        if m.stat_name not in worst_mem or m.peak_bytes > worst_mem[m.stat_name].peak_bytes:
            worst_mem[m.stat_name] = m
    lines = ['| stat | worst time | worst peak memory |', '| --- | --- | --- |']
    for name in sorted(worst_time):
        wt, wm = worst_time[name], worst_mem[name]
        lines.append(
            f'| {name} | {wt.seconds * 1000:.1f}ms ({wt.frame}.{wt.column}, {wt.rows} rows) '
            f'| {wm.peak_bytes / 1e6:.1f}MB ({wm.frame}.{wm.column}, {wm.rows} rows) |')
    return '\n'.join(lines)
