#!/bin/bash
# Playwright tests against a marimo notebook running Buckaroo widgets
#
# Verifies that Buckaroo renders correctly inside marimo via anywidget.
#
# Usage:
#   bash scripts/test_playwright_marimo.sh
set -e

cd "$(dirname "$0")/.."
ROOT_DIR="$(pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_message() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}$1${NC}"
}

error() {
    echo -e "${RED}$1${NC}"
}

echo "Starting Marimo Playwright Tests"

# ---------- 1. Verify marimo is available -------------------------------------

log_message "Checking marimo is installed..."
uv run marimo --version || {
    error "marimo not found. Install with: uv pip install marimo"
    exit 1
}
success "marimo is available"

# ---------- 2. Install npm / playwright deps ---------------------------------

cd packages/buckaroo-js-core

log_message "Installing npm dependencies..."
if command -v pnpm &> /dev/null; then
    pnpm install
else
    npm install
fi

log_message "Ensuring Playwright browsers are installed..."
if command -v pnpm &> /dev/null; then
    pnpm exec playwright install chromium
else
    npx playwright install chromium
fi

success "Dependencies ready"

# ---------- 3. Warm up marimo server ------------------------------------------
# Under CPU contention (CI with parallel jobs), marimo's first page load can
# take 30s+ to compile widgets.  Start the server early, wait for it to serve
# a real page, then let Playwright reuse it.

MARIMO_PORT=2718
cd "$ROOT_DIR"

log_message "Starting marimo server for warmup..."
uv run marimo run --headless --port $MARIMO_PORT --no-token \
    tests/notebooks/marimo_pw_test.py &
MARIMO_PID=$!

# Wait for HTTP to respond
for i in $(seq 1 60); do
    if curl -sf "http://localhost:$MARIMO_PORT" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -sf "http://localhost:$MARIMO_PORT" >/dev/null 2>&1; then
    error "marimo server failed to start within 60s"
    kill $MARIMO_PID 2>/dev/null || true
    exit 1
fi
success "marimo server is responding"

# Warm up: fetch the page so marimo compiles widgets and caches them.
# Poll until the response contains JS (compiled widgets) instead of hard sleep.
log_message "Warming up marimo (fetching page to trigger widget compilation)..."
curl -sf "http://localhost:$MARIMO_PORT" >/dev/null 2>&1
for _i in $(seq 1 20); do
    body=$(curl -sf "http://localhost:$MARIMO_PORT" 2>/dev/null || echo "")
    if echo "$body" | grep -q '<script'; then
        break
    fi
    sleep 0.5
done
success "marimo warmup complete"

cd packages/buckaroo-js-core

# ---------- 4. Run the marimo playwright tests --------------------------------

log_message "Running Playwright tests against marimo notebook..."

# Tell Playwright to reuse the running server (reuseExistingServer in config
# is only set for non-CI; we override via env so the warmup server is used)
if MARIMO_WARMUP_PID=$MARIMO_PID pnpm test:marimo; then
    success "ALL MARIMO PLAYWRIGHT TESTS PASSED!"
    EXIT_CODE=0
else
    error "MARIMO TESTS FAILED"
    EXIT_CODE=1
fi

# Clean up the warmup server
kill $MARIMO_PID 2>/dev/null || true
wait $MARIMO_PID 2>/dev/null || true

exit $EXIT_CODE
