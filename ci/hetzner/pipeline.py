#!/usr/bin/env python3
"""
CI pipeline entry point — Python replacement for run-ci.sh orchestration.

Usage (inside container):
    python3 /opt/ci-runner/pipeline.py SHA BRANCH [--fast-fail] [--only-jobs=...] ...

Job bodies remain as shell scripts in ci/hetzner/jobs/. This module handles
DAG scheduling, parallelism, filtering, caching, and status reporting.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Allow imports when running from /opt/ci-runner/ or /repo/ci/hetzner/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dsl import Job, Cache, Pipeline
from lib.status import status_pending, status_success, status_failure
from lib.lockcheck import lockcheck_valid, lockcheck_update, rebuild_deps
from lib.cleanup import cleanup_processes, snapshot_container_state


# ── Caches ────────────────────────────────────────────────────────────────────

JS_CACHE_DIR = "/opt/ci/js-cache"

js_cache = Cache(
    key_cmd=(
        "git ls-tree -r HEAD "
        "packages/buckaroo-js-core/src/ "
        "packages/buckaroo-js-core/package.json "
        "packages/buckaroo-js-core/tsconfig.json "
        "packages/buckaroo-js-core/vite.config.ts "
        "2>/dev/null | sha256sum | cut -c1-16"
    ),
    artifact_path="packages/buckaroo-js-core/dist",
    store_dir=JS_CACHE_DIR,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str, log_dir: Path) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(log_dir / "ci.log", "a") as f:
        f.write(line + "\n")


def log_url(sha: str) -> str:
    server_ip = os.environ.get("HETZNER_SERVER_IP", "localhost")
    return f"http://{server_ip}:9000/logs/{sha}"


def sh(cmd: str, cwd: str = "/repo") -> int:
    return subprocess.run(cmd, shell=True, cwd=cwd).returncode


# ── Job definitions ───────────────────────────────────────────────────────────

def runner_dir() -> str:
    return os.environ.get("CI_RUNNER_DIR", "/opt/ci-runner")


def job_script(name: str) -> str:
    return f"bash {runner_dir()}/jobs/{name}"


def make_jobs(js_tree_hash: str, js_cached: bool) -> list[Job]:
    """Build the full list of CI jobs."""
    rd = runner_dir()

    return [
        Job(
            name="lint-python",
            cmd=job_script("lint_python.sh"),
            nice=10,
        ),
        Job(
            name="build-js",
            cmd=job_script("build_js.sh"),
            nice=-10,
            fast_fail=True,
            env={
                "JS_CACHE_DIR": JS_CACHE_DIR,
                "JS_TREE_HASH": js_tree_hash,
                "JS_DIST_CACHED": "1" if js_cached else "0",
            },
        ),
        Job(
            name="test-js",
            cmd=job_script("test_js.sh"),
            nice=10,
        ),
        Job(
            name="test-python-3.11",
            cmd=f"{job_script('test_python.sh')} 3.11",
            nice=10,
        ),
        Job(
            name="test-python-3.13",
            cmd=f"{job_script('test_python.sh')} 3.13",
            nice=10,
        ),
        Job(
            name="build-wheel",
            cmd=job_script("build_wheel.sh"),
            depends_on=["build-js"],
            nice=-10,
            fast_fail=True,
        ),
        Job(
            name="jupyter-warmup",
            cmd=job_script("jupyter_warmup.sh"),
            outputs={"venv": "/tmp/ci-jupyter-warmup-venv"},
            env={"CI_RUNNER_DIR": rd},
        ),
        Job(
            name="playwright-storybook",
            cmd=job_script("pw_storybook.sh"),
            depends_on=["build-js"],
            nice=10,
        ),
        Job(
            name="test-mcp-wheel",
            cmd=job_script("test_mcp_wheel.sh"),
            depends_on=["build-wheel"],
            nice=10,
        ),
        Job(
            name="playwright-marimo",
            cmd=job_script("pw_marimo.sh"),
            depends_on=["build-wheel"],
        ),
        Job(
            name="playwright-server",
            cmd=job_script("pw_server.sh"),
            depends_on=["build-wheel"],
        ),
        Job(
            name="playwright-wasm-marimo",
            cmd=job_script("pw_wasm_marimo.sh"),
            delay=2,
        ),
        Job(
            name="smoke-test-extras",
            cmd=job_script("smoke_test_extras.sh"),
            depends_on=["build-wheel"],
            delay=2,
        ),
        Job(
            name="test-python-3.12",
            cmd=f"{job_script('test_python.sh')} 3.12",
            depends_on=["build-wheel"],
            delay=10,
            nice=10,
        ),
        Job(
            name="test-python-3.14",
            cmd=f"{job_script('test_python.sh')} 3.14",
            depends_on=["build-wheel"],
            delay=10,
            nice=10,
        ),
        Job(
            name="playwright-jupyter",
            cmd=job_script("pw_jupyter.sh"),
            depends_on=["build-wheel", "jupyter-warmup"],
            timeout=120,
            env={"CI_RUNNER_DIR": rd},
        ),
    ]


# ── Phase 5b: standalone pw-jupyter ──────────────────────────────────────────

def run_phase_5b(sha: str, branch: str, wheel_from: str, log_dir: Path) -> int:
    """Standalone pw-jupyter using cached wheel from a prior run."""
    wheel_cache_dir = f"/opt/ci/wheel-cache/{wheel_from or sha}"
    result = subprocess.run(
        f"ls {wheel_cache_dir}/buckaroo-*.whl 2>/dev/null | head -1",
        shell=True, capture_output=True, text=True,
    )
    wheel_path = result.stdout.strip()
    if not wheel_path:
        log(f"ERROR: no cached wheel at {wheel_cache_dir}", log_dir)
        return 1

    sh(f"mkdir -p dist && cp {wheel_path} dist/")
    log(f"Loaded cached wheel: {Path(wheel_path).name}", log_dir)

    # Extract static files from wheel
    sh("""python3 -c "
import zipfile, glob
wheel = glob.glob('dist/buckaroo-*.whl')[0]
with zipfile.ZipFile(wheel) as z:
    for name in z.namelist():
        if name.startswith('buckaroo/static/'):
            z.extract(name, '.')
print('Extracted static files from wheel')
" """)

    log("=== Phase 5b (standalone): playwright-jupyter ===", log_dir)

    rd = runner_dir()
    jobs = [
        Job("jupyter-warmup", cmd=job_script("jupyter_warmup.sh"),
            env={"CI_RUNNER_DIR": rd}),
        Job("playwright-jupyter", cmd=job_script("pw_jupyter.sh"),
            depends_on=["jupyter-warmup"], timeout=120,
            env={"CI_RUNNER_DIR": rd}),
    ]
    pipeline = Pipeline(jobs=jobs, sha=sha, branch=branch, log_dir=log_dir)
    return pipeline.run()


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CI pipeline runner")
    p.add_argument("sha", help="Git commit SHA")
    p.add_argument("branch", help="Git branch name")
    p.add_argument("--phase", default="all")
    p.add_argument("--wheel-from", default="")
    p.add_argument("--fast-fail", action="store_true")
    p.add_argument("--only-jobs", default="")
    p.add_argument("--skip-jobs", default="")
    p.add_argument("--only-testcases", default="")
    p.add_argument("--first-jobs", default="")
    p.add_argument("--first-testcases", default="")
    p.add_argument("--pytest-workers", type=int, default=4)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    sha = args.sha
    branch = args.branch
    log_dir = Path(f"/opt/ci/logs/{sha}")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Capture versions
    rd = runner_dir()
    capture_versions = Path(rd) / "capture-versions.sh"
    if capture_versions.exists():
        subprocess.run(
            ["bash", str(capture_versions)],
            stdout=open(log_dir / "versions.txt", "w"),
            stderr=subprocess.STDOUT,
        )

    # Pre-run snapshot
    snapshot_container_state("before-cleanup", str(log_dir / "container-before.txt"))

    # Cleanup
    cleanup_processes()

    # Post-cleanup snapshot
    snapshot_container_state("after-cleanup", str(log_dir / "container-after.txt"))

    status_pending(sha, "ci/hetzner", f"Running CI (phase={args.phase})...", log_url(sha))

    # Phase 5b: standalone pw-jupyter
    if args.phase == "5b":
        rc = run_phase_5b(sha, branch, args.wheel_from, log_dir)
        if rc == 0:
            status_success(sha, "ci/hetzner", "All checks passed", log_url(sha))
        else:
            status_failure(sha, "ci/hetzner", "CI failed — see logs", log_url(sha))
        return rc

    # ── Full CI ───────────────────────────────────────────────────────────────

    # Git checkout
    os.chdir("/repo")
    sh("git fetch origin")
    sh(f"git checkout -f {sha}")
    sh("git clean -fdx "
       "--exclude='packages/buckaroo-js-core/node_modules' "
       "--exclude='packages/js/node_modules' "
       "--exclude='packages/node_modules'")

    # Lockfile check
    if lockcheck_valid():
        log("Lockfiles unchanged — using warm caches", log_dir)
    else:
        log("Lockfiles changed — rebuilding deps", log_dir)
        rebuild_deps()
        lockcheck_update()

    # JS cache
    js_cached = js_cache.restore()
    js_tree_hash = js_cache._key()
    if js_cached:
        log(f"JS build cache HIT ({js_tree_hash})", log_dir)
    else:
        log(f"JS build cache MISS ({js_tree_hash})", log_dir)

    # Create empty static files so Python unit tests can import buckaroo
    Path("buckaroo/static").mkdir(parents=True, exist_ok=True)
    for f in ["compiled.css", "widget.js", "widget.css"]:
        Path(f"buckaroo/static/{f}").touch()

    # Build job list
    jobs = make_jobs(js_tree_hash, js_cached)

    # Cache wheel after build-wheel completes
    # (handled via a post-completion hook — the pipeline stores it)

    pipeline = Pipeline(
        jobs=jobs,
        sha=sha,
        branch=branch,
        log_dir=log_dir,
        timeout=int(os.environ.get("CI_TIMEOUT", "180")),
    )

    # Parse filter args
    only_jobs = [j for j in args.only_jobs.split(",") if j] or None
    skip_jobs = [j for j in args.skip_jobs.split(",") if j] or None
    first_jobs = [j for j in args.first_jobs.split(",") if j] or None

    # Mutual exclusion checks
    if first_jobs and only_jobs:
        log("ERROR: --first-jobs and --only-jobs are mutually exclusive", log_dir)
        return 1
    if args.first_testcases and args.only_testcases:
        log("ERROR: --first-testcases and --only-testcases are mutually exclusive", log_dir)
        return 1

    log(f"CI pipeline: phase={args.phase}"
        f"{'  only-jobs=' + args.only_jobs if args.only_jobs else ''}"
        f"{'  skip-jobs=' + args.skip_jobs if args.skip_jobs else ''}"
        f"{'  first-jobs=' + args.first_jobs if args.first_jobs else ''}", log_dir)
    log(f"Checkout {sha} (branch: {branch})", log_dir)

    rc = pipeline.run(
        fast_fail=args.fast_fail,
        only_jobs=only_jobs,
        skip_jobs=skip_jobs,
        first_jobs=first_jobs,
        only_testcases=args.only_testcases,
        first_testcases=args.first_testcases,
        pytest_workers=args.pytest_workers,
    )

    # Cache wheel
    wheel_cache = Path(f"/opt/ci/wheel-cache/{sha}")
    wheel_cache.mkdir(parents=True, exist_ok=True)
    sh(f"cp dist/buckaroo-*.whl {wheel_cache}/ 2>/dev/null || true")

    # End-of-run snapshot
    snapshot_container_state("end-of-run", str(log_dir / "container-end.txt"))

    # Final status
    if rc == 0:
        log(f"=== ALL JOBS PASSED (phase={args.phase}) ===", log_dir)
        status_success(sha, "ci/hetzner", "All checks passed", log_url(sha))
        Path("/opt/ci/last-success").touch()
    else:
        log(f"=== SOME JOBS FAILED — see {log_url(sha)} ===", log_dir)
        status_failure(sha, "ci/hetzner", "CI failed — see logs", log_url(sha))

    return rc


if __name__ == "__main__":
    sys.exit(main())
