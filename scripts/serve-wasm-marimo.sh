#!/bin/bash
# Simple HTTP server for WASM marimo HTML files
# Usage: serve-wasm-marimo.sh [port] [directory]

PORT=${1:-8765}
DIR=${2:-docs/extra-html/example_notebooks/buckaroo_ddd_tour}

if [ ! -d "$DIR" ]; then
    echo "Error: Directory not found: $DIR"
    exit 1
fi

cd "$(dirname "$0")/.."
echo "Starting HTTP server on http://localhost:$PORT"
echo "Serving: $(pwd)/$DIR"
python3 -m http.server "$PORT" --directory "$DIR"
