"""Digests of the source code that defines a stat (ADR-001 D4).

A stat's cached cells are keyed by a hash of its implementation. For a stat
defined in a file, that is the whole file's content: stats call module-level
helpers and read module constants, so the function's own source isn't enough.
A function with no readable file (a notebook cell, ``<string>``) has no
digest: its code object doesn't cover the globals it reads, so it isn't
cached.

The digest is taken when the stat is defined (``StatFunc`` is constructed at
import or compile time), not when it's looked up. A file edited after import
must not lend its new digest to results computed by the old code still loaded.
"""
from __future__ import annotations

import hashlib
import inspect
import os
from typing import Any, Dict, Optional, Tuple

_FILE_DIGESTS: Dict[Tuple[str, int, int], str] = {}


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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


def callable_digest(fn: Any) -> Optional[str]:
    """Digest of the file that defines ``fn``, or None when it has none."""
    fn = inspect.unwrap(fn)
    code = getattr(fn, "__code__", None)
    if code is None:
        # A callable object: the file defining its class.
        try:
            path = inspect.getsourcefile(type(fn))
        except TypeError:
            return None
        return file_digest(path) if path else None
    return file_digest(code.co_filename)
