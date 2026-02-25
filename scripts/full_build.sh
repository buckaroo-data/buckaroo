#!/bin/bash
set -e

# Clean previous builds
rm -rf packages/buckaroo-js-core/dist || true
rm -f packages/buckaroo-js-core/tsconfig.tsbuildinfo || true
rm -rf buckaroo/static/*.js buckaroo/static/*.css || true

# Install all workspace dependencies (once)
cd packages
pnpm install

# Build buckaroo-js-core first (tsc + vite)
pnpm --filter buckaroo-js-core run build

# Copy CSS to Python package
cd ..
mkdir -p buckaroo/static
cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css

# Build anywidget wrapper + standalone entry point (esbuild)
cd packages
pnpm --filter buckaroo-widget run build
pnpm --filter buckaroo-widget run build:standalone
pnpm --filter buckaroo-widget run build:static

# Build Python wheel
cd ..
rm -rf dist || true
uv build --wheel
