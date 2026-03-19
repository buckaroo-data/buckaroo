#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
VENV_DIR="./.venv-pyc-test"
RESULTS_DIR="./pyc-test-results"
rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

# Simple import script
IMPORT_SCRIPT=$(mktemp /tmp/pyc_test_XXXXX.py)
cat > "$IMPORT_SCRIPT" << 'PYEOF'
import jupyterlab
import buckaroo
import polars
PYEOF

cleanup() {
    rm -f "$IMPORT_SCRIPT"
}
trap cleanup EXIT

# Helper: snapshot the venv file listing (non-pyc files only)
snapshot_files() {
    local label="$1"
    find "$VENV_DIR" -type f -not -path '*__pycache__*' -not -name '*.pyc' | sort > "$RESULTS_DIR/${label}.txt"
    du -sh "$VENV_DIR" | cut -f1 > "$RESULTS_DIR/${label}.size"
}

delete_pyc() {
    echo "--- Deleting all .pyc files and __pycache__ dirs ---"
    find "$VENV_DIR" -name '*.pyc' -delete
    find "$VENV_DIR" -type d -name '__pycache__' -delete
}

# Helper: run a command and capture wall-clock seconds
# Saves timing to a file since macOS bash 3.2 lacks associative arrays
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

echo "=== PYC Impact Test ==="
echo "Results saved to $RESULTS_DIR/"
echo ""

# 1. Blow away and recreate venv
echo "--- Removing $VENV_DIR and recreating ---"
rm -rf "$VENV_DIR"
uv venv --python 3.13 "$VENV_DIR"

# 2. Install packages
echo "--- Installing buckaroo, jupyterlab, polars ---"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars

snapshot_files "step0_after_install"

# 3. Run 1: Cold (no pyc, cold fs cache)
echo ""
echo "--- Run 1: Cold (first execution after fresh install) ---"
timed "Run 1" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step1_after_run1"

# 4. Run 2: Warm (pyc exist, warm fs cache)
echo ""
echo "--- Run 2: Warm (pyc files already exist) ---"
timed "Run 2" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step2_after_run2"

# 5. Delete pyc, run again (warm fs cache, no pyc)
echo ""
delete_pyc
snapshot_files "step3_after_pyc_delete"

echo ""
echo "--- Run 3: Warm fs cache, no pyc (pyc being recreated) ---"
timed "Run 3" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step4_after_run3"

# 6. Run 4: Warm again
echo ""
echo "--- Run 4: Warm (confirmation) ---"
timed "Run 4" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step5_after_run4"

# ============================================================
# Test 2: Same venv, delete pyc, purge fs cache, run again
# ============================================================
echo ""
echo "=========================================="
echo "=== Test 2: Purged FS Cache, No PYC ==="
echo "=========================================="

echo ""
delete_pyc
snapshot_files "step6_before_run5"

if command -v purge &>/dev/null; then
    echo "--- Purging OS filesystem cache (sudo purge) ---"
    sudo purge
else
    echo "ERROR: purge not available, this test won't be meaningful"
fi

echo ""
echo "--- Run 5: Same venv, no pyc, fs cache purged ---"
timed "Run 5" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step7_after_run5"

echo ""
echo "--- Run 6: Warm again (confirmation) ---"
timed "Run 6" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step8_after_run6"

# ============================================================
# Test 3: Completely fresh venv, cat to prime fs cache
# ============================================================
echo ""
echo "=========================================="
echo "=== Test 3: Fresh Venv, FS Cache Primed ==="
echo "=========================================="

echo ""
echo "--- Removing $VENV_DIR and recreating ---"
rm -rf "$VENV_DIR"
uv venv --python 3.13 "$VENV_DIR"

echo "--- Installing buckaroo, jupyterlab, polars ---"
VIRTUAL_ENV="$VENV_DIR" uv pip install buckaroo jupyterlab polars
snapshot_files "step9_fresh_install"

if command -v purge &>/dev/null; then
    echo "--- Purging OS filesystem cache ---"
    sudo purge
fi

echo ""
echo "--- Priming filesystem cache: cat all files in $VENV_DIR ---"
timed "cat prime" find "$VENV_DIR" -type f -exec cat {} + > /dev/null

echo ""
echo "--- Run 7: Fresh venv, fs cache primed, no pyc files ---"
timed "Run 7" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step10_after_run7"

echo ""
echo "--- Run 8: Warm (pyc files now exist) ---"
timed "Run 8" "$VENV_DIR/bin/python" "$IMPORT_SCRIPT"
snapshot_files "step11_after_run8"

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
printf "%-50s %8s\n" "Run" "Time"
printf "%-50s %8s\n" "---" "----"
printf "%-50s %8ss\n" "Run 1: cold fs + no pyc (first ever)"          "$(get_time "Run 1")"
printf "%-50s %8ss\n" "Run 2: warm fs + pyc"                          "$(get_time "Run 2")"
printf "%-50s %8ss\n" "Run 3: warm fs + no pyc (pyc deleted)"         "$(get_time "Run 3")"
printf "%-50s %8ss\n" "Run 4: warm fs + pyc (confirmation)"           "$(get_time "Run 4")"
printf "%-50s %8ss\n" "Run 5: purged fs + no pyc"                     "$(get_time "Run 5")"
printf "%-50s %8ss\n" "Run 6: warm fs + pyc (confirmation)"           "$(get_time "Run 6")"
printf "%-50s %8ss\n" "cat prime: read all files into fs cache"       "$(get_time "cat prime")"
printf "%-50s %8ss\n" "Run 7: fresh venv, cat-primed fs + no pyc"    "$(get_time "Run 7")"
printf "%-50s %8ss\n" "Run 8: warm fs + pyc (confirmation)"           "$(get_time "Run 8")"

echo ""
echo "=== Non-PYC File Counts ==="
echo ""
printf "%-30s %8s %8s\n" "Step" "Files" "Size"
printf "%-30s %8s %8s\n" "----" "-----" "----"
prev=""
for f in "$RESULTS_DIR"/step*.txt; do
    label=$(basename "$f" .txt)
    count=$(wc -l < "$f" | tr -d ' ')
    size=$(cat "${f/.txt/.size}")
    if [ -n "$prev" ]; then
        added=$(comm -13 "$prev" "$f" | wc -l | tr -d ' ')
        removed=$(comm -23 "$prev" "$f" | wc -l | tr -d ' ')
        delta=""
        [ "$added" -gt 0 ] && delta="+${added}"
        [ "$removed" -gt 0 ] && delta="${delta:+$delta }−${removed}"
        printf "%-30s %8s %8s  %s\n" "$label" "$count" "$size" "${delta:-(no change)}"
    else
        printf "%-30s %8s %8s\n" "$label" "$count" "$size"
    fi
    prev="$f"
done

# Show exactly which non-pyc files were created between install and first run
echo ""
echo "=== Non-PYC files created between install and Run 1 ==="
comm -13 "$RESULTS_DIR/step0_after_install.txt" "$RESULTS_DIR/step1_after_run1.txt" || echo "(none)"

echo ""
echo "=== Interpretation ==="
echo "Run 1  = cold fs cache + no pyc     — first ever execution after install"
echo "Run 2  = warm fs cache + pyc        — best case baseline"
echo "Run 3  = warm fs cache + no pyc     — isolates pyc creation cost"
echo "Run 4  = warm fs cache + pyc        — baseline confirmation"
echo "Run 5  = purged fs cache + no pyc   — should match Run 1 if fs cache is the cause"
echo "Run 6  = warm fs cache + pyc        — baseline confirmation"
echo "Run 7  = cat-primed fs + no pyc     — does pre-reading files eliminate cold penalty?"
echo "Run 8  = warm fs cache + pyc        — baseline confirmation"
echo ""
echo "File listings saved in $RESULTS_DIR/ — diff them to see exactly what changed."

# Cleanup
rm -rf "$VENV_DIR"
