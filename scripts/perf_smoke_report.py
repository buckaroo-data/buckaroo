#!/usr/bin/env python3
"""Run the perf/memory smoke harness over the shipped stat lists and report.

Used by the `Stats / Perf Smoke Report` CI job: prints a per-stat worst-case
time / memory markdown table per engine (pandas, polars, xorq — the latter
two when installed), appends them to the job summary when
$GITHUB_STEP_SUMMARY is set, and exits 1 if any stat blows the loose smoke
limits. The tables are for spotting drift between runs; only
order-of-magnitude blowups fail the job. See issue #920.

Usage:
    uv run python scripts/perf_smoke_report.py
"""
import os
import sys

from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2
from buckaroo.pluggable_analysis_framework.perf_smoke import (
    measurements_markdown, run_perf_smoke)

try:
    from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2
    from buckaroo.pluggable_analysis_framework.perf_smoke_pl import PL_SMOKE_FRAME_MAKERS
except ImportError:
    PL_ANALYSIS_V2 = None

try:
    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2
    from buckaroo.pluggable_analysis_framework.perf_smoke_xorq import run_xorq_perf_smoke
except ImportError:
    XORQ_STATS_V2 = None


def _suites():
    suites = [('PD_ANALYSIS_V2 (pandas)', lambda: run_perf_smoke(PD_ANALYSIS_V2))]
    if PL_ANALYSIS_V2 is not None:
        suites.append(('PL_ANALYSIS_V2 (polars)',
            lambda: run_perf_smoke(PL_ANALYSIS_V2, frames=PL_SMOKE_FRAME_MAKERS)))
    else:
        print('polars not installed — skipping polars suite', file=sys.stderr)
    if XORQ_STATS_V2 is not None:
        suites.append(('XORQ_STATS_V2 (xorq)', lambda: run_xorq_perf_smoke(XORQ_STATS_V2)))
    else:
        print('xorq not installed — skipping xorq suite', file=sys.stderr)
    return suites


def main() -> int:
    all_passed = True
    sections = []
    for title, runner in _suites():
        result = runner()
        all_passed = all_passed and result.passed
        sections += [f'## Summary stat perf smoke — {title}', '',
            measurements_markdown(result.measurements), '']
        if result.findings:
            sections += ['### Findings', '']
            sections += [f'- {finding.message}' for finding in result.findings]
            sections += ['']
    report = '\n'.join(sections)
    print(report)
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a') as fh:
            fh.write(report + '\n')
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
