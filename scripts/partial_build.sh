#!/bin/bash
set -e
#partial doesn't delete node_modules
cd packages/buckaroo-js-core
pnpm install && pnpm run build
cd ../..
cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css
pnpm install && pnpm run build
rm -rf dist
uv build --wheel
#time hatch build
#python -m twine upload --repository pypi dist/*.whl

