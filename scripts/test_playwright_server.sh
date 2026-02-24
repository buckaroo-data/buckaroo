#!/bin/bash
# Playwright tests against the Buckaroo standalone server
#
# Verifies that `buckaroo[mcp]` contains everything needed to run
# the standalone data server — no dev extras, no polars, no full env.
#
# Expects a pre-built wheel in dist/. Run full_build.sh first.
#
# Usage:
#   bash scripts/test_playwright_server.sh
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

echo "Starting Buckaroo Server Playwright Tests"

# ---------- 1. Find the pre-built wheel --------------------------------------

WHEEL=$(ls "$ROOT_DIR"/dist/buckaroo-*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL" ]; then
    error "No wheel found in dist/. Run full_build.sh first."
    exit 1
fi
log_message "Using wheel: $WHEEL"

# ---------- 2. Create a clean venv with only buckaroo[mcp] -------------------

MCP_VENV="$ROOT_DIR/.venv-mcp-test"
log_message "Creating clean venv at $MCP_VENV ..."
rm -rf "$MCP_VENV"
uv venv "$MCP_VENV" -q
uv pip install --python "$MCP_VENV/bin/python" "${WHEEL}[mcp]" pandas -q

# Sanity-check: server module must be importable
"$MCP_VENV/bin/python" -c "from buckaroo.server.app import make_app" 2>&1 \
    || { error "buckaroo.server failed to import from clean [mcp] venv"; exit 1; }
success "Clean [mcp] venv ready"

# Export so playwright.config.server.ts picks it up
export BUCKAROO_SERVER_PYTHON="$MCP_VENV/bin/python"

# ---------- 3. Install npm / playwright deps ---------------------------------

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

# ---------- 4. Run the server playwright tests --------------------------------

log_message "Running Playwright tests against Buckaroo server..."

if pnpm test:server; then
    success "ALL SERVER PLAYWRIGHT TESTS PASSED!"
    EXIT_CODE=0
else
    error "SERVER TESTS FAILED"
    EXIT_CODE=1
fi

# ---------- 5. Cleanup -------------------------------------------------------
rm -rf "$MCP_VENV"

exit $EXIT_CODE
