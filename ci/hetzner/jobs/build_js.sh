#!/bin/bash
set -euo pipefail
cd /repo/packages
pnpm install --frozen-lockfile --store-dir /opt/pnpm-store
cd buckaroo-js-core
if [[ "${JS_DIST_CACHED:-0}" != "1" ]]; then
    pnpm run build
    # Cache for future runs
    mkdir -p "${JS_CACHE_DIR:?}"
    rm -rf "$JS_CACHE_DIR/$JS_TREE_HASH"
    cp -r dist "$JS_CACHE_DIR/$JS_TREE_HASH"
    echo "JS build cached ($JS_TREE_HASH)"
else
    echo "JS build skipped (cache hit)"
fi
