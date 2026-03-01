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
2. **uv** — `COPY --from=ghcr.io/astral-sh/uv:0.6.6` (pin a specific version). We don't need to track uv releases proactively — uv is a build tool, not a runtime dependency. When something breaks or we want a new feature, we bump the pin. The Docker image rebuild is fast either way.
3. **Python 3.11-3.14 via uv** — `uv python install 3.11 3.12 3.13 3.14` (no deadsnakes PPA needed)
4. **Node 22 LTS + pnpm@9.10.0** — Node installed via nodesource, pnpm via `corepack enable && corepack prepare pnpm@9.10.0`. Both pinned to specific versions in the Dockerfile. Same philosophy as uv: pin, don't track. Bump when needed. Node 22 is current LTS (supported through April 2027), no reason to stay on 20.
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

Template with required secrets and infrastructure state:
- `GITHUB_TOKEN` — fine-grained PAT with `repo:status` write scope on `buckaroo-data/buckaroo`
- `WEBHOOK_SECRET` — shared secret for HMAC validation
- `GITHUB_REPO` — `buckaroo-data/buckaroo`
- `HETZNER_SERVER_ID` — numeric ID of the CCX33 (from `hcloud server list`), used by any scripts that manage the server
- `HETZNER_SERVER_IP` — public IP, used for SSH and webhook URL configuration

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

## Development Verification (how Claude develops this autonomously)

Every script is built to be testable locally without a Hetzner server or live GitHub webhooks. The goal is: Claude can write, run, verify, and iterate without asking the user.

**Dockerfile** — Build it locally (`docker build`). Verify: image builds, `docker exec` into it and confirm `uv`, `python3.11-3.14`, `node`, `pnpm`, `playwright` are all on PATH. Run `pnpm install --frozen-lockfile` and `uv sync` inside to confirm deps install correctly.

**run-ci.sh** — Run locally inside the Docker container against the repo's current HEAD. Every test job already has a known-good baseline (what Depot CI produces). Compare: same tests pass, same tests fail. The script is pure shell — no external dependencies beyond what's in the container.

**lockcheck.sh** — Unit-testable with temp directories. Create fake lockfiles, run `--update` to store hashes, verify return code 0. Modify a lockfile, verify return code 1. All locally.

**status.sh** — Add a `--dry-run` flag that prints the curl command instead of executing it. Verify the correct URL, SHA, and status are in the output. For live testing, use a throwaway commit on a test branch.

**webhook.py** — Test with `curl` against localhost:
- Send a valid payload with correct HMAC → verify 200 + CI triggered
- Send invalid HMAC → verify 401
- Send irrelevant event type → verify 200 + ignored
- Flask has a built-in test client, so these can be pytest tests in the same file or a small test script.

**cloud-init.yml** — This one can't be tested locally. Verify by provisioning a real CCX33 and SSH-ing in to check each step completed. Since cloud-init is idempotent and only runs once, the blast radius is low (worst case: delete server, fix script, reprovision).

**Integration test sequence** (run by Claude after all scripts are written):
1. `docker build` → `docker-compose up -d` → `docker exec buckaroo-ci bash run-ci.sh HEAD main` → all tests pass
2. Modify a lockfile → rerun → verify lockcheck detects change and reinstalls
3. Run webhook.py locally → send test payloads with curl → verify status.sh dry-run output
4. Push to a test branch → verify Depot and Hetzner both report status

## Monitoring & Alerting

**Depot as canary** — Both Depot and Hetzner run on every push. Missing or disagreeing `ci/hetzner` status when Depot is green = something is wrong with the Hetzner setup. This is the primary detection mechanism and requires zero extra infrastructure.

**Health endpoint** — `GET /health` on the webhook returns JSON with: webhook process up, Docker container running (`docker inspect`), disk usage %, last successful CI run timestamp. One `curl` tells you the full system status.

**Systemd watchdog** — `WatchdogSec=60` in the service file. `webhook.py` pings systemd every 30s via `sd_notify`. If the process hangs (not just crashes), systemd restarts it automatically.

**Disk hygiene** — Weekly cron: `docker system prune --force`, rotate CI logs older than 7 days. Disk filling up is the most likely silent failure mode.

**Dead man's switch** — After each successful CI run, touch `/opt/ci/last-success`. A daily cron on weekdays checks if this file is older than 24 hours. If so, post a warning to the webhook's `/health` endpoint (health check goes from "ok" to "stale"). You'd see this next time you check, or could optionally wire it to a Slack/email notification later.

## Testing & Ongoing Verification

### Initial Verification

1. **Local Docker test**: Build the image locally, `docker exec` into it, run `run-ci.sh` against current HEAD. All tests must pass and match what GitHub Actions produces.
2. **Webhook smoke test**: Run `webhook.py` locally behind ngrok, configure a test webhook on GitHub, push a commit, verify pending/success status appears on the commit.
3. **Hetzner deploy**: Provision CCX33 with cloud-init, configure secrets, push a PR, verify end-to-end green status.
4. **Concurrency test**: Push two commits rapidly on same branch, verify first run is cancelled and only second reports status.
5. **Lockfile change test**: Bump a dep, push, verify the container detects the lockfile change and reinstalls.

### Ongoing Verification (keeping it working as we change things)

**Depot CI stays on as the source of truth.** Both Depot and Hetzner run on every push. If Hetzner disagrees with Depot, Hetzner is wrong. This gives us a permanent regression check with zero extra effort — we never have to wonder if Hetzner is silently broken because Depot is always there to compare against.

**When to investigate**: If Hetzner reports failure but Depot is green (environment drift, stale cache, port conflict). If Hetzner reports success but Depot is red (shouldn't happen — means Hetzner is skipping something).

**Deprecating Depot**: Only after Hetzner has been green and agreeing with Depot for 2+ weeks of active development. At that point, flip the GitHub branch protection to require `ci/hetzner` instead of the Depot check, then disable the Depot workflow. Keep the workflow file around (commented out) so it's easy to re-enable if Hetzner has issues.

