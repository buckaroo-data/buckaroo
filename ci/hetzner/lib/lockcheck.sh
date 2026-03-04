#!/bin/bash
# Lockfile hash comparison — determines whether CI deps need rebuilding.
#
# On 95% of pushes, lockfiles don't change; skip expensive dep install entirely.
# When they do change (new dependency, version bump), detect it and rebuild.
#
# Tracked files:
#   uv.lock               — Python deps
#   packages/pnpm-lock.yaml — JS deps
#   pyproject.toml        — may add new extras without touching uv.lock
#
# Hash storage: /opt/ci/logs/.lockcheck-hashes/ — persists across container
# restarts because /opt/ci/logs is bind-mounted to the host.
#
# Usage (inside run-ci.sh, from /repo):
#   source /repo/ci/hetzner/lib/lockcheck.sh
#   if ! lockcheck_valid; then
#       rebuild_deps
#       lockcheck_update
#   fi

LOCKCHECK_HASH_DIR=/opt/ci/logs/.lockcheck-hashes
LOCKCHECK_FILES=(
    uv.lock
    packages/pnpm-lock.yaml
    pyproject.toml
)

_lockcheck_hash_path() {
    local file=$1
    # Replace slashes with underscores for filename
    echo "$LOCKCHECK_HASH_DIR/${file//\//_}.sha256"
}

# Returns 0 (valid) if all stored hashes match current files.
# Returns 1 (rebuild needed) if any hash differs or is missing.
lockcheck_valid() {
    mkdir -p "$LOCKCHECK_HASH_DIR"
    for f in "${LOCKCHECK_FILES[@]}"; do
        local hash_file
        hash_file=$(_lockcheck_hash_path "$f")
        if [[ ! -f "$hash_file" ]]; then
            return 1
        fi
        local stored current
        stored=$(cat "$hash_file")
        current=$(sha256sum "$f" | awk '{print $1}')
        if [[ "$stored" != "$current" ]]; then
            return 1
        fi
    done
    return 0
}

# Stores current hashes. Call after a successful rebuild.
lockcheck_update() {
    mkdir -p "$LOCKCHECK_HASH_DIR"
    for f in "${LOCKCHECK_FILES[@]}"; do
        local hash_file
        hash_file=$(_lockcheck_hash_path "$f")
        sha256sum "$f" | awk '{print $1}' > "$hash_file"
    done
}

# Rebuilds Python venvs and JS node_modules.
# Run from /repo inside the container.
rebuild_deps() {
    echo "[lockcheck] Rebuilding Python deps..."
    for v in 3.11 3.12 3.13 3.14; do
        UV_PROJECT_ENVIRONMENT=/opt/venvs/$v \
            uv sync --locked --dev --all-extras --no-install-project
    done

    echo "[lockcheck] Rebuilding JS deps..."
    cd packages
    pnpm install --frozen-lockfile --store-dir /opt/pnpm-store
    cd ..

    echo "[lockcheck] Reinstalling Playwright browsers (versions may have changed)..."
    /opt/venvs/3.13/bin/playwright install chromium
    cd packages/buckaroo-js-core && pnpm exec playwright install chromium && cd ../..

    echo "[lockcheck] Rebuild complete."
}
