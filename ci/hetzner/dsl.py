"""
CI DAG runner — stdlib-only Python replacement for run-ci.sh orchestration.

Provides Job, Cache, and Pipeline primitives. Job bodies remain shell scripts;
this module handles DAG scheduling, parallelism, filtering, fast-fail, caching,
and state passing.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Job:
    name: str
    cmd: str | list[str]
    depends_on: list[str] = field(default_factory=list)
    nice: int = 0
    delay: float = 0
    fast_fail: bool = False
    timeout: int = 120
    outputs: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Cache:
    key_cmd: str
    artifact_path: str
    store_dir: str

    def _key(self) -> str:
        result = subprocess.run(
            self.key_cmd, shell=True, capture_output=True, text=True, cwd="/repo",
        )
        return result.stdout.strip()

    def restore(self) -> bool:
        key = self._key()
        cached = Path(self.store_dir) / key
        if cached.is_dir():
            dest = Path(self.artifact_path)
            if dest.exists():
                subprocess.run(["rm", "-rf", str(dest)])
            subprocess.run(["cp", "-r", str(cached), str(dest)])
            return True
        return False

    def store(self) -> None:
        key = self._key()
        src = Path(self.artifact_path)
        if not src.exists():
            return
        dest = Path(self.store_dir) / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            subprocess.run(["rm", "-rf", str(dest)])
        subprocess.run(["cp", "-r", str(src), str(dest)])


def _log(msg: str, log_dir: Path) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_file = log_dir / "ci.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")


class Pipeline:
    def __init__(
        self,
        jobs: list[Job],
        sha: str,
        branch: str,
        log_dir: Path,
        timeout: int = 180,
        cwd: str = "/repo",
    ):
        self.jobs = {j.name: j for j in jobs}
        self.sha = sha
        self.branch = branch
        self.log_dir = log_dir
        self.timeout = timeout
        self.cwd = cwd
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str) -> None:
        _log(msg, self.log_dir)

    def run(
        self,
        fast_fail: bool = False,
        only_jobs: list[str] | None = None,
        skip_jobs: list[str] | None = None,
        first_jobs: list[str] | None = None,
        only_testcases: str = "",
        first_testcases: str = "",
        pytest_workers: int = 4,
    ) -> int:
        if first_testcases:
            # Phase 1: filtered run
            self.log("=== FIRST-TESTCASES Phase 1: filtered run ===")
            rc1 = self._run_dag(
                fast_fail=fast_fail, only_jobs=only_jobs, skip_jobs=skip_jobs,
                testcase_filter=first_testcases, pytest_workers=pytest_workers,
            )
            if fast_fail and rc1 != 0:
                self.log("FAST-FAIL: filtered testcases failed — skipping full suite")
                return rc1
            # Phase 2: full run
            self.log("=== FIRST-TESTCASES Phase 2: full suite ===")
            return self._run_dag(
                fast_fail=fast_fail, only_jobs=only_jobs, skip_jobs=skip_jobs,
                testcase_filter="", pytest_workers=pytest_workers,
            )

        if first_jobs:
            # Phase A: first-jobs only
            self.log(f"=== FIRST-JOBS Phase A: {','.join(first_jobs)} ===")
            rc_a = self._run_dag(
                fast_fail=fast_fail, only_jobs=first_jobs, skip_jobs=skip_jobs,
                pytest_workers=pytest_workers,
            )
            if fast_fail and rc_a != 0:
                self.log("FAST-FAIL: first-jobs failed — skipping Phase B")
                return rc_a
            # Phase B: remaining jobs
            remaining = [n for n in self.jobs if n not in first_jobs]
            self.log("=== FIRST-JOBS Phase B: remaining jobs ===")
            return self._run_dag(
                fast_fail=fast_fail, only_jobs=remaining, skip_jobs=skip_jobs,
                pytest_workers=pytest_workers,
            )

        return self._run_dag(
            fast_fail=fast_fail, only_jobs=only_jobs, skip_jobs=skip_jobs,
            testcase_filter=only_testcases, pytest_workers=pytest_workers,
        )

    def _run_dag(
        self,
        fast_fail: bool = False,
        only_jobs: list[str] | None = None,
        skip_jobs: list[str] | None = None,
        testcase_filter: str = "",
        pytest_workers: int = 4,
    ) -> int:
        # Determine which jobs to run
        runnable = set(self.jobs.keys())
        if only_jobs is not None:
            runnable = set(only_jobs) & runnable
        if skip_jobs:
            runnable -= set(skip_jobs)

        # Validate dependencies exist
        for name in runnable:
            for dep in self.jobs[name].depends_on:
                if dep not in self.jobs:
                    self.log(f"ERROR: job '{name}' depends on unknown job '{dep}'")
                    return 1

        # Track state
        completed: dict[str, int] = {}  # name → exit code
        running: dict[str, _RunningJob] = {}  # name → running info
        delayed: dict[str, float] = {}  # name → eligible_at timestamp
        overall = 0
        aborted = False

        # Watchdog
        deadline = time.monotonic() + self.timeout

        while True:
            now = time.monotonic()
            if now > deadline:
                self.log(f"TIMEOUT: CI exceeded {self.timeout}s")
                for rj in running.values():
                    _kill_tree(rj.pid)
                return 1

            # Start jobs whose deps are satisfied
            ready = []
            for name in runnable:
                if name in completed or name in running:
                    continue
                job = self.jobs[name]
                deps_ok = all(d in completed for d in job.depends_on)
                deps_passed = all(completed.get(d, 1) == 0 for d in job.depends_on)
                if not deps_ok:
                    continue
                # If a fast_fail dep failed, skip this job
                if not deps_passed and any(
                    self.jobs[d].fast_fail for d in job.depends_on if completed.get(d, 0) != 0
                ):
                    self.log(f"SKIP  {name} (dependency failed)")
                    completed[name] = 1
                    overall = 1
                    continue
                ready.append(name)

            for name in ready:
                job = self.jobs[name]
                if job.delay > 0 and name not in delayed:
                    delayed[name] = now + job.delay
                if name in delayed and now < delayed[name]:
                    continue

                # Start the job
                env = dict(os.environ)
                env.update(job.env)
                env["npm_config_store_dir"] = "/opt/pnpm-store"
                if testcase_filter:
                    # Convert comma-separated to pytest -k / PW --grep
                    env["PYTEST_K_FILTER"] = testcase_filter.replace(",", " or ")
                    env["PW_GREP_FILTER"] = testcase_filter.replace(",", "|")
                env["PYTEST_WORKERS"] = str(pytest_workers)

                log_file = self.log_dir / f"{name}.log"
                self.log(f"START {name}")

                cmd = job.cmd
                if isinstance(cmd, str):
                    cmd = ["bash", "-c", cmd]

                fh = open(log_file, "w")
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=fh, stderr=subprocess.STDOUT,
                        env=env, cwd=self.cwd,
                        preexec_fn=os.setpgrp,
                    )
                except Exception as e:
                    self.log(f"FAIL  {name}  (launch error: {e})")
                    fh.close()
                    completed[name] = 1
                    overall = 1
                    continue

                # Apply nice
                if job.nice != 0:
                    try:
                        os.setpriority(os.PRIO_PROCESS, proc.pid, job.nice)
                    except OSError:
                        pass

                running[name] = _RunningJob(
                    pid=proc.pid, proc=proc, fh=fh, job=job,
                    started=time.monotonic(),
                )

            # Poll running jobs
            finished = []
            for name, rj in running.items():
                rc = rj.proc.poll()
                # Per-job timeout
                if rc is None and (now - rj.started) > rj.job.timeout:
                    self.log(f"TIMEOUT {name} (>{rj.job.timeout}s)")
                    _kill_tree(rj.pid)
                    rc = -1
                if rc is not None:
                    rj.fh.close()
                    # pytest exit code 5 = no tests collected → treat as pass
                    if rc == 5:
                        rc = 0
                    if rc == 0:
                        self.log(f"PASS  {name}")
                    else:
                        log_url = os.environ.get("LOG_URL", "")
                        self.log(f"FAIL  {name}  (see {log_url}/{name}.log)")
                        overall = 1
                    completed[name] = rc
                    finished.append(name)

                    # Fast-fail check
                    if fast_fail and rc != 0 and rj.job.fast_fail:
                        self.log(f"FAST-FAIL: {name} failed — aborting remaining jobs")
                        aborted = True

            for name in finished:
                del running[name]

            if aborted:
                for rj in running.values():
                    _kill_tree(rj.pid)
                    rj.fh.close()
                for name in running:
                    completed[name] = 1
                running.clear()
                return 1

            # All done?
            active_or_pending = set(runnable) - set(completed.keys())
            if not active_or_pending:
                break

            # Nothing running and nothing can start → deadlock or all remaining
            # are waiting on failed deps
            if not running and not any(
                name for name in active_or_pending
                if name not in completed
                and all(d in completed for d in self.jobs[name].depends_on)
            ):
                for name in active_or_pending:
                    if name not in completed:
                        self.log(f"SKIP  {name} (unresolvable dependency)")
                        completed[name] = 1
                        overall = 1
                break

            time.sleep(0.1)

        return overall


@dataclass
class _RunningJob:
    pid: int
    proc: subprocess.Popen
    fh: object
    job: Job
    started: float


def _kill_tree(pid: int) -> None:
    """Kill a process group (all children)."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    time.sleep(0.5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
