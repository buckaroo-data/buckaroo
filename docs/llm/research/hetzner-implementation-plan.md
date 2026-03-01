# Hetzner Self-Hosted CI Implementation Plan

## Context

Current CI runs 22 jobs on Depot cloud runners with a ~3:27 critical path. Most time is overhead (provisioning, dep install), not tests. A persistent Hetzner CCX33 with warm Docker containers eliminates that overhead, targeting ~60-70s critical path.

**Approach**: Bare GitHub webhook → Python receiver on Hetzner → `docker exec` into warm sidecar container → run tests → report status back to GitHub via commit status API. No CI framework.

## What Moves to Hetzner vs Stays on GitHub Actions

**Hetzner (fast feedback):**
- LintPython, TestJS, BuildWheel
- TestPython (3.11, 3.12, 3.13, 3.14)
- All Playwright: Storybook, Server, Marimo, WASMMarimo, JupyterLab
- TestMCPWheel, SmokeTestExtras

**Stays on GitHub Actions:**
- TestPythonWindows (can't run on Linux)
- TestPythonMaxVersions (low-priority edge-case testing)
- PublishTestPyPI (needs GitHub OIDC trusted publishing)
- StylingScreenshots (complex baseline git checkout workflow)
- CheckDocs (low value for fast feedback)

## File Structure

```
ci/hetzner/
  Dockerfile              # Multi-layer image: OS → uv → Python 3.11-3.14 → Node/pnpm → deps → Playwright
  docker-compose.yml      # Sidecar container (sleep infinity) with volume-mounted caches
  webhook.py              # Flask webhook receiver (~120 lines)
  run-ci.sh               # Main CI orchestrator (git fetch → build → parallel tests → status)
  lib/
    status.sh             # GitHub commit status API helpers
    lockcheck.sh          # Lockfile hash comparison → triggers docker rebuild
  cloud-init.yml          # CCX33 provisioning (Docker, webhook systemd service, firewall)
  .env.example            # Template: GITHUB_TOKEN, WEBHOOK_SECRET, GITHUB_REPO
```

## Implementation Steps

### Step 1: Dockerfile

Multi-layer, ordered from least to most frequently changing:

1. **OS + system deps** — Ubuntu 24.04, Playwright system libs (libnss3, libatk, etc.), curl, git
2. **uv** — `COPY --from=ghcr.io/astral-sh/uv:latest`
How do we know when a newer version of uv comes out?

3. **Python 3.11-3.14 via uv** — `uv python install 3.11 3.12 3.13 3.14` (no deadsnakes PPA needed)
4. **Node 20 + pnpm@9.10.0** — via nodesource
same of pnpm/node 20?
5. **JS deps from lockfile** — COPY `pnpm-lock.yaml` + `package.json` files, `pnpm install --frozen-lockfile`
6. **Python deps from lockfile** — COPY `pyproject.toml` + `uv.lock`, create venvs for each Python version with `uv sync`
7. **Playwright chromium** — `playwright install chromium`

Source code is NOT baked in — mounted at runtime. Image rebuilds only when lockfiles change.

### Step 2: docker-compose.yml

Single `ci` service running `sleep infinity` (warm sidecar). Volumes:
- Source code bind-mounted read-only
- Named volumes for pnpm store, uv cache, Playwright browsers
- `/opt/ci/logs` for CI output

The webhook runs directly on the host via systemd (avoids Docker-in-Docker complexity).

### Step 3: webhook.py

Minimal Flask app running on port 9000:
- Validates GitHub webhook secret (HMAC-SHA256)
- Handles `push` and `pull_request` (opened/synchronize/reopened) events
- Sets GitHub commit status to "pending" immediately
- Runs CI in background thread via `docker exec buckaroo-ci bash run-ci.sh <sha> <branch>`
- **Concurrency**: Same branch → kill previous run (only latest commit matters). Different branches → run concurrently (max 2 via semaphore)
- On completion: sets commit status to "success" or "failure"

Deployed as systemd service (`buckaroo-webhook.service`) running under gunicorn.

### Step 4: run-ci.sh

Runs inside the Docker container. Orchestrates:

1. `git fetch` + `checkout` the specific SHA
2. `git clean -fdx` excluding `node_modules`, `.venv-*` (warm caches)
3. Lockfile hash check — skip dep install if unchanged (95% of pushes)
4. **Wave 1 (parallel)**: lint-python, test-js (build+jest), build-wheel (`full_build.sh`), test-python-3.13
5. Wait for build-wheel, then run test-python 3.11/3.12/3.14 sequentially
6. **Wave 2 (sequential)**: Playwright tests — storybook, server, marimo, jupyter, wasm-marimo. Run sequentially because they bind to specific ports (6006, 8889, 2718, 8701, 8765)
7. **Wave 2 (parallel with Playwright)**: mcp-wheel test, smoke tests (no ports needed)
8. Collect results, exit 0 or 1

Each job's stdout/stderr captured to `$RESULTS_DIR/<job>.log` for debugging.

### Step 5: lib/status.sh + lib/lockcheck.sh

**status.sh**: Shell functions wrapping `curl` calls to GitHub's commit status API (`POST /repos/:owner/:repo/statuses/:sha`). Functions: `status_pending`, `status_success`, `status_failure`.

**lockcheck.sh**: Compares SHA256 hashes of `uv.lock`, `pnpm-lock.yaml`, `pyproject.toml`, `packages/buckaroo-js-core/package.json` against stored hashes in `/opt/ci/hashes/`. Returns 0 if caches valid, 1 if rebuild needed. `--update` flag stores current hashes.

### Step 6: cloud-init.yml

Provisions CCX33 from zero:
- Creates `ci` user with Docker group access
- Installs Docker, git, python3, ufw, fail2ban
- Clones repo to `/opt/ci/repo`
- Creates webhook venv, installs flask + gunicorn
- Builds CI Docker image, starts sidecar container
- Configures firewall (SSH + port 9000 only)
- Installs systemd service for webhook

**Post-cloud-init manual steps**: Fill in `/opt/ci/.env` (GITHUB_TOKEN, WEBHOOK_SECRET), start webhook service, configure GitHub webhook in repo settings.

### Step 7: .env.example

Template with required secrets:
- `GITHUB_TOKEN` — fine-grained PAT with `repo:status` write scope on `buckaroo-data/buckaroo`
- `WEBHOOK_SECRET` — shared secret for HMAC validation
- `GITHUB_REPO` — `buckaroo-data/buckaroo`

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Webhook vs CI framework | Bare webhook | Least infrastructure, ~120 lines of Python |
| Flask vs netcat | Flask | Needs concurrent handling, HMAC validation, threading |
| Webhook in Docker vs host | Host (systemd) | Avoids Docker-in-Docker complexity |
| Container per run vs sidecar | Sidecar (`docker exec`) | ~50ms overhead vs ~500ms for `docker run` |
| Playwright parallel vs sequential | Sequential | Port conflicts (6006, 8889, 2718, etc.) |
| Python tests parallel vs sequential | 3.13 parallel, rest sequential | Stay within 8-vCPU budget |
| Log viewing | `/logs/<sha>` endpoint on webhook | Click-through from GitHub commit status |

## Expected Performance

| Scenario | Time |
|----------|------|
| Warm push (no lockfile change) | ~60-75s |
| Cold push (lockfiles changed) | ~100-140s |
| Full wipe + reprovision (cloud-init) | ~5-8 min |

## Verification Plan

1. **Local Docker test**: Build the image locally, run `run-ci.sh` inside it against current HEAD, verify all tests pass
2. **Webhook test**: Run `webhook.py` locally, use `ngrok` to forward, configure GitHub webhook, push a commit, verify status appears on commit
3. **Hetzner deploy**: Provision CCX33 with cloud-init, SSH in, configure secrets, push a PR, verify end-to-end
4. **Concurrency test**: Push two commits rapidly on same branch, verify first run is cancelled
5. **Lockfile change test**: Change a dep, push, verify Docker image rebuilds

## Files to Create

All new files in `ci/hetzner/`:
- `ci/hetzner/Dockerfile`
- `ci/hetzner/docker-compose.yml`
- `ci/hetzner/webhook.py`
- `ci/hetzner/run-ci.sh`
- `ci/hetzner/lib/status.sh`
- `ci/hetzner/lib/lockcheck.sh`
- `ci/hetzner/cloud-init.yml`
- `ci/hetzner/.env.example`

Existing scripts (`scripts/test_playwright_*.sh`, `scripts/full_build.sh`) are reused as-is. The existing `pnpm install` and `playwright install chromium` calls in those scripts become no-ops in the warm container (deps already installed).

No changes to `.github/workflows/checks.yml` — Depot CI continues running in parallel. The Hetzner CI is additive (shows as a separate commit status context `ci/hetzner`).

how will you test/verify that this is working?
as we update this, how will we continue to test and verify that this is working?

