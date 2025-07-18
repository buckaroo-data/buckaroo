#!/bin/bash
set -e
#partial doesn't delete node_modules


mv node_modules temp_node_modules || true
cd packages/buckaroo-js-core
pnpm install
pnpm run build:tsc
pnpm run build:vite 
cd ../..
cp packages/buckaroo-js-core/dist/style.css buckaroo/static/compiled.css
mv packages/buckaroo-js-core/node_modules  packages/buckaroo-js-core/temp_node_modules || true
pnpm install && pnpm run build
rm -rf dist
uv build --wheel
mv temp_node_modules node_modules 
mv packages/buckaroo-js-core/temp_node_modules packages/buckaroo-js-core/node_modules  
#time hatch build
#python -m twine upload --repository pypi dist/*.whl

#./scripts/partial_build.sh && uv pip install  buckaroo@dist/buckaroo-0.10.5-py3-none-any.whl && time python scripts/warm_imports.py 
