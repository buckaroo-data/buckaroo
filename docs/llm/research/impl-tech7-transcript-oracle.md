# Tech 7: Synthetic Test Split (Transcript Oracle + Layer B)

**Goal:** Skip pw-jupyter entirely when Python output + JS code haven't changed
(cache hit → ~2s). On cache miss, Layer B gives fast signal (~10s) while full
pw-jupyter runs in parallel (~37s). Weighted average: **~16s** vs current 37s.

This is the most complex technique. Broken into three sub-tasks.

---

## Sub-task 7A: Transcript hash computation

### New file: `ci/hetzner/compute-transcript-hash.sh`

```bash
#!/bin/bash
# Compute content-addressed transcript hash for pw-jupyter oracle.
# Runs at t=0 alongside lint/build jobs.
set -euo pipefail

CACHE_DIR=/opt/ci/transcript-result-cache
HASH_FILE=/opt/ci/transcript-hashes.json
mkdir -p "$CACHE_DIR"

# JS hash: tree hash of packages/*/src/
JS_HASH=$(git ls-tree -r HEAD \
    packages/buckaroo-js-core/src/ \
    packages/buckaroo-js-core/pw-tests/ \
    2>/dev/null | sha256sum | cut -c1-16)

# Python transcript hash: instantiate widgets, hash their output
python3 - <<'PYEOF'
import json, hashlib, sys
sys.path.insert(0, '.')

from buckaroo import BuckarooWidget
import pandas as pd
try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False

datasets = {
    "test_buckaroo_widget": pd.DataFrame({"a": [1,2,3], "b": ["x","y","z"]}),
    "test_dfviewer": pd.DataFrame({"a": [1,2,3], "b": [4.0,5.0,6.0]}),
    # ... add all 9 notebook datasets ...
}
if HAS_POLARS:
    datasets["test_polars_dfviewer"] = pl.DataFrame({"a": [1,2,3], "b": ["x","y","z"]})

hashes = {}
for name, df in datasets.items():
    try:
        w = BuckarooWidget(df)
        blob = json.dumps(w.df_display_args, sort_keys=True, default=str)
        hashes[name] = hashlib.sha256(blob.encode()).hexdigest()[:16]
    except Exception as e:
        hashes[name] = f"ERROR:{e}"

combined = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
result = {"per_notebook": hashes, "combined": combined}
json.dump(result, open("/opt/ci/transcript-hashes.json", "w"), indent=2)
print(f"Transcript hash: {combined}")
PYEOF

echo "$JS_HASH" > /opt/ci/js-hash.txt
```

### New file: `ci/hetzner/check-transcript-cache.sh`

```bash
#!/bin/bash
# Check if (transcript_hash, js_hash) pair has a cached PASS result.
set -euo pipefail

CACHE_DIR=/opt/ci/transcript-result-cache

T_HASH=$(python3 -c "import json; print(json.load(open('/opt/ci/transcript-hashes.json'))['combined'])")
J_HASH=$(cat /opt/ci/js-hash.txt)
CACHE_KEY="${T_HASH}-${J_HASH}"

if [[ -f "$CACHE_DIR/$CACHE_KEY.result" ]]; then
    RESULT=$(cat "$CACHE_DIR/$CACHE_KEY.result")
    echo "CACHE HIT: ($T_HASH, $J_HASH) -> $RESULT"
    exit 0  # cache hit
else
    echo "CACHE MISS: ($T_HASH, $J_HASH)"
    exit 1  # cache miss
fi
```

### Modify `run_dag()` in `run-ci.sh`

Add transcript hash computation at t=0, and cache check before pw-jupyter:

```bash
# At t=0 (Wave 0), alongside lint/build:
run_job transcript-hash bash "$CI_RUNNER_DIR/compute-transcript-hash.sh" & PID_THASH=$!

# Before starting pw-jupyter:
wait $PID_THASH || true  # transcript hash needed for cache check

local pw_skip=0
if bash "$CI_RUNNER_DIR/check-transcript-cache.sh"; then
    log "SKIP playwright-jupyter (transcript+JS cache hit)"
    pw_skip=1
fi

if [[ $pw_skip -eq 0 ]]; then
    run_job playwright-jupyter job_playwright_jupyter_warm & PID_PW_JP=$!
else
    PID_PW_JP=""
fi

# After pw-jupyter completes (if it ran):
if [[ -n "$PID_PW_JP" ]]; then
    wait $PID_PW_JP || OVERALL=1
    # Store result in cache
    T_HASH=$(python3 -c "import json; print(json.load(open('/opt/ci/transcript-hashes.json'))['combined'])")
    J_HASH=$(cat /opt/ci/js-hash.txt)
    if [[ $OVERALL -eq 0 ]]; then
        echo "PASS" > "/opt/ci/transcript-result-cache/${T_HASH}-${J_HASH}.result"
    else
        echo "FAIL" > "/opt/ci/transcript-result-cache/${T_HASH}-${J_HASH}.result"
    fi
fi
```

---

## Sub-task 7B: Layer A — Python transcript snapshot tests

### New file: `tests/unit/test_transcript_snapshots.py`

```python
"""Capture widget transcripts and compare against golden snapshots.

These tests verify that Python produces the correct output for each notebook
dataset, without a browser. Runs in ~1s total.
"""
import json
import hashlib
import pytest
from unittest.mock import patch
from buckaroo import BuckarooWidget
import pandas as pd

DATASETS = {
    "test_buckaroo_widget": lambda: pd.DataFrame({"a": [1,2,3], "b": ["x","y","z"]}),
    "test_dfviewer": lambda: pd.DataFrame({"a": [1,2,3], "b": [4.0,5.0,6.0]}),
    # ... fill in all 9 notebook datasets ...
}

def capture_transcript(df, **kwargs):
    sent_messages = []
    with patch.object(BuckarooWidget, 'send',
                      lambda self, msg, buffers=None:
                      sent_messages.append({"msg": msg, "has_buffers": buffers is not None})):
        widget = BuckarooWidget(df, **kwargs)
    return {
        "df_display_args": widget.df_display_args,
        "buckaroo_state": widget.buckaroo_state,
        "sent_count": len(sent_messages),
    }

@pytest.mark.parametrize("name,df_factory", list(DATASETS.items()))
def test_transcript_snapshot(name, df_factory, snapshot):
    transcript = capture_transcript(df_factory())
    # Use syrupy or pytest-snapshot for golden comparison
    assert transcript == snapshot
```

---

## Sub-task 7C: Layer B — Storybook transcript replay

### New Playwright spec: `packages/buckaroo-js-core/pw-tests/transcript-replay-from-snapshot.spec.ts`

```typescript
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { waitForCells } from './ag-pw-utils';

const SNAPSHOT_DIR = path.resolve(__dirname, '../../../tests/unit/snapshots/transcripts');

// Only run if snapshot dir exists
const snapshotFiles = fs.existsSync(SNAPSHOT_DIR)
    ? fs.readdirSync(SNAPSHOT_DIR).filter(f => f.endsWith('.json'))
    : [];

for (const file of snapshotFiles) {
    const transcript = JSON.parse(fs.readFileSync(path.join(SNAPSHOT_DIR, file), 'utf-8'));

    test(`replay: ${file}`, async ({ page }) => {
        await page.addInitScript((t) => {
            (window as any)._buckarooTranscript = t;
        }, transcript.js_events);

        await page.goto(
            'http://localhost:6006/iframe.html?id=buckaroo-dfviewer-pinnedrowstranscriptreplayer--primary'
        );
        await waitForCells(page);

        const startButton = page.getByRole('button', { name: 'Start Replay' });
        await startButton.click();
        await page.waitForTimeout(500);

        const rowCount = await page.locator('.ag-row').count();
        expect(rowCount).toBeGreaterThan(0);
    });
}
```

---

## Validation

1. **7A:** Run transcript hash computation. Verify it produces consistent hashes
   for same code. Verify hash changes when widget logic changes.
2. **7B:** Run `pytest tests/unit/test_transcript_snapshots.py`. Generate golden
   snapshots. Modify widget code, verify test fails.
3. **7C:** Run replay tests against Storybook. Verify cells render.
4. **End-to-end:** Run CI twice with no widget/JS changes. Second run should skip
   pw-jupyter (cache hit).

## Risks

- **Transcript format drift:** Internal refactors silently invalidate all snapshots.
  Mitigation: version the snapshot format.
- **Dataset mismatch:** The CI transcript hash uses simplified test datasets that may
  not match the actual notebook datasets. Must use identical data.
- **False cache hit:** If transcript hash doesn't capture all relevant state (e.g.,
  missing `send()` payloads), a change could slip through. Start conservative —
  hash everything.
