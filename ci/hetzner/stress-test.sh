#!/bin/bash
# Stress test: run the Hetzner CI against a list of known commits.
#
# Usage:
#   bash ci/hetzner/stress-test.sh                  # run all safe (passing) commits
#   bash ci/hetzner/stress-test.sh --dag             # use run-ci-dag.sh
#   bash ci/hetzner/stress-test.sh --stagger DELAY_PY311=15 DELAY_PY312=15
#   bash ci/hetzner/stress-test.sh --set=failing     # run known-failing commits
#   bash ci/hetzner/stress-test.sh --set=older       # run older Jan/Feb commits
#   bash ci/hetzner/stress-test.sh --set=new         # run 50 deeper commits
#   bash ci/hetzner/stress-test.sh --set=all         # run all commit sets
#   bash ci/hetzner/stress-test.sh --limit=5         # first 5 only
#   bash ci/hetzner/stress-test.sh --dry-run         # print what would run
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

SERVER=${HETZNER_SERVER:-root@137.220.56.81}
CONTAINER=${HETZNER_CONTAINER:-buckaroo-ci}
RUNNER="run-ci.sh"
LIMIT=0
DRY_RUN=false
COMMIT_SET="safe"
CUSTOM_SHAS=()
DOCKER_ENV_ARGS=()
LOCAL=false   # --local: run directly on this machine (no SSH), for server-side execution

while [[ $# -gt 0 ]]; do
    case $1 in
        --dag)       RUNNER="run-ci-dag.sh"; shift ;;
        --stagger)   RUNNER="run-ci-dag-stagger.sh"; shift ;;
        --limit=*)   LIMIT="${1#*=}"; shift ;;
        --limit)     LIMIT="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --local)     LOCAL=true; shift ;;
        --runner=*)  RUNNER="${1#*=}"; shift ;;
        --set=*)     COMMIT_SET="${1#*=}"; shift ;;
        --set)       COMMIT_SET="$2"; shift 2 ;;
        DELAY_PY*=*) DOCKER_ENV_ARGS+=("-e" "$1"); shift ;;
        *)           CUSTOM_SHAS+=("$1"); shift ;;
    esac
done

# rsh: run a command either locally or via SSH depending on --local flag
rsh() { $LOCAL && bash -c "$1" || ssh "$SERVER" "$1"; }

# ── Commit sets ────────────────────────────────────────────────────────────────
# Each SHA is a pre-baked merge: old app code + test infra from 82c148b.
# Created by ci/hetzner/create-merge-commits.sh. Comments show original SHA.

# 16 recent main commits — all passed GitHub CI (2026-02-23 → 2026-02-28).
SAFE_COMMITS=(
    d301edb   # 7b6a05c feat: content-aware column widths
    55f158a   # fcfe368 feat: compact_number displayer
    4f24190   # 5ff4d6e Add CLAUDE.md
    83b4841   # 837654e fix: defaultMinWidth on fitCellContents
    bb953b1   # f8a8b94 feat: color_static color rule
    401b997   # 314e89f feat: /load_compare endpoint
    7516544   # 8e9e1ed Fix BuckarooCompare for arbitrary join keys
    d389537   # 1fccaba fix: Playwright row count off-by-one
    bbefc32   # b7956f8 fix: harden release workflow
    e7a6e56   # 612e22f Fix left-pinned index column
    8d4de1d   # e392c78 fix: MCP + server reliability
    ba219c9   # 6b9e695 fix: handle zero PRs in release notes
    1baaf8e   # 6056636 fix: plain release notes fallback
    0d2efa1   # ec68a78 for the PR
    adf6088   # 2175249 fix: add GH_TOKEN to release notes
    973e3e0   # fdbe325 test: MCP server integration tests
)

# 10 commits that failed at least one check on GitHub Actions.
# (5 original SHAs not in local clone: cf7e02a, e0f358a, 7b3141c, 516a1fa, f01c9c6)
FAILING_COMMITS=(
    27603ae   # 703c034 Address PR review on compare module       (Python Test 3.11 fail)
    ad3fec4   # db1ca96 Fix left-pinned index column              (pw-server + pw-marimo fail)
    19686a7   # 4ddcac1 fix: release workflow review comments      (pw-server + pw-marimo fail)
    44a9a7c   # 7d8b751 Fix marimo Playwright tests               (pw-wasm-marimo fail)
    356585d   # b1eb6a5 ci: continue-on-error in build.yml        (pw-wasm-marimo fail)
    a67bc5c   # 1839f59 ci: skip unnecessary lint deps             (pw-wasm-marimo fail)
    1c1d0ae   # 88a8743 ci: Python 3.14 in build.yml              (pw-wasm-marimo fail)
    371d59e   # 2bec338 ci: optimize job structure + cache PW      (pw-wasm-marimo fail)
    5362efa   # c8e98d3 ci: 4min timeout to marimo tests          (pw-wasm-marimo fail)
    ada8bb1   # 7b9c341 Remove accidental -l and wc files          (Python Test 3.11 fail)
)

# 50 deeper commits (after fdbe325) — merge SHAs from create-merge-commits.sh --set=new.
NEW_COMMITS=(
    d7108fe0  # 5170fa2 Add DFViewerInfinite unit tests
    f49f7275  # aab8b96 feat: automated release workflow
    67382568  # c307fb3 fix: pandas 3.0+ compatibility
    ebfbf28d  # 66b7b4c fix: --index-strategy unsafe-best-match
    f2c71c73  # f2ad09d ci: add non-blocking Windows Python test
    f3d4e867  # 366389b ci: add smoke tests for extras
    bc22f4b8  # a918c09 Bump astral-sh/setup-uv from 6 to 7
    1780ae73  # 094a90a Bump actions/setup-node from 4 to 6
    415d4b8f  # b8f0900 Bump actions/github-script from 7 to 8
    a6f0b019  # bb38628 Bump actions/checkout from 4 to 6
    43444951  # 6ff2b56 Bump actions/cache from 4 to 5
    77d7ebf2  # 1b0a782 feat: per-request no_browser in /load
    1ed3d310  # 7b43be4 ci: add Dependabot
    9d7407a2  # 5ac690b fix: summary stats inherit alignment
    a5b88109  # 36dabd5 ci: make marimo PW tests required
    f007011b  # cb77802 ci: publish dev wheel to TestPyPI
    ac0d9782  # 8897a64 ci: consolidate ci.yml + build.yml
    39d72c80  # 7545a24 ci: move JupyterLab PW to dedicated job
    f0f755e8  # eb08afb fix: Pyodide-bundled fastparquet for WASM
    15501c71  # 25492e7 ci: fix dead if-conditions in build.yml
    858b9f98  # 8dcdb33 Fix marimo PW tests — display widgets as output
    1595156a  # 7c3e07d ci: skip unnecessary dep install for lint
    c708a603  # aacc4d3 CI: optimize jobs, add timeouts, Python 3.14
    d836bc8f  # fc56645 CI: add Python 3.14 to test matrices
    db0d3f0b  # 74d55a4 ci: optimize job structure + cache PW
    ac0badd3  # 27eb8f5 CI v3: artifact upload/download
    fb416eaf  # 1dcb47f feat/paf-v2-polars-v2 merge
    6ad47b71  # c0635af Wire up polars widgets to DfStatsV2
    98763844  # 3f56728 Split default_summary_stats
    e21ff3f9  # f2f06a2 feat/light-adaptable-v2 merge
    f3e904b5  # b4d32c0 feat/pluggable-analysis-v2 merge
    0174137e  # f1e45dd Adapt histogram colors to light/dark
    3971c41f  # f4ac6a6 Remove double borders on search input
    3ad08336  # d0a4277 Fix theme-hanger background
    e7d6c604  # 135754a Fix light mode styling
    b1dc3eb5  # af585ec Add automatic light/dark theme support
    aca2cb3b  # c7ba883 Add notebook context to screenshots
    5aea6ec6  # 7e6392e Wire up pandas widgets to DfStatsV2
    39e7af5f  # 3190319 Rewrite v1 ColAnalysis as v2 @stat functions
    6a953f00  # 14b00ed Fix ruff lint in test file
    ee8d1102  # a27a2b7 Fix ruff lint: remove unused imports
    11a457aa  # 87c2957 Add runtime type enforcement at stat boundaries
    650404b7  # 6bfdb18 Add Pluggable Analysis Framework v2
    ce9a7cd9  # bc9a06c Add buckaroo/static/ to .gitignore
    1870489a  # 14f5ad7 feat/fix-marimo-wasm merge
    ae6fc1ce  # e5d78bd Remove accidental -l and wc files
    a11541a8  # f38e56e Lower fastparquet version for Pyodide
    fe7ecdcd  # af17de6 Trim WASM tests to single smoke test
    9c17495b  # 0f31209 Optimize WASM tests: single page load
    fdde46d4  # 7806961 Switch WASM test server to npx serve
)

# 16 older commits from Jan–mid Feb 2026 (pre-CI or early CI era).
OLDER_COMMITS=(
    1c8abfd   # f10ee77 Auto-kill old server on upgrade            (2026-02-17)
    30fb572   # 3bb6d71 Fix search not updating table in MCP app   (2026-02-16)
    f2e759a   # 8623244 Fix summary stats view in MCP app          (2026-02-16)
    6597cdb   # 5c3f861 MCP install tweaks 2                       (2026-02-14)
    68dccf8   # e2f610f Summary stats parquet b64                  (2026-02-12)
    b8fe50c   # ae9006d MCP UI tool                                (2026-02-08)
    35a9048   # 5f20962 Fix blank rows scrolling small DataFrames  (2026-02-06)
    1aed18f   # dbac567 pandas_commands tests + suite analysis     (2026-01-30)
    064c892   # fa011f8 pandas 3.0 compat regression tests         (2026-01-26)
    ece6615   # 25d674b more specific cache-dependency-glob        (2026-01-20)
    e0e0589   # 79da494 BuckarooCompare + Pandera README links     (2026-01-17)
    127125f   # 2ea8866 enable cache for pnpm                      (2026-01-14)
    b3c57bf   # 14ec761 reduced CI timeout experiment              (2026-01-13)
    c219eb7   # af9fa79 integrate Depot                            (2026-01-12)
    bc442c7   # 9693b9b Serialize summary stats as parquet         (2026-02-10)
    94a25bb   # 23e3096 Fix lint: unused imports, ordering          (2026-02-10)
)

# ── Select commit set ──────────────────────────────────────────────────────────

if [[ ${#CUSTOM_SHAS[@]} -gt 0 ]]; then
    COMMITS=("${CUSTOM_SHAS[@]}")
else
    case "$COMMIT_SET" in
        safe)    COMMITS=("${SAFE_COMMITS[@]}") ;;
        failing) COMMITS=("${FAILING_COMMITS[@]}") ;;
        older)   COMMITS=("${OLDER_COMMITS[@]}") ;;
        new)     COMMITS=("${NEW_COMMITS[@]}") ;;
        all)     COMMITS=("${SAFE_COMMITS[@]}" "${FAILING_COMMITS[@]}" "${OLDER_COMMITS[@]}" "${NEW_COMMITS[@]}") ;;
        *)       echo "Unknown --set value: $COMMIT_SET (use safe|failing|older|new|all)"; exit 1 ;;
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
rsh "mkdir -p $LOGDIR"

# Results arrays
declare -a R_SHA R_STATUS R_TIME

# ── Resource monitor helpers ─────────────────────────────────────────────────

start_monitor() {
    local csv=$1
    # Sample CPU idle% and memory every 2s on the HOST (not inside container).
    # Container workload shows up in host CPU/mem since it's not a VM.
    rsh "nohup bash -c '
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
    rsh "kill $pid 2>/dev/null; wait $pid 2>/dev/null" </dev/null 2>/dev/null || true
}

# ── Per-job timing extractor ─────────────────────────────────────────────────

extract_job_timings() {
    local sha=$1
    local csv="$LOGDIR/jobs-${sha}.csv"
    # Parse ci.log: lines like "[HH:MM:SS] START job-name" / "[HH:MM:SS] PASS job-name"
    # Produce CSV: job,status,start_time,end_time,duration_s
    rsh "python3 -c \"
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

# ── Run one commit ───────────────────────────────────────────────────────────

run_commit() {
    local idx=$1 sha=$2
    local logfile="$LOGDIR/${sha}.log"
    local resfile="$LOGDIR/resources-${sha}.csv"

    echo "[$((idx+1))/$TOTAL] Running $sha ..."

    # Start resource monitor
    local mon_pid
    mon_pid=$(start_monitor "$resfile")

    local start_ts end_ts elapsed status
    start_ts=$(date +%s)

    # Run CI on the server
    rsh "docker exec ${DOCKER_ENV_ARGS[*]} $CONTAINER \
        bash /opt/ci-runner/$RUNNER $sha main \
        > $logfile 2>&1" \
        </dev/null
    local rc=$?

    end_ts=$(date +%s)
    elapsed=$((end_ts - start_ts))

    # Stop resource monitor
    stop_monitor "$mon_pid"

    # Extract per-job timings from ci.log
    extract_job_timings "$sha"

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
rsh "cat > $LOGDIR/summary.txt" << SUMMARY
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
rsh "python3 -c \"
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
