"""Regression tests for the git-state guard against the *real* xorq stack (#885).

xorq records git provenance by shelling out to `git rev-parse HEAD` /
`git diff` / `git diff --cached` from `logging_utils.get_git_state`, called
inline on the compile path (`xorq/ibis_yaml/compiler.py`). Those bare-name
`subprocess` calls fork, and `fork()` from the long-lived, multithreaded
buckaroo Tornado server on macOS can die with SIGSEGV — `subprocess` then
re-raises `CalledProcessError(returncode=-11)`, which propagates out of the
xorq call behind `/load_expr` and turns a logging detail into a hard 500.

These tests exercise the real xorq `get_git_state` (the unedited library
function) through buckaroo's guard:

- `test_*_fork_free`   — git is dispatched via `os.posix_spawn`, never fork.
- `test_*_reflects_*`  — provenance is fresh per call (no permanent cache).
- `test_*_degrades_*`  — a signal-killed git degrades to placeholders.
- `test_loading_surface_installs_guard` — importing the server's xorq surface
  installs the guard, so the server is protected without an explicit call.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("xorq.common.utils.logging_utils")

from buckaroo.server import git_state_guard as g  # noqa: E402


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# The three commands xorq's get_git_state runs. A forked command never reaches
# os.posix_spawn, so "all three were spawned" is exactly "none of them forked".
_PROVENANCE_COMMANDS = (("rev-parse", "HEAD"), ("diff",), ("diff", "--cached"))


def _provenance_spawns(seen: list) -> list:
    """From recorded posix_spawn argvs, the git sub-commands that were spawned."""
    out = []
    for argv in seen:
        if argv and "git" in os.path.basename(str(argv[0])):
            out.append(tuple(str(a) for a in argv[1:]))
    return out


def _assert_provenance_fork_free(seen: list, context: str) -> None:
    prov = _provenance_spawns(seen)
    forked = [cmd for cmd in _PROVENANCE_COMMANDS if cmd not in prov]
    assert not forked, (
        f"{context}: git {forked} forked instead of using os.posix_spawn — the "
        f"macOS fork-from-multithreaded hazard. posix_spawn'd git calls: {prov}")


@pytest.fixture
def guard_env(monkeypatch):
    """Snapshot/restore the swapped `lu.get_git_state` so tests don't leak."""
    from xorq.common.utils import logging_utils as lu
    original = lu.get_git_state
    monkeypatch.delenv("BUCKAROO_DISABLE_GIT_STATE", raising=False)
    try:
        yield lu, g
    finally:
        lu.get_git_state = original


@pytest.fixture
def spawn_spy(monkeypatch):
    """Record every `os.posix_spawn` argv; pass-through to the real one."""
    seen = []
    real = os.posix_spawn

    def spy(path, argv, env, **kwargs):
        seen.append(list(argv))
        return real(path, argv, env, **kwargs)

    monkeypatch.setattr(os, "posix_spawn", spy)
    return seen


@pytest.fixture
def temp_git_repo(tmp_path: Path, monkeypatch) -> Path:
    """A throwaway real git repo with one commit; cwd points here."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.com", cwd=repo)
    _git("config", "user.name", "tester", cwd=repo)
    (repo / "a.txt").write_text("one\n")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture
def segfault_git_repo(tmp_path: Path, monkeypatch) -> Path:
    """A dir that looks like a repo, with a `git` on PATH that dies via SIGSEGV.

    Mirrors the observed crash (git killed by signal -> returncode -11).
    """
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)  # makes xorq's _git_is_present() true
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_git = bindir / "git"
    fake_git.write_text("#!/bin/sh\nkill -SEGV $$\n")
    fake_git.chmod(0o755)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return repo


@pytest.mark.skipif(
    not hasattr(os, "posix_spawn"),
    reason="posix_spawn (the fork-free path) is POSIX-only; Windows has no fork hazard")
def test_installed_guard_dispatches_git_fork_free(guard_env, spawn_spy, temp_git_repo):
    """The real xorq get_git_state, through the guard, must use posix_spawn."""
    lu, _ = guard_env
    g.install_git_state_guard()

    state = lu.get_git_state(hash_diffs=False)

    # Capture actually ran in this repo (not the degraded placeholder), so the
    # assertion below is about a real provenance call, not a no-op.
    assert state["commit"] != "unknown", state
    _assert_provenance_fork_free(spawn_spy, "guarded get_git_state")


def test_guard_reflects_repo_state_changes(guard_env, temp_git_repo):
    """Provenance is fresh per call — no permanent one-shot cache."""
    lu, _ = guard_env
    g.install_git_state_guard()

    first = lu.get_git_state(hash_diffs=False)
    assert first["diff_cached"] == ""

    (temp_git_repo / "new.txt").write_text("hello\n")
    _git("add", "new.txt", cwd=temp_git_repo)

    second = lu.get_git_state(hash_diffs=False)
    assert second["diff_cached"] != first["diff_cached"], (
        "guard returned stale, permanently-cached provenance; each call must "
        "reflect current repo state")
    assert "new.txt" in second["diff_cached"]


def test_guard_subprocess_fallback_captures_real_provenance(
        guard_env, temp_git_repo, monkeypatch):
    """On platforms without os.posix_spawn (Windows), the guard must fall back
    to subprocess and still capture real provenance — not degrade every capture
    to placeholders. Exercised on POSIX by forcing the no-posix_spawn branch."""
    lu, _ = guard_env
    monkeypatch.setattr(g, "_HAS_POSIX_SPAWN", False)
    g.install_git_state_guard()

    state = lu.get_git_state(hash_diffs=False)

    assert state["commit"] != "unknown", (
        "subprocess fallback degraded to placeholders instead of capturing "
        "real git provenance")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell shim / signals")
def test_guard_degrades_on_signal_death(guard_env, segfault_git_repo):
    """A signal-killed git degrades to placeholders, never raises."""
    lu, _ = guard_env

    # The unguarded form xorq ships raises on signal death (the original bug).
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
    assert excinfo.value.returncode == -11  # -SIGSEGV

    # The guard contains it: placeholder provenance instead of a raise.
    g.install_git_state_guard()
    state = lu.get_git_state(hash_diffs=False)
    assert state == {"commit": "unknown", "diff": "", "diff_cached": ""}


def test_loading_surface_installs_guard(guard_env):
    """Importing the server's xorq surface installs the guard, so the server's
    /load_expr path is protected without callers wiring it up explicitly."""
    lu, _ = guard_env
    import importlib

    # Reload logging_utils to restore xorq's unguarded function, then reload
    # the surface module so its import-time install() runs against it again.
    from xorq.common.utils import logging_utils
    importlib.reload(logging_utils)
    assert not getattr(logging_utils.get_git_state, "_buckaroo_guarded", False)

    import buckaroo.server.xorq_loading as xl
    importlib.reload(xl)

    assert getattr(logging_utils.get_git_state, "_buckaroo_guarded", False), (
        "importing buckaroo.server.xorq_loading must install the git-state guard")
