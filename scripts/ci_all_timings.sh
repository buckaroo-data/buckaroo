#!/bin/bash
# Usage: bash scripts/ci_all_timings.sh <run-id> [<run-id> ...]
#
# Outputs one JSON line per run with critical path, wave1 stagger, per-job
# durations, and cache read/write stats. Pipe to ci_timing_table.py for
# formatted output.
#
# Example:
#   bash scripts/ci_all_timings.sh 12345 67890 | python3 scripts/ci_timing_table.py

set -euo pipefail

for RUN_ID in "$@"; do
python3 -c "
import json, subprocess, sys
from datetime import datetime

def parse(t):
    return datetime.fromisoformat(t.replace('Z','+00:00'))

def dur(s, e):
    return int((parse(e) - parse(s)).total_seconds())

run_id = '$RUN_ID'
result = subprocess.run(
    ['gh', 'api', f'repos/buckaroo-data/buckaroo/actions/runs/{run_id}/jobs', '--paginate'],
    capture_output=True, text=True)
data = json.loads(result.stdout)

# Run metadata
run_meta = subprocess.run(
    ['gh', 'api', f'repos/buckaroo-data/buckaroo/actions/runs/{run_id}'],
    capture_output=True, text=True)
meta = json.loads(run_meta.stdout)
branch = meta.get('head_branch', '')
created = meta.get('created_at', '')

# Per-job timings (excl Windows)
jobs = {}
for j in data['jobs']:
    if not j['completed_at'] or 'Windows' in j['name']:
        continue
    jobs[j['name']] = dur(j['started_at'], j['completed_at'])

# Critical path
completed = [(j['name'], j['started_at'], j['completed_at'])
             for j in data['jobs'] if j['completed_at'] and 'Windows' not in j['name']]
if not completed:
    sys.exit(0)
starts = [parse(s) for _, s, _ in completed]
ends = [parse(e) for _, _, e in completed]
critical_path = int((max(ends) - min(starts)).total_seconds())

# Wave 1 stagger
wave1_names = [n for n, _, _ in completed if 'Playwright' not in n and 'MCP' not in n
               and 'Smoke' not in n and 'Publish' not in n and 'Static Embed' not in n]
wave1_starts = sorted([parse(s) for n, s, _ in completed if n in wave1_names])
wave1_stagger = int((wave1_starts[-1] - wave1_starts[0]).total_seconds()) if len(wave1_starts) >= 2 else 0

# Cache stats from steps
reads = []
writes = []
for j in data['jobs']:
    if 'Windows' in j['name']:
        continue
    for step in j['steps']:
        if not step['completed_at']:
            continue
        d = dur(step['started_at'], step['completed_at'])
        name = step['name']
        is_read = (any(x in name for x in ['Install uv', 'Install the project', 'Install pnpm', 'Cache Playwright'])
                   and not name.startswith('Post'))
        is_write = (name.startswith('Post ')
                    and any(x in name for x in ['uv', 'cache', 'Cache', 'Playwright'])
                    and 'checkout' not in name and 'pnpm' not in name)
        if is_read:
            reads.append(d)
        elif is_write:
            writes.append(d)

output = {
    'run_id': run_id,
    'branch': branch,
    'created': created,
    'critical_path': critical_path,
    'wave1_stagger': wave1_stagger,
    'jobs': jobs,
    'cache_reads': reads,
    'cache_writes': writes,
    'cache_read_total': sum(reads),
    'cache_write_total': sum(writes),
    'cache_read_mean': round(sum(reads)/len(reads), 1) if reads else 0,
    'cache_write_mean': round(sum(writes)/len(writes), 1) if writes else 0,
}
print(json.dumps(output))
"
done
