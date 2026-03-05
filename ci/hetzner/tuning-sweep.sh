#!/bin/bash
# Exp 57: Systematic parameter sweep for CI tuning.
#
# Sweeps JUPYTER_PARALLEL × STAGGER_DELAY across multiple runs to find
# the optimal configuration. Results saved to a CSV for analysis.
#
# Usage:
#   ssh root@137.220.56.81
#   tmux new -s sweep
#   bash /opt/ci/repo/ci/hetzner/tuning-sweep.sh
#
# Or from local:
#   bash ci/hetzner/tuning-sweep.sh
#
# Parameters:
#   --runs=N       Runs per combination (default 3)
#   --sha=SHA      Commit to test (default: latest main)
#   --dry-run      Print what would run

set -uo pipefail

SERVER=${HETZNER_SERVER:-root@137.220.56.81}
CONTAINER=${HETZNER_CONTAINER:-buckaroo-ci}
RUNS_PER_COMBO=3
TEST_SHA=""
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --runs=*)   RUNS_PER_COMBO="${arg#*=}" ;;
        --sha=*)    TEST_SHA="${arg#*=}" ;;
        --dry-run)  DRY_RUN=true ;;
    esac
done

# Use latest main if no SHA specified
if [[ -z "$TEST_SHA" ]]; then
    TEST_SHA=$(git rev-parse --short origin/main 2>/dev/null || echo "")
    if [[ -z "$TEST_SHA" ]]; then
        echo "ERROR: no SHA specified and can't determine origin/main"
        exit 1
    fi
fi

# Parameter grid
PARALLEL_VALUES=(5 7 9)
STAGGER_VALUES=(0 1 2 3)

TOTAL_COMBOS=$(( ${#PARALLEL_VALUES[@]} * ${#STAGGER_VALUES[@]} ))
TOTAL_RUNS=$(( TOTAL_COMBOS * RUNS_PER_COMBO ))

LOGDIR="/opt/ci/logs/sweep-$(date +%Y%m%d-%H%M%S)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Tuning sweep: ${#PARALLEL_VALUES[@]} PARALLEL × ${#STAGGER_VALUES[@]} STAGGER = $TOTAL_COMBOS combos"
echo "  Runs per combo: $RUNS_PER_COMBO  Total runs: $TOTAL_RUNS"
echo "  SHA: $TEST_SHA  Server: $SERVER"
echo "  Log dir: $LOGDIR"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    for p in "${PARALLEL_VALUES[@]}"; do
        for s in "${STAGGER_VALUES[@]}"; do
            echo "  P=$p STAGGER=$s × $RUNS_PER_COMBO runs"
        done
    done
    echo ""
    echo "(dry run — nothing executed)"
    exit 0
fi

# Create log dir on server
ssh "$SERVER" "mkdir -p $LOGDIR" </dev/null

# CSV header
ssh "$SERVER" "echo 'parallel,stagger,run,status,total_s,pw_jupyter_s' > $LOGDIR/sweep.csv" </dev/null

run_idx=0

for p in "${PARALLEL_VALUES[@]}"; do
    for s in "${STAGGER_VALUES[@]}"; do
        for run in $(seq 1 "$RUNS_PER_COMBO"); do
            ((run_idx++))
            echo "[$run_idx/$TOTAL_RUNS] P=$p STAGGER=$s run=$run ..."

            start_ts=$(date +%s)

            # Run CI with tuning parameters
            ssh "$SERVER" "docker exec \
                -e JUPYTER_PARALLEL=$p \
                -e STAGGER_DELAY=$s \
                $CONTAINER bash /opt/ci-runner/run-ci.sh $TEST_SHA main \
                > $LOGDIR/run-P${p}-S${s}-R${run}.log 2>&1" </dev/null
            rc=$?

            end_ts=$(date +%s)
            elapsed=$((end_ts - start_ts))
            status=$( [[ $rc -eq 0 ]] && echo "PASS" || echo "FAIL" )

            # Extract pw-jupyter duration from ci.log
            pw_dur=$(ssh "$SERVER" "python3 -c \"
import re
from datetime import datetime
lines = open('/opt/ci/logs/${TEST_SHA}/ci.log').readlines()
start = end = None
for line in lines:
    m = re.match(r'\[(\d{2}:\d{2}:\d{2})\] (START|PASS|FAIL)\s+playwright-jupyter', line)
    if m:
        ts = datetime.strptime(m.group(1), '%H:%M:%S')
        if m.group(2) == 'START': start = ts
        else: end = ts
if start and end:
    print(int((end - start).total_seconds()))
else:
    print('')
\" 2>/dev/null" </dev/null || echo "")

            echo "  $status  ${elapsed}s  pw-jupyter=${pw_dur:-?}s"

            # Append to CSV
            ssh "$SERVER" "echo '$p,$s,$run,$status,$elapsed,$pw_dur' >> $LOGDIR/sweep.csv" </dev/null
        done
    done
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Sweep complete: $LOGDIR/sweep.csv"
echo "═══════════════════════════════════════════════════════════════"

# Print summary table
ssh "$SERVER" "python3 -c \"
import csv
from collections import defaultdict

rows = list(csv.DictReader(open('$LOGDIR/sweep.csv')))
combos = defaultdict(list)
for r in rows:
    key = (r['parallel'], r['stagger'])
    combos[key].append(r)

print(f'{'P':>3} {'S':>3} {'Pass':>6} {'Mean(s)':>8} {'PW-JP(s)':>9}')
print('-' * 35)
for (p, s), runs in sorted(combos.items()):
    passes = sum(1 for r in runs if r['status'] == 'PASS')
    total = len(runs)
    mean_t = sum(int(r['total_s']) for r in runs) / total
    pw_times = [int(r['pw_jupyter_s']) for r in runs if r['pw_jupyter_s']]
    mean_pw = sum(pw_times) / len(pw_times) if pw_times else 0
    print(f'{p:>3} {s:>3} {passes}/{total:>2}  {mean_t:>7.0f}  {mean_pw:>8.0f}')
\"" </dev/null 2>/dev/null || true
