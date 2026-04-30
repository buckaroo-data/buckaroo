"""Tests for scripts/paddy_format.py — lisp-style closing-bracket formatter.

The formatter takes Python source where closing brackets dangle on their own
line (Black/ruff style) and rewrites them to stack on the previous line
(lisp style). It's idempotent: running twice produces the same output.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from paddy_format import paddy_format  # noqa: E402


def dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


@pytest.mark.parametrize(
    "name,src,expected",
    [
        (
            "call_with_trailing_comma",
            """
            func(
                a,
                b,
            )
            """,
            """
            func(a, b)
            """,
        ),
        (
            "call_no_trailing_comma",
            """
            func(
                a,
                b
            )
            """,
            """
            func(
                a,
                b)
            """,
        ),
        (
            "list_literal",
            """
            xs = [
                1,
                2,
                3,
            ]
            """,
            """
            xs = [
                1,
                2,
                3]
            """,
        ),
        (
            "dict_literal",
            """
            d = {
                'a': 1,
                'b': 2,
            }
            """,
            """
            d = {
                'a': 1,
                'b': 2}
            """,
        ),
        (
            "tuple_with_parens",
            """
            t = (
                1,
                2,
                3,
            )
            """,
            """
            t = (
                1,
                2,
                3)
            """,
        ),
        (
            "set_literal",
            """
            s = {
                1,
                2,
                3,
            }
            """,
            """
            s = {
                1,
                2,
                3}
            """,
        ),
        (
            "nested_list_in_call",
            """
            func(
                [
                    1,
                    2,
                ],
            )
            """,
            """
            func(
                [
                    1,
                    2])
            """,
        ),
        (
            "function_def",
            """
            def f(
                a,
                b,
                c,
            ):
                return a
            """,
            """
            def f(
                a,
                b,
                c):
                return a
            """,
        ),
        (
            "from_import",
            """
            from x import (
                foo,
                bar,
            )
            """,
            """
            from x import (
                foo,
                bar)
            """,
        ),
        (
            "single_line_unchanged",
            """
            func(a, b, c)
            """,
            """
            func(a, b, c)
            """,
        ),
        (
            "empty_call_unchanged",
            """
            func()
            """,
            """
            func()
            """,
        ),
        (
            "no_args_multiline_unchanged",
            """
            func(
            )
            """,
            """
            func(
            )
            """,
        ),
    ],
)
def test_paddy_format_golden(name, src, expected):
    got = paddy_format(dedent(src))
    assert got == dedent(expected), (
        f"\n--- input ---\n{dedent(src)}"
        f"\n--- expected ---\n{dedent(expected)}"
        f"\n--- got ---\n{got}"
    )


def test_idempotent():
    src = dedent(
        """
        result = func(
            arg1,
            arg2,
            [
                1,
                2,
            ],
        )
        """
    )
    once = paddy_format(src)
    twice = paddy_format(once)
    assert (
        once == twice
    ), f"not idempotent:\n--- once ---\n{once}\n--- twice ---\n{twice}"


def test_preserves_comment_before_close():
    """If a comment sits immediately before the close, leave it alone — don't
    eat the comment by stacking the close."""
    src = dedent(
        """
        func(
            a,
            b,
            # important note
        )
        """
    )
    got = paddy_format(src)
    assert "# important note" in got


def test_handles_syntax_error_gracefully():
    """Invalid Python should not crash — return input unchanged."""
    src = "this is not python ((("
    assert paddy_format(src) == src
