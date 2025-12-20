#!/bin/bash
# Integration test script for PolarsBuckarooWidget
# Usage:
#   bash scripts/test_polars_widget_integration.sh                    # Creates test venv and builds buckaroo
#   bash scripts/test_polars_widget_integration.sh --use-local-venv   # Uses existing .venv (skips build)
#   bash scripts/test_polars_widget_integration.sh --venv-location=/path/to/venv  # Uses specified venv location
set -e

# Make sure we're in the buckaroo directory (scripts/ is one level down from root)
cd "$(dirname "$0")/.."

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

# Parse command line arguments
USE_LOCAL_VENV=false
VENV_LOCATION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --use-local-venv|--local-dev)
            USE_LOCAL_VENV=true
            shift
            ;;
        --venv-location=*)
            VENV_LOCATION="${1#*=}"
            shift
            ;;
        --venv-location)
            VENV_LOCATION="$2"
            shift 2
            ;;
        *)
            # Unknown option, skip it (might be for future use)
            shift
            ;;
    esac
done

echo "🧪 Starting PolarsBuckarooWidget Integration Test"

# Create and activate a virtual environment for the test
if [ -n "$VENV_LOCATION" ]; then
    # Use explicitly provided venv location
    VENV_DIR="$VENV_LOCATION"
    if [ ! -d "$VENV_DIR" ]; then
        error "Venv not found at $VENV_DIR. Please create it first or check the path."
        exit 1
    fi
    log_message "Using specified venv location: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
    log_message "Virtual environment activated: $VIRTUAL_ENV"
elif [ "$USE_LOCAL_VENV" = true ]; then
    VENV_DIR=".venv"
    if [ ! -d "$VENV_DIR" ]; then
        error "Local venv not found at $VENV_DIR. Please create it first or run without --use-local-venv"
        exit 1
    fi
    log_message "Using local development venv: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
    log_message "Virtual environment activated: $VIRTUAL_ENV"
else
    VENV_DIR="./test_venv"
    log_message "Creating virtual environment with uv..."
    uv venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    log_message "Virtual environment activated: $VIRTUAL_ENV"
fi

cleanup() {
    log_message "Cleaning up..."
    if [ ! -z "$JUPYTER_PID" ]; then
        log_message "Stopping JupyterLab (PID: $JUPYTER_PID)"
        kill $JUPYTER_PID 2>/dev/null || true
        wait $JUPYTER_PID 2>/dev/null || true
    fi
    # Remove test notebook if it exists
    rm -f test_polars_widget.ipynb
    # Remove virtual environment only if it's a test venv (not existing venv)
    if [ -z "$VENV_LOCATION" ] && [ "$USE_LOCAL_VENV" = false ] && [ -d "$VENV_DIR" ]; then
        log_message "Removing virtual environment..."
        rm -rf "$VENV_DIR"
    fi
}

trap cleanup EXIT

# Check if required Python packages are installed (only when creating new venv)
if [ -z "$VENV_LOCATION" ] && [ "$USE_LOCAL_VENV" = false ]; then
    log_message "Checking Python dependencies..."
    if ! python3 -c "
import sys
try:
    import polars
    print('polars: OK')
except ImportError:
    print('polars: MISSING')
    sys.exit(1)

try:
    import jupyterlab
    print('jupyterlab: OK')
except ImportError:
    print('jupyterlab: MISSING')
    sys.exit(1)
"; then
        warning "Missing required Python packages. Installing automatically..."
        if ! uv pip install pandas polars jupyterlab; then
            error "Failed to install Python dependencies automatically."
            exit 1
        fi
        success "Python dependencies installed automatically"
    fi
else
    log_message "Using existing venv - skipping dependency installation"
fi

if [ -n "$VENV_LOCATION" ] || [ "$USE_LOCAL_VENV" = true ]; then
    # Using existing venv - check if buckaroo is installed
    log_message "Checking if buckaroo is installed in venv..."
    if ! python -c "import buckaroo" 2>/dev/null; then
        error "buckaroo is not installed in venv. Please install it first."
        exit 1
    fi
    success "Using buckaroo from existing venv"
else
    # Build and install buckaroo from source (only when creating new test venv)
    success "Required Python dependencies available (buckaroo will be built from source)"
    
    # Run full build
    log_message "Running full build..."
    if ! bash scripts/full_build.sh; then
        error "Full build failed"
        exit 1
    fi
    success "Build completed successfully"
    
    # Install the built wheel
    log_message "Installing built buckaroo wheel..."
    if [ ! -f dist/*.whl ]; then
        error "No wheel file found in dist/ directory"
        ls -la dist/ || true
        exit 1
    fi
    
    if ! uv pip install --force-reinstall dist/*.whl; then
        error "Failed to install built buckaroo wheel"
        exit 1
    fi
    success "Built buckaroo wheel installed"
fi

# Verify buckaroo can be imported
log_message "Verifying buckaroo installation..."
python -c "
try:
    import buckaroo
    print('✅ buckaroo imported successfully')
    print(f'Version: {getattr(buckaroo, \"__version__\", \"unknown\")}')
except ImportError as e:
    print(f'❌ Failed to import buckaroo: {e}')
    import sys
    sys.exit(1)
" || {
    error "buckaroo installation verification failed"
    exit 1
}

# Create test notebook
log_message "Creating test notebook..."
cat > test_polars_widget.ipynb << 'EOF'
{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Test buckaroo import\n",
    "try:\n",
    "    import buckaroo\n",
    "    print(f\"✅ buckaroo imported successfully: {buckaroo.__version__}\")\n",
    "except ImportError as e:\n",
    "    print(f\"❌ Failed to import buckaroo: {e}\")\n",
    "    raise\n",
    "\n",
    "import polars as pl\n",
    "from buckaroo.polars_buckaroo import PolarsBuckarooWidget\n",
    "\n",
    "# Create test data\n",
    "df = pl.DataFrame({\n",
    "    'name': ['Alice', 'Bob', 'Charlie'],\n",
    "    'age': [25, 30, 35],\n",
    "    'score': [85.5, 92.0, 78.3]\n",
    "})\n",
    "print(f\"✅ Created DataFrame with shape: {df.shape}\")\n",
    "\n",
    "# Display the widget\n",
    "widget = PolarsBuckarooWidget(df)\n",
    "print(\"✅ PolarsBuckarooWidget created successfully\")\n",
    "widget"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 4
}
EOF
success "Test notebook created"

# Start JupyterLab in background (using virtual environment Python)
log_message "Starting JupyterLab..."
# Kill any existing JupyterLab processes on port 8889
lsof -ti:8889 | xargs kill -9 2>/dev/null || true
sleep 1

export JUPYTER_TOKEN="test-token-12345"
PYTHON_EXECUTABLE="$VENV_DIR/bin/python"
log_message "Using virtual environment Python: $PYTHON_EXECUTABLE"

# Set JupyterLab to allow root (needed for CI) and disable token check for localhost
python -m jupyter lab --no-browser --port=8889 --ServerApp.token=$JUPYTER_TOKEN --ServerApp.allow_origin='*' --ServerApp.disable_check_xsrf=True &
JUPYTER_PID=$!
log_message "JupyterLab started with PID: $JUPYTER_PID"

# Wait for JupyterLab to be ready
log_message "Waiting for JupyterLab to start..."
MAX_WAIT=30
COUNTER=0
while ! curl -s -f http://localhost:8889/lab?token=$JUPYTER_TOKEN > /dev/null 2>&1; do
    if [ $COUNTER -ge $MAX_WAIT ]; then
        error "JupyterLab failed to start within $MAX_WAIT seconds"
        # Show JupyterLab logs for debugging
        log_message "Checking JupyterLab process status..."
        if kill -0 $JUPYTER_PID 2>/dev/null; then
            log_message "JupyterLab process is still running"
        else
            error "JupyterLab process has exited"
        fi
        exit 1
    fi
    sleep 2
    COUNTER=$((COUNTER + 2))
    log_message "Still waiting... ($COUNTER/$MAX_WAIT seconds)"
done
success "JupyterLab is ready at http://localhost:8889"

# Give JupyterLab extra time to fully initialize (especially important in CI)
log_message "Waiting for JupyterLab to fully initialize..."
sleep 5

# Install npm dependencies for Playwright
log_message "Installing npm dependencies for Playwright..."
cd packages/buckaroo-js-core
if ! command -v pnpm &> /dev/null; then
    warning "pnpm not found, trying npm..."
    if ! npm install; then
        error "Failed to install npm dependencies"
        exit 1
    fi
else
    if ! pnpm install; then
        error "Failed to install npm dependencies with pnpm"
        exit 1
    fi
fi

# Install Playwright browsers if needed
log_message "Ensuring Playwright browsers are installed..."
if command -v pnpm &> /dev/null; then
    if pnpm exec playwright install chromium 2>&1 | grep -q "already installed\|chromium.*downloaded\|chromium.*installed"; then
        success "Playwright browsers ready"
    else
        pnpm exec playwright install chromium
    fi
else
    npx playwright install chromium
fi

success "npm dependencies and Playwright browsers ready"

# Run Playwright test
log_message "Running Playwright test..."
if npx playwright test --config playwright.config.integration.ts --reporter=line --timeout=120000; then
    success "Playwright test passed!"
    TEST_RESULT=0
else
    error "Playwright test failed!"
    TEST_RESULT=1
fi
cd ../..

if [ $TEST_RESULT -eq 0 ]; then
    success "🎉 INTEGRATION TEST PASSED: PolarsBuckarooWidget works in JupyterLab!"
    log_message "ag-grid renders correctly in JupyterLab environment"
else
    error "💥 INTEGRATION TEST FAILED: PolarsBuckarooWidget has issues"
fi

exit $TEST_RESULT
