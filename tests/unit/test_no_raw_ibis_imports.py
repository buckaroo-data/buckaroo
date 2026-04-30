"""Architectural test: buckaroo's source must not import raw ``ibis``.

The xorq pipeline operates on xorq expressions only — i.e. the ibis
vendored inside xorq (``xorq.vendor.ibis``), not the standalone
``ibis-framework`` package. Importing raw ``ibis`` would create a second,
incompatible expression type hierarchy and silently couple us to a
package whose dtype objects, ops, and Table classes are *not* the same
identities as xorq's vendored copies.

This test grep-asserts the rule. Scoped to the ``buckaroo/`` source
package; test fixtures may construct inputs however they like.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_FORBIDDEN = re.compile(r"^\s*(?:import\s+ibis(?:\s|$|\.)|from\s+ibis(?:\s|\.))")
_PKG_ROOT = Path(__file__).resolve().parents[2] / "buckaroo"


def _python_sources():
    for path in _PKG_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_no_raw_ibis_imports_in_source():
    offenders: list[tuple[Path, int, str]] = []
    for path in _python_sources():
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if _FORBIDDEN.match(line):
                offenders.append((path.relative_to(_PKG_ROOT.parent), lineno, line))
    if offenders:
        formatted = "\n".join(f"  {p}:{n}: {ln}" for p, n, ln in offenders)
        pytest.fail(
            "buckaroo/ source must not import raw ibis — use "
            "`import xorq.api as xo` (or xorq.vendor.ibis) instead:\n" + formatted
        )
