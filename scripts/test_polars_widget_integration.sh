#!/bin/bash
# Integration test script for Buckaroo widgets
# Usage:
#   bash scripts/test_polars_widget_integration.sh                    # Tests all widgets (creates test venv and builds buckaroo)
#   bash scripts/test_polars_widget_integration.sh --use-local-venv   # Tests all widgets (uses existing .venv, skips build)
#   bash scripts/test_polars_widget_integration.sh --notebook=test_polars_widget.ipynb  # Test specific notebook
#   bash scripts/test_polars_widget_integration.sh --venv-location=/path/to/venv  # Uses specified venv location
set -e

# Make sure we're in the buckaroo directory (scripts/ is one level down from root)
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

# Parse command line arguments
USE_LOCAL_VENV=false
VENV_LOCATION=""
NOTEBOOK=""

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
        --notebook=*)
            NOTEBOOK="${1#*=}"
            shift
            ;;
        --notebook)
            NOTEBOOK="$2"
            shift 2
            ;;
        *)
            # Unknown option, skip it (might be for future use)
            shift
            ;;
    esac
done

# Define all notebooks to test
NOTEBOOKS=(
    "test_buckaroo_widget.ipynb"
    "test_buckaroo_infinite_widget.ipynb"
    "test_polars_widget.ipynb"
    "test_polars_infinite_widget.ipynb"
    "test_dfviewer.ipynb"
    "test_dfviewer_infinite.ipynb"
    "test_polars_dfviewer.ipynb"
    "test_polars_dfviewer_infinite.ipynb"
)

# If specific notebook(s) provided, test only those (comma-separated)
if [ -n "$NOTEBOOK" ]; then
    IFS=',' read -ra NOTEBOOKS <<< "$NOTEBOOK"
fi

echo "🧪 Starting Buckaroo Widget Integration Tests"

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
    # Remove test notebooks if they exist
    if [ -n "${NOTEBOOKS+x}" ]; then
        for notebook in "${NOTEBOOKS[@]}"; do
            rm -f "$notebook"
        done
    else
        # Fallback: remove common test notebook names
        rm -f test_*.ipynb
    fi
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

# Function to test a single notebook
test_notebook() {
    local notebook_name=$1
    local notebook_source="$ROOT_DIR/tests/integration_notebooks/$notebook_name"
    
    log_message "Testing notebook: $notebook_name [$CURRENT_TEST/$TOTAL_NOTEBOOKS]"
    
    # Copy test notebook to current directory
    if [ ! -f "$notebook_source" ]; then
        error "Test notebook not found at $notebook_source"
        return 1
    fi
    cp "$notebook_source" "$notebook_name"
    success "Test notebook copied: $notebook_name"
    
    # Export notebook name for Playwright test
    export TEST_NOTEBOOK="$notebook_name"
    
    return 0
}

# Function to start JupyterLab
start_jupyter() {
    log_message "Starting JupyterLab..."
    # Kill any existing JupyterLab processes on port 8889 (but not browsers)
    lsof -ti:8889 | while read pid; do
        if ps -p "$pid" -o comm= 2>/dev/null | grep -qE 'jupyter|python'; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done || true
    
    # Clear JupyterLab workspace state to ensure clean start
    rm -rf .jupyter/lab/workspaces 2>/dev/null || true
    rm -rf ~/.jupyter/lab/workspaces 2>/dev/null || true

    export JUPYTER_TOKEN="test-token-12345"
    
    # Start JupyterLab with clean workspace
    python -m jupyter lab --no-browser --port=8889 --ServerApp.token=$JUPYTER_TOKEN --ServerApp.allow_origin='*' --ServerApp.disable_check_xsrf=True &
    JUPYTER_PID=$!
    log_message "JupyterLab started with PID: $JUPYTER_PID"

    # Wait for JupyterLab to be ready
    MAX_WAIT=30
    COUNTER=0
    while ! curl -s -f http://localhost:8889/lab?token=$JUPYTER_TOKEN > /dev/null 2>&1; do
        if [ $COUNTER -ge $MAX_WAIT ]; then
            error "JupyterLab failed to start within $MAX_WAIT seconds"
            return 1
        fi
        sleep 2
        COUNTER=$((COUNTER + 2))
    done
    success "JupyterLab is ready at http://localhost:8889"
}

# Function to stop JupyterLab
stop_jupyter() {
    if [ -n "$JUPYTER_PID" ] && kill -0 $JUPYTER_PID 2>/dev/null; then
        log_message "Stopping JupyterLab (PID: $JUPYTER_PID)"
        kill -15 $JUPYTER_PID 2>/dev/null || true
        kill -9 $JUPYTER_PID 2>/dev/null || true
    fi
    # Also kill any stragglers on port 8889
    lsof -ti:8889 | while read pid; do
        if ps -p "$pid" -o comm= 2>/dev/null | grep -qE 'jupyter|python'; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done || true
}

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

# Test all notebooks
OVERALL_RESULT=0
FAILED_NOTEBOOKS=()
TOTAL_NOTEBOOKS=${#NOTEBOOKS[@]}
CURRENT_TEST=0

for notebook in "${NOTEBOOKS[@]}"; do
    CURRENT_TEST=$((CURRENT_TEST + 1))
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Testing: $notebook [$CURRENT_TEST/$TOTAL_NOTEBOOKS]"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Start fresh JupyterLab for each notebook
    cd "$ROOT_DIR"
    start_jupyter
    
    # Copy notebook to root directory (where JupyterLab serves from)
    if ! test_notebook "$notebook"; then
        error "Failed to prepare notebook: $notebook"
        OVERALL_RESULT=1
        FAILED_NOTEBOOKS+=("$notebook (preparation failed)")
        stop_jupyter
        continue
    fi
    
    # Run Playwright test (from packages/buckaroo-js-core)
    cd packages/buckaroo-js-core
    log_message "Running Playwright test for $notebook..."
    if npx playwright test --config playwright.config.integration.ts --reporter=line --timeout=30000; then
        success "✅ Playwright test passed for $notebook!"
    else
        error "❌ Playwright test failed for $notebook!"
        OVERALL_RESULT=1
        FAILED_NOTEBOOKS+=("$notebook")
    fi
    
    # Clean up notebook file (from root directory)
    cd "$ROOT_DIR"
    rm -f "$notebook"
    
    # Stop JupyterLab to ensure clean state for next test
    stop_jupyter
done

cd ../..

# Final summary
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $OVERALL_RESULT -eq 0 ]; then
    success "🎉 ALL INTEGRATION TESTS PASSED!"
    log_message "All widgets work correctly in JupyterLab"
else
    error "💥 SOME INTEGRATION TESTS FAILED"
    log_message "Failed notebooks:"
    for failed in "${FAILED_NOTEBOOKS[@]}"; do
        error "  - $failed"
    done
fi
log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $OVERALL_RESULT
