#!/bin/bash
# GitHub commit status API helpers.
# Requires GITHUB_TOKEN and GITHUB_REPO to be set in the environment.
# GITHUB_REPO format: "owner/repo"
#
# Usage:
#   source ci/hetzner/lib/status.sh
#   status_pending  "$SHA" "ci/hetzner" "Running…" "$LOG_URL"
#   status_success  "$SHA" "ci/hetzner" "All checks passed" "$LOG_URL"
#   status_failure  "$SHA" "ci/hetzner" "lint-python failed" "$LOG_URL"
#
# Add --dry-run as the last arg to print the curl command instead of running it.

_github_status() {
    local state=$1
    local sha=$2
    local context=$3
    local description=$4
    local target_url=$5
    local dry_run=${6:-}

    local url="https://api.github.com/repos/${GITHUB_REPO}/statuses/${sha}"
    local payload
    payload=$(printf '{"state":"%s","context":"%s","description":"%s","target_url":"%s"}' \
        "$state" "$context" "$description" "$target_url")

    if [[ "$dry_run" == "--dry-run" ]]; then
        echo "[dry-run] POST $url"
        echo "[dry-run] $payload"
        return 0
    fi

    curl -sf -X POST "$url" \
        -H "Authorization: token ${GITHUB_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        -o /dev/null
}

status_pending() {
    local sha=$1 context=$2 description=$3 url=$4 dry_run=${5:-}
    _github_status "pending" "$sha" "$context" "$description" "$url" "$dry_run"
}

status_success() {
    local sha=$1 context=$2 description=$3 url=$4 dry_run=${5:-}
    _github_status "success" "$sha" "$context" "$description" "$url" "$dry_run"
}

status_failure() {
    local sha=$1 context=$2 description=$3 url=$4 dry_run=${5:-}
    _github_status "failure" "$sha" "$context" "$description" "$url" "$dry_run"
}
