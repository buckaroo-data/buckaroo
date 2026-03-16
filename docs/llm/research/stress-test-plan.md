# Stress Test Plan — Hetzner CI Reliability Validation

**Branch:** docs/ci-research
**Server:** Vultr 32 vCPU / 64 GB (45.76.18.207)
**Script:** `ci/hetzner/stress-test.sh`

---

## Goal

Run the Hetzner CI against a corpus of historical commits to measure pass rate, timing stability, and flake patterns. The stress test answers: "Does the CI runner produce correct, repeatable results across diverse codebases?"

## Commit Corpus

42 pre-baked merge commits across 3 categories. Each is a synthetic merge: old application code + latest test infrastructure from `82c148b` (docs/ci-research HEAD). Created by `ci/hetzner/create-merge-commits.sh`, pushed as `synth/*` branches.

| Set | Count | Description |
|-----|-------|-------------|
| `safe` | 16 | Recent main commits (2026-02-23 → 2026-02-28), all passed GitHub CI |
| `failing` | 10 | Commits that failed at least one GitHub Actions check (Playwright, pytest, lint) |
| `older` | 16 | Jan–mid Feb 2026, pre-CI or early CI era |

5 original failing commits (cf7e02a, e0f358a, 7b3141c, 516a1fa, f01c9c6) were not available in the local clone and are excluded.

### Why synthetic merges?

Old commits lack the CI runner scripts, Playwright tests, and build infrastructure the Hetzner runner depends on. A naive `git checkout <old-sha>` would fail immediately because `run-ci.sh`, `full_build.sh`, pw-tests/, etc. don't exist.

The synthetic merge overlays these paths from `82c148b` onto the old SHA:
- `ci/hetzner/` — runner scripts
- `packages/buckaroo-js-core/pw-tests/` — Playwright test specs
- `scripts/test_playwright_*.sh`, `scripts/full_build.sh`, `scripts/smoke_test.py`, `scripts/serve-wasm-marimo.sh` — build/test scripts

App code (buckaroo/, packages/buckaroo-js-core/src/, tests/, pyproject.toml, etc.) comes from the original commit. This tests whether the CI runner handles real code variation — different dependencies, different component implementations, different Python/JS APIs — while the test harness remains constant.

Each merge commit has two parents (old SHA + 82c148b) for traceability via `git log --graph`.

## How to Run

### Quick validation (safe set, default runner)
```bash
bash ci/hetzner/stress-test.sh --dry-run          # preview
bash ci/hetzner/stress-test.sh --limit=3           # first 3 commits
bash ci/hetzner/stress-test.sh                     # all 16 safe commits
```

### Full corpus
```bash
bash ci/hetzner/stress-test.sh --set=all           # all 42 commits
```

### With DAG runner
```bash
bash ci/hetzner/stress-test.sh --dag --set=safe
```

### Unattended (on server via tmux)
```bash
ssh root@45.76.18.207
tmux new -s stress
bash stress-test.sh --dag --set=all
# Ctrl-B D to detach
```

## Data Collected Per Commit

| File | Contents |
|------|----------|
| `<sha>.log` | Full CI output |
| `resources-<sha>.csv` | CPU idle% + memory at 2s intervals |
| `jobs-<sha>.csv` | Per-job start/end/duration/status parsed from ci.log |
| `summary.txt` | Pass/fail table for the run |
| `all-jobs.csv` | Combined job timing across all commits |

All stored on server at `/opt/ci/logs/stress-<runner>-<set>/`.

## What to Measure

### 1. Pass rate by set
- **Safe set target:** 100% (16/16). Any failure is a CI runner bug or flake.
- **Failing set:** Expect some failures (app bugs), but failures should be in the _same jobs_ as GitHub Actions. Different failure patterns indicate runner issues.
- **Older set:** Exploratory — these may fail due to missing dependencies or API changes.

### 2. Timing stability
- Wall-clock time per commit (expect ~1m40s ± 15s on 32 vCPU)
- Per-job duration variance across runs (from `all-jobs.csv`)
- Critical path consistency: pw-jupyter should be ~52s ± 10s

### 3. Flake detection
- Run safe set 2–3× back-to-back
- Any commit that passes once and fails once is a flake
- Cross-reference flaky jobs against known issues (pw-jupyter timeout, marimo WASM)

### 4. Resource pressure
- Peak memory from `resources-<sha>.csv` — should stay under 80% of 64GB
- CPU saturation — idle% should not drop to 0% for sustained periods

## Interpreting Results

**All safe commits pass:** Runner is reliable. Ship it.

**1–2 safe commits fail:** Investigate the specific commit. Check if the app code is incompatible with the overlaid test infra (e.g., renamed component that a Playwright test references). If so, that's expected — not a runner bug.

**Widespread failures across safe set:** Runner bug. Check ci.log for the failing job, compare with a known-good run.

**Failing set matches GitHub Actions failures:** Good — runner reproduces real CI behavior.

**Failing set has _different_ failures than GitHub Actions:** Interesting — could be runner-specific issues (Docker environment, timing, resource limits) or could mean the runner is more/less strict than GitHub Actions.

## Previous Results

From `ci-tuning-experiments.md`, the current best config (P=9, 2s stagger, 64GB) achieved:
- **1m40s total, all jobs PASS** on commit 634452d
- Confirmed 2/2 back-to-back runs
- Critical path: warmup(20s) → wheel-install(3s) → pw-jupyter(52s) → test-python(24s) = 99s

The stress test extends this from 1 commit to 42, validating that the result holds across code variation.
