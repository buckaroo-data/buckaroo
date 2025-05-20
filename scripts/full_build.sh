#!/bin/bash
set -e
rm -rf node_modules buckaroo/widget.js || true
rm -rf  packages/buckaroo-js-core/dist packages/buckaroo-js-core/node_modules || true
cd packages/buckaroo-js-core
pnpm install
pnpm run build:tsc
pnpm run build:vite 
cd ../..
cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css
rm -rf packages/buckaroo-js-core/node_modules || true
pnpm install && pnpm run build
rm -rf dist || true
uv build --wheel
#time hatch build
#python -m twine upload --repository pypi dist/*.whl
