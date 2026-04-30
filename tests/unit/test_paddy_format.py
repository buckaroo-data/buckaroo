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
            "table_format_ints_only_wrap",
            # Int-only column: max_int_width = 5 (for 40000), max_frac = 0,
            # so each cell is 5 chars right-aligned. Sep is ", " (2 chars),
            # decimal-equivalent stride is 7. 24 items = 16 on row 1 + 8 on
            # row 2. The "least significant digit" (rightmost char of each
            # int) lines up across rows at fixed columns.
            """
            # table-format
            data = [10, 200, 3000, 40000, 10, 200, 3000, 40000, 10, 200, 3000, 40000, 10, 200, 3000, 40000, 10, 200, 3000, 40000, 10, 200, 3000, 40000]
            """,
            """
            # table-format
            data = [   10,   200,  3000, 40000,    10,   200,  3000, 40000,    10,   200,  3000, 40000,    10,   200,  3000, 40000,
                       10,   200,  3000, 40000,    10,   200,  3000, 40000]
            """,
        ),
        (
            "table_format_mixed_ints_floats_wrap",
            # Mixed ints and floats long enough to wrap: max_int_width = 2
            # (for 30), max_frac_width = 3 (for 4.567). Cell width = 6.
            # Ints sitting in a column with floats get trailing padding to
            # fill the cell (so "1" renders as " 1    " — 1 leading +
            # "1" + 4 trailing for the missing ".XXX"). Decimal column
            # is at offset 2 within each cell, lined up across rows at
            # an 8-char stride.
            """
            # table-format
            data = [1, 2.5, 30, 4.567, 1, 2.5, 30, 4.567, 1, 2.5, 30, 4.567, 1, 2.5, 30, 4.567, 1, 2.5, 30, 4.567, 1, 2.5, 30, 4.567]
            """,
            """
            # table-format
            data = [ 1    ,  2.5  , 30    ,  4.567,  1    ,  2.5  , 30    ,  4.567,  1    ,  2.5  , 30    ,  4.567,  1    ,  2.5  ,
                    30    ,  4.567,  1    ,  2.5  , 30    ,  4.567,  1    ,  2.5  , 30    ,  4.567]
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
            # Short multi-col list — directive is a no-op when single-line
            # form already fits in budget.
            """
            # table-format
            data = [(1.23, 5), (4.56, 600), (7.89, 70)]
            """,
            """
            # table-format
            data = [(1.23, 5), (4.56, 600), (7.89, 70)]
            """,
        ),
        (
            "table_format_list_of_dicts_wrap",
            # List of dicts that share the same keys and have numeric
            # values. Each key becomes a column; values in that column
            # are decimal-aligned with uniform cell widths so the keys
            # line up across rows.
            #
            # Per-column padding:
            #   'a': max_int=2, max_frac=3, cell width 6
            #   'b': max_int=4, max_frac=0, cell width 4
            #   'c': max_int=2, max_frac=3, cell width 6
            #
            # Per the design discussion: each dict is < 100 chars and
            # has no nested dicts.
            """
            # table-format
            data = [{'a': 1.5, 'b': 100, 'c': 0.001}, {'a': 23.456, 'b': 7, 'c': 99.9}, {'a': 0.5, 'b': 8000, 'c': 1.0}, {'a': 12.34, 'b': 50, 'c': 3.14}, {'a': 7.89, 'b': 1000, 'c': 0.5}]
            """,
            """
            # table-format
            data = [
                {'a':  1.5  , 'b':  100, 'c':  0.001},
                {'a': 23.456, 'b':    7, 'c': 99.9  },
                {'a':  0.5  , 'b': 8000, 'c':  1.0  },
                {'a': 12.34 , 'b':   50, 'c':  3.14 },
                {'a':  7.89 , 'b': 1000, 'c':  0.5  },
            ]
            """,
        ),
        (
            "table_format_multi_col_tuples_wrap",
            # Long multi-col list — single-line form exceeds 120 chars.
            # Each tuple goes on its own line; cells within tuples are
            # aligned across rows. Continuation = line_indent + 4 (the
            # standard paddy rule); cross-row decimal alignment is
            # automatic because every row has the same shape.
            """
            # table-format
            data = [(1.23, 5), (4.56, 600), (7.89, 70), (1.23, 5), (4.56, 600), (7.89, 70), (1.23, 5), (4.56, 600), (7.89, 70), (1.23, 5), (4.56, 600), (7.89, 70)]
            """,
            """
            # table-format
            data = [
                (1.23,   5),
                (4.56, 600),
                (7.89,  70),
                (1.23,   5),
                (4.56, 600),
                (7.89,  70),
                (1.23,   5),
                (4.56, 600),
                (7.89,  70),
                (1.23,   5),
                (4.56, 600),
                (7.89,  70),
            ]
            """,
        ),
        (
            "idempotent_outer_call_continuation_shifts_inner_dict",
            # Minimal repro from buckaroo/pluggable_analysis_framework/
            # safe_summary_df.py. The outer Call has its continuation line
            # at col 23; the inner Dict's second key sits at col 24 (just
            # past the `{`). On the first pass, the outer Call's
            # continuation gets re-indented to col 8 (line_indent + 4),
            # but the inner Dict's continuation stays at col 24 because
            # _line_indent_plus_4 reads the *current* line indent of the
            # Dict's `{` line, which still points at col 23. On the
            # second pass, the Dict's `{` line is now at col 8, so the
            # inner key gets re-indented to col 12. Two passes to settle.
            """
            def f(dct):
                cleaned_dct = val_replace(dct,
                                   {pd.NA: UnquotedString("pd.NA"),
                                    np.nan: UnquotedString("np.nan")})
                return cleaned_dct
            """,
            """
            def f(dct):
                cleaned_dct = val_replace(dct,
                    {pd.NA: UnquotedString("pd.NA"),
                        np.nan: UnquotedString("np.nan")})
                return cleaned_dct
            """,
        ),
        (
            "idempotent_nested_list_inside_dict_value",
            # Minimal repro from buckaroo/ddd_library.py. After Pass 1
            # collapses the outer Dict's trailing-comma multiline form,
            # the 'timedelta' key's value (a multi-line List) sits at a
            # new line indent. The inner List's continuation lines were
            # at col 39 in the original; on run 1 they get re-indented to
            # col 8 (line_indent + 4 of the OUTER dict's row). On run 2,
            # they shift to col 12 (line_indent + 4 of the inner Call's
            # row, which is now at col 8). Same root cause as the case
            # above.
            """
            def f():
                return pd.DataFrame({
                    'categorical': pd.Categorical(['red', 'green', 'blue', 'red', 'green']),
                    'timedelta': pd.to_timedelta(['1 days 02:03:04', '0 days 00:00:01',
                                                   '365 days', '0 days 00:00:00.001',
                                                   '0 days 00:00:00.000100']),
                    'int_col': [10, 20, 30, 40, 50],
                })
            """,
            """
            def f():
                return pd.DataFrame({'categorical': pd.Categorical(['red', 'green', 'blue', 'red', 'green']),
                    'timedelta': pd.to_timedelta(['1 days 02:03:04', '0 days 00:00:01',
                        '365 days', '0 days 00:00:00.001',
                        '0 days 00:00:00.000100']),
                    'int_col': [10, 20, 30, 40, 50]})
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
