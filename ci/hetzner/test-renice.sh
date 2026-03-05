#!/bin/bash
# Exp 60: Test whether renice actually helps CI performance.
#
# Runs CI 3 times with renice enabled, 3 times with DISABLE_RENICE=1,
# then compares total time and pw-jupyter duration.
#
# Usage:
#   bash ci/hetzner/test-renice.sh
#   bash ci/hetzner/test-renice.sh --sha=abc1234 --runs=5

set -uo pipefail

SERVER=${HETZNER_SERVER:-root@137.220.56.81}
CONTAINER=${HETZNER_CONTAINER:-buckaroo-ci}
RUNS=3
TEST_SHA=""

for arg in "$@"; do
    case "$arg" in
        --runs=*) RUNS="${arg#*=}" ;;
        --sha=*)  TEST_SHA="${arg#*=}" ;;
    esac
done

if [[ -z "$TEST_SHA" ]]; then
    TEST_SHA=$(git rev-parse --short origin/main 2>/dev/null || echo "")
    if [[ -z "$TEST_SHA" ]]; then
        echo "ERROR: no SHA specified and can't determine origin/main"
        exit 1
    fi
fi

LOGDIR="/opt/ci/logs/renice-test-$(date +%Y%m%d-%H%M%S)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Renice A/B test: $RUNS runs with, $RUNS runs without"
echo "  SHA: $TEST_SHA  Server: $SERVER"
echo "  Log dir: $LOGDIR"
echo "═══════════════════════════════════════════════════════════════"
echo ""

ssh "$SERVER" "mkdir -p $LOGDIR" </dev/null
ssh "$SERVER" "echo 'renice,run,status,total_s,pw_jupyter_s' > $LOGDIR/results.csv" </dev/null

run_one() {
    local label=$1 disable_renice=$2 run_num=$3

    echo -n "  [$label run $run_num/$RUNS] "

    local start_ts end_ts elapsed
    start_ts=$(date +%s)

    ssh "$SERVER" "docker exec \
        -e DISABLE_RENICE=$disable_renice \
        $CONTAINER bash /opt/ci-runner/run-ci.sh $TEST_SHA main \
        > $LOGDIR/${label}-run${run_num}.log 2>&1" </dev/null
    local rc=$?

    end_ts=$(date +%s)
    elapsed=$((end_ts - start_ts))
    local status=$( [[ $rc -eq 0 ]] && echo "PASS" || echo "FAIL" )

    # Extract pw-jupyter duration
    local pw_dur
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

    echo "$status  ${elapsed}s  pw-jupyter=${pw_dur:-?}s"
    ssh "$SERVER" "echo '$label,$run_num,$status,$elapsed,$pw_dur' >> $LOGDIR/results.csv" </dev/null
}

echo "── Phase 1: renice ENABLED ──"
for i in $(seq 1 "$RUNS"); do
    run_one "with-renice" 0 "$i"
done

echo ""
echo "── Phase 2: renice DISABLED ──"
for i in $(seq 1 "$RUNS"); do
    run_one "no-renice" 1 "$i"
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Results: $LOGDIR/results.csv"
echo "═══════════════════════════════════════════════════════════════"

# Summary
ssh "$SERVER" "python3 -c \"
import csv
from collections import defaultdict

rows = list(csv.DictReader(open('$LOGDIR/results.csv')))
groups = defaultdict(list)
for r in rows:
    groups[r['renice']].append(r)

for label, runs in sorted(groups.items()):
    times = [int(r['total_s']) for r in runs]
    pw_times = [int(r['pw_jupyter_s']) for r in runs if r['pw_jupyter_s']]
    passes = sum(1 for r in runs if r['status'] == 'PASS')
    mean_t = sum(times) / len(times)
    mean_pw = sum(pw_times) / len(pw_times) if pw_times else 0
    print(f'  {label:15s}  pass={passes}/{len(runs)}  mean={mean_t:.0f}s  pw-jupyter={mean_pw:.0f}s')
\"" </dev/null 2>/dev/null || true
