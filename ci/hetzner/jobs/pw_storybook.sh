#!/bin/bash
set -euo pipefail
cd /repo
SKIP_INSTALL=1 \
PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-storybook-$$ \
PW_GREP="${PW_GREP_FILTER:-}" \
    bash scripts/test_playwright_storybook.sh
