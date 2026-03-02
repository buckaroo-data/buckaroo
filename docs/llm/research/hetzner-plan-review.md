# Adversarial Review: Hetzner CI Implementation Plan

**Date:** 2026-03-01
**Status:** Review of plan that is already being executed. These are notes for future iterations, not blockers.

---

## Critical Issues

### 1. The 60-75s estimate is wrong

The plan targets 60-75s warm critical path. But it specifies **sequential Playwright** in a single sidecar container due to "port conflicts." Five sequential Playwright suites at ~30-45s each = **150-225s just for Playwright**.

**However, the port conflict premise is false.** All 5 suites bind to different ports:

| Suite | Port |
|-------|------|
| Storybook | 6006 |
| JupyterLab | 8889 |
| Marimo | 2718 |
| Buckaroo Server | 8701 |
| WASM Marimo | 8765 |

The only conflict (Storybook vs Screenshots on 6006) doesn't apply — Screenshots stays on GitHub Actions.

**Fix:** Run all 5 Playwright suites in parallel. Critical path becomes ~45s (longest single suite, JupyterLab). Combined with build overhead (~17s) and dep verification (~2s), warm critical path is realistically **~65-75s** — which actually matches the plan's target, just for different reasons than stated.

### 2. Concurrent runs in shared container will corrupt state

The plan says "different branches → run concurrently (max 2 via semaphore)." But both runs share one container filesystem. Two concurrent `git checkout` calls clobber each other. `git clean -fdx` in run A nukes run B's working state.

**Resolution (agreed):** Run only 1 build at a time. Kill previous run on same branch, queue or reject different-branch runs. This is simpler and avoids the entire class of problems.

### 3. Bash orchestrator is under-scoped

`run-ci.sh` needs to handle: parallel execution with background processes, per-job timeouts, structured error collection, wave dependencies, process cleanup on failure. This is exactly what CI frameworks solve.

The "~120 lines of Python" pitch describes the webhook, not the orchestrator. The orchestrator is the hard part.

**Options evaluated:**
- **doit** — Python DAG runner, good parallel + fail-fast, but tasks are atomic (no mid-task artifact emission). See `doit-task-runner.md`.
- **Custom asyncio** — ~50-80 lines, `asyncio.Event` per artifact, `gather` for fail-fast. Matches the desired pattern exactly but is bespoke.
- **Bash with discipline** — Workable if kept simple (no waves, just parallel backgrounded jobs with `wait`). Fragile at scale.

No recommendation yet. The plan can start with bash and migrate if it gets painful.

---

## Moderate Issues

### 4. Webhook is an unauthenticated attack surface

Port 9000 open to the internet, HMAC as only defense. This is standard for GitHub webhooks, but:

- **No TLS** — webhook payloads (commit SHAs, branch names) sent in plaintext
- **No rate limiting** — endpoint can be spammed
- **Injection risk** — `docker exec ... bash run-ci.sh <sha>` is vulnerable if `sha` isn't validated as hex. A payload with `sha="; rm -rf /"` would be catastrophic

**Mitigations:**
- Validate SHA is `/^[0-9a-f]{40}$/` before passing to shell
- Put nginx or caddy in front for TLS (Let's Encrypt) and rate limiting
- Or restrict port 9000 to GitHub's webhook IP ranges (documented at `api.github.com/meta`)

### 5. No per-job GitHub commit status

On Depot, each job reports independently — you see which specific test failed. The plan reports a single `ci/hetzner` commit status. One flaky Playwright test fails the entire run with no granularity.

**Fix:** Report multiple commit status contexts: `ci/hetzner/lint`, `ci/hetzner/test-js`, `ci/hetzner/pw-storybook`, etc. Each job calls `status_success` or `status_failure` independently. More `status.sh` calls but much better UX.

### 6. 240GB disk might be tight

Estimated usage:
- Docker image: 8-12GB
- Docker build cache: 5-10GB
- Named volumes (pnpm store, uv cache, Playwright browsers): 5-10GB
- Git repo: 1-2GB
- OS + Docker overhead: 5-10GB
- CI logs (7 day retention): 1-2GB

**Total: ~25-46GB steady state.** 240GB is fine. This is less of a concern than initially flagged — the weekly `docker system prune` cron handles growth.

### 7. No rollback story after Depot deprecation

The plan says deprecate Depot after 2+ weeks of agreement. But after deprecation, there's no canary. Re-enabling Depot requires active credentials and runner access.

**Recommendation:** Keep Depot running indefinitely as a read-only canary. At ~$9/month for 50 runs, it's cheap insurance. Don't make it a branch protection requirement — just let it run and alert if it disagrees with Hetzner.

---

## Minor Issues

### 8. Research doc / plan contradictions

| Topic | Research doc | Implementation plan | Notes |
|-------|-------------|-------------------|-------|
| Python install | deadsnakes PPA | `uv python install` | Plan is better |
| Node version | Node 20 | Node 22 LTS | Plan is better |
| Playwright | Parallel (separate containers) | Sequential (single container) | Both wrong — should be parallel in single container |
| CI trigger | Forgejo or GH self-hosted runner recommended | Bare webhook chosen | Intentional, but research recommendation was ignored without justification |
| Container command | `tail -f /dev/null` | `sleep infinity` | Doesn't matter |

### 9. `sleep infinity` sidecar has no health check

If the container's main process dies or the container enters a bad state (OOM, zombie processes), nothing detects it. The webhook's `/health` endpoint checks `docker inspect` but that only tells you the container exists, not that it's functional.

**Fix:** Add a lightweight health check to docker-compose:
```yaml
healthcheck:
  test: ["CMD", "python3", "-c", "import sys; sys.exit(0)"]
  interval: 30s
```

### 10. Systemd watchdog adds complexity for little benefit

`sd_notify` integration in Python requires the `systemd` Python bindings or manual socket handling. For a Flask app behind gunicorn, gunicorn's own `--timeout` flag handles hung workers. The systemd watchdog is solving a problem gunicorn already solves.

---

## What the Plan Gets Right

- **CCX33 cloud over dedicated** — simpler automation, easy wipe, adequate CPU for Playwright-bound workload
- **Depot as parallel canary during rollout** — exactly the right approach
- **Source mounted, not baked in** — image rebuilds only on lockfile changes
- **Lockfile hash check** — skipping dep install on 95% of pushes is the key optimization
- **Reusing existing scripts** — `test_playwright_*.sh` and `full_build.sh` already work, no rewrite needed
- **Development verification plan** — every component testable locally before deploying
