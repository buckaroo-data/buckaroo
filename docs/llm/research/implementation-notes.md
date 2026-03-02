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

**Critical path** after all parallelisation:
`test-js (~25s) → build-wheel (~21s) → playwright-jupyter (~100s) ≈ 2m30s`

Nothing else can beat this without shortening playwright-jupyter or decoupling
build-wheel from test-js.

### Why CCX43 didn't help
Upgrading from CCX33 (8 vCPU) to CCX43 (16 vCPU) gave identical timing
(~5m05s vs ~4m58s). The bottleneck is the sequential critical path, not CPU
core count. More cores only help if there's parallelisable work waiting on them.

### Why the DAG approach failed
Running all independent jobs simultaneously (9 concurrent on 8 vCPUs) caused:
- CPU saturation → forkserver tests hit hardcoded 1s timeouts
- playwright-marimo server too slow to start → 6-minute hang
The phased approach (P1→P2→P3→P4→P5) naturally throttles concurrency.

---

## Bugs That Will Bite You Again

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

### `uv sync` in a parallel job strips extras from a shared venv
`uv sync --dev --no-install-project` removes packages not in the lock file for
the current sync scope. If job A syncs the shared 3.13 venv and job B is
running tests that require an extras package (e.g. `pl-series-hash`), job B
fails non-deterministically. Either: don't sync in the parallel job, or use
`UV_PROJECT_ENVIRONMENT` pointing to a job-private venv.

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

## What's Left

| Item | Notes |
|------|-------|
| Parallel jupyter notebooks (PARALLEL=9) | Still being debugged (runs 14–16+); should save ~60–70s off Phase 5 |
| Webhook + GITHUB_TOKEN | For automatic PR status; currently all runs are manual |
| `cffi` source compilation | Should be using manylinux wheels; investigate why uv falls back to source |
| `mp_timeout` Docker tuning | forkserver spawn is ~1.5s on CCX43; tests hardcoded to 1.0s |
