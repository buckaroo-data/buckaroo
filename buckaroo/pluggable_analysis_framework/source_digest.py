"""Digests of the source code that defines a stat (ADR-001 D4).

A stat's cached cells are keyed by a hash of its implementation. For a stat
defined in a file, that is the whole file's content: stats call module-level
helpers and read module constants, so the function's own source isn't enough.
A ``functools.partial`` or a closure also carries values the file doesn't
show, so those are part of its digest. A function with no readable file (a
notebook cell, ``<string>``) has no digest: its code object doesn't cover the
globals it reads, so it isn't cached.

The digest is taken when the stat is defined (``StatFunc`` is constructed at
import or compile time), not when it's looked up. A file edited after import
must not lend its new digest to results computed by the old code still loaded.
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import os
from typing import Any, Dict, Optional, Tuple

_FILE_DIGESTS: Dict[Tuple[str, int, int], str] = {}

# Types whose repr is exact: equal reprs mean equal values of the same type.
_LITERAL_TYPES = (type(None), bool, int, float, complex, str, bytes)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def text_md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def file_digest(path: Any) -> Optional[str]:
    """sha256 of a file's content, or None when it can't be read. Memoised on
    ``(path, mtime, size)`` so a module defining many stats is read once."""
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    digest = _FILE_DIGESTS.get(key)
    if digest is None:
        try:
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None
        _FILE_DIGESTS[key] = digest
    return digest


def file_md5(path: Any) -> Optional[str]:
    """md5 of a file's content, or None when it can't be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def callable_file(fn: Any) -> Optional[str]:
    """The file that defines ``fn``'s code (a partial's function), or None."""
    fn = inspect.unwrap(fn)
    if isinstance(fn, functools.partial):
        return callable_file(fn.func)
    code = getattr(fn, "__code__", None)
    return None if code is None else code.co_filename


def _captured(v: Any) -> Optional[str]:
    """Exact text for a value a callable carries besides its code: literals,
    and lists, tuples and dicts of them, by repr; functions, classes and
    modules by name, like the globals a function calls. None for anything
    else, whose repr needn't show all of its state."""
    if type(v) in _LITERAL_TYPES:
        return repr(v)
    if type(v) in (list, tuple, dict):
        parts = []
        for x in (v.items() if type(v) is dict else v):
            part = _captured(x)
            if part is None:
                return None
            parts.append(part)
        return f"{type(v).__name__}({', '.join(parts)})"
    if inspect.isfunction(v) or inspect.isbuiltin(v) or inspect.isclass(v) or inspect.ismodule(v):
        return f"{getattr(v, '__module__', '')}:{getattr(v, '__qualname__', v.__name__)}"
    return None


def callable_digest(fn: Any) -> Optional[str]:
    """Digest of the file that defines ``fn``, plus what ``fn`` carries that
    the file doesn't show: a ``functools.partial``'s bound arguments, a
    closure's captured values. None when it has no file, carries a value
    ``_captured`` can't spell out, or is a callable object or a method bound
    to one, whose instance state no file covers."""
    fn = inspect.unwrap(fn)
    if isinstance(fn, functools.partial):
        inner = callable_digest(fn.func)
        bound = _captured((fn.args, sorted(fn.keywords.items())))
        return None if inner is None or bound is None else text_digest(f"{inner}|partial{bound}")
    if inspect.ismethod(fn) and not inspect.isclass(fn.__self__):
        return None
    code = getattr(fn, "__code__", None)
    if code is None:
        return None
    digest = file_digest(code.co_filename)
    cells = getattr(fn, "__closure__", None)
    if digest is None or not cells:
        return digest
    captured = []
    for cell in cells:
        try:
            part = _captured(cell.cell_contents)
        except ValueError:  # an empty cell
            part = "<empty>"
        if part is None:
            return None
        captured.append(part)
    return text_digest(f"{digest}|closure({', '.join(captured)})")
