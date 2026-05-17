"""xorq Command coverage — exercise each ported command through the
``XorqAutocleaning`` lisp-interpreter path that the widget uses for
quick commands today.

These are not pure-function tests of the ``transform`` static methods;
the point of porting them was that they now flow through the same
``configure_buckaroo`` interpreter the pandas/polars commands do, so
the tests drive them via ``handle_ops_and_clean`` with a hand-built op
list. That's the same shape the widget sends on a ``quick_command_args``
change, plus an ``existing_operations`` list for the cleaning_method
path.
"""
from __future__ import annotations

import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.customizations.xorq_autoclean_conf import NoCleaningConfXorq  # noqa: E402
from buckaroo.customizations.xorq_commands import (  # noqa: E402
    DropCol, DropDuplicates, FillNA, NoOp, Search)
from buckaroo.jlisp.lisp_utils import s  # noqa: E402
from buckaroo.xorq_buckaroo import XorqAutocleaning  # noqa: E402


def _expr():
    # 'a' has a null, 'b' has duplicates, 'c' is a non-string for Search coverage.
    return xo.memtable(
        {"a": [1, 2, None, 4, 4],
         "b": ["x", "y", "x", "z", "z"],
         "c": [10, 20, 30, 40, 50]})


def _ac():
    return XorqAutocleaning(ac_configs=(NoCleaningConfXorq,), conf_name="")


def _run(ac, expr, ops):
    """Drive the interpreter path: pretend the frontend pre-merged
    ``ops`` into existing_operations, with no cleaning_method and no
    quick_command_args. ``handle_ops_and_clean`` then collapses through
    ``produce_final_ops`` -> ``_run_df_interpreter`` and returns the
    cleaned expression.

    Ops carry plain ``s(...)`` symbols (no ``auto_clean: True`` meta) so
    ``merge_ops`` treats them as user-entered and preserves them rather
    than discarding them as stale autocleaning output.
    """
    return ac.handle_ops_and_clean(expr, "", {}, ops)


class TestCommandsViaInterpreter:
    def test_noop_returns_same_expr(self):
        ac = _ac()
        expr = _expr()
        op = [s("noop"), {"symbol": "df"}, "a"]
        cleaned, _sd, _code, final_ops = _run(ac, expr, [op])
        assert cleaned.count().execute() == 5
        assert final_ops == [op]

    def test_dropcol_removes_column(self):
        ac = _ac()
        expr = _expr()
        op = [s("dropcol"), {"symbol": "df"}, "b"]
        cleaned, *_ = _run(ac, expr, [op])
        assert "b" not in cleaned.columns
        assert set(cleaned.columns) == {"a", "c"}

    def test_fillna_substitutes_null(self):
        ac = _ac()
        expr = _expr()
        op = [s("fillna"), {"symbol": "df"}, "a", 99]
        cleaned, *_ = _run(ac, expr, [op])
        result = cleaned.execute().sort_values("c").reset_index(drop=True)
        # The original null at row 2 became 99 — pandas may upcast to
        # float so compare numerically.
        assert list(result["a"]) == [1, 2, 99, 4, 4]

    def test_drop_duplicates_dedupes_by_column(self):
        ac = _ac()
        expr = _expr()
        op = [s("drop_duplicates"), {"symbol": "df"}, "b"]
        cleaned, *_ = _run(ac, expr, [op])
        result = cleaned.execute()
        # Three distinct values in 'b': x, y, z.
        assert sorted(result["b"]) == ["x", "y", "z"]
        assert len(result) == 3

    def test_search_via_quick_command_args(self):
        """Search is the only quick-command — drive it through the
        ``quick_command_args`` channel the widget actually uses."""
        ac = _ac()
        expr = _expr()
        cleaned, *_ = ac.handle_ops_and_clean(
            expr, "", {"search": ["x"]}, [{"meta": "no-op"}])
        result = cleaned.execute()
        # 'b' = ['x','y','x','z','z'] → rows where any string col contains 'x'.
        assert sorted(result["b"]) == ["x", "x"]

    def test_search_empty_value_short_circuits(self):
        ac = _ac()
        expr = _expr()
        cleaned, *_ = ac.handle_ops_and_clean(
            expr, "", {"search": [""]}, [{"meta": "no-op"}])
        # Empty / cleared search must keep all rows — the polars regression
        # in PR #743 hinged on this contract. Quick-arg machinery drops the
        # empty value before it reaches the interpreter.
        assert cleaned.count().execute() == 5
        # And on the no-op short-circuit the expression comes back by
        # reference — the autocleaning ``df_interpreter`` short-circuit
        # exists precisely so traitlets observers don't churn.
        assert cleaned is expr


class TestPipelining:
    """Ops compose through the interpreter: each transform returns a new
    expression that the next op consumes — the same expr-to-expr push-down
    pipeline that the postprocessing path already exercised."""

    def test_dropcol_then_fillna(self):
        ac = _ac()
        expr = _expr()
        ops = [
            [s("dropcol"), {"symbol": "df"}, "b"],
            [s("fillna"), {"symbol": "df"}, "a", 0],
        ]
        cleaned, *_ = _run(ac, expr, ops)
        result = cleaned.execute().sort_values("c").reset_index(drop=True)
        assert "b" not in cleaned.columns
        assert list(result["a"]) == [1, 2, 0, 4, 4]


class TestConfigRegistration:
    def test_conf_lists_all_five_commands(self):
        """Sanity-check the autocleaning conf so the widget surfaces every
        ported command via ``command_config['argspecs']``."""
        ac = _ac()
        argspecs = ac.command_config["argspecs"]
        for k in ("noop", "dropcol", "fillna", "drop_duplicates", "search"):
            assert k in argspecs

    def test_search_is_the_only_quick_command(self):
        assert NoCleaningConfXorq.quick_command_klasses == [Search]
        # Five commands total in the conf.
        assert set(NoCleaningConfXorq.command_klasses) == {
            DropCol, DropDuplicates, FillNA, NoOp, Search}
