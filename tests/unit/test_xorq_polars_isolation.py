"""Architectural test: ``buckaroo.xorq_buckaroo`` must import without
polars, and ``buckaroo.polars_buckaroo`` must import without xorq.

Both ``polars`` and ``xorq`` are optional extras; pulling one in
through the other turns ``pip install 'buckaroo[xorq]'`` into a
broken install. Run each import in a fresh subprocess with a
meta-path blocker so a regression shows up as a clear ImportError.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


def _run_with_blocked(blocked_packages: list[str], target_module: str) -> None:
    blocked_repr = repr(tuple(blocked_packages))
    script = textwrap.dedent(
        f"""
        import sys
        import importlib.abc

        BLOCKED = {blocked_repr}

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name in BLOCKED or any(name.startswith(b + '.') for b in BLOCKED):
                    raise ImportError(f'BLOCKED: {{name}}')

        sys.meta_path.insert(0, Blocker())
        __import__({target_module!r})
        """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.fail(
            f"Importing {target_module} pulled in a blocked package "
            f"({blocked_packages}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}")


def test_xorq_buckaroo_imports_without_polars():
    """``buckaroo[xorq]`` must not transitively require ``polars``."""
    pytest.importorskip("xorq.api")
    _run_with_blocked(
        blocked_packages=["polars", "buckaroo.customizations.pl_autocleaning_conf",
            "buckaroo.customizations.polars_commands", "buckaroo.customizations.polars_analysis",
            "buckaroo.customizations.pl_stats_v2", "buckaroo.polars_buckaroo", "buckaroo.lazy_infinite_polars_widget",
            "buckaroo.pluggable_analysis_framework.polars_analysis_management",
            "buckaroo.pluggable_analysis_framework.polars_utils"],
        target_module="buckaroo.xorq_buckaroo")


def test_polars_buckaroo_imports_without_xorq():
    """``buckaroo[polars]`` must not transitively require ``xorq``."""
    pytest.importorskip("polars")
    _run_with_blocked(
        blocked_packages=["xorq", "buckaroo.xorq_buckaroo", "buckaroo.customizations.xorq_stats_v2",
            "buckaroo.pluggable_analysis_framework.xorq_stat_pipeline"],
        target_module="buckaroo.polars_buckaroo")
