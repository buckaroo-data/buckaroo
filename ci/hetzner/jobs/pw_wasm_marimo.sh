#!/bin/bash
set -euo pipefail
cd /repo
SKIP_INSTALL=1 \
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-wasm-marimo-$$ \
UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 \
PW_GREP="${PW_GREP_FILTER:-}" \
    bash scripts/test_playwright_wasm_marimo.sh
