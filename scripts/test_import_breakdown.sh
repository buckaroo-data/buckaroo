#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
VENV_DIR="./.venv-import-test"
RESULTS_DIR="./import-test-results"
rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

PACKAGES="polars pyarrow pandas numpy jupyterlab buckaroo"

cleanup() {
    [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null || true
}
trap cleanup EXIT

delete_venv() {
    echo "--- Removing $VENV_DIR ---"
    rm -rf "$VENV_DIR"
}

create_venv() {
    delete_venv
    uv venv --python 3.13 "$VENV_DIR" 2>&1 | tail -1
    VIRTUAL_ENV="$VENV_DIR" uv pip install $PACKAGES 2>&1 | tail -1
}

# Time a python import and echo the elapsed seconds
time_import() {
    local pkg="$1"
    local start end elapsed
    start=$(python3 -c 'import time; print(time.time())')
    "$VENV_DIR/bin/python" -c "import $pkg" 2>/dev/null
    end=$(python3 -c 'import time; print(time.time())')
    elapsed=$(printf '%.2f' "$(echo "$end - $start" | bc)")
    echo "$elapsed"
}

# Count .so/.dylib files and total size for a package
so_stats() {
    local pkg="$1"
    local site="$VENV_DIR/lib/python3.13/site-packages"
    local dirs

    # Some packages have top-level .so files (e.g. _polars_runtime_32)
    case "$pkg" in
        polars)     dirs="$site/polars $site/_polars_runtime_32*" ;;
        pyarrow)    dirs="$site/pyarrow" ;;
        pandas)     dirs="$site/pandas" ;;
        numpy)      dirs="$site/numpy" ;;
        buckaroo)   dirs="$site/buckaroo" ;;
        jupyterlab) dirs="$site/jupyterlab" ;;
        *)          dirs="$site/$pkg" ;;
    esac

    local files=0
    local size_bytes=0
    for d in $dirs; do
        if [ -e "$d" ]; then
            local f s
            f=$(find "$d" -type f \( -name '*.so' -o -name '*.dylib' \) 2>/dev/null | wc -l | tr -d ' ')
            s=$(find "$d" -type f \( -name '*.so' -o -name '*.dylib' \) -exec stat -f%z {} + 2>/dev/null | awk '{sum+=$1} END {print sum+0}')
            files=$((files + f))
            size_bytes=$((size_bytes + s))
        fi
    done

    echo "$files $size_bytes"
}

human_size() {
    local bytes=$1
    if [ "$bytes" -ge 1073741824 ]; then
        printf '%.1fG' "$(echo "$bytes / 1073741824" | bc -l)"
    elif [ "$bytes" -ge 1048576 ]; then
        printf '%.1fM' "$(echo "$bytes / 1048576" | bc -l)"
    elif [ "$bytes" -ge 1024 ]; then
        printf '%.1fK' "$(echo "$bytes / 1024" | bc -l)"
    else
        printf '%dB' "$bytes"
    fi
}

echo "=== Per-Package Import Timing ==="
echo ""
echo "Each package is tested in a fresh venv (cold syspolicyd),"
echo "then immediately re-tested (warm syspolicyd)."
echo ""

for pkg in $PACKAGES; do
    echo "--- Testing: $pkg ---"
    create_venv

    cold=$(time_import "$pkg")
    warm=$(time_import "$pkg")
    delta=$(printf '%.2f' "$(echo "$cold - $warm" | bc)")

    stats=$(so_stats "$pkg")
    so_count=$(echo "$stats" | cut -d' ' -f1)
    so_bytes=$(echo "$stats" | cut -d' ' -f2)

    echo "$cold" > "$RESULTS_DIR/cold_${pkg}.txt"
    echo "$warm" > "$RESULTS_DIR/warm_${pkg}.txt"
    echo "$delta" > "$RESULTS_DIR/delta_${pkg}.txt"
    echo "$so_count" > "$RESULTS_DIR/so_count_${pkg}.txt"
    echo "$so_bytes" > "$RESULTS_DIR/so_bytes_${pkg}.txt"

    echo "  cold: ${cold}s  warm: ${warm}s  delta: ${delta}s  .so files: $so_count  .so size: $(human_size "$so_bytes")"
done

# Also test all packages together
echo ""
echo "--- Testing: all packages together ---"
create_venv

IMPORT_ALL=$(printf '%s\n' $PACKAGES | paste -sd',' -)
all_cold=$(time_import "$IMPORT_ALL")
all_warm=$(time_import "$IMPORT_ALL")
all_delta=$(printf '%.2f' "$(echo "$all_cold - $all_warm" | bc)")

echo "  cold: ${all_cold}s  warm: ${all_warm}s  delta: ${all_delta}s"

# ============================================================
# Summary
# ============================================================
echo ""
echo "========================================"
echo "=== Results ==="
echo "========================================"
echo ""
printf "%-15s %8s %8s %8s %8s %10s\n" "Package" "Cold" "Warm" "Delta" ".so#" ".so Size"
printf "%-15s %8s %8s %8s %8s %10s\n" "-------" "----" "----" "-----" "----" "--------"

for pkg in $PACKAGES; do
    cold=$(cat "$RESULTS_DIR/cold_${pkg}.txt")
    warm=$(cat "$RESULTS_DIR/warm_${pkg}.txt")
    delta=$(cat "$RESULTS_DIR/delta_${pkg}.txt")
    so_count=$(cat "$RESULTS_DIR/so_count_${pkg}.txt")
    so_bytes=$(cat "$RESULTS_DIR/so_bytes_${pkg}.txt")
    printf "%-15s %7ss %7ss %7ss %8s %10s\n" "$pkg" "$cold" "$warm" "$delta" "$so_count" "$(human_size "$so_bytes")"
done

printf "%-15s %7ss %7ss %7ss\n" "ALL TOGETHER" "$all_cold" "$all_warm" "$all_delta"

echo ""
echo "Delta = cold - warm = time attributable to syspolicyd scanning"
echo "Note: individual deltas won't sum to ALL TOGETHER (shared deps)"

# Cleanup
delete_venv
