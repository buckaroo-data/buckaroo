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

# ---------- 3. Run the marimo playwright tests --------------------------------

log_message "Running Playwright tests against marimo notebook..."

if pnpm test:marimo; then
    success "ALL MARIMO PLAYWRIGHT TESTS PASSED!"
    EXIT_CODE=0
else
    error "MARIMO TESTS FAILED"
    EXIT_CODE=1
fi

exit $EXIT_CODE
