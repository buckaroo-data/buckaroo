#!/usr/bin/env bash
set -euo pipefail

# Test whether --link-mode hardlink avoids syspolicyd rescans on reinstall.
#
# Hypothesis: uv defaults to clone (APFS reflink) which creates new inodes.
# syspolicyd caches scan results per-inode, so cloned .so files get rescanned
# every time. Hardlinks share the cache's inode, so syspolicyd sees them as
# already scanned.
#
# Runs:
#   A: clone install, first execution          (expect slow, ~3k syspolicyd lines)
#   B: clone reinstall, first execution         (expect slow again — new inodes)
#   C: hardlink install, first execution        (expect slow — first time for these inodes)
#   D: hardlink reinstall, first execution      (expect FAST — same inodes as C)

cd "$(dirname "$0")/.."
VENV_DIR="./.venv-linkmode-test"
RESULTS_DIR="./linkmode-test-results"
rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

IMPORT_SCRIPT=$(mktemp /tmp/linkmode_test_XXXXX.py)
cat > "$IMPORT_SCRIPT" << 'PYEOF'
import jupyterlab
import buckaroo
import polars
PYEOF

cleanup() {
    rm -f "$IMPORT_SCRIPT"
    [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null || true
}
trap cleanup EXIT

delete_venv() {
    echo "--- Removing $VENV_DIR ---"
    rm -rf "$VENV_DIR"
}

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

# Count .so files and sample an inode for later comparison
snapshot_inodes() {
    local label="$1"
    local so_count inode
    so_count=$(find "$VENV_DIR" -name '*.so' | wc -l | tr -d ' ')
    # Pick a representative .so to track
    inode=$(find "$VENV_DIR" -name '*.so' -print -quit | xargs stat -f '%i')
    echo "$so_count" > "$RESULTS_DIR/so_count_${label}.txt"
    echo "$inode" > "$RESULTS_DIR/sample_inode_${label}.txt"
    echo "  .so files: $so_count, sample inode: $inode"
}

echo "=== Hardlink vs Clone: syspolicyd Rescan Test ==="
echo "Results saved to $RESULTS_DIR/"
echo ""

# ============================================================
# Run A: clone (default) — first install
# ============================================================
echo "--- Creating fresh venv (clone mode, default) ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars
snapshot_inodes "run_a"

echo ""
echo "--- Run A: clone install, first execution ---"
start_syslog "run_a"
timed "Run A" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_a"

# ============================================================
# Run B: clone — delete venv and reinstall (new inodes expected)
# ============================================================
echo ""
echo "--- Reinstalling (clone mode) ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars
snapshot_inodes "run_b"

echo ""
echo "--- Run B: clone reinstall, first execution ---"
start_syslog "run_b"
timed "Run B" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_b"

# ============================================================
# Run C: hardlink — first install (new cache archive, new inodes)
# ============================================================
echo ""
echo "--- Creating fresh venv (hardlink mode) ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install --link-mode hardlink buckaroo jupyterlab polars
snapshot_inodes "run_c"

echo ""
echo "--- Run C: hardlink install, first execution ---"
start_syslog "run_c"
timed "Run C" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_c"

# ============================================================
# Run D: hardlink — delete venv and reinstall (same inodes expected)
# ============================================================
echo ""
echo "--- Reinstalling (hardlink mode) ---"
delete_venv
uv venv --python 3.13 "$VENV_DIR"
VIRTUAL_ENV="$VENV_DIR" uv pip install --link-mode hardlink buckaroo jupyterlab polars
snapshot_inodes "run_d"

echo ""
echo "--- Run D: hardlink reinstall, first execution ---"
start_syslog "run_d"
timed "Run D" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
stop_syslog "run_d"

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
printf "%-55s %8s  %8s  %s\n" "Run" "Time" ".so cnt" "Sample inode"
printf "%-55s %8s  %8s  %s\n" "---" "----" "-------" "------------"
for run in "Run A" "Run B" "Run C" "Run D"; do
    label="$(echo "$run" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')"
    printf "%-55s %8ss  %8s  %s\n" \
        "$run" \
        "$(get_time "$run")" \
        "$(cat "$RESULTS_DIR/so_count_${label}.txt")" \
        "$(cat "$RESULTS_DIR/sample_inode_${label}.txt")"
done

echo ""
echo "=== syspolicyd log lines ==="
echo ""
for f in "$RESULTS_DIR"/syslog_*.txt; do
    label=$(basename "$f" .txt | sed 's/syslog_//')
    lines=$(wc -l < "$f" | tr -d ' ')
    printf "%-20s %s lines\n" "$label:" "$lines"
done

echo ""
echo "=== Inode comparison ==="
echo ""
INODE_A=$(cat "$RESULTS_DIR/sample_inode_run_a.txt")
INODE_B=$(cat "$RESULTS_DIR/sample_inode_run_b.txt")
INODE_C=$(cat "$RESULTS_DIR/sample_inode_run_c.txt")
INODE_D=$(cat "$RESULTS_DIR/sample_inode_run_d.txt")
echo "Clone:    Run A=$INODE_A  Run B=$INODE_B  same? $([ "$INODE_A" = "$INODE_B" ] && echo YES || echo NO)"
echo "Hardlink: Run C=$INODE_C  Run D=$INODE_D  same? $([ "$INODE_C" = "$INODE_D" ] && echo YES || echo NO)"

echo ""
echo "=== Expected results ==="
echo ""
echo "If the hypothesis is correct:"
echo "  - Run A (clone, first):       SLOW  — syspolicyd scans all .so files"
echo "  - Run B (clone, reinstall):   SLOW  — new inodes, syspolicyd rescans"
echo "  - Run C (hardlink, first):    SLOW  — new inodes from new cache entry"
echo "  - Run D (hardlink, reinstall): FAST — same inodes as Run C, already scanned"
echo ""
echo "Full logs saved in $RESULTS_DIR/syslog_*.txt"

# Cleanup
delete_venv
