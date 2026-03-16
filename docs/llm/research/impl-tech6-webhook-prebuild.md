# Tech 6: Speculative Pre-Build on Push Webhook

**Goal:** Move `git fetch` + `git checkout` + (optionally) JS build before `run-ci.sh`
is formally called. Saves **2-3s** on every run, up to **15s** on JS-cache-miss runs.

---

## What changes

### 1. Modify `ci/hetzner/webhook.py`

Currently webhook.py receives the push event and calls `run-ci.sh`. Add a pre-build
step between receiving the webhook and calling run-ci:

```python
# In webhook handler, before launching run-ci.sh:
def on_push(sha, branch):
    # Speculative pre-build (runs before run-ci.sh)
    subprocess.run([
        'docker', 'exec', 'buckaroo-ci', 'bash', '-c',
        f'cd /repo && git fetch origin && git checkout -f {sha} && '
        f'git clean -fdx --exclude=packages/*/node_modules && '
        f'echo {sha} > /opt/ci/prewarm-ready'
    ], timeout=30)

    # Now run CI (which checks for prewarm-ready)
    subprocess.Popen([
        'docker', 'exec', '-e', f'GITHUB_TOKEN={token}',
        'buckaroo-ci', 'bash', '/opt/ci-runner/run-ci.sh', sha, branch
    ])
```

### 2. Modify `run-ci.sh` — check for pre-warmed checkout

After the checkout section (~line 278):
```bash
# Check if webhook already did the checkout
if [[ -f /opt/ci/prewarm-ready ]] && [[ "$(cat /opt/ci/prewarm-ready)" == "$SHA" ]]; then
    log "Using pre-warmed checkout for $SHA"
    rm -f /opt/ci/prewarm-ready
else
    git fetch origin
    git checkout -f "$SHA"
    git clean -fdx \
        --exclude='packages/buckaroo-js-core/node_modules' \
        --exclude='packages/js/node_modules' \
        --exclude='packages/node_modules'
fi
```

---

## Validation

1. Trigger via webhook. Verify git fetch happens before run-ci.sh.
2. Verify SHA mismatch (rapid pushes) falls back to full checkout.
3. Time savings: compare total CI time with/without pre-warm.

## Risks

- Rapid successive pushes: SHA X pre-build, then SHA Y arrives before X's CI starts.
  Pre-build for X is wasted, Y does a full checkout. Harmless but no savings.
- Pre-build failure (network, disk): run-ci.sh falls back to full checkout. Safe.
