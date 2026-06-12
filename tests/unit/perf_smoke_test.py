"""Tests for perf_smoke_test — perf/memory smoke testing of summary stats.

StatPipeline.unit_test() runs stats against the 10-row PERVERSE_DF and only
catches raised errors. perf_smoke_test() catches stats that are *correct but
pathological* — per-row python loops, O(n^2) algorithms, huge intermediate
allocations — which is what user- and LLM/MCP-authored stats tend to get
wrong.
"""

import numpy as np
import pandas as pd

from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2
from buckaroo.pluggable_analysis_framework.perf_smoke import (
    SMOKE_FRAME_MAKERS, measurements_markdown, perf_smoke_test, run_perf_smoke)
from buckaroo.pluggable_analysis_framework.perf_smoke_pl import PL_SMOKE_FRAME_MAKERS
from buckaroo.pluggable_analysis_framework.perf_smoke_xorq import run_xorq_perf_smoke
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
    # Shapes with bug history: unhashable cells (#843), int64 past 2^53
    # (#800/#632), Decimal (#801), tz-aware datetimes (#277), all-null,
    # categorical.
    expected = {'base', 'unhashable', 'big_int64', 'decimal', 'tz_datetime',
        'all_null', 'categorical'}
    assert expected <= set(SMOKE_FRAME_MAKERS)
    frames = {name: maker(100) for name, maker in SMOKE_FRAME_MAKERS.items()}
    for name, df in frames.items():
        assert len(df) == 100, name
    assert isinstance(frames['unhashable'].iloc[0, 0], list)
    assert (frames['big_int64'] > 2**53).any().any()
    assert frames['all_null'].isna().all().all()
    assert isinstance(frames['categorical'].dtypes.iloc[0], pd.CategoricalDtype)


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
    assert {m.frame for m in result.measurements} == set(PL_SMOKE_FRAME_MAKERS)


def test_xorq_batch_stats_measured():
    # Batch aggregate stats never execute inside their own python func; the
    # xorq runner times each one as its own single-expression aggregate.
    result = run_xorq_perf_smoke(XORQ_STATS_V2, rows=2_000,
        frames={'base': SMOKE_FRAME_MAKERS['base']})
    measured = {m.stat_name for m in result.measurements}
    assert {'min', 'mean'} <= measured  # batch aggregates, individually executed
    assert 'histogram' in measured  # post-batch expression stat via the pipeline


def test_xorq_slow_stat_flagged():
    # Deterministic CPU burn standing in for a pathological post-batch stat.
    @stat()
    def xorq_slow_post(length: int) -> int:
        total = 0
        for _ in range(length):
            for _ in range(5_000):
                total += 1
        return total

    result = run_xorq_perf_smoke(list(XORQ_STATS_V2) + [xorq_slow_post], rows=2_000,
        frames={'base': SMOKE_FRAME_MAKERS['base']})
    assert result.passed is False
    time_findings = [f for f in result.findings
        if f.kind == 'time' and f.stat_name == 'xorq_slow_post']
    assert time_findings
