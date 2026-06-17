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

The frame suite (``SMOKE_FRAME_MAKERS``) covers shapes with bug history in
buckaroo and shapes tallyman learned to stop emitting because the viewer
choked: unhashable object cells (#843), list<string> (#842), int64 beyond
2^53 (#800, #632), Decimal (#801), tz-aware datetimes (#277), all-null,
categorical, timedelta/duration (#622 and tallyman's cast-to-int64
guidance), Period/Interval (#799), date-only/time/binary (#918, tallyman's
date-not-timestamp guidance), uint8/uint64 (#791), inf/-inf extremes and
python ints past int64 (ddd_library ancestry). Findings name the frame that
triggered them. A frame whose maker or engine conversion raises is skipped —
shapes an engine rejects outright are unit-test territory, not perf
territory.

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
- Peak memory is measured two ways per call: ``tracemalloc`` (exact, but only
  sees python-heap allocations like numpy/pandas) and a native peak-RSS
  tracker (``_NativePeak``) that catches what tracemalloc can't — polars,
  Arrow and DataFusion allocate in native memory. A memory finding fires when
  either signal exceeds the limit.
- The harness is engine-agnostic where it can be: ``run_perf_smoke`` accepts
  polars frames (``perf_smoke_pl.PL_SMOKE_FRAME_MAKERS``) with a polars stat
  list, since polars stats run through the same ``StatPipeline``. The xorq
  pipeline executes differently — see ``perf_smoke_xorq``.
"""
from __future__ import annotations

import dataclasses
import datetime
import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import psutil
except ImportError:  # pragma: no cover - optional, used only as a fallback tracker
    psutil = None

try:
    import resource
except ImportError:  # pragma: no cover - windows
    resource = None

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
    # make others crawl (value_counts succeeds but takes seconds at 10k rows).
    # 842: list<string> columns were 80-100x slower through ServerDataflow.
    return pd.DataFrame({'list_cells': [[i, i + 1] for i in range(rows)],
        'dict_cells': [{'k': i} for i in range(rows)],
        'list_str_cells': [[f's{i}', f's{i + 1}'] for i in range(rows)]})


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


def _make_timedelta_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # Durations were so problematic downstream (mean() raises, parquet write
    # fails, polars Duration #622) that tallyman's MCP guidance tells LLMs to
    # cast them to int64 before buckaroo ever sees them. The viewer still
    # meets them from every other source.
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        'timedelta_col': pd.to_timedelta(rng.integers(0, 10**9, rows), unit='us'),
        'mixed_magnitude_td': pd.to_timedelta(
            rng.choice([1, 10**3, 10**6, 86_400 * 10**6], rows), unit='us')})


def _make_period_interval_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 799: xo.memtable rejects Period; ddd_library weird_types ancestry.
    # polars/xorq conversion rejects this frame — it skips there by design
    # and exercises the pandas pipeline only.
    return pd.DataFrame({
        'period_col': pd.period_range('2020-01', periods=rows, freq='M'),
        'interval_col': pd.arrays.IntervalArray.from_breaks(np.arange(rows + 1))})


def _make_date_time_binary_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # date-only columns: tallyman steers schemas to 'date' (timestamp shows
    # off-by-one across timezones). time + binary: 918 missed the approx
    # distinct path for both.
    base_date = datetime.date(2020, 1, 1)
    return pd.DataFrame({
        'date_col': [base_date + datetime.timedelta(days=int(i % 3650)) for i in range(rows)],
        'time_col': [datetime.time((i // 3600) % 24, (i // 60) % 60, i % 60)
                     for i in range(rows)],
        'binary_col': [b'\x00\x01' + str(i).encode() for i in range(rows)]})


def _make_uint_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # 791: uint8 dictionary indices broke /load; uint64 beyond int64 range
    # breaks anything that round-trips through int64.
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        'uint8_col': rng.integers(0, 255, rows, dtype=np.uint8),
        'uint64_beyond_int64': np.uint64(2**63) + rng.integers(0, 1_000, rows).astype(np.uint64)})


def _make_extreme_floats_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # df_with_infinity ancestry: inf/-inf/nan mixed, plus magnitudes at both
    # float64 extremes (overflow bait for sums/squares).
    rng = np.random.default_rng(seed)
    vals = rng.random(rows)
    vals[::7] = np.inf
    vals[1::11] = -np.inf
    vals[2::13] = np.nan
    return pd.DataFrame({'inf_floats': vals,
        'tiny_huge': np.where(rng.random(rows) < 0.5, 1e-308, 1e308)})


def _make_python_big_int_df(rows: int = DEFAULT_ROWS, seed: int = 42) -> pd.DataFrame:
    # df_with_really_big_number ancestry: python ints past int64 stay object
    # dtype and overflow any int64/float cast.
    return pd.DataFrame({
        'huge_int_obj': [9_999_999_999_999_999_999 + i for i in range(rows)]})


SMOKE_FRAME_MAKERS: Dict[str, Callable[..., pd.DataFrame]] = {'base': make_smoke_df, 'unhashable': _make_unhashable_df,
    'big_int64': _make_big_int64_df, 'decimal': _make_decimal_df, 'tz_datetime': _make_tz_datetime_df,
    'all_null': _make_all_null_df, 'categorical': _make_categorical_df,
    'timedelta': _make_timedelta_df, 'period_interval': _make_period_interval_df,
    'date_time_binary': _make_date_time_binary_df, 'uint': _make_uint_df,
    'extreme_floats': _make_extreme_floats_df, 'python_big_int': _make_python_big_int_df}


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
    and what it cost. Collected for every call, not just limit exceedances.
    ``peak_bytes`` is tracemalloc's python-heap peak; ``native_peak_bytes``
    is the process peak-RSS delta (catches polars/Arrow allocations)."""
    stat_name: str
    frame: str
    column: str
    rows: int
    seconds: float
    peak_bytes: float
    native_peak_bytes: float = 0.0


@dataclass
class SmokeResult:
    passed: bool
    findings: List[SmokeFinding]
    measurements: List[SmokeMeasurement]


class _SmokeSkip(Exception):
    """Raised inside a wrapped stat that was already flagged, so the pipeline
    records an Err instead of running the pathological code again."""


def _read_status_bytes(field: str) -> float:
    """Read a kB-valued field (VmRSS, VmHWM) from /proc/self/status."""
    with open('/proc/self/status') as fh:
        for line in fh:
            if line.startswith(field + ':'):
                return float(line.split()[1]) * 1024
    return 0.0


def _maxrss_bytes() -> float:
    # ru_maxrss is kB on linux, bytes on macOS
    val = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(val) * (1024 if sys.platform.startswith('linux') else 1)


def _choose_native_strategy() -> str:
    """Pick the best available native peak-memory tracker once at import.

    linux: the kernel's peak-RSS counter (VmHWM), reset per call by writing
    '5' to /proc/self/clear_refs — exact and dependency-free.
    psutil: a ~1ms sampling thread reading current RSS — approximate, but
    blowups big enough to matter (>20MB) live long enough to be sampled.
    maxrss: ru_maxrss high-water only — registers a peak only when it exceeds
    the process's previous maximum.
    """
    if sys.platform.startswith('linux'):
        try:
            with open('/proc/self/clear_refs', 'w') as fh:
                fh.write('5')
            if _read_status_bytes('VmHWM') > 0:
                return 'linux'
        except Exception:
            pass
    if psutil is not None:
        return 'psutil'
    if resource is not None:
        return 'maxrss'
    return 'none'


_NATIVE_STRATEGY = _choose_native_strategy()
_PSUTIL_PROC = psutil.Process() if psutil is not None else None


class _NativePeak:
    """Peak process-RSS delta across one call — the native-memory complement
    to tracemalloc. Catches polars/Arrow/DataFusion allocations, which never
    touch the python heap. RSS is confounded by allocator pooling (memory
    reused from a freed pool shows no delta), so this under-reports repeats;
    with flag-and-skip the first blowup is the one that matters."""

    def start(self) -> None:
        self.before = 0.0
        if _NATIVE_STRATEGY == 'linux':
            with open('/proc/self/clear_refs', 'w') as fh:
                fh.write('5')
            self.before = _read_status_bytes('VmRSS')
        elif _NATIVE_STRATEGY == 'psutil':
            self.before = float(_PSUTIL_PROC.memory_info().rss)
            self.peak = self.before
            self._stop_evt = threading.Event()
            self._thread = threading.Thread(target=self._sample, daemon=True)
            self._thread.start()
        elif _NATIVE_STRATEGY == 'maxrss':
            self.before = _maxrss_bytes()

    def _sample(self) -> None:
        while not self._stop_evt.wait(0.001):
            rss = float(_PSUTIL_PROC.memory_info().rss)
            if rss > self.peak:
                self.peak = rss

    def stop(self) -> float:
        if _NATIVE_STRATEGY == 'linux':
            return max(0.0, _read_status_bytes('VmHWM') - self.before)
        if _NATIVE_STRATEGY == 'psutil':
            self._stop_evt.set()
            self._thread.join()
            rss = float(_PSUTIL_PROC.memory_info().rss)
            if rss > self.peak:
                self.peak = rss
            return max(0.0, self.peak - self.before)
        if _NATIVE_STRATEGY == 'maxrss':
            return max(0.0, _maxrss_bytes() - self.before)
        return 0.0


def _frame_bytes(df) -> float:
    """Deep size of a pandas or polars frame."""
    if isinstance(df, pd.DataFrame):
        return float(df.memory_usage(deep=True).sum())
    return float(df.estimated_size())


# (pandas name, polars name) pairs for the canonical baseline ops
_CANONICAL_OP_NAMES = (('value_counts', 'value_counts'), ('sort_values', 'sort'),
    ('nunique', 'n_unique'))


def _canonical_ops(ser) -> list:
    ops = []
    for pd_name, pl_name in _CANONICAL_OP_NAMES:
        op = getattr(ser, pd_name, None)
        if op is None:
            op = getattr(ser, pl_name, None)
        if op is not None:
            ops.append(op)
    return ops


def _baseline_seconds(df) -> float:
    """Time canonical per-column work on a smoke frame (pandas or polars). A
    reasonable stat does far less than this; the time limit is a multiple of
    it. Ops that raise on a shape (value_counts on unhashable cells) are
    skipped — the absolute floor keeps the limit sane when most ops skip."""
    def work():
        for col in df.columns:
            for op in _canonical_ops(df[col]):
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

    def record(self, stat_name: str, seconds: float, peak_bytes: float,
               native_peak_bytes: float = 0.0) -> None:
        self.measurements.append(SmokeMeasurement(
            stat_name=stat_name, frame=self.frame, column=self.column,
            rows=self.rows, seconds=seconds, peak_bytes=peak_bytes,
            native_peak_bytes=native_peak_bytes))
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
        worst_mem = max(peak_bytes, native_peak_bytes)
        if worst_mem > self.memory_limit:
            signal = 'python-heap' if peak_bytes >= native_peak_bytes else 'native'
            self.flagged.add(stat_name)
            self.findings.append(SmokeFinding(
                stat_name=stat_name, frame=self.frame, column=self.column,
                kind='memory', measured=worst_mem, limit=self.memory_limit, rows=self.rows,
                message=(
                    f"stat '{stat_name}' allocated a peak of {worst_mem / 1e6:.0f}MB "
                    f"({signal}) on column '{self.column}' of the {self.rows}-row "
                    f"'{self.frame}' frame (limit {self.memory_limit / 1e6:.0f}MB). "
                    f"Avoid materializing large intermediates (pairwise matrices, "
                    f"cross joins, full copies per row).")))


def _measure(recorder: _Recorder, stat_name: str, fn, *args, **kwargs):
    """Run ``fn`` under wall-time + tracemalloc + native-RSS instrumentation
    and record the measurement. Exceptions propagate after recording; the
    flagged check is the caller's job."""
    before_bytes = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    native = _NativePeak()
    native.start()
    t0 = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        elapsed = time.perf_counter() - t0
        native_peak = native.stop()
        peak = tracemalloc.get_traced_memory()[1] - before_bytes
        recorder.record(stat_name, elapsed, peak, native_peak)


def _wrap(sf: StatFunc, recorder: _Recorder) -> StatFunc:
    inner = sf.func

    def measured(*args, **kwargs):
        if sf.name in recorder.flagged:
            raise _SmokeSkip(f"'{sf.name}' skipped after an earlier perf finding")
        return _measure(recorder, sf.name, inner, *args, **kwargs)

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
                try:
                    df = maker(n)
                except Exception:
                    continue  # engine can't represent this shape (e.g. Period in polars)
                recorder.frame = frame_name
                baseline = _baseline_seconds(df)
                recorder.configure(
                    rows=n,
                    time_limit=max(time_floor_seconds, max_time_ratio * baseline),
                    memory_limit=max(memory_floor_bytes,
                                     max_memory_ratio * _frame_bytes(df)))
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
    """Per-stat markdown table: worst wall-time, worst python-heap peak and
    worst native (RSS) peak across all frames/columns/scales, naming where
    each worst case happened."""
    worst_time: Dict[str, SmokeMeasurement] = {}
    worst_mem: Dict[str, SmokeMeasurement] = {}
    worst_native: Dict[str, SmokeMeasurement] = {}
    for m in measurements:
        if m.stat_name not in worst_time or m.seconds > worst_time[m.stat_name].seconds:
            worst_time[m.stat_name] = m
        if m.stat_name not in worst_mem or m.peak_bytes > worst_mem[m.stat_name].peak_bytes:
            worst_mem[m.stat_name] = m
        if (m.stat_name not in worst_native
                or m.native_peak_bytes > worst_native[m.stat_name].native_peak_bytes):
            worst_native[m.stat_name] = m
    lines = ['| stat | worst time | worst python-heap peak | worst native peak |',
        '| --- | --- | --- | --- |']
    for name in sorted(worst_time):
        wt, wm, wn = worst_time[name], worst_mem[name], worst_native[name]
        lines.append(
            f'| {name} | {wt.seconds * 1000:.1f}ms ({wt.frame}.{wt.column}, {wt.rows} rows) '
            f'| {wm.peak_bytes / 1e6:.1f}MB ({wm.frame}.{wm.column}, {wm.rows} rows) '
            f'| {wn.native_peak_bytes / 1e6:.1f}MB ({wn.frame}.{wn.column}, {wn.rows} rows) |')
    return '\n'.join(lines)
