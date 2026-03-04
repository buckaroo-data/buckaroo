#!/bin/bash
# Stress test: run the Hetzner CI against a list of known commits.
#
# Usage:
#   bash ci/hetzner/stress-test.sh                  # run all safe (passing) commits
#   bash ci/hetzner/stress-test.sh --dag             # use run-ci-dag.sh
#   bash ci/hetzner/stress-test.sh --stagger DELAY_PY311=15 DELAY_PY312=15
#   bash ci/hetzner/stress-test.sh --set=failing     # run known-failing commits
#   bash ci/hetzner/stress-test.sh --set=older       # run older Jan/Feb commits
#   bash ci/hetzner/stress-test.sh --set=all         # run all commit sets
#   bash ci/hetzner/stress-test.sh --limit=5         # first 5 only
#   bash ci/hetzner/stress-test.sh --dry-run         # print what would run
#   bash ci/hetzner/stress-test.sh --synth           # use synthetic merge commits
#   bash ci/hetzner/stress-test.sh <sha1> <sha2> ... # specific SHAs
#
# Runs each commit sequentially on the Hetzner server via docker exec.
# For each commit, collects:
#   - pass/fail status and wall time
#   - CPU/memory samples at 2s intervals (resources-<sha>.csv)
#   - per-job START/PASS/FAIL timing parsed from ci.log (jobs-<sha>.csv)
#
# All results saved to $LOGDIR on the server, plus a local summary printed.
#
# NOTE: This script runs from your LOCAL machine and SSHes into Hetzner for
# each commit. If your laptop sleeps or loses network, the run dies mid-way.
# For unattended runs (e.g. kick off before driving to work), SSH into the
# server and run inside tmux/screen:
#
#   ssh root@5.161.210.126
#   tmux new -s stress
#   # scp or git pull this script onto the server first, then:
#   bash stress-test.sh --dag --set=safe
#   # Ctrl-B D to detach, reattach later with: tmux attach -t stress
#
# The script would need a small refactor to skip the SSH wrapping when
# running directly on the server (replace `ssh $SERVER "docker exec ..."`
# with just `docker exec ...`). Not yet implemented.

set -uo pipefail

SERVER=${HETZNER_SERVER:-root@5.161.210.126}
CONTAINER=${HETZNER_CONTAINER:-buckaroo-ci}
RUNNER="run-ci.sh"
LIMIT=0
DRY_RUN=false
COMMIT_SET="safe"
USE_SYNTH=false
SYNTH_MAP=/opt/ci/synth-map.txt
CUSTOM_SHAS=()
DOCKER_ENV_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --dag)       RUNNER="run-ci-dag.sh"; shift ;;
        --stagger)   RUNNER="run-ci-dag-stagger.sh"; shift ;;
        --limit=*)   LIMIT="${1#*=}"; shift ;;
        --limit)     LIMIT="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --runner=*)  RUNNER="${1#*=}"; shift ;;
        --set=*)     COMMIT_SET="${1#*=}"; shift ;;
        --set)       COMMIT_SET="$2"; shift 2 ;;
        --synth)     USE_SYNTH=true; shift ;;
        --synth=*)   USE_SYNTH=true; SYNTH_MAP="${1#*=}"; shift ;;
        DELAY_PY*=*) DOCKER_ENV_ARGS+=("-e" "$1"); shift ;;
        *)           CUSTOM_SHAS+=("$1"); shift ;;
    esac
done

# ── Commit sets ────────────────────────────────────────────────────────────────

# 16 recent main commits — all passed GitHub CI (2026-02-23 → 2026-02-28).
SAFE_COMMITS=(
    7b6a05c   # feat: content-aware column widths
    fcfe368   # feat: compact_number displayer
    5ff4d6e   # Add CLAUDE.md
    837654e   # fix: defaultMinWidth on fitCellContents
    f8a8b94   # feat: color_static color rule
    314e89f   # feat: /load_compare endpoint
    8e9e1ed   # Fix BuckarooCompare for arbitrary join keys
    1fccaba   # fix: Playwright row count off-by-one
    b7956f8   # fix: harden release workflow
    612e22f   # Fix left-pinned index column
    e392c78   # fix: MCP + server reliability
    6b9e695   # fix: handle zero PRs in release notes
    6056636   # fix: plain release notes fallback
    ec68a78   # for the PR
    2175249   # fix: add GH_TOKEN to release notes
    fdbe325   # test: MCP server integration tests
)

# 15 commits that failed at least one check on GitHub Actions.
# Mix of Playwright, Python test, lint, and CI config failures.
FAILING_COMMITS=(
    cf7e02a   # ci: test 8-CPU Depot runners              (Screenshots fail)
    e0f358a   # ci: test 4-CPU Depot runners              (Screenshots fail)
    7b3141c   # ci: latency measurement test              (Screenshots fail)
    703c034   # Address PR review on compare module       (Python Test 3.11 fail)
    db1ca96   # Fix left-pinned index column              (pw-server + pw-marimo fail)
    4ddcac1   # fix: release workflow review comments      (pw-server + pw-marimo fail)
    7d8b751   # Fix marimo Playwright tests               (pw-wasm-marimo fail)
    b1eb6a5   # ci: continue-on-error in build.yml        (pw-wasm-marimo fail)
    1839f59   # ci: skip unnecessary lint deps             (pw-wasm-marimo fail)
    88a8743   # ci: Python 3.14 in build.yml              (pw-wasm-marimo fail)
    2bec338   # ci: optimize job structure + cache PW      (pw-wasm-marimo fail)
    c8e98d3   # ci: 4min timeout to marimo tests          (pw-wasm-marimo fail)
    7b9c341   # Remove accidental -l and wc files          (Python Test 3.11 fail)
    516a1fa   # ci: v1 cache-based BuildWheel              (pw-wasm + pw-marimo + lint)
    f01c9c6   # ci: v2 self-build per job                  (pw-wasm + pw-marimo + pytest)
)

# 16 older commits from Jan–mid Feb 2026 (pre-CI or early CI era).
# No GitHub Actions results, but good for testing the Hetzner runner against
# older code that may lack scripts/configs the runner expects.
OLDER_COMMITS=(
    f10ee77   # Auto-kill old server on upgrade            (2026-02-17)
    3bb6d71   # Fix search not updating table in MCP app   (2026-02-16)
    8623244   # Fix summary stats view in MCP app          (2026-02-16)
    5c3f861   # MCP install tweaks 2                       (2026-02-14)
    e2f610f   # Summary stats parquet b64                  (2026-02-12)
    ae9006d   # MCP UI tool                                (2026-02-08)
    5f20962   # Fix blank rows scrolling small DataFrames  (2026-02-06)
    dbac567   # pandas_commands tests + suite analysis     (2026-01-30)
    fa011f8   # pandas 3.0 compat regression tests         (2026-01-26)
    25d674b   # more specific cache-dependency-glob        (2026-01-20)
    79da494   # BuckarooCompare + Pandera README links     (2026-01-17)
    2ea8866   # enable cache for pnpm                      (2026-01-14)
    14ec761   # reduced CI timeout experiment              (2026-01-13)
    af9fa79   # integrate Depot                            (2026-01-12)
    9693b9b   # Serialize summary stats as parquet         (2026-02-10)
    23e3096   # Fix lint: unused imports, ordering          (2026-02-10)
)

# ── Select commit set ──────────────────────────────────────────────────────────

if [[ ${#CUSTOM_SHAS[@]} -gt 0 ]]; then
    COMMITS=("${CUSTOM_SHAS[@]}")
else
    case "$COMMIT_SET" in
        safe)    COMMITS=("${SAFE_COMMITS[@]}") ;;
        failing) COMMITS=("${FAILING_COMMITS[@]}") ;;
        older)   COMMITS=("${OLDER_COMMITS[@]}") ;;
        all)     COMMITS=("${SAFE_COMMITS[@]}" "${FAILING_COMMITS[@]}" "${OLDER_COMMITS[@]}") ;;
        *)       echo "Unknown --set value: $COMMIT_SET (use safe|failing|older|all)"; exit 1 ;;
    esac
fi

if [[ $LIMIT -gt 0 && $LIMIT -lt ${#COMMITS[@]} ]]; then
    COMMITS=("${COMMITS[@]:0:$LIMIT}")
fi

TOTAL=${#COMMITS[@]}

# Capture the hetzner-ci repo commit so we know which CI code was under test.
HETZNER_CI_SHA=$(git -C "$(dirname "$0")/../.." rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Predictable directory name: runner + set.  Re-running the same combo overwrites.
RUNNER_TAG="${RUNNER%.sh}"                     # run-ci or run-ci-dag
LOGDIR="/opt/ci/logs/stress-${RUNNER_TAG}-${COMMIT_SET}"

echo "═══════════════════════════════════════════════════════════════"
echo "  Stress test: $TOTAL commits using /opt/ci-runner/$RUNNER"
echo "  Server: $SERVER  Container: $CONTAINER"
echo "  Hetzner-CI commit: $HETZNER_CI_SHA"
if $USE_SYNTH; then
    echo "  Synthetic merges: $SYNTH_MAP"
fi
echo "  Remote log dir: $LOGDIR"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    for i in "${!COMMITS[@]}"; do
        echo "  [$((i+1))/$TOTAL] ${COMMITS[$i]}"
    done
    echo ""
    echo "(dry run — nothing executed)"
    exit 0
fi

# Create remote log directory
ssh "$SERVER" "mkdir -p $LOGDIR"

# Results arrays
declare -a R_SHA R_STATUS R_TIME

# ── Resource monitor helpers ─────────────────────────────────────────────────

start_monitor() {
    local csv=$1
    # Sample CPU idle% and memory every 2s on the HOST (not inside container).
    # Container workload shows up in host CPU/mem since it's not a VM.
    ssh "$SERVER" "nohup bash -c '
        echo \"time,cpu_idle,mem_used_mb,mem_total_mb\" > $csv
        while true; do
            cpu_idle=\$(top -bn1 | grep \"Cpu(s)\" | awk \"{print \\\$8}\")
            mem_line=\$(free -m | grep Mem)
            mem_used=\$(echo \$mem_line | awk \"{print \\\$3}\")
            mem_total=\$(echo \$mem_line | awk \"{print \\\$2}\")
            echo \"\$(date +%H:%M:%S),\${cpu_idle},\${mem_used},\${mem_total}\" >> $csv
            sleep 2
        done
    ' > /dev/null 2>&1 & echo \$!" </dev/null
}

stop_monitor() {
    local pid=$1
    ssh "$SERVER" "kill $pid 2>/dev/null; wait $pid 2>/dev/null" </dev/null 2>/dev/null || true
}

# ── Per-job timing extractor ─────────────────────────────────────────────────

extract_job_timings() {
    local sha=$1
    local csv="$LOGDIR/jobs-${sha}.csv"
    # Parse ci.log: lines like "[HH:MM:SS] START job-name" / "[HH:MM:SS] PASS job-name"
    # Produce CSV: job,status,start_time,end_time,duration_s
    ssh "$SERVER" "python3 -c \"
import re, sys
from datetime import datetime

lines = open('/opt/ci/logs/${sha}/ci.log').readlines()
starts = {}
results = []

for line in lines:
    m = re.match(r'\[(\d{2}:\d{2}:\d{2})\] (START|PASS|FAIL)\s+(\S+)', line)
    if not m:
        continue
    ts_str, action, job = m.groups()
    ts = datetime.strptime(ts_str, '%H:%M:%S')
    if action == 'START':
        starts[job] = ts
    elif job in starts:
        dur = (ts - starts[job]).total_seconds()
        results.append((job, action, starts[job].strftime('%H:%M:%S'), ts_str, dur))
        del starts[job]

with open('$csv', 'w') as f:
    f.write('job,status,start,end,duration_s\n')
    for job, status, start, end, dur in results:
        f.write(f'{job},{status},{start},{end},{dur}\n')
\"" </dev/null 2>/dev/null || true
}

# ── Synthetic SHA lookup ─────────────────────────────────────────────────────

lookup_synth() {
    local sha=$1
    if $USE_SYNTH; then
        local synth
        synth=$(ssh "$SERVER" "grep '^${sha}' $SYNTH_MAP 2>/dev/null | awk '{print \$2}'" </dev/null)
        if [[ -n "$synth" ]]; then
            echo "$synth"
            return 0
        fi
    fi
    echo "$sha"
}

# ── Run one commit ───────────────────────────────────────────────────────────

run_commit() {
    local idx=$1 sha=$2
    local logfile="$LOGDIR/${sha}.log"
    local resfile="$LOGDIR/resources-${sha}.csv"

    # Look up synthetic SHA if --synth enabled
    local run_sha
    run_sha=$(lookup_synth "$sha")
    if [[ "$run_sha" != "$sha" ]]; then
        echo "[$((idx+1))/$TOTAL] Running $sha (synth: ${run_sha:0:10}) ..."
    else
        echo "[$((idx+1))/$TOTAL] Running $sha ..."
    fi

    # Start resource monitor
    local mon_pid
    mon_pid=$(start_monitor "$resfile")

    local start_ts end_ts elapsed status
    start_ts=$(date +%s)

    # Run CI on the server, capture exit code (use run_sha for the actual checkout)
    ssh "$SERVER" "docker exec ${DOCKER_ENV_ARGS[*]} $CONTAINER \
        bash /opt/ci-runner/$RUNNER $run_sha main \
        > $logfile 2>&1" \
        </dev/null
    local rc=$?

    end_ts=$(date +%s)
    elapsed=$((end_ts - start_ts))

    # Stop resource monitor
    stop_monitor "$mon_pid"

    # Extract per-job timings from ci.log (use run_sha since logs are stored under that)
    extract_job_timings "$run_sha"

    if [[ $rc -eq 0 ]]; then
        status="PASS"
    else
        status="FAIL"
    fi

    local mins=$((elapsed / 60))
    local secs=$((elapsed % 60))
    local time_str="${mins}m$(printf '%02d' $secs)s"

    R_SHA+=("$sha")
    R_STATUS+=("$status")
    R_TIME+=("$time_str")

    if [[ "$status" == "PASS" ]]; then
        echo "  PASS  ${time_str}  $sha"
    else
        echo "  FAIL  ${time_str}  $sha  (see $logfile)"
    fi
}

# ── Run all commits ──────────────────────────────────────────────────────────

for i in "${!COMMITS[@]}"; do
    run_commit "$i" "${COMMITS[$i]}"
done

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  RESULTS ($TOTAL commits, runner: $RUNNER)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
printf "  %-10s  %-6s  %s\n" "SHA" "STATUS" "TIME"
printf "  %-10s  %-6s  %s\n" "──────────" "──────" "──────"

pass_count=0
fail_count=0
for i in "${!R_SHA[@]}"; do
    printf "  %-10s  %-6s  %s\n" "${R_SHA[$i]}" "${R_STATUS[$i]}" "${R_TIME[$i]}"
    if [[ "${R_STATUS[$i]}" == "PASS" ]]; then
        ((pass_count++))
    else
        ((fail_count++))
    fi
done

echo ""
echo "  $pass_count passed, $fail_count failed out of $TOTAL"
echo ""
echo "  Logs on server ($SERVER):"
echo "    $LOGDIR/"
echo "    ├── summary.txt              # this table"
echo "    ├── <sha>.log                # full CI output per commit"
echo "    ├── resources-<sha>.csv      # CPU/mem samples (2s intervals)"
echo "    └── jobs-<sha>.csv           # per-job timing (parsed from ci.log)"
echo "═══════════════════════════════════════════════════════════════"

# Save summary to server
ssh "$SERVER" "cat > $LOGDIR/summary.txt" << SUMMARY
Runner: $RUNNER
Hetzner-CI: $HETZNER_CI_SHA
Set: $COMMIT_SET
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Commits: $TOTAL
Passed: $pass_count
Failed: $fail_count

$(printf "%-10s  %-6s  %s\n" "SHA" "STATUS" "TIME")
$(printf "%-10s  %-6s  %s\n" "──────────" "──────" "──────")
$(for i in "${!R_SHA[@]}"; do printf "%-10s  %-6s  %s\n" "${R_SHA[$i]}" "${R_STATUS[$i]}" "${R_TIME[$i]}"; done)
SUMMARY

# Build combined job timing CSV across all commits
ssh "$SERVER" "python3 -c \"
import csv, glob, os

outpath = '$LOGDIR/all-jobs.csv'
rows = []
for f in sorted(glob.glob('$LOGDIR/jobs-*.csv')):
    sha = os.path.basename(f).replace('jobs-','').replace('.csv','')
    with open(f) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row['sha'] = sha
            rows.append(row)

with open(outpath, 'w', newline='') as fh:
    writer = csv.DictWriter(fh, fieldnames=['sha','job','status','start','end','duration_s'])
    writer.writeheader()
    writer.writerows(rows)
\"" </dev/null 2>/dev/null || true

echo ""
echo "  Combined timing: $LOGDIR/all-jobs.csv"

[[ $fail_count -eq 0 ]]
