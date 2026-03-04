#!/bin/bash
# Local test harness for run-ci-dag.sh DAG orchestration.
# Builds a patched copy with mock job functions, validates:
#   1. All 15 jobs execute (build-js + test-js are now separate)
#   2. DAG ordering (test-js + build-wheel after build-js, wheel jobs after build-wheel)
#   3. Parallelism (independent jobs overlap, test-js || build-wheel)
#   4. Failure propagation (any job failure → OVERALL=1)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMPDIR=$(mktemp -d -t ci-dag-test)
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0
FAIL=0
assert() {
    local desc=$1; shift
    if "$@"; then
        echo "  PASS: $desc"
        ((PASS++))
    else
        echo "  FAIL: $desc"
        ((FAIL++))
    fi
}

# ── Build patched script ─────────────────────────────────────────────────────

build_patched_script() {
    local fail_job=${1:-__none__}
    local patched="$TMPDIR/patched-${fail_job}.sh"

    # Header: stubs for everything run-ci-dag.sh needs
    cat > "$patched" << 'HEADER'
#!/bin/bash
set -uo pipefail

SHA=${1:?}
BRANCH=${2:?}
RESULTS_DIR=${TEST_RESULTS_DIR}
LOG_URL="http://localhost:9000/logs/$SHA"
OVERALL=0
mkdir -p "$RESULTS_DIR"

status_pending() { :; }; status_success() { :; }; status_failure() { :; }
log() { echo "[$(date +'%H:%M:%S')] $*" | tee -a "$RESULTS_DIR/ci.log"; }

run_job() {
    local name=$1; shift
    local logfile="$RESULTS_DIR/$name.log"
    log "START $name"
    if "$@" >"$logfile" 2>&1; then
        log "PASS  $name"
        return 0
    else
        log "FAIL  $name  (see $LOG_URL/$name.log)"
        return 1
    fi
}

# Portable millisecond timestamp (macOS date lacks %N)
now_ms() { python3 -c "import time; print(int(time.time()*1000))"; }

mock_job() {
    local name=$1 dur_s=${2:-0.1} rc=${3:-0}
    echo "$name START $(now_ms)" >> "$TIMELINE"
    sleep "$dur_s"
    echo "$name END $(now_ms)" >> "$TIMELINE"
    return "$rc"
}
HEADER

    # Job functions with failure injection (unquoted heredoc so $fail_job expands)
    cat >> "$patched" << JOBS
job_lint_python()            { if [[ "$fail_job" == "lint-python" ]]; then mock_job lint-python 0.1 1; else mock_job lint-python 0.1; fi; }
job_build_js()               { if [[ "$fail_job" == "build-js" ]]; then mock_job build-js 0.3 1; else mock_job build-js 0.3; fi; }
job_test_js()                { if [[ "$fail_job" == "test-js" ]]; then mock_job test-js 0.2 1; else mock_job test-js 0.2; fi; }
job_test_python()            { local v=\$1; local n="test-python-\$v"; if [[ "$fail_job" == "\$n" ]]; then mock_job "\$n" 0.3 1; else mock_job "\$n" 0.3; fi; }
job_build_wheel()            { if [[ "$fail_job" == "build-wheel" ]]; then mock_job build-wheel 0.3 1; else mock_job build-wheel 0.3; fi; }
job_test_mcp_wheel()         { mock_job test-mcp-wheel 0.1; }
job_smoke_test_extras()      { mock_job smoke-test-extras 0.1; }
job_playwright_storybook()   { mock_job pw-storybook 0.2; }
job_playwright_server()      { mock_job pw-server 0.2; }
job_playwright_marimo()      { mock_job pw-marimo 0.2; }
job_playwright_wasm_marimo() { mock_job pw-wasm 0.2; }
job_playwright_jupyter()     { mock_job pw-jupyter 0.3; }

export -f now_ms mock_job job_lint_python job_build_js job_test_js job_test_python job_build_wheel \\
           job_test_mcp_wheel job_smoke_test_extras \\
           job_playwright_storybook job_playwright_server job_playwright_marimo \\
           job_playwright_wasm_marimo job_playwright_jupyter
JOBS

    # Append the DAG execution and final status sections from the real script
    sed -n '/^# ── DAG execution/,$ p' "$SCRIPT_DIR/run-ci-dag.sh" >> "$patched"

    chmod +x "$patched"
    echo "$patched"
}

# ── Run a test scenario ──────────────────────────────────────────────────────

run_dag() {
    local fail_job=${1:-__none__}
    local timeline="$TMPDIR/timeline-${fail_job}"
    > "$timeline"

    local run_dir="$TMPDIR/run-${fail_job}-$$"
    mkdir -p "$run_dir"

    local patched
    patched=$(build_patched_script "$fail_job")

    TEST_RESULTS_DIR="$run_dir" TIMELINE="$timeline" \
        bash "$patched" fakesha000 main 2>/dev/null
    local rc=$?

    # Store timeline path for assertions
    LAST_TIMELINE="$timeline"
    return $rc
}

get_ts() {
    local job=$1 event=$2
    grep "^$job $event " "$LAST_TIMELINE" | awk '{print $3}'
}

started_before_ended() {
    local a_start b_end
    a_start=$(get_ts "$1" START)
    b_end=$(get_ts "$2" END)
    [[ -n "$a_start" && -n "$b_end" && "$a_start" -lt "$b_end" ]]
}

# ── Test 1: All 15 jobs run ──────────────────────────────────────────────────

echo ""
echo "Test 1: All jobs execute (happy path)"
run_dag
rc=$?

assert "exit code is 0" test "$rc" -eq 0

job_count=$(grep ' START ' "$LAST_TIMELINE" | awk '{print $1}' | sort -u | wc -l | tr -d ' ')
assert "15 jobs ran (got $job_count)" test "$job_count" -eq 15

for job in lint-python build-js test-js test-python-3.11 test-python-3.12 test-python-3.13 \
           test-python-3.14 build-wheel test-mcp-wheel smoke-test-extras \
           pw-storybook pw-server pw-marimo pw-wasm pw-jupyter; do
    assert "job $job ran" grep -q "^$job START" "$LAST_TIMELINE"
done

# ── Test 2: DAG ordering ────────────────────────────────────────────────────

echo ""
echo "Test 2: DAG ordering constraints"

# build-js must complete before test-js and build-wheel start
bj_end=$(get_ts build-js END)
tj_start=$(get_ts test-js START)
bw_start=$(get_ts build-wheel START)
assert "test-js starts after build-js ends ($tj_start >= $bj_end)" test "$tj_start" -ge "$bj_end"
assert "build-wheel starts after build-js ends ($bw_start >= $bj_end)" test "$bw_start" -ge "$bj_end"

# wheel-dependent jobs must start after build-wheel ends
bw_end=$(get_ts build-wheel END)
for job in test-mcp-wheel smoke-test-extras pw-server pw-jupyter pw-marimo pw-wasm; do
    j_start=$(get_ts "$job" START)
    assert "$job starts after build-wheel ends ($j_start >= $bw_end)" test "$j_start" -ge "$bw_end"
done

# ── Test 3: Parallelism ────────────────────────────────────────────────────

echo ""
echo "Test 3: Independent jobs run in parallel"

# These should all be running while build-js is still going (0.3s)
assert "test-python-3.11 overlaps build-js" started_before_ended test-python-3.11 build-js
assert "test-python-3.13 overlaps build-js" started_before_ended test-python-3.13 build-js
assert "lint-python overlaps build-js" started_before_ended lint-python build-js
assert "pw-storybook overlaps build-js" started_before_ended pw-storybook build-js

# test-js and build-wheel should run in parallel after build-js
assert "test-js overlaps build-wheel" started_before_ended test-js build-wheel

# Wheel-dependent jobs should run in parallel with each other
assert "pw-jupyter overlaps pw-server" started_before_ended pw-jupyter pw-server
assert "pw-marimo overlaps pw-server" started_before_ended pw-marimo pw-server
assert "pw-wasm overlaps pw-server" started_before_ended pw-wasm pw-server

# ── Test 4: Failure propagation ─────────────────────────────────────────────

echo ""
echo "Test 4: Failure propagation"

run_dag "test-python-3.12"
rc=$?
assert "test-python-3.12 failure → exit 1" test "$rc" -eq 1
assert "build-wheel still ran despite py3.12 failure" grep -q "^build-wheel START" "$LAST_TIMELINE"
assert "pw-jupyter still ran despite py3.12 failure" grep -q "^pw-jupyter START" "$LAST_TIMELINE"

run_dag "build-js"
rc=$?
assert "build-js failure → exit 1" test "$rc" -eq 1
# build-wheel should still attempt (we don't short-circuit)
assert "build-wheel still ran despite build-js failure" grep -q "^build-wheel START" "$LAST_TIMELINE"

run_dag "lint-python"
rc=$?
assert "lint-python failure → exit 1" test "$rc" -eq 1

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════"
echo "  $PASS passed, $FAIL failed"
echo "═══════════════════════════════════"

[[ $FAIL -eq 0 ]]
