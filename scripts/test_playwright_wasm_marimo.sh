#!/bin/bash
# Playwright tests against marimo notebooks compiled to WASM/Pyodide
#
# Verifies that Buckaroo renders correctly inside marimo WASM via anywidget.
#
# Usage:
#   bash scripts/test_playwright_wasm_marimo.sh
set -e

cd "$(dirname "$0")/.."
ROOT_DIR="$(pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

warning() {
    echo -e "${YELLOW}$1${NC}"
}

echo "Starting WASM Marimo Playwright Tests"

# ---------- 1. Verify marimo is available -----------------------------------------

log_message "Checking marimo is installed..."
uv run marimo --version || {
    error "marimo not found. Install with: uv pip install marimo"
    exit 1
}
success "marimo is available"

# ---------- 2. Generate WASM HTML if needed ----------------------------------------

log_message "Checking WASM HTML output..."
WASM_HTML_DIR="$ROOT_DIR/docs/extra-html/example_notebooks/buckaroo_simple"
if [ ! -f "$WASM_HTML_DIR/index.html" ]; then
    log_message "WASM HTML not found. Generating from marimo notebook..."
    bash "$ROOT_DIR/scripts/marimo_wasm_output.sh" "buckaroo_simple.py" "run" || {
        error "Failed to generate WASM HTML"
        exit 1
    }
    success "WASM HTML generated"
else
    success "WASM HTML already present"
fi

# ---------- 3. Install npm / playwright deps ----------------------------------------

cd "$ROOT_DIR/packages/buckaroo-js-core"

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

# ---------- 4. Run the WASM marimo playwright tests --------------------------------

log_message "Running Playwright tests against WASM marimo notebook..."
warning "Note: First test run may take 15-30 seconds for Pyodide initialization"

if pnpm exec playwright test --config playwright.config.wasm-marimo.ts; then
    success "ALL WASM MARIMO PLAYWRIGHT TESTS PASSED!"
    EXIT_CODE=0
else
    error "WASM MARIMO TESTS FAILED"
    EXIT_CODE=1
fi

exit $EXIT_CODE
