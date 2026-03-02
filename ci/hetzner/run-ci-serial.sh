#!/bin/bash
# Serial CI runner — runs every job alone (no parallelism) to measure
# uncontended timing.  Used to find the critical path and estimate the
# fastest possible CI time on a machine with more cores.
#
# Output:
#   /opt/ci/logs/$SHA/serial-timings.csv   — job,status,duration_s
#   /opt/ci/logs/$SHA/serial.log           — timestamped run log
#
# At the end, prints a timing table and the critical-path time (= lower
# bound for any parallel runner regardless of core count).
#
# Usage:
#   docker exec buckaroo-ci bash /opt/ci-runner/run-ci-serial.sh <sha> <branch>

set -uo pipefail

SHA=${1:?usage: run-ci-serial.sh SHA BRANCH}
BRANCH=${2:?usage: run-ci-serial.sh SHA BRANCH}

REPO_DIR=/repo
RESULTS_DIR=/opt/ci/logs/$SHA
OVERALL=0

mkdir -p "$RESULTS_DIR"

CI_RUNNER_DIR=${CI_RUNNER_DIR:-/opt/ci-runner}
source "$CI_RUNNER_DIR/status.sh"
source "$CI_RUNNER_DIR/lockcheck.sh"

log() { echo "[$(date +'%H:%M:%S')] $*" | tee -a "$RESULTS_DIR/serial.log"; }

# ── Setup (identical to run-ci.sh) ───────────────────────────────────────────

RUNNER_VERSION=$(cat "$CI_RUNNER_DIR/VERSION" 2>/dev/null || echo "unknown")
log "CI runner: $RUNNER_VERSION (serial mode)"
log "Checkout $SHA (branch: $BRANCH)"
cd "$REPO_DIR"
git fetch origin
git checkout -f "$SHA"
git clean -fdx \
    --exclude='packages/buckaroo-js-core/node_modules' \
    --exclude='packages/js/node_modules' \
    --exclude='packages/node_modules'

if lockcheck_valid; then
    log "Lockfiles unchanged — using warm caches"
else
    log "Lockfiles changed — rebuilding deps"
    rebuild_deps
    lockcheck_update
fi

mkdir -p buckaroo/static
touch buckaroo/static/compiled.css buckaroo/static/widget.js buckaroo/static/widget.css

# ── Job definitions (kept in sync with run-ci.sh) ────────────────────────────

job_lint_python() {
    cd /repo
    /opt/venvs/3.13/bin/ruff check
}

job_test_js() {
    cd /repo/packages
    pnpm install --frozen-lockfile --store-dir /opt/pnpm-store
    cd buckaroo-js-core
    pnpm run build
    pnpm run test
}

job_test_python() {
    local v=$1
    cd /repo
    UV_PROJECT_ENVIRONMENT=/opt/venvs/$v \
        uv sync --locked --dev --all-extras

    if [[ "$v" == "3.14" ]]; then
        echo "[skip] Python 3.14 alpha known to segfault — skipping pytest"
        return 0
    fi

    /opt/venvs/$v/bin/python -m pytest tests/unit -m "not slow" --color=yes \
        --ignore=tests/unit/file_cache/mp_timeout_decorator_test.py \
        --deselect tests/unit/file_cache/multiprocessing_executor_test.py::test_multiprocessing_executor_success \
        --deselect "tests/unit/server/test_mcp_tool_cleanup.py::TestServerMonitor::test_server_killed_on_parent_death"
}

job_build_wheel() {
    cd /repo
    PNPM_STORE_DIR=/opt/pnpm-store bash scripts/full_build.sh
}

job_test_mcp_wheel() {
    cd /repo
    local venv=/tmp/ci-mcp-$$
    rm -rf "$venv"
    uv venv "$venv" -q
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "${wheel}[mcp]" pytest -q
    local rc=0
    BUCKAROO_MCP_CMD="$venv/bin/buckaroo-table" \
        "$venv/bin/pytest" \
            tests/unit/server/test_mcp_uvx_install.py \
            tests/unit/server/test_mcp_server_integration.py \
            -v --color=yes -m slow || rc=$?
    "$venv/bin/pytest" \
        tests/unit/server/test_mcp_uvx_install.py::TestUvxFailureModes \
        -v --color=yes -m slow || rc=$?
    rm -rf "$venv"
    return $rc
}

job_smoke_test_extras() {
    cd /repo
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    for extra in base polars mcp marimo jupyterlab notebook; do
        local venv=/tmp/ci-smoke-${extra}-$$
        rm -rf "$venv"
        uv venv "$venv" -q
        if [[ "$extra" == "base" ]]; then
            uv pip install --python "$venv/bin/python" "$wheel" -q
        else
            uv pip install --python "$venv/bin/python" "${wheel}[${extra}]" -q
        fi
        "$venv/bin/python" scripts/smoke_test.py "$extra"
        rm -rf "$venv"
    done
}

job_playwright_storybook() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-storybook-$$ \
        bash scripts/test_playwright_storybook.sh
}

job_playwright_server() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-server-$$ \
        bash scripts/test_playwright_server.sh
}

job_playwright_marimo() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
        bash scripts/test_playwright_marimo.sh
}

job_playwright_wasm_marimo() {
    cd /repo
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-wasm-marimo-$$ \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
        bash scripts/test_playwright_wasm_marimo.sh
}

job_playwright_jupyter() {
    cd /repo
    local venv=/tmp/ci-jupyter-$$
    uv venv "$venv" --python 3.13 -q
    local wheel
    wheel=$(ls dist/buckaroo-*.whl | head -1)
    uv pip install --python "$venv/bin/python" "$wheel" polars jupyterlab -q
    local rc=0
    ROOT_DIR=/repo \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
    PARALLEL=1 \
        bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" --venv-location="$venv" || rc=$?
    rm -rf "$venv"
    return $rc
}

# ── Serial execution with per-job timing ─────────────────────────────────────

CSV="$RESULTS_DIR/serial-timings.csv"
echo "job,status,duration_s" > "$CSV"

run_serial() {
    local name=$1; shift
    local logfile="$RESULTS_DIR/$name.log"
    local t0 t1 dur status
    t0=$(date +%s)
    log "START $name"
    if "$@" > "$logfile" 2>&1; then
        status=PASS
        log "PASS  $name"
    else
        status=FAIL
        OVERALL=1
        log "FAIL  $name"
    fi
    t1=$(date +%s)
    dur=$((t1 - t0))
    echo "$name,$status,$dur" >> "$CSV"
}

# Independent jobs (no deps on each other)
run_serial lint-python           job_lint_python
run_serial test-js               job_test_js
run_serial test-python-3.13      job_test_python 3.13
run_serial test-python-3.11      job_test_python 3.11
run_serial test-python-3.12      job_test_python 3.12
run_serial test-python-3.14      job_test_python 3.14

# build-wheel: JS artifacts already present from test-js above
run_serial build-wheel           job_build_wheel

# Post-wheel jobs: all depend on build-wheel, independent of each other
run_serial test-mcp-wheel        job_test_mcp_wheel
run_serial smoke-test-extras     job_smoke_test_extras
run_serial playwright-storybook  job_playwright_storybook
run_serial playwright-server     job_playwright_server
run_serial playwright-marimo     job_playwright_marimo
run_serial playwright-wasm-marimo job_playwright_wasm_marimo
run_serial playwright-jupyter    job_playwright_jupyter

# ── Summary ──────────────────────────────────────────────────────────────────

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 - "$CSV" <<'PYEOF'
import csv, sys

rows = list(csv.DictReader(open(sys.argv[1])))

print(f"\n  {'Job':<26}  {'Status':<6}  {'Time':>6}")
print(f"  {'─'*26}  {'─'*6}  {'─'*6}")
for r in rows:
    m, s = divmod(int(r['duration_s']), 60)
    print(f"  {r['job']:<26}  {r['status']:<6}  {m}m{s:02d}s")

# Dependency graph (mirrors the phase structure in run-ci.sh)
deps = {
    'lint-python':             [],
    'test-js':                 [],
    'test-python-3.13':        [],
    'test-python-3.11':        [],
    'test-python-3.12':        [],
    'test-python-3.14':        [],
    'build-wheel':             ['test-js'],
    'test-mcp-wheel':          ['build-wheel'],
    'smoke-test-extras':       ['build-wheel'],
    'playwright-storybook':    ['build-wheel'],
    'playwright-server':       ['build-wheel'],
    'playwright-marimo':       ['build-wheel'],
    'playwright-wasm-marimo':  ['build-wheel'],
    'playwright-jupyter':      ['build-wheel'],
}

times = {r['job']: int(r['duration_s']) for r in rows}

memo = {}
def finish(job):
    if job not in memo:
        memo[job] = times.get(job, 0) + max(
            (finish(d) for d in deps.get(job, [])), default=0
        )
    return memo[job]

for j in deps:
    finish(j)

critical = max(memo.values())
bottleneck = max(memo, key=memo.get)

# Trace the critical path back from the bottleneck
def trace(job):
    predecessors = deps.get(job, [])
    if not predecessors:
        return [job]
    return trace(max(predecessors, key=finish)) + [job]

path = trace(bottleneck)
m, s = divmod(critical, 60)
print(f"\n  Critical path (∞ cores): {m}m{s:02d}s")
print(f"  Path: {' → '.join(path)}")

# Also show total sequential time for context
total = sum(int(r['duration_s']) for r in rows)
mt, st = divmod(total, 60)
print(f"  Total sequential time:   {mt}m{st:02d}s")
PYEOF
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $OVERALL
