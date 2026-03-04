#!/bin/bash
# Sync CI runner scripts from repo to /opt/ci/runner/ and restart container
# if the Dockerfile changed.
#
# Usage: ci/hetzner/update-runner.sh [BRANCH]
#   BRANCH defaults to the current branch in /opt/ci/repo.
#
# This replaces the manual rebuild cycle:
#   git checkout origin/<branch> -- ci/hetzner/
#   docker build ... && docker compose down && docker compose up -d
#
# Now:
#   - Script changes (run-ci.sh, lib/, test_playwright_jupyter_parallel.sh):
#     just copies files to /opt/ci/runner/ — takes effect instantly via bind mount.
#   - Dockerfile changes (new deps, system packages):
#     triggers full docker build + compose recreate.
set -euo pipefail

# Support both ramdisk layout (/opt/ci/ramdisk/repo) and legacy (/opt/ci/repo).
if [[ -d /opt/ci/ramdisk/repo/.git ]]; then
    REPO_DIR=/opt/ci/ramdisk/repo
else
    REPO_DIR=/opt/ci/repo
fi
RUNNER_DIR=/opt/ci/runner
BRANCH=${1:-}

cd "$REPO_DIR"
git fetch origin

if [[ -n "$BRANCH" ]]; then
    git checkout "origin/$BRANCH" -- ci/hetzner/ scripts/test_playwright_server.sh scripts/test_playwright_jupyter_parallel.sh 2>/dev/null || \
    git checkout "origin/$BRANCH" -- ci/hetzner/ scripts/test_playwright_jupyter_parallel.sh
fi

# ── Check if Dockerfile changed ──────────────────────────────────────────────
DOCKERFILE_HASH=$(sha256sum ci/hetzner/Dockerfile | cut -c1-64)
OLD_HASH=$(cat "$RUNNER_DIR/.dockerfile-hash" 2>/dev/null || echo "none")

if [[ "$DOCKERFILE_HASH" != "$OLD_HASH" ]]; then
    echo "Dockerfile changed — rebuilding image + recreating container"
    docker build -t buckaroo-ci -f ci/hetzner/Dockerfile .
    # Sync scripts before compose up (container mounts /opt/ci/runner/)
    mkdir -p "$RUNNER_DIR"
    cp ci/hetzner/run-ci.sh "$RUNNER_DIR/"
    cp ci/hetzner/capture-versions.sh "$RUNNER_DIR/"
    cp ci/hetzner/lib/*.sh "$RUNNER_DIR/"
    cp scripts/test_playwright_jupyter_parallel.sh "$RUNNER_DIR/"
    echo "$DOCKERFILE_HASH" > "$RUNNER_DIR/.dockerfile-hash"
    chmod +x "$RUNNER_DIR"/*.sh
    docker compose -f ci/hetzner/docker-compose.yml down
    docker compose -f ci/hetzner/docker-compose.yml up -d
    echo "Done — image rebuilt, container recreated"
else
    # ── Scripts only — just copy, no restart needed ──────────────────────────
    mkdir -p "$RUNNER_DIR"
    cp ci/hetzner/run-ci.sh "$RUNNER_DIR/"
    cp ci/hetzner/capture-versions.sh "$RUNNER_DIR/"
    cp ci/hetzner/lib/*.sh "$RUNNER_DIR/"
    cp scripts/test_playwright_jupyter_parallel.sh "$RUNNER_DIR/"
    chmod +x "$RUNNER_DIR"/*.sh
    echo "Scripts updated (no rebuild needed)"
fi
