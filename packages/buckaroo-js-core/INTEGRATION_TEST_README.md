# PolarsBuckarooWidget Integration Test

This integration test verifies that the PolarsBuckarooWidget correctly renders ag-grid in JupyterLab through a complete end-to-end workflow.

## Prerequisites

Before running the integration test, ensure you have:

1. **Python dependencies installed**:
   ```bash
   python3 -m pip install --user polars buckaroo jupyterlab
   ```

2. **Node.js dependencies** (must be installed):
   ```bash
   cd packages/buckaroo-js-core
   pnpm install
   ```
   
   **Important**: You must run `pnpm install` before running the integration test, as it installs Playwright and other required dependencies.

## Running the Integration Test

The integration test performs the following steps:

1. **Dependency Check**: Verifies polars, buckaroo, and jupyterlab are installed
2. **Full Build**: Runs `scripts/full_build.sh` to build the entire project
3. **Notebook Creation**: Creates a test notebook with PolarsBuckarooWidget code
4. **JupyterLab Startup**: Starts JupyterLab server on port 8889 with authentication
5. **Browser Automation**: Uses Playwright to:
   - Navigate to JupyterLab
   - Open the test notebook
   - Execute the PolarsBuckarooWidget cell
   - Verify ag-grid renders correctly

To run the complete integration test:

```bash
# From the buckaroo root directory (recommended - handles everything)
./test_polars_widget_integration.sh
```

**Alternative**: If JupyterLab is already running, you can run just the Playwright tests:

```bash
# From packages/buckaroo-js-core directory
cd packages/buckaroo-js-core
pnpm test:integration
```

**Note**: The `pnpm test:integration` command requires:
- JupyterLab to be running on `http://localhost:8889` with token `test-token-12345`
- The test notebook `test_polars_widget.ipynb` to exist in the JupyterLab working directory

## What the Test Verifies

- ✅ Python dependencies are available (polars, buckaroo, jupyterlab)
- ✅ Full build process completes successfully
- ✅ JupyterLab server starts and responds
- ✅ Test notebook is created with proper PolarsBuckarooWidget code
- ✅ JupyterLab loads the notebook interface
- ✅ PolarsBuckarooWidget cell executes without errors
- ✅ Buckaroo widget appears in the output area
- ✅ ag-grid renders with proper structure
- ✅ Column headers are correct (name, age, score)
- ✅ Data rows are displayed
- ✅ Specific data values are visible (Alice, 25, 85.5)

## Debugging

If the test fails:

1. **Check Python dependencies**:
   ```bash
   python3 -c "import polars, buckaroo, jupyterlab; print('All dependencies OK')"
   ```

2. **Check build process**:
   ```bash
   bash scripts/full_build.sh
   ```

3. **Manual testing**: Start JupyterLab manually and test the widget:
   ```bash
   python3 -m jupyter lab --no-browser --port=8889 --ServerApp.token=test-token
   ```
   Then open http://localhost:8889/lab?token=test-token in a browser

4. **Test logs**: The script provides detailed logging of each step
5. **Playwright debugging**: Set `DEBUG=pw:api` environment variable for detailed Playwright logs

## Test Architecture

### Shell Script (`test_polars_widget_integration.sh`)
- Handles dependency checking and installation
- Runs the full build process
- Manages JupyterLab server lifecycle
- Calls Playwright for browser automation

### Playwright Test (`packages/buckaroo-js-core/pw-tests/integration.spec.ts`)
- Automates browser interaction with JupyterLab
- Verifies widget rendering and ag-grid functionality
- Uses realistic test data and assertions

### Configuration (`playwright.config.integration.ts`)
- Serial test execution (not parallel)
- Extended timeouts for integration operations
- Single worker to avoid conflicts

## Expected Test Output

```
🧪 Starting PolarsBuckarooWidget Integration Test
[HH:MM:SS] Checking Python dependencies...
✅ All Python dependencies available
[HH:MM:SS] Running full build...
✅ Build completed successfully
[HH:MM:SS] Creating test notebook...
✅ Test notebook created
[HH:MM:SS] Starting JupyterLab...
✅ JupyterLab started with PID: 12345
[HH:MM:SS] Waiting for JupyterLab to start...
✅ JupyterLab is ready at http://localhost:8889
[HH:MM:SS] Running Playwright test...
Running 1 test using 1 worker
✅ PolarsBuckarooWidget renders ag-grid in JupyterLab
🎉 SUCCESS: PolarsBuckarooWidget rendered ag-grid with 3 rows, 3 columns, and 9 cells
📊 Verified data: Alice (age 25, score 85.5)
[HH:MM:SS] Cleaning up...
🎉 INTEGRATION TEST PASSED: PolarsBuckarooWidget works in JupyterLab!
```

## Manual Testing Alternative

If the automated test fails, you can test manually:

1. **Build the project**:
   ```bash
   bash scripts/full_build.sh
   ```

2. **Start JupyterLab**:
   ```bash
   python3 -m jupyter lab
   ```

3. **Create and run a test notebook** with this code:
   ```python
   import polars as pl
   from buckaroo.polars_buckaroo import PolarsBuckarooWidget

   # Create test data
   df = pl.DataFrame({
       "name": ["Alice", "Bob", "Charlie"],
       "age": [25, 30, 35],
       "score": [85.5, 92.0, 78.3]
   })

   # Display the widget
   PolarsBuckarooWidget(df)
   ```

4. **Verify**: The widget should display an interactive ag-grid table with the data
