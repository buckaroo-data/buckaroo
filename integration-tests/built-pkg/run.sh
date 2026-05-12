#!/usr/bin/env bash
#
# Builds buckaroo-js-core, packs it to a tarball, installs the tarball into
# this directory with plain npm (NOT pnpm — we want to bypass the parent
# pnpm workspace entirely so we are definitively testing the built module,
# not workspace-linked source), then runs Playwright against a Vite dev server.
#
# Usage:
#   bash integration-tests/built-pkg/run.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
CORE_DIR="$REPO_ROOT/packages/buckaroo-js-core"

echo "==> Building buckaroo-js-core"
(cd "$CORE_DIR" && pnpm install --frozen-lockfile=false && pnpm run build)

echo "==> Packing buckaroo-js-core"
# `pnpm pack` writes buckaroo-js-core-<version>.tgz; rename to a fixed
# filename so the consumer package.json can reference it without a version.
rm -f "$HERE"/buckaroo-js-core-*.tgz "$HERE/buckaroo-js-core.tgz"
(cd "$CORE_DIR" && pnpm pack --pack-destination "$HERE/")
mv "$HERE"/buckaroo-js-core-*.tgz "$HERE/buckaroo-js-core.tgz"

echo "==> Installing tarball into consumer (plain npm, no workspace)"
cd "$HERE"
# Wipe node_modules and any lockfile so we never reuse a previous install.
rm -rf node_modules package-lock.json
npm install --no-fund --no-audit

echo "==> Ensuring Playwright browser is installed"
npx --no-install playwright install chromium >/dev/null 2>&1 || npx playwright install chromium

echo "==> Running Playwright"
npm test
