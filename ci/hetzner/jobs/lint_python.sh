#!/bin/bash
set -euo pipefail
cd /repo
# ruff is already in the 3.13 venv from the image build.
# Do NOT run uv sync here — it would strip --all-extras packages (e.g.
# pl-series-hash) from the shared venv, racing with job_test_python_3.13.
/opt/venvs/3.13/bin/ruff check
