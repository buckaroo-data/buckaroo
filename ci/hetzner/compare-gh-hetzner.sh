#!/bin/bash
# Compare Hetzner CI results with GitHub Actions for the same original SHAs.
#
# For each synth commit in a stress test set, looks up the original SHA,
# queries GitHub CI status for that SHA, and builds a comparison table.
#
# Usage:
#   bash ci/hetzner/compare-gh-hetzner.sh --set=safe
#   bash ci/hetzner/compare-gh-hetzner.sh --set=new --stress-dir=/opt/ci/logs/stress-run-ci-new

set -uo pipefail

SERVER=${HETZNER_SERVER:-root@137.220.56.81}
COMMIT_SET="safe"
STRESS_DIR=""

for arg in "$@"; do
    case "$arg" in
        --set=*)        COMMIT_SET="${arg#*=}" ;;
        --stress-dir=*) STRESS_DIR="${arg#*=}" ;;
    esac
done

if [[ -z "$STRESS_DIR" ]]; then
    STRESS_DIR="/opt/ci/logs/stress-run-ci-${COMMIT_SET}"
fi

# Mapping: synth SHA → original SHA (from create-merge-commits.sh / stress-test.sh)
# We parse the stress-test.sh file itself for the comments
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Hetzner vs GitHub CI comparison — set=$COMMIT_SET"
echo "  Stress dir: $STRESS_DIR"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Extract the mapping from stress-test.sh comments
# Format in file: "    merge_sha   # orig_sha description"
python3 -c "
import re, subprocess, json, sys

# Parse stress-test.sh for commit mappings
with open('$SCRIPT_DIR/stress-test.sh') as f:
    content = f.read()

# Find the right array block based on set name
set_name = '$COMMIT_SET'.upper()
if set_name == 'NEW':
    pattern = r'NEW_COMMITS=\((.*?)\)'
elif set_name == 'SAFE':
    pattern = r'SAFE_COMMITS=\((.*?)\)'
elif set_name == 'FAILING':
    pattern = r'FAILING_COMMITS=\((.*?)\)'
elif set_name == 'OLDER':
    pattern = r'OLDER_COMMITS=\((.*?)\)'
else:
    print(f'Unknown set: $COMMIT_SET', file=sys.stderr)
    sys.exit(1)

m = re.search(pattern, content, re.DOTALL)
if not m:
    print(f'Could not find {set_name}_COMMITS array', file=sys.stderr)
    sys.exit(1)

block = m.group(1)
mappings = []
for line in block.strip().split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    # Format: merge_sha   # orig_sha description
    match = re.match(r'(\w+)\s+#\s+(\w+)\s+(.*)', line)
    if match:
        merge_sha, orig_sha, desc = match.groups()
        mappings.append((merge_sha, orig_sha, desc.strip()))

if not mappings:
    print('No mappings found — is the array populated?', file=sys.stderr)
    sys.exit(1)

print(f'Found {len(mappings)} commits to compare')
print()
print(f'{\"Orig SHA\":>10}  {\"Synth SHA\":>10}  {\"GH CI\":>8}  {\"Hetzner\":>8}  Description')
print(f'{\"─\"*10}  {\"─\"*10}  {\"─\"*8}  {\"─\"*8}  {\"─\"*40}')

for merge_sha, orig_sha, desc in mappings:
    # Query GitHub CI for original SHA
    try:
        result = subprocess.run(
            ['gh', 'api', f'repos/buckaroo-data/buckaroo/commits/{orig_sha}/check-suites',
             '--jq', '.check_suites[0].conclusion // \"none\"'],
            capture_output=True, text=True, timeout=10
        )
        gh_status = result.stdout.strip() or 'none'
    except Exception:
        gh_status = 'error'

    # Query Hetzner result from stress test summary
    try:
        result = subprocess.run(
            ['ssh', '$SERVER',
             f'grep -m1 \"^{merge_sha}\" $STRESS_DIR/summary.txt 2>/dev/null || echo \"{merge_sha} UNKNOWN\"'],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
        )
        parts = result.stdout.strip().split()
        hz_status = parts[1] if len(parts) > 1 else 'UNKNOWN'
    except Exception:
        hz_status = 'error'

    gh_short = gh_status[:8]
    hz_short = hz_status[:8]
    desc_short = desc[:40]
    print(f'{orig_sha:>10}  {merge_sha:>10}  {gh_short:>8}  {hz_short:>8}  {desc_short}')
"
