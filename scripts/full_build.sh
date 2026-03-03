#!/bin/bash
set -e

# If JS core dist already exists (e.g. from a prior `pnpm build` in test-js),
# skip the expensive tsc+vite rebuild and just do the packaging steps.
if [ -f packages/buckaroo-js-core/dist/style.css ] && \
   [ -f packages/buckaroo-js-core/dist/index.js ]; then
    echo "[full_build] JS core dist exists — skipping rebuild"
else
    # Clean previous builds
    rm -rf packages/buckaroo-js-core/dist || true
    rm -f packages/buckaroo-js-core/tsconfig.tsbuildinfo || true
    rm -rf buckaroo/static/*.js buckaroo/static/*.css || true

    # Install all workspace dependencies (once)
    cd packages
    pnpm install

    # Build buckaroo-js-core first (tsc + vite)
    pnpm --filter buckaroo-js-core run build
    cd ..
fi

# Copy CSS to Python package
mkdir -p buckaroo/static
cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css

# Build anywidget wrapper + standalone entry point (esbuild)
cd packages
pnpm install 2>/dev/null || true
pnpm --filter buckaroo-widget run build
pnpm --filter buckaroo-widget run build:standalone

# Build Python wheel
cd ..
rm -rf dist || true
uv build --wheel
