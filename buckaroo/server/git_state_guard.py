"""Crash-safe wrapper around xorq's git-provenance capture.

xorq records git provenance during expression compilation by shelling out to
``git rev-parse HEAD`` / ``git diff`` / ``git diff --cached``
(``xorq.common.utils.logging_utils.get_git_state``, called from
``xorq/ibis_yaml/compiler.py``). Those bare-name ``subprocess.check_output``
calls ``fork()`` — CPython only takes the ``posix_spawn`` path when the
executable has a directory component, which ``"git"`` lacks.

The buckaroo server is a long-lived, multithreaded Tornado process. Forking
from a multithreaded process on macOS leaves the child's address space in a
partially-copied state (threads other than the forking one are gone, but any
lock they held stays held forever); git can then die with ``SIGSEGV`` and
``subprocess`` re-raises it as ``CalledProcessError(returncode=-11)``. That
exception propagates out of the xorq build/load call behind ``/load_expr`` and
turns a best-effort logging detail into a hard 500. See issue #885.

The root-cause fix belongs in xorq, but buckaroo can protect itself by
installing a wrapper that:

1. spawns git **fork-free** via ``os.posix_spawn`` — a vfork-style spawn that
   does not clone the parent's address space or threads, so the
   fork-from-multithreaded hazard cannot fire by construction; and
2. **degrades to placeholders on any failure** (signal death, missing git,
   timeout) instead of raising.

Each call captures fresh — no permanent cache — so successive loads record the
repo state at the time rather than freezing the first capture.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

# Matches xorq's get_git_state command set (sub-commands; "git" prepended at spawn).
_GIT_COMMANDS = (["rev-parse", "HEAD"], ["diff"], ["diff", "--cached"])


def _run_git(args: list, timeout: float = 10.0) -> str:
    """Run ``git <args>`` without forking, via ``os.posix_spawn``.

    Resolves git on PATH at call time (posix_spawn does not search PATH).
    Returns stripped stdout; raises on a missing git, signal death, or non-zero
    exit — all of which ``_capture`` turns into placeholders.
    """
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git not found on PATH")
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        with tempfile.TemporaryFile() as out:
            file_actions = [
                (os.POSIX_SPAWN_DUP2, out.fileno(), 1),  # stdout -> temp file
                (os.POSIX_SPAWN_DUP2, devnull, 2),       # stderr -> /dev/null
            ]
            pid = os.posix_spawn(git, [git, *args], os.environ, file_actions=file_actions)
            _, status = os.waitpid(pid, 0)
            if os.WIFSIGNALED(status):
                raise RuntimeError(f"git {args} killed by signal {os.WTERMSIG(status)}")
            if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
                raise RuntimeError(f"git {args} exited non-zero (status={status})")
            out.seek(0)
            return out.read().decode().strip()
    finally:
        os.close(devnull)


def _format(triple: tuple, hash_diffs: bool) -> dict:
    """Shape a (commit, diff, diff_cached) triple like xorq's get_git_state does."""
    commit, diff, diff_cached = triple
    state = {"commit": commit, "diff": diff, "diff_cached": diff_cached}
    if hash_diffs:
        for key in ("diff", "diff_cached"):
            state[f"{key}_hash"] = hashlib.md5(state.pop(key).encode()).hexdigest()
    return state


def _capture() -> tuple:
    """Run the git commands fork-free; ``("unknown", "", "")`` on any failure."""
    try:
        out = [_run_git(cmd) for cmd in _GIT_COMMANDS]
        return (out[0], out[1], out[2])
    except BaseException:
        # RuntimeError (signal death like SIGSEGV / non-zero exit),
        # FileNotFoundError, OSError — none of it may reach the caller.
        return ("unknown", "", "")


def _safe_get_git_state(hash_diffs: bool = False) -> dict:
    if os.environ.get("BUCKAROO_DISABLE_GIT_STATE"):
        return _format(("unknown", "", ""), hash_diffs)
    return _format(_capture(), hash_diffs)


_safe_get_git_state._buckaroo_guarded = True  # type: ignore[attr-defined]


def install_git_state_guard() -> None:
    """Idempotently replace ``logging_utils.get_git_state`` with the safe version.

    Lazy xorq import so importing this module doesn't pull in xorq eagerly.
    A no-op if xorq isn't installed.
    """
    try:
        from xorq.common.utils import logging_utils as lu
    except ImportError:
        return

    if getattr(lu.get_git_state, "_buckaroo_guarded", False):
        return
    lu.get_git_state = _safe_get_git_state
