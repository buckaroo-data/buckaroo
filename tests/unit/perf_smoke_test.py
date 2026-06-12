"""Tests for perf_smoke_test — perf/memory smoke testing of summary stats.

StatPipeline.unit_test() runs stats against the 10-row PERVERSE_DF and only
catches raised errors. perf_smoke_test() catches stats that are *correct but
pathological* — per-row python loops, O(n^2) algorithms, huge intermediate
allocations — which is what user- and LLM/MCP-authored stats tend to get
wrong.
"""

import datetime

import numpy as np
import pandas as pd

from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
from buckaroo.pluggable_analysis_framework.perf_smoke import (
    SMOKE_FRAME_MAKERS, measurements_markdown, perf_smoke_test, run_perf_smoke)
from buckaroo.pluggable_analysis_framework.perf_smoke_pl import PL_SMOKE_FRAME_MAKERS
from buckaroo.pluggable_analysis_framework.stat_func import stat, RawSeries


@stat()
def smoke_length(ser: RawSeries) -> int:
    return len(ser)


@stat()
def smoke_null_count(ser: RawSeries) -> int:
    return int(ser.isna().sum())


def test_well_behaved_stats_pass():
    passed, findings = perf_smoke_test([smoke_length, smoke_null_count], rows=2_000)
    assert passed is True
    assert findings == []


def test_slow_stat_flagged():
    # The classic LLM-authored shape: a nested python loop over the series.
    # Quadratic, so it sails through the 10-row unit_test but is unusable on
    # real data.
    @stat()
    def slow_pairwise(ser: RawSeries) -> int:
        total = 0
        for v in ser:
            for w in ser:
                if v == w:
                    total += 1
        return total

    passed, findings = perf_smoke_test([slow_pairwise], rows=2_000)
    assert passed is False
    time_findings = [f for f in findings if f.kind == 'time' and f.stat_name == 'slow_pairwise']
    assert time_findings
    assert 'slow_pairwise' in time_findings[0].message
    # Once flagged, the stat must not keep running: at most one time finding
    # per scale, not one per column.
    assert len(time_findings) <= 2


def test_memory_hog_flagged():
    # ~64MB scratch allocation on a ~0.3MB input frame.
    @stat()
    def memory_hog(ser: RawSeries) -> float:
        scratch = np.ones((len(ser), 4_000))
        return float(scratch.sum())

    passed, findings = perf_smoke_test([memory_hog], rows=2_000)
    assert passed is False
    mem_findings = [f for f in findings if f.kind == 'memory' and f.stat_name == 'memory_hog']
    assert mem_findings
    assert 'memory_hog' in mem_findings[0].message


def test_smoke_frames_cover_known_killers():
    # Shapes with bug history in buckaroo — unhashable cells (#843),
    # list<string> (#842), int64 past 2^53 (#800/#632), Decimal (#801),
    # tz-aware datetimes (#277), Period (#799), uint8 (#791), time/binary
    # (#918), all-null, categorical — plus shapes tallyman learned to stop
    # emitting (timedelta/duration, timestamp-for-date) and ddd_library
    # ancestry (inf, python ints past int64).
    expected = {'base', 'unhashable', 'big_int64', 'decimal', 'tz_datetime',
        'all_null', 'categorical', 'timedelta', 'period_interval',
        'date_time_binary', 'uint', 'extreme_floats', 'python_big_int'}
    assert expected <= set(SMOKE_FRAME_MAKERS)
    frames = {name: maker(100) for name, maker in SMOKE_FRAME_MAKERS.items()}
    for name, df in frames.items():
        assert len(df) == 100, name
    assert isinstance(frames['unhashable'].iloc[0, 0], list)
    assert isinstance(frames['unhashable']['list_str_cells'].iloc[0][0], str)
    assert (frames['big_int64'] > 2**53).any().any()
    assert frames['all_null'].isna().all().all()
    assert isinstance(frames['categorical'].dtypes.iloc[0], pd.CategoricalDtype)
    assert frames['timedelta']['timedelta_col'].dtype.kind == 'm'
    assert isinstance(frames['period_interval']['period_col'].dtype, pd.PeriodDtype)
    assert isinstance(frames['date_time_binary']['date_col'].iloc[0], datetime.date)
    assert isinstance(frames['date_time_binary']['binary_col'].iloc[0], bytes)
    assert int(frames['uint']['uint64_beyond_int64'].iloc[0]) > 2**63 - 1
    assert np.isinf(frames['extreme_floats']['inf_floats']).any()
    assert frames['python_big_int']['huge_int_obj'].iloc[0] > np.iinfo(np.int64).max


def test_findings_name_the_frame():
    @stat()
    def memory_hog_frames(ser: RawSeries) -> float:
        scratch = np.ones((len(ser), 4_000))
        return float(scratch.sum())

    passed, findings = perf_smoke_test([memory_hog_frames], rows=2_000)
    assert passed is False
    finding = findings[0]
    assert finding.frame in SMOKE_FRAME_MAKERS
    assert finding.frame in finding.message


def test_run_perf_smoke_measurements_and_markdown():
    result = run_perf_smoke([smoke_length], rows=2_000)
    assert result.passed is True
    assert {m.frame for m in result.measurements} == set(SMOKE_FRAME_MAKERS)
    md = measurements_markdown(result.measurements)
    assert 'smoke_length' in md
    assert md.startswith('|')
    assert 'native' in md


def test_polars_native_memory_hog_flagged():
    # ~32MB allocated by polars' Rust-side allocator — invisible to
    # tracemalloc, which is why the harness also tracks peak RSS.
    @stat()
    def pl_native_hog(ser: RawSeries) -> int:
        big = ser.sample(len(ser) * 4_000, with_replacement=True, seed=1)
        return len(big)

    passed, findings = perf_smoke_test([pl_native_hog], rows=2_000,
        frames={'base': PL_SMOKE_FRAME_MAKERS['base']})
    assert passed is False
    mem_findings = [f for f in findings if f.kind == 'memory' and f.stat_name == 'pl_native_hog']
    assert mem_findings
    assert 'native' in mem_findings[0].message


def test_polars_stats_over_polars_frames():
    result = run_perf_smoke(PL_ANALYSIS_V2, rows=2_000, frames=PL_SMOKE_FRAME_MAKERS)
    assert result.passed is True, [f.message for f in result.findings]
    measured_frames = {m.frame for m in result.measurements}
    # Frames whose pandas->polars conversion raises (Period/Interval) skip by
    # design; everything else must be measured.
    assert measured_frames <= set(PL_SMOKE_FRAME_MAKERS)
    assert {'base', 'unhashable', 'big_int64', 'decimal', 'tz_datetime',
        'all_null', 'categorical', 'timedelta', 'uint'} <= measured_frames
