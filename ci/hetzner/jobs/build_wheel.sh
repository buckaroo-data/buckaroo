#!/bin/bash
set -euo pipefail
cd /repo
PNPM_STORE_DIR=/opt/pnpm-store bash scripts/full_build.sh
