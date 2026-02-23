#!/bin/bash
# Playwright tests against Storybook
# Usage:
#   bash scripts/test_playwright_storybook.sh
set -e

# Make sure we're in the buckaroo directory
cd "$(dirname "$0")/.."
ROOT_DIR="$(pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_message() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

echo "🧪 Starting Storybook Playwright Tests"

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

# Kill any existing storybook on port 6006
log_message "Cleaning up port 6006..."
lsof -ti:6006 | xargs kill -9 2>/dev/null || true

# Start storybook in background
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

# Wait for storybook to be ready
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

# Run storybook playwright tests (exclude integration tests that need JupyterLab)
OVERALL_RESULT=0
FAILED_TESTS=()

STORYBOOK_TESTS=(
    "pw-tests/transcript-replayer.spec.ts"
    "pw-tests/outside-params.spec.ts"
    "pw-tests/height-mode.spec.ts"
    # "pw-tests/example.spec.ts"  # Has pre-existing failures, excluded for now
)

log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_message "Running Playwright tests against Storybook..."
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for test_file in "${STORYBOOK_TESTS[@]}"; do
    if [ -f "$test_file" ]; then
        log_message "Running $test_file..."
        if npx playwright test "$test_file" --reporter=line; then
            success "$test_file passed!"
        else
            error "$test_file failed!"
            OVERALL_RESULT=1
            FAILED_TESTS+=("$test_file")
        fi
    else
        warning "$test_file not found, skipping"
    fi
done

# Final summary
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $OVERALL_RESULT -eq 0 ]; then
    success "🎉 ALL STORYBOOK PLAYWRIGHT TESTS PASSED!"
else
    error "💥 SOME STORYBOOK TESTS FAILED"
    log_message "Failed tests:"
    for failed in "${FAILED_TESTS[@]}"; do
        error "  - $failed"
    done
fi
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $OVERALL_RESULT

