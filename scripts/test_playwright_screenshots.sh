#!/bin/bash
# Capture light/dark theme screenshots of every important Storybook story.
# Usage:
#   bash scripts/test_playwright_screenshots.sh
set -e

cd "$(dirname "$0")/.."
ROOT_DIR="$(pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_message() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
success()     { echo -e "${GREEN}$1${NC}"; }
error()       { echo -e "${RED}$1${NC}"; }

echo "Capturing theme screenshots"

cd packages/buckaroo-js-core

# Install deps
log_message "Installing dependencies..."
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

# Kill any existing storybook on port 6006
log_message "Cleaning up port 6006..."
lsof -ti:6006 | xargs kill -9 2>/dev/null || true

# Start Storybook
log_message "Starting Storybook..."
if command -v pnpm &> /dev/null; then
    pnpm storybook --no-open &
else
    npm run storybook -- --no-open &
fi
STORYBOOK_PID=$!

cleanup() {
    log_message "Cleaning up..."
    kill $STORYBOOK_PID 2>/dev/null || true
    lsof -ti:6006 | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT

MAX_WAIT=60
COUNTER=0
log_message "Waiting for Storybook to start..."
while ! curl -s -f http://localhost:6006 > /dev/null 2>&1; do
    if [ $COUNTER -ge $MAX_WAIT ]; then
        error "Storybook failed to start within $MAX_WAIT seconds"
        exit 1
    fi
    sleep 2
    COUNTER=$((COUNTER + 2))
done
success "Storybook is ready at http://localhost:6006"

# Run only the screenshot spec
log_message "Running theme screenshot capture..."
npx playwright test pw-tests/theme-screenshots.spec.ts --reporter=line

SCREENSHOT_COUNT=$(ls -1 screenshots/*.png 2>/dev/null | wc -l | tr -d ' ')
success "Captured $SCREENSHOT_COUNT screenshots in packages/buckaroo-js-core/screenshots/"
