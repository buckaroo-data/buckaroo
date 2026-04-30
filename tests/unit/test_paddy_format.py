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
            xs = [1, 2, 3]
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
            d = {'a': 1, 'b': 2}
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
            t = (1, 2, 3)
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
            s = {1, 2, 3}
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
            func([1, 2])
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
            def f(a, b, c):
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
            from x import (foo, bar)
            """,
        ),
        (
            "long_call_greedy_wrap",
            # 203 chars on one line — should wrap greedily at 120,
            # continuation indented at line_indent + 4 (here, 0 + 4 = 4).
            "result = some_function_name(very_long_argument_1, very_long_argument_2, very_long_argument_3, very_long_argument_4, very_long_argument_5, very_long_argument_6, very_long_argument_7, very_long_argument_8)\n",
            "result = some_function_name(very_long_argument_1, very_long_argument_2, very_long_argument_3, very_long_argument_4,\n    very_long_argument_5, very_long_argument_6, very_long_argument_7, very_long_argument_8)\n",
        ),
        (
            "multiline_collapse_target_too_long_wraps_instead",
            # Trailing-comma multiline; collapsed form would be 203 chars.
            # Don't collapse — wrap greedily instead. Trailing comma is dropped.
            "result = some_function_name(\n    very_long_argument_1,\n    very_long_argument_2,\n    very_long_argument_3,\n    very_long_argument_4,\n    very_long_argument_5,\n    very_long_argument_6,\n    very_long_argument_7,\n    very_long_argument_8,\n)\n",
            "result = some_function_name(very_long_argument_1, very_long_argument_2, very_long_argument_3, very_long_argument_4,\n    very_long_argument_5, very_long_argument_6, very_long_argument_7, very_long_argument_8)\n",
        ),
        (
            "long_list_greedy_wrap",
            # 162 chars on one line — wrap greedily.
            "long_xs = [very_long_value_1, very_long_value_2, very_long_value_3, very_long_value_4, very_long_value_5, very_long_value_6, very_long_value_7, very_long_value_8]\n",
            "long_xs = [very_long_value_1, very_long_value_2, very_long_value_3, very_long_value_4, very_long_value_5,\n    very_long_value_6, very_long_value_7, very_long_value_8]\n",
        ),
        (
            "reindent_continuation_to_indent_plus_4",
            # Continuation line of a multi-line call sits at column 0 (legal
            # inside parens, but visually broken). Re-indent it to
            # original_indent + 4. Trailing space after the comma on line 1
            # is also cleaned up.
            "class C:\n    def f(self, ser):\n        return dict(str_bool_frac=str_bool_frac(ser), \nregular_int_parse_frac=regular_int_parse_frac(ser))\n",
            "class C:\n    def f(self, ser):\n        return dict(str_bool_frac=str_bool_frac(ser),\n            regular_int_parse_frac=regular_int_parse_frac(ser))\n",
        ),
        (
            "table_format_single_col_floats",
            # `# table-format` directive on the line above forces a column
            # table layout — each element on its own line, decimal points
            # right-aligned. Other paddy rules (collapse / stack) are
            # overridden when the directive is present.
            """
            # table-format
            data = [1.23, 45.6, 7.89, 100.5]
            """,
            """
            # table-format
            data = [1.23, 45.6, 7.89, 100.5]
            """,
        ),
        (
            "table_format_single_col_floats_wrap",
            # When the single-line form exceeds 120 chars, table-format
            # wraps using strict uniform cells: each cell is
            # max_int_width + 1 + max_frac_width chars wide (left-pad int,
            # right-pad frac). Continuation indent = position right after
            # the open bracket, so decimals align across rows at fixed
            # 8-column strides. Trailing spaces inside cells before commas
            # are accepted as the cost of strict alignment.
            """
            # table-format
            data = [1.23, 45.6, 7.89, 100.5, 1.23, 45.6, 7.89, 100.5, 1.23, 45.6, 7.89, 100.5, 1.23, 45.6, 7.89, 100.5, 1.23, 45.6, 7.89, 100.5, 1.23, 45.6, 7.89, 100.5]
            """,
            """
            # table-format
            data = [  1.23,  45.6 ,   7.89, 100.5 ,   1.23,  45.6 ,   7.89, 100.5 ,   1.23,  45.6 ,   7.89, 100.5 ,   1.23,  45.6 ,
                      7.89, 100.5 ,   1.23,  45.6 ,   7.89, 100.5 ,   1.23,  45.6 ,   7.89, 100.5 ]
            """,
        ),
        (
            "table_format_mixed_ints_floats",
            # Mixed ints and floats: ints align by least-significant digit
            # (the position the decimal point would occupy). Decimal column
            # = max integer-part width across all items.
            """
            # table-format
            data = [1, 2.5, 30, 4.567, 50000]
            """,
            """
            # table-format
            data = [1, 2.5, 30, 4.567, 50000]
            """,
        ),
        (
            "table_format_multi_col_tuples",
            # Each tuple position is treated as an independent column.
            # Col 0 here (floats) all share the same width; col 1 (ints)
            # is right-aligned to the widest element.
            """
            # table-format
            data = [(1.23, 5), (4.56, 600), (7.89, 70)]
            """,
            """
            # table-format
            data = [
                (1.23,   5),
                (4.56, 600),
                (7.89,  70),
            ]
            """,
        ),
        (
            "unsplittable_single_arg_overflows",
            # Single arg > 120 chars; nothing to break on, stays as-is.
            "result = func(extremely_long_single_argument_that_cannot_be_broken_apart_into_smaller_pieces_and_must_overflow_the_line_budget)\n",
            "result = func(extremely_long_single_argument_that_cannot_be_broken_apart_into_smaller_pieces_and_must_overflow_the_line_budget)\n",
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
            func()
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
    # Idempotency: a second pass over `got` must be a no-op.
    again = paddy_format(got)
    assert again == got, (
        f"\n--- not idempotent for {name} ---"
        f"\n--- once ---\n{got}"
        f"\n--- twice ---\n{again}"
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
