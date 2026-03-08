#!/bin/bash
# Usage: test_python.sh <version>
# Runs pytest for a given Python version with timing_dependent + regular split.
set -uo pipefail

v=${1:?usage: test_python.sh VERSION}
cd /repo

# Quick sync installs buckaroo in editable mode (deps already in venv).
UV_PROJECT_ENVIRONMENT=/opt/venvs/$v \
    uv sync --locked --dev --all-extras

# pytest-xdist may not be in older commits' lockfiles — force-install it
# so -n 4 --dist load always works.
uv pip install --python "/opt/venvs/$v/bin/python" pytest-xdist -q 2>/dev/null || true

# 3.14 is still alpha — segfaults on pytest startup; skip for now.
if [[ "$v" == "3.14" ]]; then
    echo "[skip] Python 3.14 alpha known to segfault — skipping pytest"
    exit 0
fi

# Ignored in Docker — require forkserver/spawn multiprocessing which behaves
# differently inside container PID namespaces and takes >1s to spawn.
common_ignores=(
    --ignore=tests/unit/file_cache/mp_timeout_decorator_test.py
    --ignore=tests/unit/file_cache/multiprocessing_executor_test.py
    --ignore=tests/unit/server/test_mcp_server_integration.py
    --deselect "tests/unit/server/test_mcp_tool_cleanup.py::TestServerMonitor::test_server_killed_on_parent_death"
)

# Testcase filter from pipeline
k_expr=""
if [[ -n "${PYTEST_K_FILTER:-}" ]]; then
    k_expr="$PYTEST_K_FILTER"
fi

# ── timing_dependent: high priority, single worker
timing_args=(
    tests/unit -m "timing_dependent" --color=yes
    --dist no
    "${common_ignores[@]}"
)
[[ -n "$k_expr" ]] && timing_args+=(-k "$k_expr")

# ── regular: low priority, parallel workers
regular_args=(
    tests/unit -m "not slow and not timing_dependent" --color=yes
    -n "${PYTEST_WORKERS:-4}" --dist load
    "${common_ignores[@]}"
)
[[ -n "$k_expr" ]] && regular_args+=(-k "$k_expr")

# Run both in parallel; timing tests get high CPU priority
nice -n -15 /opt/venvs/$v/bin/python -m pytest "${timing_args[@]}" &
pid_timing=$!
nice -n 19  /opt/venvs/$v/bin/python -m pytest "${regular_args[@]}" &
pid_regular=$!

wait "$pid_timing";  rc_timing=$?
wait "$pid_regular"; rc_regular=$?

# pytest exit code 5 = no tests collected — treat as pass
[[ $rc_timing  -eq 5 ]] && rc_timing=0
[[ $rc_regular -eq 5 ]] && rc_regular=0

exit $(( rc_timing != 0 || rc_regular != 0 ))
