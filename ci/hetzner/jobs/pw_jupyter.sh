#!/bin/bash
# Playwright-jupyter — uses pre-warmed servers from jupyter_warmup.sh.
# Reads /tmp/ci-jupyter-warmup-venv and /tmp/ci-jupyter-warmup-pids.
set -uo pipefail
cd /repo

CI_RUNNER_DIR=${CI_RUNNER_DIR:-/opt/ci-runner}
JUPYTER_PARALLEL=${JUPYTER_PARALLEL:-9}

venv=$(cat /tmp/ci-jupyter-warmup-venv)

# Install wheel into the warmup venv
wheel=$(ls dist/buckaroo-*.whl | head -1)
uv pip install --python "$venv/bin/python" "$wheel" -q
"$venv/bin/python" -c "import buckaroo; import pandas; import polars" 2>/dev/null || true

rc=0
ROOT_DIR=/repo \
SKIP_INSTALL=1 \
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-jupyter-$$ \
PARALLEL=$JUPYTER_PARALLEL \
BASE_PORT=8889 \
PW_GREP="${PW_GREP_FILTER:-}" \
    timeout 120 bash "$CI_RUNNER_DIR/test_playwright_jupyter_parallel.sh" \
        --venv-location="$venv" --servers-running || rc=$?

# Cleanup servers
for pid in $(cat /tmp/ci-jupyter-warmup-pids 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
done
rm -f /tmp/ci-jupyter-warmup-venv /tmp/ci-jupyter-warmup-pids

exit $rc
