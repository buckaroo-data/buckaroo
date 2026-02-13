#!/bin/bash
# Playwright tests against the Buckaroo standalone server
# Usage:
#   bash scripts/test_playwright_server.sh
set -e

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_message() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "🧪 Starting Buckaroo Server Playwright Tests"

cd packages/buckaroo-js-core

# Install npm dependencies
log_message "Installing npm dependencies..."
if command -v pnpm &> /dev/null; then
    pnpm install
else
    npm install
fi

# Install Playwright browsers if needed
log_message "Ensuring Playwright browsers are installed..."
if command -v pnpm &> /dev/null; then
    pnpm exec playwright install chromium
else
    npx playwright install chromium
fi

success "Dependencies ready"

# Run the server tests (playwright config handles starting/stopping the server)
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_message "Running Playwright tests against Buckaroo server..."
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if pnpm test:server; then
    success "🎉 ALL SERVER PLAYWRIGHT TESTS PASSED!"
else
    error "💥 SERVER TESTS FAILED"
    exit 1
fi
