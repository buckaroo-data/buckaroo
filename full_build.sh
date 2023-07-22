#!/bin/bash
set -e
#rm -rf node_modules 
rm -rf dist
python -m build .
rm -f dist/index.js dist/index.js.LICENSE.txt
twine check dist/*
python -m twine upload --repository testpypi dist/*
python -m twine upload --repository pypi dist/*
#npm publish
