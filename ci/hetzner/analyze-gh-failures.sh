#!/bin/bash
# Exp 59: Analyze GitHub Actions failure patterns on main branch.
#
# Queries the last N CI runs on main, identifies which jobs fail most often,
# and correlates with commit types (Python-only, JS-only, mixed).
#
# Usage (local):
#   bash ci/hetzner/analyze-gh-failures.sh
#   bash ci/hetzner/analyze-gh-failures.sh --limit=100

set -uo pipefail

LIMIT=50

for arg in "$@"; do
    case "$arg" in
        --limit=*) LIMIT="${arg#*=}" ;;
    esac
done

echo "═══════════════════════════════════════════════════════════════"
echo "  GitHub Actions failure analysis — last $LIMIT runs on main"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Get recent runs
echo "Fetching runs..."
RUNS_JSON=$(gh run list --branch main --limit "$LIMIT" --json databaseId,conclusion,headSha,displayTitle,event,createdAt)
TOTAL=$(echo "$RUNS_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "  Found $TOTAL runs"
echo ""

# Analyze conclusions
echo "── Run outcomes ──"
echo "$RUNS_JSON" | python3 -c "
import json, sys
from collections import Counter

runs = json.load(sys.stdin)
c = Counter(r['conclusion'] for r in runs)
for conclusion, count in c.most_common():
    pct = 100 * count / len(runs)
    print(f'  {conclusion:15s} {count:4d} ({pct:.0f}%)')
print()
"

# Get failed run details
echo "── Failed runs — per-job breakdown ──"
FAILED_IDS=$(echo "$RUNS_JSON" | python3 -c "
import json, sys
runs = json.load(sys.stdin)
for r in runs:
    if r['conclusion'] == 'failure':
        print(r['databaseId'])
")

if [[ -z "$FAILED_IDS" ]]; then
    echo "  No failures found!"
    exit 0
fi

# For each failed run, get which jobs failed
declare -A JOB_FAIL_COUNT
OUTFILE=$(mktemp -t gh-failures.XXXX)

echo "$FAILED_IDS" | while read -r run_id; do
    gh run view "$run_id" --json jobs 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for job in data.get('jobs', []):
        if job.get('conclusion') == 'failure':
            print(f\"$run_id {job['name']}\")
except Exception:
    pass
" >> "$OUTFILE"
done

echo ""
echo "── Job failure frequency ──"
python3 -c "
from collections import Counter

lines = open('$OUTFILE').readlines()
jobs = [line.strip().split(' ', 1)[1] for line in lines if ' ' in line.strip()]
c = Counter(jobs)
total_fails = len(set(line.strip().split(' ', 1)[0] for line in lines if ' ' in line.strip()))
print(f'  Total failed runs with job data: {total_fails}')
print()
for job, count in c.most_common(20):
    print(f'  {count:4d}  {job}')
"

# Correlate with file types changed
echo ""
echo "── Failure correlation with change type ──"
echo "$RUNS_JSON" | python3 -c "
import json, sys, subprocess

runs = json.load(sys.stdin)
failed = [r for r in runs if r['conclusion'] == 'failure']

for r in failed[:10]:  # Sample first 10
    sha = r['headSha'][:7]
    title = r['displayTitle'][:60]
    try:
        diff = subprocess.check_output(
            ['git', 'diff', '--name-only', f'{sha}~1', sha],
            stderr=subprocess.DEVNULL, text=True
        )
        files = diff.strip().split('\n') if diff.strip() else []
        py_files = [f for f in files if f.endswith('.py')]
        js_files = [f for f in files if f.endswith(('.ts', '.tsx', '.js', '.jsx'))]
        ci_files = [f for f in files if f.startswith(('ci/', '.github/'))]
        change_type = []
        if py_files: change_type.append(f'py:{len(py_files)}')
        if js_files: change_type.append(f'js:{len(js_files)}')
        if ci_files: change_type.append(f'ci:{len(ci_files)}')
        if not change_type: change_type = ['other']
        print(f'  {sha}  {\" \".join(change_type):20s}  {title}')
    except Exception:
        print(f'  {sha}  (diff unavailable)  {title}')
"

rm -f "$OUTFILE"
echo ""
echo "Done."
