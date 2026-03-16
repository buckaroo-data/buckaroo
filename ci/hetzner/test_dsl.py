"""Tests for the CI DAG runner (dsl.py)."""
import tempfile
from pathlib import Path

from dsl import Job, Pipeline


def test_simple_pass():
    """Two independent jobs that both pass."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("a", cmd="true"),
            Job("b", cmd="true"),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run() == 0
        assert (log_dir / "a.log").exists()
        assert (log_dir / "b.log").exists()
        ci_log = (log_dir / "ci.log").read_text()
        assert "PASS  a" in ci_log
        assert "PASS  b" in ci_log


def test_simple_fail():
    """A failing job returns non-zero overall."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("good", cmd="true"),
            Job("bad", cmd="false"),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run() != 0
        ci_log = (log_dir / "ci.log").read_text()
        assert "PASS  good" in ci_log
        assert "FAIL  bad" in ci_log


def test_dependency_ordering():
    """Job B depends on A; B should not start until A finishes."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        marker = Path(td) / "marker"
        jobs = [
            Job("a", cmd=f"touch {marker}"),
            Job("b", cmd=f"test -f {marker}", depends_on=["a"]),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run() == 0


def test_fast_fail():
    """Fast-fail aborts remaining jobs when a critical job fails."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("critical", cmd="false", fast_fail=True),
            Job("downstream", cmd="true", depends_on=["critical"]),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        rc = p.run(fast_fail=True)
        assert rc != 0
        ci_log = (log_dir / "ci.log").read_text()
        assert "FAST-FAIL" in ci_log


def test_skip_jobs():
    """--skip-jobs prevents a job from running."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("a", cmd="true"),
            Job("b", cmd="false"),  # would fail if it ran
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run(skip_jobs=["b"]) == 0
        assert not (log_dir / "b.log").exists()


def test_only_jobs():
    """--only-jobs runs only the listed jobs."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("a", cmd="true"),
            Job("b", cmd="false"),  # would fail if it ran
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run(only_jobs=["a"]) == 0
        assert not (log_dir / "b.log").exists()


def test_delay():
    """Job with delay starts after the specified time."""
    import time
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("fast", cmd="true"),
            Job("delayed", cmd="true", delay=0.5),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        start = time.monotonic()
        assert p.run() == 0
        elapsed = time.monotonic() - start
        # Delayed job should have waited at least 0.4s
        assert elapsed >= 0.4


def test_job_timeout():
    """Per-job timeout kills a hung job."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("hung", cmd="sleep 60", timeout=1),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, timeout=10, cwd=td)
        rc = p.run()
        assert rc != 0
        ci_log = (log_dir / "ci.log").read_text()
        assert "TIMEOUT" in ci_log


def test_env_passed_to_job():
    """Job env vars are passed to the subprocess."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        out = Path(td) / "val.txt"
        jobs = [
            Job("check-env", cmd=f'echo "$MY_VAR" > {out}', env={"MY_VAR": "hello"}),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run() == 0
        assert out.read_text().strip() == "hello"


def test_pytest_exit_5_is_pass():
    """pytest exit code 5 (no tests collected) should be treated as pass."""
    with tempfile.TemporaryDirectory() as td:
        log_dir = Path(td)
        jobs = [
            Job("no-tests", cmd="exit 5"),
        ]
        p = Pipeline(jobs=jobs, sha="abc123", branch="main", log_dir=log_dir, cwd=td)
        assert p.run() == 0


if __name__ == "__main__":
    import sys
    failures = 0
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS  {name}")
            except Exception as e:
                print(f"  FAIL  {name}: {e}")
                failures += 1
    sys.exit(1 if failures else 0)
