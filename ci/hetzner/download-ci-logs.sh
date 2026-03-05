#!/bin/bash
# Download GitHub Actions CI logs for all stress-test commits.
#
# Usage:
#   bash ci/hetzner/download-ci-logs.sh                  # all sets
#   bash ci/hetzner/download-ci-logs.sh --set=safe        # just safe commits
#   bash ci/hetzner/download-ci-logs.sh --set=failing     # just failing commits
#   bash ci/hetzner/download-ci-logs.sh --set=older       # just older commits
#   bash ci/hetzner/download-ci-logs.sh <sha1> <sha2> ... # specific SHAs
#
# Downloads to: ci-logs/<short-sha>/checks.log
# Each log file contains the full text output from the "Checks" workflow run.

set -uo pipefail

REPO="buckaroo-data/buckaroo"
OUTDIR="ci-logs"
COMMIT_SET="all"
CUSTOM_SHAS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --set=*)   COMMIT_SET="${1#*=}"; shift ;;
        --set)     COMMIT_SET="$2"; shift 2 ;;
        --outdir=*) OUTDIR="${1#*=}"; shift ;;
        --outdir)  OUTDIR="$2"; shift 2 ;;
        *)         CUSTOM_SHAS+=("$1"); shift ;;
    esac
done

# ── Same commit arrays as stress-test.sh ──────────────────────────────────────

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

if [[ ${#CUSTOM_SHAS[@]} -gt 0 ]]; then
    COMMITS=("${CUSTOM_SHAS[@]}")
else
    case "$COMMIT_SET" in
        safe)    COMMITS=("${SAFE_COMMITS[@]}") ;;
        failing) COMMITS=("${FAILING_COMMITS[@]}") ;;
        older)   COMMITS=("${OLDER_COMMITS[@]}") ;;
        all)     COMMITS=("${SAFE_COMMITS[@]}" "${FAILING_COMMITS[@]}" "${OLDER_COMMITS[@]}") ;;
        *)       echo "Unknown --set: $COMMIT_SET (use safe|failing|older|all)"; exit 1 ;;
    esac
fi

TOTAL=${#COMMITS[@]}
mkdir -p "$OUTDIR"

echo "Downloading CI logs for $TOTAL commits → $OUTDIR/"
echo ""

DOWNLOADED=0
SKIPPED=0
NO_RUNS=0

for i in "${!COMMITS[@]}"; do
    sha="${COMMITS[$i]}"
    dir="$OUTDIR/$sha"
    log="$dir/checks.log"

    printf "[%d/%d] %s " "$((i+1))" "$TOTAL" "$sha"

    # Skip if already downloaded (real logs only, not placeholder files)
    if [[ -f "$log" && -s "$log" ]] && ! head -1 "$log" | grep -qE '^(NO_CHECKS_RUN|DOWNLOAD_FAILED)'; then
        echo "  (cached)"
        ((SKIPPED++))
        continue
    fi

    mkdir -p "$dir"

    # Find the CI workflow run for this commit.
    # Workflow was renamed over time: "CI" → "Build" → "Checks".
    # check-runs API gives us details_url containing the run ID.
    run_ids=$(
        gh api "repos/$REPO/commits/$sha/check-runs" \
            -q '.check_runs[].details_url' 2>/dev/null \
        | sed 's|.*/runs/||;s|/.*||' \
        | sort -u
    )

    run_id=""
    # Prefer "Checks" (current), fall back to "CI" or "Build" (older)
    for rid in $run_ids; do
        name=$(gh api "repos/$REPO/actions/runs/$rid" -q '.name' 2>/dev/null)
        case "$name" in
            Checks) run_id="$rid"; break ;;
            CI)     [[ -z "$run_id" ]] && run_id="$rid" ;;
            Build)  [[ -z "$run_id" ]] && run_id="$rid" ;;
        esac
    done

    if [[ -z "$run_id" ]]; then
        echo "  (no Checks run found)"
        echo "NO_CHECKS_RUN" > "$dir/checks.log"
        ((NO_RUNS++))
        continue
    fi

    # Download text logs
    if gh run view "$run_id" --repo "$REPO" --log > "$log" 2>/dev/null; then
        lines=$(wc -l < "$log" | tr -d ' ')
        echo "  run=$run_id  ${lines} lines"
        ((DOWNLOADED++))
    else
        echo "  (log download failed for run $run_id)"
        echo "DOWNLOAD_FAILED run=$run_id" > "$log"
        ((NO_RUNS++))
    fi

    # Also save per-job summary
    gh run view "$run_id" --repo "$REPO" \
        --json jobs -q '.jobs[] | "\(.name)\t\(.conclusion)\t\(.startedAt)\t\(.completedAt)"' \
        > "$dir/jobs.tsv" 2>/dev/null || true
done

echo ""
echo "═══════════════════════════════════════"
echo "  Downloaded: $DOWNLOADED"
echo "  Cached:     $SKIPPED"
echo "  No runs:    $NO_RUNS"
echo "  Total:      $TOTAL"
echo "  Output:     $OUTDIR/"
echo "═══════════════════════════════════════"
