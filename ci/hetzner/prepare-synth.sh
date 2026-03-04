#!/bin/bash
# Generate synthetic merge commits: merge latest test improvements onto old SHAs.
#
# Usage:
#   bash prepare-synth.sh TEST_SHA SHA1 SHA2 ...
#   bash prepare-synth.sh TEST_SHA --set=safe          # use safe commit set from stress-test.sh
#
# Runs inside the container's /repo (full clone). No pushes to GitHub —
# synthetic SHAs are local-only. run-ci.sh's `git checkout SHA` works
# with local commits.
#
# Output: /opt/ci/synth-map.txt (OLD_SHA SYNTH_SHA per line)

set -uo pipefail

TEST_SHA=${1:?usage: prepare-synth.sh TEST_SHA [--set=safe|SHA1 SHA2 ...]}
shift

# ── Commit sets (mirrored from stress-test.sh) ──────────────────────────────

SAFE_COMMITS=(
    7b6a05c fcfe368 5ff4d6e 837654e f8a8b94 314e89f 8e9e1ed 1fccaba
    b7956f8 612e22f e392c78 6b9e695 6056636 ec68a78 2175249 fdbe325
)

# ── Parse args ───────────────────────────────────────────────────────────────

SHAS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --set=safe) SHAS=("${SAFE_COMMITS[@]}"); shift ;;
        *)          SHAS+=("$1"); shift ;;
    esac
done

if [[ ${#SHAS[@]} -eq 0 ]]; then
    echo "No SHAs specified. Use --set=safe or provide SHAs."
    exit 1
fi

# ── Files to take from TEST_SHA (theirs) on conflict ─────────────────────────

THEIRS_PATHS=(
    "packages/buckaroo-js-core/pw-tests/"
    "scripts/test_playwright_*.sh"
    "scripts/full_build.sh"
)

# ── Generate synthetic commits ───────────────────────────────────────────────

REPO_DIR=/repo
MAP_FILE=/opt/ci/synth-map.txt
> "$MAP_FILE"  # truncate

cd "$REPO_DIR"

# Ensure we have the test SHA
git fetch origin 2>/dev/null || true

total=${#SHAS[@]}
success=0
skipped=0

echo "Generating synthetic merges: $total SHAs × TEST_SHA=$TEST_SHA"
echo ""

for i in "${!SHAS[@]}"; do
    old_sha="${SHAS[$i]}"
    branch_name="synth/${old_sha}"
    idx=$((i + 1))

    echo "[$idx/$total] $old_sha ..."

    # Clean up any previous attempt
    git checkout -f HEAD 2>/dev/null || true
    git branch -D "$branch_name" 2>/dev/null || true

    # Create branch at old SHA
    if ! git checkout -b "$branch_name" "$old_sha" 2>/dev/null; then
        echo "  SKIP: cannot checkout $old_sha"
        ((skipped++))
        continue
    fi

    # Attempt merge
    if git merge --no-edit "$TEST_SHA" 2>/dev/null; then
        # Clean merge
        synth_sha=$(git rev-parse HEAD)
        echo "$old_sha $synth_sha" >> "$MAP_FILE"
        echo "  OK (clean merge) → ${synth_sha:0:10}"
        ((success++))
    else
        # Conflict — resolve with theirs for test files, ours for app code

        # Accept theirs for test-related paths
        for pattern in "${THEIRS_PATHS[@]}"; do
            # Use git checkout --theirs for conflicting files matching pattern
            git diff --name-only --diff-filter=U 2>/dev/null | grep -E "$pattern" | while read -r f; do
                git checkout --theirs "$f" 2>/dev/null && git add "$f" 2>/dev/null
            done
        done

        # Accept ours for everything else still conflicting
        git diff --name-only --diff-filter=U 2>/dev/null | while read -r f; do
            git checkout --ours "$f" 2>/dev/null && git add "$f" 2>/dev/null
        done

        # Check if all conflicts resolved
        if git diff --name-only --diff-filter=U 2>/dev/null | grep -q .; then
            echo "  SKIP: unresolvable conflicts"
            git merge --abort 2>/dev/null || true
            git checkout -f HEAD 2>/dev/null || true
            git branch -D "$branch_name" 2>/dev/null || true
            ((skipped++))
            continue
        fi

        # Commit the merge
        if git commit --no-edit -m "synth: merge $TEST_SHA onto $old_sha" 2>/dev/null; then
            synth_sha=$(git rev-parse HEAD)
            echo "$old_sha $synth_sha" >> "$MAP_FILE"
            echo "  OK (conflict resolved) → ${synth_sha:0:10}"
            ((success++))
        else
            echo "  SKIP: commit failed"
            git merge --abort 2>/dev/null || true
            git branch -D "$branch_name" 2>/dev/null || true
            ((skipped++))
        fi
    fi
done

# Return to detached HEAD so run-ci.sh works normally
git checkout -f HEAD 2>/dev/null || true

echo ""
echo "Done: $success merged, $skipped skipped out of $total"
echo "Map: $MAP_FILE"
cat "$MAP_FILE"
