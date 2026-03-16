#!/bin/bash
# Create synthetic merge commits locally: overlay test infra from a TEST_SHA
# onto each old SHA, then push the branches so SHAs are available on origin.
#
# Strategy:
#   - Start from old SHA
#   - Overlay test infra files from TEST_SHA (ci/, scripts/, pw-tests/)
#   - Create a merge commit with both parents for traceability
#
# Usage:
#   bash ci/hetzner/create-merge-commits.sh                # all sets
#   bash ci/hetzner/create-merge-commits.sh --set=new      # new (50 deeper) commits only
#   bash ci/hetzner/create-merge-commits.sh --set=safe     # safe commits only
#
# After running, push branches:
#   git push origin 'refs/heads/synth/*'
#
# Then paste the mapping output into stress-test.sh commit arrays.

set -uo pipefail

TEST_SHA=031c787e
ORIG_BRANCH=$(git rev-parse --abbrev-ref HEAD)
COMMIT_SET="all"

for arg in "$@"; do
    case "$arg" in
        --set=*) COMMIT_SET="${arg#*=}" ;;
    esac
done

# All commits from stress-test.sh (original SHAs)
SAFE_COMMITS=(
    7b6a05c fcfe368 5ff4d6e 837654e f8a8b94 314e89f 8e9e1ed 1fccaba
    b7956f8 612e22f e392c78 6b9e695 6056636 ec68a78 2175249 fdbe325
)

FAILING_COMMITS=(
    cf7e02a e0f358a 7b3141c 703c034 db1ca96 4ddcac1 7d8b751 b1eb6a5
    1839f59 88a8743 2bec338 c8e98d3 7b9c341 516a1fa f01c9c6
)

OLDER_COMMITS=(
    f10ee77 3bb6d71 8623244 5c3f861 e2f610f ae9006d 5f20962 dbac567
    fa011f8 25d674b 79da494 2ea8866 14ec761 af9fa79 9693b9b 23e3096
)

# 50 deeper commits (after fdbe325) for expanded stress testing
NEW_COMMITS=(
    5170fa2 aab8b96 c307fb3 66b7b4c f2ad09d 366389b a918c09 094a90a
    b8f0900 bb38628 6ff2b56 1b0a782 7b43be4 5ac690b 36dabd5 cb77802
    8897a64 7545a24 eb08afb 25492e7 8dcdb33 7c3e07d aacc4d3 fc56645
    74d55a4 27eb8f5 1dcb47f c0635af 3f56728 f2f06a2 b4d32c0 f1e45dd
    f4ac6a6 d0a4277 135754a af585ec c7ba883 7e6392e 3190319 14b00ed
    a27a2b7 87c2957 6bfdb18 bc9a06c 14f5ad7 e5d78bd f38e56e af17de6
    0f31209 7806961
)

case "$COMMIT_SET" in
    safe)    ALL_COMMITS=("${SAFE_COMMITS[@]}") ;;
    failing) ALL_COMMITS=("${FAILING_COMMITS[@]}") ;;
    older)   ALL_COMMITS=("${OLDER_COMMITS[@]}") ;;
    new)     ALL_COMMITS=("${NEW_COMMITS[@]}") ;;
    all)     ALL_COMMITS=("${SAFE_COMMITS[@]}" "${FAILING_COMMITS[@]}" "${OLDER_COMMITS[@]}" "${NEW_COMMITS[@]}") ;;
    *)       echo "Unknown --set value: $COMMIT_SET (use safe|failing|older|new|all)"; exit 1 ;;
esac

# Paths to overlay from TEST_SHA (test infrastructure)
OVERLAY_PATHS=(
    ci/hetzner/
    packages/buckaroo-js-core/pw-tests/
    packages/buckaroo-js-core/playwright.config.marimo.ts
    packages/buckaroo-js-core/playwright.config.wasm-marimo.ts
    packages/buckaroo-js-core/playwright.config.server.ts
    packages/buckaroo-js-core/playwright.config.ts
    scripts/test_playwright_jupyter_parallel.sh
    scripts/test_playwright_marimo.sh
    scripts/test_playwright_screenshots.sh
    scripts/test_playwright_server.sh
    scripts/test_playwright_wasm_marimo.sh
    scripts/full_build.sh
    scripts/smoke_test.py
    scripts/serve-wasm-marimo.sh
)

total=${#ALL_COMMITS[@]}
success=0
skipped=0

echo "Creating $total synthetic commits: old SHA + test infra from $TEST_SHA"
echo ""

MAPPING=()

for i in "${!ALL_COMMITS[@]}"; do
    old_sha="${ALL_COMMITS[$i]}"
    branch_name="synth/${old_sha}"
    idx=$((i + 1))

    echo -n "[$idx/$total] $old_sha ... "

    # Skip if synth branch already exists on origin
    if git rev-parse --verify "origin/$branch_name" >/dev/null 2>&1; then
        merge_sha=$(git rev-parse --short "origin/$branch_name")
        MAPPING+=("$old_sha $merge_sha")
        echo "EXISTS → $merge_sha"
        ((success++))
        continue
    fi

    # Clean up any previous attempt
    git checkout -f "$ORIG_BRANCH" 2>/dev/null || true
    git branch -D "$branch_name" 2>/dev/null || true

    # Create branch at old SHA
    if ! git checkout -b "$branch_name" "$old_sha" 2>/dev/null; then
        echo "SKIP (cannot checkout)"
        ((skipped++))
        continue
    fi

    # Overlay test infra files from TEST_SHA
    for path in "${OVERLAY_PATHS[@]}"; do
        git checkout "$TEST_SHA" -- "$path" 2>/dev/null || true
    done

    # Stage everything
    git add -A 2>/dev/null

    # Check if there are actually changes to commit
    if git diff --cached --quiet 2>/dev/null; then
        echo "SKIP (no changes needed)"
        git checkout -f "$ORIG_BRANCH" 2>/dev/null || true
        git branch -D "$branch_name" 2>/dev/null || true
        ((skipped++))
        continue
    fi

    # Create a merge commit with both parents for traceability
    tree=$(git write-tree)
    merge_sha_full=$(git commit-tree "$tree" -p "$old_sha" -p "$TEST_SHA" \
        -m "synth: overlay test infra from $TEST_SHA onto $old_sha")

    # Update branch to point to the merge commit
    git reset --hard "$merge_sha_full" 2>/dev/null

    merge_sha=$(git rev-parse --short HEAD)
    MAPPING+=("$old_sha $merge_sha")
    echo "OK → $merge_sha"
    ((success++))
done

# Return to original branch
git checkout -f "$ORIG_BRANCH" 2>/dev/null

echo ""
echo "Done: $success created, $skipped skipped out of $total"
echo ""
echo "═══ Mapping (old_sha → merge_sha) ═══"
for entry in "${MAPPING[@]}"; do
    echo "$entry"
done

echo ""
echo "To push: git push origin 'refs/heads/synth/*'"
