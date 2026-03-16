# Warm Docker CI on Dedicated Server

**Date:** 2026-03-01
**Context:** Research into replacing Depot cloud CI with a persistent dedicated server running warm Docker containers for near-instant CI feedback.

## Motivation

Current Depot CI has a ~3.5 min critical path. Most of that is overhead — provisioning, bootstrapping, installing deps — not running tests. A persistent server with warm containers eliminates all of that.

Primary concern: **latency**, not cost.

---

## CI Framework Options

Evaluated frameworks for self-hosted CI on a dedicated box, ranked by trigger latency:

### Tier 1: Sub-second trigger

**Laminar CI** — Minimal C++ daemon, <1s trigger. No built-in Git integration (needs webhook glue). Config is just shell scripts in `/var/lib/laminar/cfg/jobs/`. Web UI for status. No Docker awareness — you'd script `docker exec` yourself. Good for: maximum simplicity, single-project servers.

**Bare git hooks** — `post-receive` hook fires instantly on push. Zero framework overhead. You write the orchestration. Good for: smallest possible setup, but you own all the plumbing.

### Tier 2: 1-5s trigger

**Forgejo Actions** — Self-hosted Gitea fork with ~95% GitHub Actions YAML compatibility. Host-mode runner (no container per job) gives ~1-3s trigger. Can reuse most of existing `.github/workflows/checks.yml` with minor edits. Built-in git hosting, PR UI, issue tracker. Good for: migrating from GitHub Actions with minimal rewrite.

**GitHub Actions self-hosted runner** — Keep GitHub as git host, run a persistent runner on the Hetzner box. Long-poll mechanism, ~2-5s job pickup. Workspace persists between runs (warm caches). Familiar ecosystem. Good for: keeping GitHub workflow, adding speed.

### Tier 3: 5-15s trigger

**Buildkite** — SaaS control plane + self-hosted agents. ~5-10s trigger (agent polls every 1-5s). Excellent parallel pipeline support, Docker-native. $15/user/mo. Good for: teams, polished UI.

**Woodpecker CI** — Lightweight Go binary, Docker-native pipelines. ~3-5s trigger. YAML config, supports matrix builds. Good for: Docker-first workflows without vendor lock-in.

**Concourse CI** — Resource-based pipeline model, very different from GitHub Actions. Steep learning curve. Good for: complex multi-repo pipelines, not great for single-project.

**Dagger** — Not a CI system — it's a container-based task runner. Wraps your CI steps in BuildKit containers. Can run inside any CI. Adds overhead (~2-5s container startup per step). Good for: portable CI definitions, not for raw speed.

### Tier 4: Framework, not a runner

**Buildbot** — Python-based, very flexible, heavy. Overkill for a single project.

### Recommendation

For Buckaroo: **Forgejo** (if willing to self-host git) or **GitHub Actions self-hosted runner** (if staying on GitHub). Both give 1-5s trigger latency with minimal setup.

---

## The Docker Setup

### Image Structure (layered for cache efficiency)

```dockerfile
# Layer 1: OS + system deps (~500MB, changes: ~never)
FROM ubuntu:24.04 AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates build-essential \
    # Playwright/Chromium system deps
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2t64 libwayland-client0 \
    pandoc graphviz \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Python 3.11-3.14 via deadsnakes (~1.5GB, changes: rarely)
RUN apt-get update && apt-get install -y software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get install -y python3.11 python3.12 python3.13 python3.14 \
       python3.11-venv python3.12-venv python3.13-venv python3.14-venv \
    && rm -rf /var/lib/apt/lists/*

# Layer 3: Node 20 + pnpm 9.10.0 (~200MB, changes: rarely)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable && corepack prepare pnpm@9.10.0 --activate

# Layer 4: uv (~50MB, changes: occasionally)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Layer 5: Lockfiles only — triggers dep install layer on change
COPY uv.lock pyproject.toml /workspace/
COPY packages/pnpm-lock.yaml packages/package.json /workspace/packages/
COPY packages/buckaroo-js-core/package.json /workspace/packages/buckaroo-js-core/
COPY packages/buckaroo-widget/package.json /workspace/packages/buckaroo-widget/

# Layer 6: Install all deps from lockfiles (~4-6GB, changes: when deps change)
WORKDIR /workspace
RUN /root/.local/bin/uv sync --locked --all-extras --dev --python 3.12
RUN cd packages && pnpm install --frozen-lockfile
RUN npx playwright install chromium

# Source code NOT baked in — mounted at runtime
```

**Estimated image size:** 8-12 GB with all Python versions.

### Docker Compose: Sidecar Pattern

A long-running container you `docker exec` into for each CI run:

```yaml
# docker-compose.ci.yml
services:
  ci-runner:
    image: buckaroo-ci:latest
    container_name: buckaroo-ci
    restart: unless-stopped
    volumes:
      - ./workspace:/workspace
      - pnpm-store:/root/.local/share/pnpm/store
      - uv-cache:/root/.cache/uv
      - pw-browsers:/root/.cache/ms-playwright
    environment:
      - UV_LINK_MODE=copy
    command: tail -f /dev/null

volumes:
  pnpm-store:
  uv-cache:
  pw-browsers:
```

### CI Trigger Script

```bash
#!/bin/bash
# Called by git post-receive hook or webhook
COMMIT_SHA=$1

# Check if image needs rebuild (lockfiles changed)
PREV_LOCK_HASH=$(cat /var/ci/.lock-hash 2>/dev/null)
CURR_LOCK_HASH=$(sha256sum uv.lock packages/pnpm-lock.yaml | sha256sum | cut -c1-12)

if [ "$PREV_LOCK_HASH" != "$CURR_LOCK_HASH" ]; then
  docker build -t buckaroo-ci:latest .
  docker compose -f docker-compose.ci.yml up -d --force-recreate
  echo "$CURR_LOCK_HASH" > /var/ci/.lock-hash
fi

# Run tests
docker exec buckaroo-ci bash -c "
  cd /workspace &&
  git fetch origin && git checkout $COMMIT_SHA &&
  pnpm install --frozen-lockfile &&
  uv sync --locked --all-extras --dev &&
  cd packages/buckaroo-js-core && pnpm build && cd /workspace &&
  bash scripts/full_build.sh &&
  pytest -vv tests/unit/ &
  (cd packages/buckaroo-js-core && pnpm test) &
  wait
"
```

---

## Container Startup Benchmarks

| Method | Startup overhead | Isolation |
|--------|-----------------|-----------|
| `docker exec` (sidecar) | ~50-100ms | Shared container state |
| `docker run` (fresh container, cached image, NVMe) | ~500-600ms | Clean process state |
| Firecracker microVM (snapshot restore) | ~125ms | Full VM (separate kernel) |

The sidecar pattern (`docker exec`) is fastest because there's no container creation, image layer resolution, or filesystem setup — it's just `exec` into an already-running process namespace.

---

## Lockfile-Hash Cache Invalidation

Docker's layer cache already handles this implicitly: when you `COPY uv.lock` into the image, Docker checksums the file. If unchanged, it reuses the cached layer and skips `RUN uv sync`.

The outer trigger (when to run `docker build` at all) can be:

1. **Hash check in git hook** — compare lockfile hashes, only rebuild on change (~1-2s check)
2. **Run `docker build` every time** — when layers are cached it's a ~1-2s no-op anyway
3. **Watchtower / Diun** — auto-pull new images from a registry on change
4. **Nix** — content-addressed by definition, change input = new hash = new environment

For a single-box setup, option 1 or 2 is simplest. The hash check is an optimization to skip even the 1-2s `docker build` verification.

---

## Playwright: Shared Wheel Across Parallel Containers

Build the wheel once, share via bind mount:

```bash
# Step 1: Build wheel in sidecar
docker exec buckaroo-ci bash -c "
  cd /workspace && bash scripts/full_build.sh
"
# Wheel lands in /workspace/dist/ — visible to all containers

# Step 2: Run Playwright jobs in parallel
for job in storybook jupyter marimo wasm; do
  docker run -d --name "pw-$job" \
    -v $(pwd)/workspace:/workspace:ro \
    -v venv-$job:/workspace/.venv \
    -v pw-browsers:/root/.cache/ms-playwright \
    -e UV_LINK_MODE=copy \
    buckaroo-ci:latest \
    bash -c "
      cd /workspace &&
      uv pip install dist/buckaroo-*.whl &&
      bash scripts/pw-$job.sh
    " &
done
wait
```

Key: `/workspace` is a bind mount shared across all containers. Each container gets its own venv volume for isolation but installs from the same wheel file.

---

## Where Time Goes (Warm Case — No Lockfile Changes)

This is ~95% of pushes.

```
t=0.000s  git push completes, post-receive hook fires
t=0.050s  Hook script starts, computes lockfile hash — no change
t=0.100s  docker exec buckaroo-ci bash -c "..."
          ├── git fetch + checkout                      ~0.3s
          ├── pnpm install --frozen-lockfile             ~1.0s  (warm, just verifying)
          ├── uv sync --locked                           ~1.0s  (warm, just verifying)
          ├── pnpm build (tsc + esbuild)                ~8-12s  (CPU-bound)
          ├── hatch build (wheel)                       ~3-5s
          │
          │   ── parallel from here ──
          │
          ├── pytest -vv tests/unit/                    ~20-30s
          ├── pnpm test (Jest)                          ~10-15s
          ├── Playwright storybook                      ~30-45s  ← critical path
          ├── Playwright jupyter                        ~30-45s
          ├── Playwright marimo                         ~20-30s
          └── Playwright wasm                           ~20-30s
t=~60-70s  All done.
```

### Time budget breakdown

| Phase | Time | % of total | Notes |
|-------|------|------------|-------|
| Git hook + fetch + checkout | ~0.5s | <1% | Negligible |
| Dep verification (pnpm + uv) | ~2s | 3% | Confirming lockfile matches installed state |
| JS build (tsc + esbuild) | ~8-12s | 15% | CPU-bound, benefits from multi-core |
| Wheel build (hatch) | ~3-5s | 6% | Packaging |
| **pytest** | **~20-30s** | **35%** | Actual tests (hidden behind Playwright) |
| **Jest** | **~10-15s** | **18%** | Actual tests (hidden behind Playwright) |
| **Playwright (longest)** | **~30-45s** | **50%** | Browser startup + test execution — **the critical path** |

**Critical path: hook → git → deps → JS build → wheel → Playwright ≈ 45-65s**

pytest and Jest finish before Playwright, so they're free (hidden behind the Playwright wall clock).

### Cold case (lockfiles changed, ~5% of pushes)

Adds ~30-60s for Docker image rebuild (only re-runs from the lockfile COPY layer onward). Total: ~90-120s.

### Compared to current Depot CI

| Phase | Depot (current) | Warm Docker (Hetzner) |
|-------|-----------------|----------------------|
| Provisioning + bootstrap | ~30s | 0s |
| Dep install | ~30-60s (cold every time) | ~2s (warm verify) |
| JS build | ~15-20s | ~8-12s (NVMe + dedicated CPU) |
| pytest | ~20-30s | ~20-30s (same) |
| Playwright | ~60-90s | ~30-45s (NVMe IOPS for browser) |
| **Critical path** | **~3-3.5 min** | **~45-65s** |

---

## CPU Contention Analysis

### Peak concurrent load during parallel test phase

| Job | Cores used | CPU vs wait |
|-----|-----------|-------------|
| pytest | 1-2 | ~60% CPU, ~40% IO |
| Jest | 2-4 | ~80% CPU |
| Playwright (per instance) | 2-3 | ~30% CPU, ~70% waiting for browser |
| JS build (tsc) | 4-6 | ~95% CPU |

Peak total during parallel tests: ~7-12 cores demanded.

### Scaling by core count

| Server | Cores | JS build | Test phase | Total | Cost |
|--------|-------|----------|------------|-------|------|
| AX41 (Ryzen 5 3600) | 6c/12t | ~10s | contention, PW ~35-40s | ~55-65s | ~€35/mo |
| AX51 (Ryzen 7 3700X) | 8c/16t | ~8s | mild contention, PW ~30-35s | ~45-55s | ~€45/mo |
| AX101 (Ryzen 9 5900X) | 12c/24t | ~7s | no contention, PW ~28-32s | ~40-50s | ~€70/mo |
| 16-core | 16c | ~7s | diminishing returns | ~38-48s | — |

Playwright is mostly waiting (browser renders, selector polls), not computing. Beyond 8 cores, you run out of CPU-bound work. The bottleneck shifts to Playwright's inherent wait time.

**Sweet spot: 8-core.** Enough headroom for full parallelism without paying for cores that idle during Playwright waits.

### Optimization priority (by impact)

| # | Optimization | Time saved | Cost |
|---|-------------|------------|------|
| 1 | Warm box with Docker sidecar | ~120s | ~€35-45/mo |
| 2 | Parallelize pytest/Jest/Playwright | ~20-30s | Free (orchestration) |
| 3 | Shard Playwright into 2 containers | ~15s | Free (orchestration) |
| 4 | 8-core instead of 6-core | ~10s | +€10/mo |
| 5 | Shard Playwright into 4 containers | ~5-8s | Diminishing (contention on 6c) |
| 6 | More cores beyond 8 | ~3-5s | Diminishing returns |

The big wins are architectural (warm box, parallelism). More cores is marginal polish.

---

## Practical Gotchas

### pnpm hardlinks across volumes

pnpm's content-addressable store uses hardlinks, but hardlinks can't cross filesystem boundaries (Docker volume → bind mount). Fix: set `package-import-method: copy` in `.npmrc` or use a volume layout where store and node_modules are on the same filesystem.

### UV_LINK_MODE=copy

Same issue with uv — it defaults to hardlinks from cache to venv. When cache and venv are on different volumes, this fails silently or errors. Set `UV_LINK_MODE=copy` in the container environment.

### Git dubious ownership

If the container runs as root but the bind-mounted workspace is owned by UID 1000, git will refuse to operate. Fix: run the container as UID 1000, or add `/workspace` to git's `safe.directory` config.

### GitHub Actions `container:` jobs always pull

GitHub Actions `container:` directive always tries to `docker pull`, even if the image exists locally. There's no `pull: never` option. For self-hosted runners using local images, run steps directly on the host and use `docker exec` manually instead of the `container:` directive.

### Docker cache location

```
/var/lib/docker/
├── overlay2/       # Image layer storage
├── buildkit/       # Build cache (modern builds)
│   ├── cache/      # Build cache entries
│   └── content/    # Content-addressed blobs
├── volumes/        # Named volumes (pnpm-store, uv-cache, etc.)
└── containers/     # Running container state
```

All on NVMe. Docker overlay2 does heavy random reads (layer lookups, file dedup) — NVMe does ~500K random IOPS vs cloud EBS at ~3-16K. This 30-100x IOPS advantage is why Playwright and pytest collection feel faster on dedicated hardware.

Maintenance: occasional `docker system prune` or `docker buildx prune --keep-storage 20GB` on a weekly cron.

---

## Environment Drift: The Two-Path Model

The key concern with persistent servers is drift — the running environment diverging from what a clean build would produce.

Docker solves this with two convergent paths:

- **Path A (clean build):** `docker build` from Dockerfile → produces `buckaroo-ci:latest`. Deterministic from lockfiles. Run weekly or on lockfile change.
- **Path B (warm update):** Running container does `git pull && pnpm install --frozen-lockfile && uv sync --locked`. Fast for code-only changes.

Both paths converge to the same state because lockfiles are deterministic. The server is a pet; the CI environment inside Docker is cattle. If drift is ever suspected, Path A rebuilds from scratch in ~2-5 minutes.

---

## Hardware: Hetzner Cloud vs Dedicated

### Hetzner Cloud CCX (Dedicated vCPU)

| Model | vCPUs | RAM | NVMe | Monthly |
|-------|-------|-----|------|---------|
| CCX13 | 2 | 8 GB | 80 GB | €12.49 |
| CCX23 | 4 | 16 GB | 160 GB | €24.49 |
| CCX33 | 8 | 32 GB | 240 GB | €48.49 |
| CCX43 | 16 | 64 GB | 360 GB | €96.49 |

All CCX use AMD EPYC with dedicated (not shared) vCPUs, local NVMe RAID-10, 20 TB included traffic.

### Hetzner Dedicated AX

| Model | CPU | RAM | NVMe | Monthly | Setup |
|-------|-----|-----|------|---------|-------|
| AX41 | Ryzen 5 3600 (6c/12t) | 64 GB DDR4 | 2x 512 GB | ~€43 | ~€39 |
| AX42 | Ryzen 7 PRO 8700GE (8c/16t) | 64 GB DDR5 | 2x 512 GB | ~€49 | €39-107 |
| AX52 | Ryzen 7 7700 (8c/16t) | 64 GB DDR5 | 2x 1 TB | ~€64 | varies |
| AX102 | Ryzen 9 7950X3D (16c/32t) | 128 GB DDR5 | 2x 1.92 TB | ~€109 | varies |

### Head-to-head at ~€49/mo

| | Cloud CCX33 | Dedicated AX42 |
|--|------------|----------------|
| CPU | 8 vCPU (EPYC) | Ryzen 7 PRO 8700GE (8c/16t) |
| PassMark | ~12,274 | ~27,882 |
| RAM | 32 GB | 64 GB |
| Storage | 240 GB NVMe | 2x 512 GB NVMe |
| Wipe-to-running | ~2-3 min | ~8-12 min |
| Automation | Trivial (1 API call) | Moderate (5-step script) |
| IaC support | Official Terraform + Pulumi | Community Terraform only |
| cloud-init | Native | Not supported |
| Billing | Hourly, no minimum | Monthly, 1-month minimum |

Dedicated gives 2.3x CPU, 2x RAM, 4x storage for the same price — but Cloud wins on automation.

---

## Server Provisioning & Wipe

### Cloud (CCX): The Easy Path

Full API lifecycle. Create, destroy, snapshot in seconds. Native cloud-init.

**Provision from zero (~2-3 min):**
```bash
hcloud server create \
  --name ci-runner \
  --type ccx33 \
  --image ubuntu-24.04 \
  --ssh-key my-key \
  --user-data-from-file cloud-init.yml
```

```yaml
# cloud-init.yml
#cloud-config
packages:
  - docker.io
  - docker-compose
runcmd:
  - systemctl enable docker
  - systemctl start docker
  - docker pull buckaroo-ci:latest
  - docker compose -f /opt/ci/docker-compose.ci.yml up -d
```

**Wipe and rebuild:**
```bash
hcloud server delete ci-runner
hcloud server create --name ci-runner --type ccx33 --image ubuntu-24.04 \
  --ssh-key my-key --user-data-from-file cloud-init.yml
```

Or with Terraform:
```bash
terraform destroy -auto-approve && terraform apply -auto-approve
```

### Dedicated (AX): The Robot API Path

Hetzner's Robot API (`https://robot-ws.your-server.de`) supports programmatic OS reinstall via rescue mode + `installimage`. Auth is HTTP Basic (credentials from Robot panel > Settings > Web service).

**Wipe and rebuild (~8-12 min):**

```bash
#!/bin/bash
SERVER_NUM="123456"
SERVER_IP="1.2.3.4"
API="https://robot-ws.your-server.de"
AUTH="robot-user:robot-pass"

# 1. Activate rescue system (~5s API call)
curl -s -u "$AUTH" "$API/boot/$SERVER_NUM/rescue" \
  -d "os=linux&authorized_key[]=$SSH_FINGERPRINT"

# 2. Hardware reset
curl -s -u "$AUTH" "$API/reset/$SERVER_NUM" -d "type=hw"

# 3. Wait for rescue SSH (~60-90s)
sleep 60
until ssh -o ConnectTimeout=5 root@$SERVER_IP true 2>/dev/null; do sleep 5; done

# 4. Upload unattended install config + run
ssh root@$SERVER_IP "cat > /autosetup" <<'AUTOSETUP'
DRIVE1 /dev/nvme0n1
DRIVE2 /dev/nvme1n1
SWRAID 1
SWRAIDLEVEL 1
HOSTNAME ci-runner
PART /boot ext4 1G
PART lvm vg0 all
LV vg0 root / ext4 all
IMAGE /root/.oldroot/nfs/images/Ubuntu-2404-noble-amd64-base.tar.gz
AUTOSETUP

ssh root@$SERVER_IP "installimage && reboot"

# 5. Wait for OS boot (~90-120s)
sleep 90
until ssh -o ConnectTimeout=5 root@$SERVER_IP true 2>/dev/null; do sleep 5; done

# 6. Post-install: Docker + CI image
ssh root@$SERVER_IP "apt-get update -qq && apt-get install -y -qq docker.io && \
  systemctl enable docker && systemctl start docker && \
  docker pull buckaroo-ci:latest"
```

**Timing breakdown:**
| Phase | Time |
|-------|------|
| Rescue activation + reset | ~5s (API calls) |
| Rescue system boot | ~60-90s |
| installimage on NVMe | ~3-5 min |
| Reboot into new OS | ~60-90s |
| apt + Docker install | ~2-3 min |
| **Total** | **~8-12 min** |

For dedicated servers, Ansible is the production-grade option. Community playbooks exist ([mwiget/hetzner-ansible](https://github.com/mwiget/hetzner-ansible), [palark/hetzner-bare-metal-ansible](https://github.com/palark/hetzner-bare-metal-ansible)) that wrap the rescue → installimage → provision flow into ~31 idempotent tasks.

### Recommendation

**Start with Cloud CCX33.** Same price as dedicated, dramatically simpler automation (cloud-init, official Terraform provider, 2-minute wipe cycle). The 2.3x CPU gap matters less than expected for CI — Playwright is wait-bound, not CPU-bound.

If the CCX33 proves CPU-limited during parallel test phases, upgrade to dedicated AX42. The Docker Compose setup is identical — only the host provisioning layer changes.

---

## Expected Performance

Running Forgejo (or bare git hooks) + Docker Compose sidecar with volume-mounted caches.

| Scenario | Cloud CCX33 | Dedicated AX42 |
|----------|------------|----------------|
| Warm push (no lockfile change) | ~55-75s | ~45-65s |
| Cold push (lockfiles changed) | ~100-140s | ~90-120s |
| Full wipe + reprovision | ~2-3 min | ~8-12 min |

Compared to current Depot CI: **~3.5 min critical path.**
