#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
VENV_DIR="./.venv-syspolicyd-test"
RESULTS_DIR="./syspolicyd-test-results"
rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

# Simple import script
IMPORT_SCRIPT=$(mktemp /tmp/syspolicyd_test_XXXXX.py)
cat > "$IMPORT_SCRIPT" << 'PYEOF'
import jupyterlab
import buckaroo
import polars
PYEOF

cleanup() {
    rm -f "$IMPORT_SCRIPT"
    # Stop syspolicyd log streaming if still running
    [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null || true
}
trap cleanup EXIT

delete_venv() {
    echo "--- Removing $VENV_DIR ---"
    rm -rf "$VENV_DIR"
}

# Run a command and capture wall-clock seconds to a file
timed() {
    local label="$1"
    shift
    local start end elapsed
    start=$(python3 -c 'import time; print(time.time())')
    "$@"
    end=$(python3 -c 'import time; print(time.time())')
    elapsed=$(printf '%.2f' "$(echo "$end - $start" | bc)")
    echo "$elapsed" > "$RESULTS_DIR/time_${label}.txt"
    echo "  → ${elapsed}s"
}

get_time() {
    cat "$RESULTS_DIR/time_${1}.txt"
}

# Start logging syspolicyd / XProtect activity for a run
start_syslog() {
    local label="$1"
    log stream --predicate 'process == "syspolicyd" OR process == "XProtect" OR process == "taskgated"' \
        --style compact > "$RESULTS_DIR/syslog_${label}.txt" 2>&1 &
    LOGPID=$!
    sleep 0.5  # let log stream attach
}

stop_syslog() {
    local label="$1"
    kill "$LOGPID" 2>/dev/null || true
    wait "$LOGPID" 2>/dev/null || true
    LOGPID=""
    local count
    count=$(wc -l < "$RESULTS_DIR/syslog_${label}.txt" | tr -d ' ')
    echo "  syspolicyd/XProtect log lines: $count"
}

echo "=== Cold Start Slowness Test ==="
echo "Results saved to $RESULTS_DIR/"
echo ""

# ============================================================
# Run A: Fresh install, first execution (the slow one)
# ============================================================
echo "--- Creating fresh venv and installing ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars

echo ""
echo "--- Run A: First execution after fresh install ---"
start_syslog "run_a"
timed "Run A" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_a"

# ============================================================
# Run B: Second execution (the fast one — baseline)
# ============================================================
echo ""
echo "--- Run B: Second execution (warm baseline) ---"
start_syslog "run_b"
timed "Run B" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_b"

# ============================================================
# Run C: Fresh install again, to confirm reproducibility
#        and capture syspolicyd activity on the slow path
# ============================================================
echo ""
echo "--- Creating fresh venv and installing (again) ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars

echo ""
echo "--- Run C: First execution after fresh install (confirmation) ---"
start_syslog "run_c"
timed "Run C" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_c"

# ============================================================
# Summary
# ============================================================
echo ""
echo "========================================"
echo "=== Results ==="
echo "========================================"

echo ""
echo "=== Timings ==="
echo ""
printf "%-55s %8s\n" "Run" "Time"
printf "%-55s %8s\n" "---" "----"
printf "%-55s %8ss\n" "Run A: fresh install, first execution"    "$(get_time "Run A")"
printf "%-55s %8ss\n" "Run B: second execution (warm baseline)"  "$(get_time "Run B")"
printf "%-55s %8ss\n" "Run C: fresh install again (confirmation)" "$(get_time "Run C")"

echo ""
echo "=== syspolicyd / XProtect / taskgated log lines ==="
echo ""
for f in "$RESULTS_DIR"/syslog_*.txt; do
    label=$(basename "$f" .txt | sed 's/syslog_//')
    lines=$(wc -l < "$f" | tr -d ' ')
    printf "%-20s %s lines\n" "$label:" "$lines"
done

echo ""
echo "=== syspolicyd log diff (Run B vs Run A) ==="
echo "Lines present in slow Run A but not in fast Run B:"
echo ""
diff "$RESULTS_DIR/syslog_run_b.txt" "$RESULTS_DIR/syslog_run_a.txt" | head -40 || echo "(no difference)"

echo ""
echo "Full logs saved in $RESULTS_DIR/syslog_*.txt"

# Cleanup
delete_venv
