#!/usr/bin/env python3
"""Run the perf/memory smoke harness over the shipped stat lists and report.

Used by the `Stats / Perf Smoke Report` CI job: prints a per-stat worst-case
time / peak-memory markdown table, appends it to the job summary when
$GITHUB_STEP_SUMMARY is set, and exits 1 if any stat blows the loose smoke
limits. The table is for spotting drift between runs; only order-of-magnitude
blowups fail the job. See issue #920.

Usage:
    uv run python scripts/perf_smoke_report.py
"""
import os
import sys

from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2
from buckaroo.pluggable_analysis_framework.perf_smoke import (
    measurements_markdown, run_perf_smoke)


def main() -> int:
    result = run_perf_smoke(PD_ANALYSIS_V2)
    sections = ['## Summary stat perf smoke (PD_ANALYSIS_V2)', '',
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
    return 1 if not result.passed else 0


if __name__ == '__main__':
    sys.exit(main())
