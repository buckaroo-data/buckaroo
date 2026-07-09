#!/bin/bash
# Usage: bash scripts/ci_list_runs.sh <pr-number-or-branch>
#
# Lists all Checks workflow runs for a PR number or branch name.

set -euo pipefail

INPUT=$1

# If it's a number, treat as PR and get the branch
if [[ "$INPUT" =~ ^[0-9]+$ ]]; then
    BRANCH=$(gh pr view "$INPUT" --json headRefName -q '.headRefName')
    echo "PR #$INPUT → branch: $BRANCH"
else
    BRANCH="$INPUT"
    echo "Branch: $BRANCH"
fi

echo ""
gh run list --branch "$BRANCH" --workflow checks.yml --limit 20 \
    --json databaseId,status,conclusion,createdAt,updatedAt,event \
    -q '.[] | "\(.databaseId)\t\(.status)\t\(.conclusion // "-")\t\(.createdAt)\t\(.updatedAt)\t\(.event)"' | \
    column -t -s $'\t'
