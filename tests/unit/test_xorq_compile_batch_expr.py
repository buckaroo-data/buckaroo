"""Tests for ``XorqStatPipeline.compile_batch_expr``.

Exports the Phase-1 batch aggregate as an ibis expression so callers can:
  - pass an ``xo.table(schema, name=...)`` UnboundTable and get a portable,
    reusable stat expression (catalog it, ship it, rebind later);
  - inspect the SQL/plan via ``ibis.to_sql``;
  - run it against a backend manually without going through ``process_table``.

Histograms (Phase 2) are intentionally not in the result — they need
scalar min/max from Phase 1 and therefore can't be folded into one expr.
"""

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline,
    XorqColumn)
from buckaroo.pluggable_analysis_framework.stat_func import stat  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402


SCHEMA = {"ints": "int64", "floats": "float64", "strs": "string", "bools": "boolean"}


def _unbound():
    return xo.table(SCHEMA, name="t")


def _real():
    return xo.memtable(pd.DataFrame(
        {"ints": [1, 2, 3, 4, 5, 6, 7], "floats": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7],
         "strs": ["a", "b", "c", "d", "e", "f", "g"], "bools": [True, False, True, False, True, False, True]}), name="t")


def _rebind(expr, unbound, real):
    """Substitute the UnboundTable op in ``expr`` with the real table's op."""
    return expr.op().replace({unbound.op(): real.op()}).to_expr()


class TestCompileBatchExpr:
    def test_returns_unbound_when_given_unbound(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        unbound = _unbound()
        expr, errors = pipeline.compile_batch_expr(unbound)
        assert errors == []
        # Should still contain the UnboundTable op — proves we didn't bind.
        # repr(expr.op()) prints an opaque object id, so walk the expr tree
        # via repr(expr) which prints the op graph.
        assert "UnboundTable" in repr(expr)

    def test_output_columns_have_expected_names(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        expr, _ = pipeline.compile_batch_expr(_unbound())
        names = set(expr.schema().names)
        assert pipeline.TOTAL_LENGTH_KEY in names
        # Every column gets null_count + distinct_count (no column_filter).
        for col in SCHEMA:
            assert f"{col}|null_count" in names
            assert f"{col}|distinct_count" in names
        # mean is numeric-not-bool → ints/floats only.
        assert "ints|mean" in names
        assert "floats|mean" in names
        assert "strs|mean" not in names
        assert "bools|mean" not in names
        # min/max use _is_numeric_ibis → numeric per ibis dtype. In xorq's
        # vendored ibis, boolean.is_numeric() is False, so bools are out
        # alongside strs.
        assert "ints|min" in names
        assert "floats|max" in names
        assert "strs|min" not in names
        assert "bools|min" not in names

    def test_no_histogram_in_batch_expr(self):
        """Histogram is Phase 2 — must not appear in the compiled batch expr."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        expr, _ = pipeline.compile_batch_expr(_unbound())
        names = set(expr.schema().names)
        for col in SCHEMA:
            assert f"{col}|histogram" not in names

    def test_rebind_matches_process_table_batch_results(self):
        """Rebinding the unbound expr to a real source and executing must yield
        the same scalar values that process_table records in its accumulator
        for the same batch-phase stats."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        unbound = _unbound()
        real = _real()

        expr, errors = pipeline.compile_batch_expr(unbound)
        assert errors == []
        rebound = _rebind(expr, unbound, real)
        df = rebound.execute()

        baseline, _ = pipeline.process_table(real)

        # __total_length__ matches `length` on every column accumulator.
        assert int(df[pipeline.TOTAL_LENGTH_KEY].iloc[0]) == baseline["ints"]["length"]

        # Spot-check a few (col, stat) pairs against the accumulator.
        for col, stat_name in [
            ("ints", "null_count"),
            ("ints", "min"),
            ("ints", "max"),
            ("ints", "mean"),
            ("floats", "median"),
            ("strs", "distinct_count"),
            ("bools", "null_count"),
        ]:
            key = f"{col}|{stat_name}"
            got = df[key].iloc[0]
            want = baseline[col][stat_name]
            # Coerce numpy scalars; allow float NaN-tolerance not needed here.
            assert float(got) == pytest.approx(float(want)), (
                f"mismatch on {key}: rebound={got} baseline={want}")

    def test_accepts_real_table_too(self):
        """compile_batch_expr should accept a bound table — just produces a
        bound aggregate expression (no rebind needed)."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        expr, errors = pipeline.compile_batch_expr(_real())
        assert errors == []
        df = expr.execute()
        assert len(df) == 1
        assert int(df[pipeline.TOTAL_LENGTH_KEY].iloc[0]) == 7

    def test_construction_error_surfaces_in_errors(self):
        """A stat that raises while building its ibis expression must appear
        in the returned errors list, not be silently dropped."""

        @stat()
        def broken_batch(col: XorqColumn) -> int:
            raise RuntimeError("intentional construction failure")

        pipeline = XorqStatPipeline([*XORQ_STATS_V2, broken_batch], unit_test=False)
        expr, errors = pipeline.compile_batch_expr(_unbound())
        # One error per column the stat would have been built for (no filter
        # → every column).
        assert len(errors) == len(SCHEMA)
        for se in errors:
            assert isinstance(se.error, RuntimeError)
            assert se.stat_key == "broken_batch"
            assert se.column in SCHEMA
        # The expression should still compile — the broken stat is just absent.
        names = set(expr.schema().names)
        for col in SCHEMA:
            assert f"{col}|broken_batch" not in names

    def test_process_table_still_works_after_refactor(self):
        """compile_batch_expr is extracted from process_table's Phase 1.
        process_table itself must continue to produce correct results."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_real())
        assert errors == []
        assert stats["ints"]["length"] == 7
        assert stats["ints"]["mean"] == pytest.approx(4.0)
        assert stats["strs"]["distinct_count"] == 7
