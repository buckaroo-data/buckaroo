"""
Tests for ``scripts/run_pytest_tolerant.sh`` — the wrapper that swallows the
intermittent polars-stream / pyo3 shutdown SIGABRT after a passing pytest
run on the "Max Versions" matrix.

The wrapper's existing logic (``e080814c``) requires BOTH a ``FATAL:
exception not rethrown`` line AND a ``panicked at ... (pyo3|polars-stream)``
panic frame in the captured output before treating exit 134 as success.

In practice the panic frame is emitted by a backgrounded tokio /
async-executor worker thread that races against ``abort()``. When abort
wins, the stdout pipe gets torn down before the panic line flushes, and
the wrapper rejects an otherwise-known shutdown race — propagating exit
134 and failing CI even though every test passed. PR 719 hit this on
``Python / Test (Max Versions) (3.12)``.

These tests pin down the desired behaviour:

* All-tests-pass + ``FATAL: exception not rethrown`` + Rust panic frame
  → wrapper exits 0 (the case the original commit already handles).
* All-tests-pass + ``FATAL: exception not rethrown`` + ``Aborted (core
  dumped)`` but **no** panic frame → wrapper still exits 0. The FATAL +
  Aborted pair is a sufficient signature of the libpython-finalization
  SIGABRT; an unrelated native crash producing exit 134 would not
  produce the ``FATAL: exception not rethrown`` libpython diagnostic.
* SIGABRT 134 without either signature line → wrapper propagates 134.
* Real pytest failure (exit 1) → wrapper propagates 1.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "scripts" / "run_pytest_tolerant.sh"


def _make_fake_pytest(tmp_path: Path, stdout: str, exit_code: int) -> Path:
    """Build a one-shot shell script that prints ``stdout`` then exits."""
    fake = tmp_path / "fake_pytest.sh"
    body = "#!/usr/bin/env bash\n"
    body += "cat <<'FAKE_PYTEST_EOF'\n"
    body += stdout
    if not stdout.endswith("\n"):
        body += "\n"
    body += "FAKE_PYTEST_EOF\n"
    body += f"exit {exit_code}\n"
    fake.write_text(body)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return fake


def _run_wrapper(fake: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(WRAPPER), str(fake)], capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))


PASSING_SUMMARY = (
    "==== 875 passed, 5 skipped, 104 deselected, 16 warnings in 100.18s ===="
)


def test_wrapper_swallows_full_signature_134(tmp_path: Path) -> None:
    """Sanity: the originally-handled case (passing + FATAL + panic frame)."""
    fake = _make_fake_pytest(tmp_path, stdout=(
            PASSING_SUMMARY + "\n"
            "FATAL: exception not rethrown\n"
            "thread 'tokio-runtime-worker' panicked at "
            ".cargo/registry/src/pyo3-0.27.2/src/interpreter_lifecycle.rs:117:13:\n"
            "  The Python interpreter is not initialized and the "
            "`auto-initialize` feature is not enabled.\n"
            "Aborted (core dumped)\n"
        ), exit_code=134)
    result = _run_wrapper(fake)
    assert result.returncode == 0, (
        f"wrapper rejected the canonical FATAL + panic signature.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_wrapper_swallows_fatal_plus_aborted_without_panic_frame(tmp_path: Path) -> None:
    """The PR 719 flake — panic frame raced abort() and never flushed.

    With this signature, the wrapper currently rejects (exit 134). After
    the fix it should accept exit 134 as the known shutdown race.
    """
    fake = _make_fake_pytest(tmp_path, stdout=(
            PASSING_SUMMARY + "\n"
            "FATAL: exception not rethrown\n"
            "Aborted (core dumped)\n"
        ), exit_code=134)
    result = _run_wrapper(fake)
    assert result.returncode == 0, (
        "wrapper should treat FATAL + Aborted as the libpython-finalization "
        "SIGABRT signature even when the racing panic frame is missing from "
        "captured output.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_wrapper_propagates_134_without_signature(tmp_path: Path) -> None:
    """An unrelated native crash producing exit 134 must NOT be swallowed."""
    fake = _make_fake_pytest(tmp_path, stdout=(
            PASSING_SUMMARY + "\n"
            "Segmentation fault (core dumped)\n"
        ), exit_code=134)
    result = _run_wrapper(fake)
    assert result.returncode == 134, (
        "wrapper must propagate exit 134 when no libpython-finalization "
        "signature is present — that's an unrelated crash and a real failure.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_wrapper_propagates_real_pytest_failure(tmp_path: Path) -> None:
    """A normal pytest failure (exit 1) must NOT be swallowed."""
    fake = _make_fake_pytest(tmp_path, stdout=(
            "FAILED tests/unit/foo_test.py::test_bar - AssertionError: ...\n"
            "==== 1 failed, 874 passed in 100.18s ====\n"
        ), exit_code=1)
    result = _run_wrapper(fake)
    assert result.returncode == 1, (
        "wrapper must propagate real pytest failures untouched.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("bash") is None, reason="wrapper requires bash")
def test_wrapper_exists_and_executable() -> None:
    assert WRAPPER.is_file(), f"missing wrapper: {WRAPPER}"
    assert os.access(WRAPPER, os.X_OK), f"wrapper not executable: {WRAPPER}"
