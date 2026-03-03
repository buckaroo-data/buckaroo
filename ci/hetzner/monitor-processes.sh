#!/usr/bin/env bash
# Per-process CPU/memory monitor for pw-jupyter experiments.
# Usage: bash monitor-processes.sh <LOGDIR>
# Runs until killed (background it, kill when experiment ends).
set -euo pipefail

LOGDIR="${1:?Usage: monitor-processes.sh <LOGDIR>}"
LOGFILE="$LOGDIR/per-process.log"
mkdir -p "$LOGDIR"

INTERVAL="${MONITOR_INTERVAL:-2}"

echo "=== Monitor started at $(date +%H:%M:%S) — interval=${INTERVAL}s ===" > "$LOGFILE"

while true; do
  {
    echo "=== $(date +%H:%M:%S.%N) ==="

    echo "--- jupyter-lab ---"
    ps aux | grep '[j]upyter-lab' | awk '{printf "PID=%s CPU=%s%% MEM=%s%% RSS=%sMB CMD=%s\n", $2, $3, $4, $6/1024, $11}' 2>/dev/null || true

    echo "--- python kernels ---"
    ps aux | grep -E '[i]pykernel|[k]ernel.*python|python.*[k]ernel' | awk '{printf "PID=%s CPU=%s%% MEM=%s%% RSS=%sMB CMD=%s %s %s\n", $2, $3, $4, $6/1024, $11, $12, $13}' 2>/dev/null || true

    echo "--- chromium (top 5 by CPU) ---"
    ps aux | grep '[c]hromium' | sort -k3 -rn | head -5 | awk '{printf "PID=%s CPU=%s%% MEM=%s%% RSS=%sMB\n", $2, $3, $4, $6/1024}' 2>/dev/null || true

    echo "--- node/playwright ---"
    ps aux | grep '[n]ode.*playwright' | awk '{printf "PID=%s CPU=%s%% MEM=%s%%\n", $2, $3, $4}' 2>/dev/null || true

    echo "--- memory ---"
    free -m | grep -E 'Mem|Swap'

    echo "--- ports ---"
    for p in 8889 8890 8891 8892 8893 8894; do
      count=$(ss -tnp 2>/dev/null | grep -c ":$p " || true)
      [ "$count" -gt 0 ] && echo "port $p: $count connections"
    done

    echo "--- load ---"
    cat /proc/loadavg 2>/dev/null || true

    echo ""
  } >> "$LOGFILE" 2>&1
  sleep "$INTERVAL"
done
