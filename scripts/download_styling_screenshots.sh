#!/usr/bin/env bash
# Download before/after styling screenshots from a CI run.
#
# Usage:
#   ./scripts/download_styling_screenshots.sh [run-id]
#
# If run-id is omitted, uses the latest successful run of checks.yml
# on the current branch.

set -e

REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
BRANCH=$(git rev-parse --abbrev-ref HEAD)
RUN_ID=${1:-}

if [ -z "$RUN_ID" ]; then
  echo "Looking up latest successful run on branch '$BRANCH'..."
  RUN_ID=$(gh run list \
    --repo "$REPO" \
    --branch "$BRANCH" \
    --workflow checks.yml \
    --status success \
    --limit 1 \
    --json databaseId \
    -q '.[0].databaseId')

  if [ -z "$RUN_ID" ]; then
    echo "No successful run found for branch '$BRANCH'. Try passing a run-id directly."
    exit 1
  fi
fi

echo "Downloading screenshots from run $RUN_ID (repo: $REPO)"

OUT_DIR="packages/buckaroo-js-core/screenshots"
mkdir -p "$OUT_DIR"

gh run download "$RUN_ID" \
  --repo "$REPO" \
  --name styling-screenshots-before \
  --dir "$OUT_DIR/before"

gh run download "$RUN_ID" \
  --repo "$REPO" \
  --name styling-screenshots-after \
  --dir "$OUT_DIR/after"

BEFORE=$(ls -1 "$OUT_DIR/before"/*.png 2>/dev/null | wc -l | tr -d ' ')
AFTER=$(ls -1 "$OUT_DIR/after"/*.png 2>/dev/null | wc -l | tr -d ' ')
echo "Downloaded: $BEFORE before screenshots, $AFTER after screenshots"
echo ""
echo "Next step:"
echo "  python scripts/gen_screenshot_compare.py && open packages/buckaroo-js-core/screenshots/compare.html"
