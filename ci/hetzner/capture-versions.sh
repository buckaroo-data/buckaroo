#!/bin/bash
# Capture exact package versions from a running CI container.
# Run: docker exec buckaroo-ci bash /opt/ci-runner/capture-versions.sh > /opt/ci/logs/versions-$(hostname).txt
set -euo pipefail

echo "=== Capture date: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "=== Hostname: $(hostname) ==="
echo ""

echo "--- OS ---"
cat /etc/os-release | grep -E "^(NAME|VERSION)="
uname -r
uname -m

echo ""
echo "--- Python ---"
for v in 3.11 3.12 3.13 3.14; do
  bin="/opt/venvs/$v/bin/python"
  [ -x "$bin" ] && echo "$v: $($bin --version 2>&1)" || echo "$v: not found"
done

echo ""
echo "--- Node / pnpm ---"
node --version
pnpm --version

echo ""
echo "--- uv ---"
uv --version

echo ""
echo "--- Chromium (Playwright) ---"
# Python playwright
/opt/venvs/3.13/bin/python -c "
from playwright._impl._driver import compute_driver_executable
import subprocess, os
driver = compute_driver_executable()
node = os.path.join(os.path.dirname(driver), '..', 'node', 'node')
# Just get browser version from registry
" 2>/dev/null || true
ls /opt/ms-playwright/ 2>/dev/null
for chrome in /opt/ms-playwright/chromium-*/chrome-linux/chrome; do
  [ -x "$chrome" ] && echo "chromium: $($chrome --version 2>/dev/null || echo 'cannot get version')"
done

echo ""
echo "--- Python packages (3.13 venv, CI primary) ---"
UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13 uv pip list --format=freeze 2>/dev/null | sort

echo ""
echo "--- JS packages (buckaroo-js-core) ---"
if [ -d /repo/packages/buckaroo-js-core/node_modules ]; then
  cd /repo/packages/buckaroo-js-core
  pnpm list --depth=0 2>/dev/null || true
else
  echo "node_modules not found (run build-js first)"
fi

echo ""
echo "--- Key packages summary ---"
/opt/venvs/3.13/bin/python -c "
pkgs = [
    'ipykernel', 'jupyterlab', 'jupyter_server', 'jupyter_client',
    'ipywidgets', 'anywidget', 'pyzmq', 'tornado', 'traitlets',
    'nbformat', 'nbconvert', 'marimo', 'solara', 'voila',
    'buckaroo', 'playwright', 'pandas', 'polars', 'numpy',
]
from importlib.metadata import version, PackageNotFoundError
for p in pkgs:
    try:
        print(f'{p}=={version(p)}')
    except PackageNotFoundError:
        print(f'{p}: NOT INSTALLED')
"
