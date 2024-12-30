#!/bin/bash
 set -e
rm -rf node_modules buckaroo/widget.js
rm -rf  packages/buckaroo-js-core/dist packages/buckaroo-js-core/node_modules
cd packages/buckaroo-js-core
npm install && npm run build
cd ../..
rm -rf packages/buckaroo-js-core/node_modules
npm install && npm run build
rm -rf dist
uv build --wheel
#time hatch build
#python -m twine upload --repository pypi dist/*.whl
