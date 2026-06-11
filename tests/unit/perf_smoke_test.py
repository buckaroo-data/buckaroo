"""Tests for perf_smoke_test — perf/memory smoke testing of summary stats.

StatPipeline.unit_test() runs stats against the 10-row PERVERSE_DF and only
catches raised errors. perf_smoke_test() catches stats that are *correct but
pathological* — per-row python loops, O(n^2) algorithms, huge intermediate
allocations — which is what user- and LLM/MCP-authored stats tend to get
wrong.
"""

import numpy as np

from buckaroo.pluggable_analysis_framework.perf_smoke import perf_smoke_test
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
