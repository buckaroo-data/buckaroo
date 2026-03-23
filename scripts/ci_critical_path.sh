#!/bin/bash
# Usage: bash scripts/ci_critical_path.sh <run-id>
#
# Prints the critical path time (excluding Windows) for a GitHub Actions run.

set -euo pipefail

RUN_ID=$1

python3 -c "
import json, subprocess, sys
from datetime import datetime

def parse(t):
    return datetime.fromisoformat(t.replace('Z','+00:00'))

run_id = '$RUN_ID'
result = subprocess.run(
    ['gh', 'api', f'repos/buckaroo-data/buckaroo/actions/runs/{run_id}/jobs', '--paginate'],
    capture_output=True, text=True)
data = json.loads(result.stdout)
jobs = [(j['name'], j['started_at'], j['completed_at'], j['conclusion'])
        for j in data['jobs'] if j['completed_at'] and 'Windows' not in j['name']]

if not jobs:
    print('No completed non-Windows jobs found.')
    sys.exit(1)

starts = [parse(s) for _, s, e, _ in jobs]
ends = [parse(e) for _, s, e, _ in jobs]
cp = int((max(ends) - min(starts)).total_seconds())

first_start = min(starts)
last_end = max(ends)
last_job = [n for n, s, e, _ in jobs if parse(e) == last_end][0]

print(f'Run {run_id}: {cp//60}m{cp%60:02d}s (critical path excl Windows)')
print(f'  First job started: {min(starts).isoformat()}')
print(f'  Last job finished: {max(ends).isoformat()} ({last_job})')
print(f'  Jobs: {len(jobs)} completed (excl Windows)')
"
