# Plan: Python CI DSL to replace run-ci.sh

## Problem

`run-ci.sh` is 917 lines of bash managing a 16-job DAG with implicit dependencies
encoded in PID variables and wait ordering. The DAG is invisible — you have to read
the entire function to understand what depends on what. Adding a new job means
threading a PID variable through 6 places. Stagger delays, fast-fail, cpuset,
filtering, and state passing are all ad-hoc bash patterns bolted on over time.

## What changes, what doesn't

**Rewrite in Python (orchestration):**
- DAG definition and execution (~250 lines of bash → ~100 lines of Python)
- Job lifecycle (start, wait, log, timeout, nice)
- Filtering (--only-jobs, --skip-jobs, --first-jobs, --first-testcases)
- Fast-fail logic
- State passing between jobs
- Caching (JS build cache, wheel cache, lockcheck)
- GitHub status reporting
- Process cleanup

**Keep as shell (job bodies):**
- Each `job_*()` function stays as a shell script/command
- `test_playwright_jupyter_parallel.sh` stays as-is
- `scripts/full_build.sh`, `scripts/test_playwright_*.sh` stay as-is
- The Python DSL calls these via `subprocess`

**Don't touch:**
- `ci-queue.sh` — works fine, runs on the HOST not in the container
- `webhook.py` — already Python, just calls `ci-queue push`
- `docker-compose.yml`, `Dockerfile` — unchanged
- `update-runner.sh` — update to copy `.py` files instead of `.sh`

## Architecture

```
HOST                              CONTAINER
webhook.py                        ci/hetzner/pipeline.py   ← NEW (entry point)
  → ci-queue push SHA BRANCH        ├── ci/hetzner/dsl.py  ← NEW (Job, Pipeline, Cache)
     → docker exec bash ...          ├── ci/hetzner/jobs.py ← NEW (job definitions)
        → python3 pipeline.py        ├── ci/hetzner/lib/status.py   ← NEW (from status.sh)
                                     ├── ci/hetzner/lib/lockcheck.py ← NEW (from lockcheck.sh)
                                     └── ci/hetzner/lib/cleanup.py   ← NEW (from ci_pkill/kill_port)
```

`ci-queue.sh` changes one line: `bash /opt/ci-runner/run-ci.sh` → `python3 /opt/ci-runner/pipeline.py`.

## Primitives

### Job

```python
@dataclass
class Job:
    name: str
    cmd: str | list[str] | Callable    # shell command or Python callable
    depends_on: list[str] = field(default_factory=list)
    nice: int = 0                      # renice value (-20 to 19)
    delay: float = 0                   # seconds to wait before starting
    fast_fail: bool = False            # abort pipeline if this job fails
    timeout: int = 120                 # per-job timeout (seconds)
    outputs: dict[str, str] = field(default_factory=dict)  # name → file path
    cpuset: str | None = None          # cgroup cpuset (e.g. "0-11")
    env: dict[str, str] = field(default_factory=dict)      # extra env vars
```

A Job wraps a shell command. The `cmd` is either:
- A string: `"cd /repo && /opt/venvs/3.13/bin/ruff check"`
- A list: `["bash", "/opt/ci-runner/test_playwright_jupyter_parallel.sh", ...]`
- A callable: `lambda ctx: subprocess.run(...)` (for complex logic like smoke-test-extras)

### Cache

```python
@dataclass
class Cache:
    key_cmd: str              # shell command that prints the cache key to stdout
    artifact_path: str        # local path to cache (glob ok)
    store_dir: str            # persistent cache directory

    def hit(self) -> bool:
        """Check if cached artifact exists for current key."""
    def restore(self) -> bool:
        """Copy cached artifact to artifact_path. Returns True if hit."""
    def store(self) -> None:
        """Copy artifact_path to cache under current key."""
```

### Pipeline

```python
@dataclass
class Pipeline:
    jobs: list[Job]
    sha: str
    branch: str
    log_dir: Path
    timeout: int = 180                         # global watchdog
    status_context: str = "ci/hetzner"

    def run(self, **filters) -> int:
        """Execute the DAG. Returns 0 on all-pass, 1 on any failure."""
```

### The runner (inside Pipeline.run)

```python
def run(self, only_jobs=None, skip_jobs=None, fast_fail=False, ...):
    # 1. Topological sort based on depends_on
    # 2. Start jobs whose dependencies are all satisfied
    # 3. When a job finishes:
    #    - Log PASS/FAIL with timestamp
    #    - If fast_fail and job.fast_fail: kill remaining, return 1
    #    - Start any jobs whose dependencies are now all satisfied
    # 4. When all jobs done: return 0 if all passed, else 1
```

This is a standard DAG executor. ~80 lines of Python. The key operations:
- `subprocess.Popen(cmd, stdout=logfile, stderr=STDOUT, env=...)` — start a job
- `os.waitpid(pid, WNOHANG)` — poll for completion (non-blocking)
- `os.setpriority(PRIO_PROCESS, pid, nice)` — renice after start
- `select.select([...], timeout=0.1)` — event loop tick

## File-by-file plan

### 1. `ci/hetzner/dsl.py` — ~150 lines

The framework. Three classes: `Job`, `Cache`, `Pipeline`.

`Pipeline.run()` implements:
- DAG validation (cycle detection, missing dependency references)
- Topological scheduling with parallelism
- Per-job: log file capture, timeout, nice, delay, env
- Filtering: `only_jobs`, `skip_jobs`, `first_jobs` (two-phase execution)
- Testcase filtering: `only_testcases`, `first_testcases` (passed as env to jobs)
- Fast-fail: on critical job failure, SIGTERM remaining, wait, exit
- State passing: job `outputs` dict → file paths readable by downstream jobs
- Timestamped logging to `ci.log` (same `[HH:MM:SS] START/PASS/FAIL` format)

No external dependencies beyond stdlib (`subprocess`, `os`, `signal`, `json`, `time`,
`pathlib`, `dataclasses`, `hashlib`).

### 2. `ci/hetzner/jobs.py` — ~200 lines

All 16 job definitions. Each job is a `Job(...)` instance. Job bodies are shell
commands — keeps the existing working commands exactly as-is.

```python
from dsl import Job, Cache

js_cache = Cache(
    key_cmd="git ls-tree -r HEAD packages/buckaroo-js-core/src/ ... | sha256sum | cut -c1-16",
    artifact_path="packages/buckaroo-js-core/dist",
    store_dir="/opt/ci/js-cache",
)

lint_python = Job(
    name="lint-python",
    cmd="/opt/venvs/3.13/bin/ruff check",
    nice=10,
)

build_js = Job(
    name="build-js",
    cmd="cd /repo/packages && pnpm install --frozen-lockfile && cd buckaroo-js-core && pnpm run build",
    nice=-10,
    fast_fail=True,
)

def test_python(version):
    return Job(
        name=f"test-python-{version}",
        cmd=f"""
            cd /repo
            UV_PROJECT_ENVIRONMENT=/opt/venvs/{version} uv sync --locked --dev --all-extras
            # ... timing_dependent + regular split, same logic as current bash
        """,
        nice=10,
    )

build_wheel = Job(
    name="build-wheel",
    cmd="cd /repo && PNPM_STORE_DIR=/opt/pnpm-store bash scripts/full_build.sh",
    depends_on=["build-js"],
    nice=-10,
    fast_fail=True,
)

jupyter_warmup = Job(
    name="jupyter-warmup",
    cmd="bash /opt/ci-runner/job_jupyter_warmup.sh",
    outputs={"venv": "/tmp/ci-jupyter-warmup-venv", "pids": "/tmp/ci-jupyter-warmup-pids"},
)

playwright_jupyter = Job(
    name="playwright-jupyter",
    cmd="bash /opt/ci-runner/job_playwright_jupyter.sh",
    depends_on=["build-wheel", "jupyter-warmup"],
    nice=-10,
    timeout=120,
)

# Staggered jobs — delay reduces CPU contention with pw-jupyter
test_python_312 = Job(
    name="test-python-3.12",
    cmd=test_python_cmd("3.12"),
    depends_on=["build-wheel"],
    delay=10,
    nice=10,
)

smoke_test_extras = Job(
    name="smoke-test-extras",
    cmd="bash /opt/ci-runner/job_smoke_test_extras.sh",
    depends_on=["build-wheel"],
    delay=2,
)

# ... etc for all 16 jobs

ALL_JOBS = [
    lint_python, build_js, test_js,
    test_python("3.11"), test_python("3.13"),
    build_wheel, jupyter_warmup,
    playwright_storybook, playwright_jupyter,
    test_mcp_wheel, playwright_marimo, playwright_server,
    playwright_wasm_marimo, smoke_test_extras,
    test_python("3.12"), test_python("3.14"),
]
```

### 3. `ci/hetzner/pipeline.py` — ~80 lines

Entry point. Replaces `run-ci.sh`. Handles:
- CLI arg parsing (sha, branch, --phase, --fast-fail, --only-jobs, etc.)
- Pre-run cleanup (extracted from current lines 186-242)
- Lockfile check + dep rebuild
- JS cache restore
- Git fetch + checkout
- Pipeline execution
- Post-run: status reporting, container state snapshot

```python
#!/usr/bin/env python3
"""CI pipeline entry point. Replaces run-ci.sh."""
import argparse, sys
from pathlib import Path
from dsl import Pipeline
from jobs import ALL_JOBS, js_cache
from lib.cleanup import cleanup_processes
from lib.lockcheck import lockcheck_valid, lockcheck_update, rebuild_deps
from lib.status import status_pending, status_success, status_failure

def main():
    args = parse_args()

    # Pre-run cleanup
    cleanup_processes()

    # Git checkout
    sh(f"git fetch origin && git checkout -f {args.sha}")
    sh("git clean -fdx --exclude=packages/*/node_modules")

    # JS cache
    js_cache.restore()

    # Lockcheck
    if not lockcheck_valid():
        rebuild_deps()
        lockcheck_update()

    # Create empty static files for Python imports
    Path("buckaroo/static").mkdir(parents=True, exist_ok=True)
    for f in ["compiled.css", "widget.js", "widget.css"]:
        Path(f"buckaroo/static/{f}").touch()

    status_pending(args.sha, "ci/hetzner", "Running CI...", log_url(args.sha))

    pipeline = Pipeline(
        jobs=ALL_JOBS,
        sha=args.sha,
        branch=args.branch,
        log_dir=Path(f"/opt/ci/logs/{args.sha}"),
        timeout=180,
    )

    rc = pipeline.run(
        fast_fail=args.fast_fail,
        only_jobs=args.only_jobs,
        skip_jobs=args.skip_jobs,
        first_jobs=args.first_jobs,
        only_testcases=args.only_testcases,
        first_testcases=args.first_testcases,
    )

    if rc == 0:
        status_success(args.sha, "ci/hetzner", "All checks passed", log_url(args.sha))
    else:
        status_failure(args.sha, "ci/hetzner", "CI failed", log_url(args.sha))

    sys.exit(rc)
```

### 4. `ci/hetzner/lib/status.py` — ~25 lines

Direct port of `status.sh`. Uses `urllib.request` (no deps).

```python
import json, os, urllib.request

def _github_status(state, sha, context, description, target_url):
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "buckaroo-data/buckaroo")
    if not token:
        return
    url = f"https://api.github.com/repos/{repo}/statuses/{sha}"
    data = json.dumps({"state": state, "context": context,
                       "description": description[:140], "target_url": target_url}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def status_pending(sha, ctx, msg, url):  _github_status("pending", sha, ctx, msg, url)
def status_success(sha, ctx, msg, url):  _github_status("success", sha, ctx, msg, url)
def status_failure(sha, ctx, msg, url):  _github_status("failure", sha, ctx, msg, url)
```

### 5. `ci/hetzner/lib/lockcheck.py` — ~40 lines

Direct port of `lockcheck.sh`.

### 6. `ci/hetzner/lib/cleanup.py` — ~50 lines

Port of `ci_pkill()`, `kill_port()`, and the temp file cleanup block.

### 7. Extract job bodies to standalone scripts

The complex job functions (`job_jupyter_warmup`, `job_test_python`,
`job_playwright_jupyter_warm`, `job_smoke_test_extras`) get extracted from
`run-ci.sh` into standalone shell scripts in `ci/hetzner/jobs/`:

```
ci/hetzner/jobs/
    lint_python.sh        # one-liner, trivial
    build_js.sh           # pnpm install + build + cache
    test_js.sh            # one-liner
    test_python.sh        # takes version as $1, handles timing_dependent split
    build_wheel.sh        # calls full_build.sh
    test_mcp_wheel.sh     # venv + wheel install + pytest
    smoke_test_extras.sh  # 6 parallel venvs
    jupyter_warmup.sh     # server startup + kernel warmup
    pw_jupyter.sh         # the warm variant (reads /tmp/ci-jupyter-warmup-venv)
    pw_storybook.sh       # wrapper
    pw_server.sh          # wrapper
    pw_marimo.sh          # wrapper
    pw_wasm_marimo.sh     # wrapper
```

Most of these are direct copy-paste from the current `job_*()` functions. The
wrappers are 3-5 lines each. The complex ones (test_python, jupyter_warmup,
smoke_test_extras) are 30-80 lines.

This extraction is the largest mechanical change but zero risk — same code, just
in separate files instead of one giant function.

## Migration strategy

### Phase 0: Extract job bodies (no Python yet)

Split each `job_*()` function out of `run-ci.sh` into `ci/hetzner/jobs/*.sh`.
Update `run-ci.sh` to source them: `job_lint_python() { bash "$CI_RUNNER_DIR/jobs/lint_python.sh"; }`.

Run CI. Verify identical behavior. This is a pure refactor with zero risk.

### Phase 1: Python DSL (shadow mode)

Write `dsl.py`, `jobs.py`, `pipeline.py`. Run the Python pipeline alongside the
bash pipeline on the same SHA. Compare:
- Same jobs ran
- Same pass/fail per job
- Same log output format (so existing log parsing works)
- Total time within 2s of bash version

The Python pipeline writes to a separate log dir (`/opt/ci/logs/$SHA/python/`)
for comparison.

### Phase 2: Cutover

Replace `bash /opt/ci-runner/run-ci.sh` with `python3 /opt/ci-runner/pipeline.py`
in `ci-queue.sh`. Keep `run-ci.sh` as a fallback (rename to `run-ci-legacy.sh`).

### Phase 3: Cleanup

Remove `run-ci.sh`. Update `update-runner.sh` to copy Python files.

## What the DAG looks like in Python vs bash

**Current bash (lines 730-849) — 120 lines:**
```bash
run_job lint-python            job_lint_python                & PID_LINT=$!
maybe_renice -n 10 -p $PID_LINT
run_job build-js               job_build_js                   & PID_BUILDJS=$!
maybe_renice -n -10 -p $PID_BUILDJS
# ... 15 more jobs with PID threading ...
wait $PID_BUILDJS || OVERALL=1
if [[ $FAST_FAIL -eq 1 && $OVERALL -ne 0 ]]; then ...
run_job build-wheel job_build_wheel & PID_WHEEL=$!
# ... more wait/check/start cycles ...
```

**Python equivalent — the full DAG is the job list in `jobs.py`:**
```python
ALL_JOBS = [
    Job("lint-python",          "ruff check",                    nice=10),
    Job("build-js",             "pnpm install && pnpm run build", nice=-10, fast_fail=True),
    Job("test-js",              "pnpm run test",                  nice=10),
    Job("test-python-3.11",     "bash jobs/test_python.sh 3.11",  nice=10),
    Job("test-python-3.13",     "bash jobs/test_python.sh 3.13",  nice=10),
    Job("build-wheel",          "bash scripts/full_build.sh",     depends_on=["build-js"], fast_fail=True),
    Job("jupyter-warmup",       "bash jobs/jupyter_warmup.sh",    outputs={"venv": "/tmp/ci-jupyter-warmup-venv"}),
    Job("pw-storybook",         "bash jobs/pw_storybook.sh",      depends_on=["build-js"]),
    Job("test-mcp-wheel",       "bash jobs/test_mcp_wheel.sh",    depends_on=["build-wheel"]),
    Job("pw-marimo",            "bash jobs/pw_marimo.sh",         depends_on=["build-wheel"]),
    Job("pw-server",            "bash jobs/pw_server.sh",         depends_on=["build-wheel"]),
    Job("pw-wasm-marimo",       "bash jobs/pw_wasm_marimo.sh",    delay=2),
    Job("smoke-test-extras",    "bash jobs/smoke_test_extras.sh", depends_on=["build-wheel"], delay=2),
    Job("test-python-3.12",     "bash jobs/test_python.sh 3.12",  depends_on=["build-wheel"], delay=10),
    Job("test-python-3.14",     "bash jobs/test_python.sh 3.14",  depends_on=["build-wheel"], delay=10),
    Job("pw-jupyter",           "bash jobs/pw_jupyter.sh",        depends_on=["build-wheel", "jupyter-warmup"], timeout=120),
]
```

The DAG is the data. Adding a new job is one line. Dependencies are explicit.

## Risks

- **Subprocess overhead:** Python's `subprocess.Popen` adds ~5ms per job start vs
  bash `&`. With 16 jobs, this is 80ms total. Negligible.
- **Python not available in container:** The container already has Python 3.11-3.14.
  The pipeline runs with `/opt/venvs/3.13/bin/python3`.
- **Log format change:** The `[HH:MM:SS] START/PASS/FAIL` format must be preserved
  exactly — existing log parsing and the CLAUDE.md reporting instructions depend on it.
- **Phase 5b / --phase routing:** The standalone pw-jupyter mode must be preserved.
  Handle in `pipeline.py` as a special case before DAG execution.
- **Wheel-install-during-warmup overlap:** The current bash does a polling loop
  (`while [[ ! -f /tmp/ci-jupyter-warmup-venv ]]; do sleep 0.2; done`) to install
  the wheel into the jupyter venv as soon as both wheel and venv are ready. In the
  Python DSL, this becomes a job with `depends_on=["build-wheel"]` plus a state
  file check — cleaner, same behavior.

## Effort estimate

| Phase | Work | Risk |
|-------|------|------|
| Phase 0: Extract job bodies | 2 hours | Zero (pure refactor) |
| Phase 1: Python DSL + shadow mode | 1 day | Low (runs alongside bash) |
| Phase 2: Cutover | 30 min | Medium (one-line change in ci-queue.sh) |
| Phase 3: Cleanup | 30 min | Low (delete old file) |

## Non-goals

- Don't rewrite job bodies in Python. Shell is fine for `pnpm install`, `uv sync`,
  `pytest`, `playwright test`. The DSL orchestrates, jobs execute.
- Don't add a config file (YAML/TOML). The DAG is Python code — type-checked,
  lintable, refactorable.
- Don't use asyncio. The DAG runner is a simple poll loop with `os.waitpid(WNOHANG)`.
  16 jobs don't need an event loop.
- Don't add external dependencies. Stdlib only.
