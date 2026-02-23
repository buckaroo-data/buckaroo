#!/usr/bin/env bash
# Download height-mode CI screenshots and serve the comparison page locally.
#
# Usage:
#   bash scripts/serve_height_comparison.sh [--port PORT] [--run-id RUN_ID] [--branch BRANCH]
#
# Requires: gh (GitHub CLI), python3

set -euo pipefail

PORT=8787
RUN_ID=""
BRANCH="worktree-height-fix"
ARTIFACT_NAME="height-mode-screenshots"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)    PORT="$2"; shift 2 ;;
    --run-id)  RUN_ID="$2"; shift 2 ;;
    --branch)  BRANCH="$2"; shift 2 ;;
    *)         echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Ensure gh is available
if ! command -v gh &>/dev/null; then
  echo "Error: GitHub CLI (gh) is required. Install it: https://cli.github.com/"
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'echo "Serving dir left at: $TMPDIR"' EXIT

echo "==> Downloading artifact '${ARTIFACT_NAME}' from branch '${BRANCH}'..."

if [[ -n "$RUN_ID" ]]; then
  gh run download "$RUN_ID" --name "$ARTIFACT_NAME" --dir "$TMPDIR"
else
  # Find latest completed run on the branch
  RUN_ID=$(gh run list --branch "$BRANCH" --workflow Checks --status completed --limit 1 --json databaseId --jq '.[0].databaseId')
  if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
    echo "Error: No completed CI run found on branch '${BRANCH}'."
    echo "Push to the branch first and wait for CI to finish."
    exit 1
  fi
  echo "    Using run ID: ${RUN_ID}"
  gh run download "$RUN_ID" --name "$ARTIFACT_NAME" --dir "$TMPDIR"
fi

echo "==> Downloaded to ${TMPDIR}"
echo "    Contents:"
ls -R "$TMPDIR"

# Verify key files exist
if [[ ! -f "$TMPDIR/pw-tests/screenshot-compare.html" ]]; then
  # Try flat layout (artifact may strip prefix)
  if [[ -f "$TMPDIR/screenshot-compare.html" ]]; then
    mkdir -p "$TMPDIR/pw-tests"
    mv "$TMPDIR/screenshot-compare.html" "$TMPDIR/pw-tests/"
  else
    echo "Warning: screenshot-compare.html not found in artifact"
  fi
fi

if [[ ! -d "$TMPDIR/screenshots/height-mode" ]]; then
  # Check if height-mode is at root level
  if ls "$TMPDIR"/*.png &>/dev/null; then
    mkdir -p "$TMPDIR/screenshots/height-mode"
    mv "$TMPDIR"/*.png "$TMPDIR/screenshots/height-mode/"
    [[ -f "$TMPDIR/manifest.json" ]] && mv "$TMPDIR/manifest.json" "$TMPDIR/screenshots/height-mode/"
  fi
fi

URL="http://localhost:${PORT}/pw-tests/screenshot-compare.html"

echo ""
echo "==> Starting server on port ${PORT}"
echo "    ${URL}"
echo "    Press Ctrl+C to stop."
echo ""

# Auto-open in browser (macOS / Linux)
(sleep 1 && {
  if command -v open &>/dev/null; then
    open "$URL"
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
  fi
}) &

cd "$TMPDIR"
python3 -m http.server "$PORT"
