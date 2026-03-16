# Hetzner CI — Implementation Notes

Lessons learned across all runs. Companion to `hetzner-ci-bringup.md`.

---

## Architecture Decisions That Worked

### Warm sidecar container
Running `docker exec` into an always-on container is dramatically better than
`docker run` per CI job. The venvs and pnpm store persist in the container for
the lifetime of the deployment; no layer caching needed.

### Bake CI scripts into the image at `/opt/ci-runner/`
`run-ci.sh` checks out arbitrary SHAs with `git checkout -f $SHA`. Any file that
lives only in `/repo/ci/hetzner/` will be wiped when the checked-out SHA predates
the CI branch. Copying scripts to `/opt/ci-runner/` at image build time gives
them a stable path that survives the checkout.

Rule: **any file called from within `run-ci.sh` must live in `/opt/ci-runner/`**,
not in `/repo/scripts/`. This burned us three times (run-ci.sh itself, lib/,
and test_playwright_jupyter_parallel.sh).

### One venv per Python version at `/opt/venvs/3.11-3.14/`
Pre-populated with all deps at image build time. `uv sync` at runtime only
installs the project itself (editable), which is nearly instant. This is the
main reason Phase 1/3 are fast.

### `UV_PROJECT_ENVIRONMENT` to prevent `.venv` creation races
When two jobs both call `uv run` or `uv sync` without this env var set, they
race to create/modify `/repo/.venv`. Set `UV_PROJECT_ENVIRONMENT=/opt/venvs/3.13`
for any job that needs to use the shared venv.

### Per-job `PLAYWRIGHT_HTML_OUTPUT_DIR`
All playwright configs default to writing HTML reports to `playwright-report/`
in the working dir. When playwright jobs run in parallel they stomp each other.
Set `PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/pw-html-<name>-$$` per job.

### Isolated venv for playwright-jupyter
`job_playwright_jupyter` creates `/tmp/ci-jupyter-$$` and installs
`buckaroo + polars + jupyterlab` there. This avoids pip-reinstalling into the
shared 3.13 venv while marimo/wasm-marimo are reading from it in parallel.

---

## Parallelisation Wins

| Change | Saved | Total after |
|--------|-------|-------------|
| Baseline (cold, sequential) | — | 8m59s |
| Warm caches | ~36s | 8m23s |
| Phase 3 parallel (3.11/3.12/3.14) | ~1m07s | 7m21s |
| Phase 5 parallel (5× playwright) | ~2m20s | 4m58s |
| Phase 5 split + parallel jupyter (PARALLEL=1) | ~1m04s | **3m56s** |
| Phase 5b PARALLEL=3 (tested, fails) | — | worse |

Run 26 (commit 1759612, warm caches):
- Phase 1: 1m15s | Phase 2: 22s | Phase 3: 1m16s | Phase 4: 20s
- Phase 5a: 59s | Phase 5b: 1m44s (9 notebooks, PARALLEL=1)
- **Total: 5m56s**

**Critical path** after all parallelisation:
`test-js (~24s) → build-wheel (~22s) → playwright-jupyter (~104s) ≈ 2m30s`

Nothing else can beat this without shortening playwright-jupyter or decoupling
build-wheel from test-js. Next opportunity: PARALLEL=3 for Phase 5b (requires
CPU headroom after Phase 5a completes — currently untested but likely viable).

### Why CCX43 didn't help
Upgrading from CCX33 (8 vCPU) to CCX43 (16 vCPU) gave identical timing
(~5m05s vs ~4m58s). The bottleneck is the sequential critical path, not CPU
core count. More cores only help if there's parallelisable work waiting on them.

### Why PARALLEL=3 fails even after Phase 5a (batch-1 timing)
PARALLEL=3 launches 3 notebooks in batch 1: 3 browsers + 3 fresh kernels + a
freshly-started JupyterLab all compete for CPU simultaneously. The Playwright
spec's 1.3s static wait (`waitForTimeout(800)` + `waitForTimeout(500)`) fires
before widgets render → 6/9 failures. The first batch is the dangerous one
because JupyterLab itself is still initialising. Batches 2+ would likely be
fine, but we can't skip batch 1. PARALLEL=1 is the only safe value until the
Playwright spec is updated to use proper `waitFor` instead of fixed timeouts.

### Why high Jupyter parallelism fails (when 5a is concurrent)
Running 9 (or even 3) Jupyter notebooks in parallel while the other 4 playwright
jobs are also running causes `tornado.iostream.StreamClosedError` — JupyterLab's
WebSocket connections drop under CPU load. The widget comm channels never
establish, giving "Comm not found" and "Widget failed to render: 0 elements."
Fix: run the 4 non-Jupyter playwright tests first (Phase 5a, ~60s), then run
Jupyter with PARALLEL=1+ after CPU is free (Phase 5b). PARALLEL=3 expected to
be viable since the system is idle during Phase 5b.

### Why the DAG approach failed
Running all independent jobs simultaneously (9 concurrent on 8 vCPUs) caused:
- CPU saturation → forkserver tests hit hardcoded 1s timeouts
- playwright-marimo server too slow to start → 6-minute hang
The phased approach (P1→P2→P3→P4→P5) naturally throttles concurrency.

---

## Bugs That Will Bite You Again

### `((x++))` with `set -e` exits on zero result
`(( expression ))` returns exit code 1 when the expression evaluates to 0.
With `set -e`, `((NEXT++))` when `NEXT=0` kills the script after the first
background job launches. This burned us: one notebook started, cleanup trap
fired, JupyterLab was killed. Fix: `((NEXT++)) || true` for all arithmetic
that can evaluate to 0.

### `cd "$(dirname "$0")/.."` breaks when called from `/opt/ci-runner/`
Already documented above — same pattern also hit `test_playwright_jupyter_parallel.sh`.

### Linux `mktemp` needs explicit X's
`mktemp -d -t prefix` fails on Linux ("too few X's"). Use `mktemp -d -t prefixXXXXXX`.

### `rm -rf` masking exit codes
```bash
job_foo() {
    local venv=/tmp/foo-$$
    uv venv "$venv"
    run_tests "$venv"   # ← if this fails...
    rm -rf "$venv"      # ← ...this succeeds, and job returns 0
}
```
Always capture the exit code explicitly before cleanup:
```bash
    local rc=0
    run_tests "$venv" || rc=$?
    rm -rf "$venv"
    return $rc
```

### `cd "$(dirname "$0")/.."` breaks when called from `/opt/ci-runner/`
Scripts that use this pattern to find the repo root will navigate to `/opt`
when called as `bash /opt/ci-runner/script.sh`. Fix: respect `ROOT_DIR` if set:
```bash
if [ -z "${ROOT_DIR:-}" ]; then
    cd "$(dirname "$0")/.."
    ROOT_DIR="$(pwd)"
fi
cd "$ROOT_DIR"
```
Then callers set `ROOT_DIR=/repo`.

### Linux `mktemp -d -t` requires explicit X's
`mktemp -d -t pw-jupyter-parallel` fails on Linux with "too few X's".
macOS silently appends the random suffix. Use:
```bash
mktemp -d -t pw-jupyter-parallelXXXXXX
```

### JupyterLab 4.x blocks widget rendering for untrusted notebooks
Freshly copied `.ipynb` files have no trust signature. JupyterLab 4.x
refuses to render widget JavaScript (anywidget's embedded `_esm`) for
untrusted notebooks — even for newly-executed live outputs. All 9
notebooks fail with "Widget failed to render: 0 elements".

Fix: run `jupyter trust "$nb"` for every notebook after copying it, before
starting Playwright tests. This adds the notebook's hash to
`~/.local/share/jupyter/nbsignatures.db`, which JupyterLab checks when
opening the notebook.

### `shutdown_kernels` JSON parsing — `"id":"uuid"` vs `"id": "uuid"`
`grep -o '"id":"[^"]*"'` requires no space between the colon and the
opening quote. JupyterLab's `/api/kernels` response returns
`"id": "uuid"` (with a space), so the grep never matches. Result: every
batch call to `shutdown_kernels` silently does nothing — kernels
accumulate throughout the test run, consuming memory and causing
JupyterLab to reconnect old sessions on each new Playwright test.

Fix: extract UUIDs with the UUID pattern instead:
```bash
grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
```

### JupyterLab workspace state restored across Playwright sessions
Even in Playwright's `--incognito` mode, JupyterLab stores workspace
state (which notebooks are open) server-side in
`~/.jupyter/lab/workspaces/`. When a new Playwright test opens JupyterLab,
it restores the previous workspace, causing old notebook sessions to
reconnect to stale kernels. The old kernel for notebook N reconnects
briefly, flooding the server log and potentially interfering with notebook
N+1's widget communication.

Fix: add `rm -rf ~/.jupyter/lab/workspaces` to `shutdown_kernels` so each
batch starts with a fresh workspace, and run the same cleanup once before
the first batch.

### `uv sync` in a parallel job strips extras from a shared venv
`uv sync --dev --no-install-project` removes packages not in the lock file for
the current sync scope. If job A syncs the shared 3.13 venv and job B is
running tests that require an extras package (e.g. `pl-series-hash`), job B
fails non-deterministically. Either: don't sync in the parallel job, or use
`UV_PROJECT_ENVIRONMENT` pointing to a job-private venv.

### Stale kernel runtime files cause batch-1 timing failures across runs
`~/.local/share/jupyter/runtime/kernel-*.json` and `jpserver-*.json` files
accumulate without cleanup — each 9-notebook CI run adds 9 kernel JSON files.
When JupyterLab starts, it scans the runtime directory and attempts ZMQ
heartbeat connections to every kernel JSON it finds. Dead kernels cause a
connection timeout for each file. With 100+ stale files, this delays JupyterLab
initialization by 1-2 seconds.

The first notebook (test_buckaroo_widget.ipynb) runs while JupyterLab is still
processing these stale connections. The Playwright test's 1.3s static wait after
Shift+Enter isn't enough time for the widget to render, so it fails. Batches 2-9
pass because JupyterLab finishes the scan before they run.

This produced an alternating PASS/FAIL pattern in stress tests: runs after a
full 9-notebook pass added more files, pushing the next run over the threshold.

Fix: add to `test_playwright_jupyter_parallel.sh` startup:
```bash
rm -f ~/.local/share/jupyter/runtime/kernel-*.json
rm -f ~/.local/share/jupyter/runtime/jpserver-*.json
rm -f ~/.local/share/jupyter/runtime/jpserver-*.html
```

### Double-run contamination from SSH heredocs
Running `ssh host << 'EOF' ... EOF` can spawn two processes if the connection
is slow. Always use `nohup bash -c "..." </dev/null &` and verify with
`pgrep -c run-ci` after start.

---

## Deploy Checklist (hotfix without image rebuild)

When `run-ci.sh` or any script in `/opt/ci-runner/` changes:

```bash
REPO=/opt/ci/repo
git -C "$REPO" fetch origin
git -C "$REPO" checkout origin/docs/ci-research -- ci/hetzner/run-ci.sh scripts/test_playwright_jupyter_parallel.sh

docker cp "$REPO/ci/hetzner/run-ci.sh" buckaroo-ci:/opt/ci-runner/run-ci.sh
docker cp "$REPO/scripts/test_playwright_jupyter_parallel.sh" buckaroo-ci:/opt/ci-runner/

SHA=$(git -C "$REPO" rev-parse --short origin/docs/ci-research)
printf "%s" "$SHA" | docker exec -i buckaroo-ci bash -c 'cat > /opt/ci-runner/VERSION'
echo "deployed VERSION=$SHA"
```

The VERSION file is read by `run-ci.sh` at startup and logged as
`CI runner: <sha>`, so every run log identifies which script version ran it.

---

## Resource Usage (CCX43, parallel Phase 5)

Peak memory: **11.8 GB** (38% of 31 GB) — driven by wasm-marimo loading a
large WASM bundle while 4 other browser processes are alive.
Peak CPU: briefly 100%, average 44% across the run.
Headroom is comfortable; CCX43 is not over-provisioned for this workload.

---

## Purpose and Design Intent

This CI system is built for **manual and agent-driven use before pushing to GitHub** —
not for PR status automation. Think of it as syntax highlighting for LLMs: fast,
low-friction feedback on a commit while still on the local branch. The webhook and
GITHUB_TOKEN integration are explicitly out of scope; the trigger is always a direct
`docker exec` call by a human or agent.

Implications for prioritisation:
- Speed and reliability matter most — false positives waste agent iteration cycles
- Webhook/PR-status integration is not a goal
- The runner should be usable with a single SSH command or script call, no GitHub setup required

---

## What's Left

### Speed — critical path is 2m49s

The entire suite currently runs in ~6min on CCX43. The theoretical minimum
(critical path with ∞ cores) is **2m49s**: `test-js(24s) → build-wheel(22s) → playwright-jupyter(2m03s)`.
Nothing else can beat this without shortening the playwright-jupyter leg.

| Item | Expected saving | Notes |
|------|----------------|-------|
| PARALLEL=3 for Phase 5b | ~45s off total | Batch-1 timing flake is now fixed (kernel warmup). Ready to retry. |
| Fix Playwright static waits (`waitForTimeout`) | Reduces playwright-jupyter from 2m03s; unblocks PARALLEL=4+ | The spec uses hardcoded 800ms+500ms waits instead of `waitFor` conditions. This is the main critical-path bottleneck and the prerequisite for any further parallelism gains. |
| Downgrade CCX43 → CCX33 | Cost only, no speed change | Benchmarked identical timing on 8 vs 16 vCPU — bottleneck is the sequential critical path, not cores. CCX43 is paying for unused capacity. |

### Reliability

| Item | Notes |
|------|-------|
| Flaky `test_lazy_widget_status_and_messages` | Timing-sensitive async widget tests that occasionally fail under parallel Phase 3 CPU load. Rerunning reliably passes. Root fix is in the test spec (proper async assertions). |
| `cffi` source compilation | `uv` falls back to building cffi from source instead of manylinux wheels on dep-change runs. Investigate wheel availability for the target platform. |
| `mp_timeout` Docker tuning | forkserver spawn is ~1.5s on CCX43; tests hardcoded to 1.0s — requires code changes, deferred. |

### Uncontended job timings (fcfe368, serial run)

Measured with `run-ci-serial.sh` — each job runs alone with no parallel contention:

| Job | Time |
|-----|------|
| lint-python | 0s |
| test-js | 24s |
| test-python-3.11/3.12/3.13 | ~63s each |
| test-python-3.14 | 0s (skipped) |
| build-wheel | 22s |
| test-mcp-wheel | 12s |
| smoke-test-extras | 20s |
| playwright-storybook | 10s |
| playwright-server | 58s |
| playwright-marimo | 56s |
| playwright-wasm-marimo | 35s |
| playwright-jupyter | 2m03s |

These are the numbers to optimise against. The Python test jobs each take ~63s
uncontended but only ~75s even when three run in parallel — good CPU efficiency.
playwright-jupyter dominates; fixing its static waits is the highest-leverage change.
