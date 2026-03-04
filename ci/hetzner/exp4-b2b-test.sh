#!/usr/bin/env bash
# Experiment 4: Back-to-back degradation test
# Runs the pw-jupyter harness N times consecutively, capturing state between runs.
set -uo pipefail

PARALLEL=${JUPYTER_PARALLEL:-9}
RUNS=${B2B_RUNS:-3}
LOGBASE=/opt/ci/logs/exp4-b2b
WHEEL_SHA=${1:-4a7fefc}
TEST_SHA=${2:-e6ea620}

mkdir -p "$LOGBASE"

capture_state() {
  local label=$1
  local f="$LOGBASE/state-$label.log"
  echo "=== $(date +%H:%M:%S) state capture: $label ===" > "$f"
  echo "--- fd count ---" >> "$f"
  find /proc -maxdepth 2 -name fd -type d 2>/dev/null | wc -l >> "$f"
  echo "--- /tmp files ---" >> "$f"
  find /tmp -maxdepth 2 -type f 2>/dev/null | wc -l >> "$f"
  echo "--- memory ---" >> "$f"
  free -m >> "$f"
  echo "--- sockets ---" >> "$f"
  ss -s >> "$f"
  echo "--- jupyter runtime files ---" >> "$f"
  ls ~/.local/share/jupyter/runtime/ 2>/dev/null | wc -l >> "$f"
  echo "--- processes ---" >> "$f"
  ps aux | wc -l >> "$f"
  echo "--- zombie count ---" >> "$f"
  ps aux | awk '$8 ~ /Z/' | wc -l >> "$f"
  echo "--- /dev/shm ---" >> "$f"
  df -h /dev/shm >> "$f"
  echo "--- TIME_WAIT sockets ---" >> "$f"
  ss -t state time-wait | wc -l >> "$f"
  echo "--- jupyter/python/chromium processes ---" >> "$f"
  ps aux | grep -E 'jupyter|ipykernel|chromium|playwright' | grep -v grep | wc -l >> "$f"
  cat "$f"
}

capture_state before-run1

for i in $(seq 1 "$RUNS"); do
  echo ""
  echo "=========================================="
  echo "=== RUN $i of $RUNS (P=$PARALLEL) ==="
  echo "=========================================="

  JUPYTER_PARALLEL=$PARALLEL CI_TIMEOUT=180 \
    bash /repo/ci/hetzner/run-pw-jupyter.sh "$WHEEL_SHA" "$TEST_SHA" 0 2>&1 | tail -8

  # Restore branch so harness script is available for next run
  cd /repo && git checkout docs/ci-research 2>/dev/null && git reset --hard origin/docs/ci-research >/dev/null 2>&1

  capture_state "after-run$i"
done
