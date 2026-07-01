"""Tests for the v2 xorq stat pipeline.

Uses ``xo.memtable`` (xorq's vendored ibis, datafusion-backed) — no raw
ibis-framework or remote backend required. Skipped if xorq is not
installed.
"""

import logging
import math
import os

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.pluggable_analysis_framework import perf_log  # noqa: E402
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline,
    XorqColumn)
from buckaroo.pluggable_analysis_framework.stat_func import stat  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import (  # noqa: E402
    XORQ_STATS_V2)


def _make_table():
    # ints/floats need >5 distinct values to land on the numeric histogram
    # branch (cf. histogram() in xorq_stats_v2 — small-cardinality numeric
    # cols fall through to categorical, mirroring pd_stats_v2).
    return xo.memtable(
        pd.DataFrame(
            {"ints": [1, 2, 3, 4, 5, 6, 7], "floats": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7],
             "strs": ["a", "b", "c", "d", "e", "f", "g"], "bools": [True, False, True, False, True, False, True]}))


def _make_table_with_nulls():
    return xo.memtable(
        pd.DataFrame(
            {"vals": [1.0, None, 3.0, None, 5.0], "strs": ["a", None, "c", None, "e"]}))


def _make_table_categorical():
    return xo.memtable(
        pd.DataFrame(
            {"cat": ["a", "a", "a", "b", "b", "c", "d", "e", "f", "g", "h"]}))


# ============================================================
# Typing stats
# ============================================================


class TestTyping:
    def test_int(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        assert stats["ints"]["is_numeric"] is True
        assert stats["ints"]["is_integer"] is True
        assert stats["ints"]["is_float"] is False
        assert stats["ints"]["_type"] == "integer"

    def test_float(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["floats"]["is_float"] is True
        assert stats["floats"]["is_integer"] is False
        assert stats["floats"]["_type"] == "float"

    def test_string(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["strs"]["is_string"] is True
        assert stats["strs"]["is_numeric"] is False
        assert stats["strs"]["_type"] == "string"

    def test_bool(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["bools"]["is_bool"] is True
        assert stats["bools"]["_type"] == "boolean"

    def test_datetime(self):
        table = xo.memtable(
            pd.DataFrame(
                {"ts": pd.to_datetime(["2021-01-01", "2021-01-02", "2021-01-03"])}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(table)
        assert stats["ts"]["is_datetime"] is True
        assert stats["ts"]["_type"] == "datetime"


# ============================================================
# Batched aggregate stats: length, null_count, min, max, distinct_count
# ============================================================


class TestBatchAggregate:
    def test_length_and_null_count(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["ints"]["length"] == 7
        assert stats["ints"]["null_count"] == 0

    def test_with_nulls(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table_with_nulls())
        assert stats["vals"]["null_count"] == 2
        assert stats["vals"]["length"] == 5
        assert stats["strs"]["null_count"] == 2

    def test_min_max_numeric(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["ints"]["min"] == 1.0
        assert stats["ints"]["max"] == 7.0

    def test_min_max_skipped_for_string(self):
        """String columns: column_filter excludes the min/max stats."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        # Either absent or None — both signal "not computed"
        assert stats["strs"].get("min") is None
        assert stats["strs"].get("max") is None

    def test_distinct_count(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["ints"]["distinct_count"] == 7
        assert stats["strs"]["distinct_count"] == 7

    def test_distinct_count_uses_approx(self):
        """distinct_count must build ApproxCountDistinct, not exact CountDistinct.

        Exact COUNT(DISTINCT) folded into the shared batch aggregate defeats
        DataFusion's single-distinct rewrite: 3.8GB peak on a 131M-row string
        column with 6.2M distinct values, vs 238MB for approx_nunique in the
        same batch shape (#906).
        """
        from xorq.vendor.ibis.expr import operations as ops

        from buckaroo.customizations.xorq_stats_v2 import distinct_count

        expr = distinct_count._stat_func.func(col=_make_table().strs)
        op = expr.op()
        assert list(op.find(ops.ApproxCountDistinct)), (
            "distinct_count should aggregate via approx_nunique")
        # ApproxCountDistinct subclasses CountDistinct, so filter it out to
        # check no *exact* distinct aggregate remains.
        exact = [n for n in op.find(ops.CountDistinct)
                 if not isinstance(n, ops.ApproxCountDistinct)]
        assert not exact, "exact COUNT(DISTINCT) must not enter the batch aggregate"

    def test_distinct_count_exact_fallback_for_bool(self):
        """Booleans keep exact nunique — approx_distinct raises on Boolean.

        One failing expression aborts the whole batch aggregate, and exact
        COUNT(DISTINCT bool) is trivially cheap (<= 3 entries of hash state),
        so booleans must fall back to the exact aggregate rather than error.
        """
        from xorq.vendor.ibis.expr import operations as ops

        from buckaroo.customizations.xorq_stats_v2 import distinct_count

        expr = distinct_count._stat_func.func(col=_make_table().bools)
        op = expr.op()
        assert not list(op.find(ops.ApproxCountDistinct))
        assert list(op.find(ops.CountDistinct))

    def test_distinct_count_skipped_for_floats(self):
        """Float columns skip distinct_count entirely.

        approx_distinct raises on Float64, and exact COUNT(DISTINCT) costs
        memory proportional to cardinality (~2.2GB measured on a 30M-distinct
        column) for a number that is rarely meaningful on floats. The stat is
        skipped: distinct_count and distinct_per resolve to None, while the
        numeric histogram and histogram_bins must still be produced.
        """
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        assert stats["floats"]["distinct_count"] is None
        assert stats["floats"]["distinct_per"] is None
        assert len(stats["floats"]["histogram"]) > 0
        assert len(stats["floats"]["histogram_bins"]) == 11
        # non-float columns are unaffected
        assert stats["ints"]["distinct_count"] == 7
        assert stats["strs"]["distinct_per"] == 1.0

    def test_distinct_count_skipped_for_nested_types(self):
        """Struct / array / map columns skip distinct_count.

        approx_distinct raises on nested types, so they fall to exact
        COUNT(DISTINCT) — and a high-cardinality nested column is the same
        multi-GB hash set #906 fixed for strings: ~25GB measured streaming the
        stats over a 24M-row ``struct<url, description>`` column, all of it the
        exact distinct on that one column (#908 only routed scalar string /
        integer / timestamp / date to approx). They must be filtered out like
        floats so distinct_count resolves to None and dependents still run.
        """
        from xorq.vendor.ibis.expr import datatypes as dt

        from buckaroo.customizations.xorq_stats_v2 import distinct_count

        cf = distinct_count._stat_func.column_filter
        assert cf(dt.Struct({"url": "string", "description": "string"})) is False
        assert cf(dt.Array(dt.string)) is False
        assert cf(dt.Map(dt.string, dt.string)) is False
        # scalar columns still computed; the existing float skip is preserved
        assert cf(dt.string) is True
        assert cf(dt.int64) is True
        assert cf(dt.float64) is False

    @pytest.mark.parametrize("dtype, supported, approx", [
        # approx_nunique works (HLL, bounded) — empirically verified across the
        # arrow dtypes on xorq-datafusion 0.2.7 (#918):
        ("int64", True, True),
        ("int32", True, True),
        ("string", True, True),
        ("binary", True, True),         # approx works; was wrongly on exact
        ("date", True, True),
        ("time", True, True),           # approx works; was wrongly on exact
        ("timestamp", True, True),
        # approx raises but cardinality is bounded -> keep exact:
        ("boolean", True, False),       # <= 2 distinct
        # approx raises AND cardinality unbounded -> skip (exact is a multi-GB
        # hash set on high cardinality):
        ("float64", False, False),
        ("decimal", False, False),      # was wrongly on exact
        ("struct", False, False),
        ("array", False, False),
        ("map", False, False),
    ])
    def test_distinct_count_type_classification(self, dtype, supported, approx):
        """Every arrow dtype is classified approx / exact / skip — never an
        unbounded exact COUNT(DISTINCT) on a type approx can't cover."""
        from xorq.vendor.ibis.expr import datatypes as dt

        from buckaroo.customizations.xorq_stats_v2 import (
            _distinct_count_approx, distinct_count)

        d = {"int64": dt.int64, "int32": dt.int32, "string": dt.string,
            "binary": dt.binary, "date": dt.date, "time": dt.time,
            "timestamp": dt.Timestamp(), "boolean": dt.boolean,
            "float64": dt.float64, "decimal": dt.Decimal(5, 2),
            "struct": dt.Struct({"a": "string"}), "array": dt.Array(dt.string),
            "map": dt.Map(dt.string, dt.string)}[dtype]
        cf = distinct_count._stat_func.column_filter
        assert cf(d) is supported, f"{dtype}: column_filter (supported)"
        assert _distinct_count_approx(d) is approx, f"{dtype}: approx path"


# ============================================================
# Numeric-only stats: mean, std, median
# ============================================================


class TestNumericStats:
    def test_int_column_has_mean(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert "mean" in stats["ints"]
        assert abs(stats["ints"]["mean"] - 4.0) < 0.01

    def test_float_column_full_numeric(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert "mean" in stats["floats"]
        assert "std" in stats["floats"]
        assert "median" in stats["floats"]

    def test_string_excluded(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["strs"].get("mean") is None
        assert stats["strs"].get("std") is None
        assert stats["strs"].get("median") is None

    def test_bool_excluded(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["bools"].get("mean") is None
        assert stats["bools"].get("std") is None


# ============================================================
# Computed (DAG-derived) stats
# ============================================================


class TestComputedStats:
    def test_no_nulls(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["ints"]["non_null_count"] == 7
        assert stats["ints"]["nan_per"] == 0.0
        assert stats["ints"]["distinct_per"] == 1.0

    def test_with_nulls(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table_with_nulls())
        assert stats["vals"]["nan_per"] == 2 / 5
        assert stats["vals"]["non_null_count"] == 3


# ============================================================
# Histogram — must be live (not dead code)
# ============================================================


class TestHistogram:
    def test_numeric_histogram_present(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        h = stats["ints"]["histogram"]
        assert isinstance(h, list)
        assert len(h) > 0
        assert "name" in h[0]
        assert "population" in h[0]
        # populations should sum to ~100.0
        total_pop = sum(b["population"] for b in h)
        assert abs(total_pop - 100.0) < 0.6  # per-bucket 1dp rounding drift

    def test_categorical_histogram_present(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table_categorical())
        assert errors == []
        h = stats["cat"]["histogram"]
        assert isinstance(h, list)
        assert 0 < len(h) <= 10  # top-10 cap
        # 'a' appears 3 times — should be present
        names = [b["name"] for b in h]
        assert "a" in names
        # cat_pop must be on the 0-100 scale like pandas/polars; all 8
        # categories fit in the top-10 cap, so they sum to ~100
        total_pop = sum(b["cat_pop"] for b in h)
        assert abs(total_pop - 100.0) < 0.6  # per-bucket 1dp rounding drift

    def test_categorical_histogram_bounded_above_100k_rows(self):
        """Above 100k rows the categorical histogram must sample, not group the full table.

        The exact top-10 query (group_by(col).count().order_by(desc).limit(10))
        materializes a hash entry per distinct value: ~1GB transient per
        high-cardinality string column on a 26M-row table (#907). Above the
        100k-row threshold the group-by input must be bounded by a Sample
        node; at or below the threshold the exact query is preserved.
        """
        from xorq.vendor.ibis.expr import operations as ops

        from buckaroo.customizations.xorq_stats_v2 import histogram

        fn = histogram._stat_func.func
        table = _make_table_categorical()
        captured = []

        def execute(query):
            captured.append(query)
            return query.execute()

        fn(expr=table, execute=execute, orig_col_name="cat", is_numeric=False,
           is_bool=False, length=200_000, distinct_count=8, min=None, max=None)
        assert len(captured) == 1
        assert list(captured[0].op().find(ops.Sample)), (
            "categorical histogram over >100k rows must bound its input with a sample")

        small = fn(expr=table, execute=execute, orig_col_name="cat", is_numeric=False,
            is_bool=False, length=11, distinct_count=8, min=None, max=None)
        assert not list(captured[1].op().find(ops.Sample)), (
            "at or below 100k rows the exact top-10 query must be preserved")
        assert [b["name"] for b in small][0] == "a"

    def test_categorical_histogram_sampled_finds_dominant_value(self):
        """Sampled top-10 still surfaces the dominant category above the threshold.

        Half the rows share one value, the rest are unique — any ~100k-row
        sample puts the shared value on top with cat_pop near 100 (the other
        top-10 entries are singletons).
        """
        n = 150_000
        vals = ["common"] * (n // 2) + [f"u{i}" for i in range(n - n // 2)]
        table = xo.memtable(pd.DataFrame({"cat": vals}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        h = stats["cat"]["histogram"]
        assert h[0]["name"] == "common"
        assert h[0]["cat_pop"] > 90

    def test_histogram_constant_column_empty(self):
        """Constant numeric column (min == max) → empty histogram, not crash."""
        table = xo.memtable(pd.DataFrame({"const": [7, 7, 7, 7]}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        # Empty list is fine; the key being present is what matters
        assert "histogram" in stats["const"]

    def test_numeric_histogram_with_nulls(self):
        """Numeric column with nulls must still produce a populated histogram.

        Regression: nulls in the source column produce a NULL ``__bucket``
        group; ``int(NaN)`` then raised inside ``_numeric_histogram`` and
        ``default=[]`` swallowed the failure, so columns with even a single
        null silently lost their histogram entirely.
        """
        table = xo.memtable(
            pd.DataFrame({"vals": [1.0, None, 3.0, None, 5.0, 7.0, 9.0, 11.0, 13.0]}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        h = stats["vals"]["histogram"]
        assert isinstance(h, list)
        assert len(h) > 0, "histogram should not be empty for a numeric column with nulls"
        total_pop = sum(b["population"] for b in h)
        assert abs(total_pop - 100.0) < 0.6  # per-bucket 1dp rounding drift

    def test_histogram_bins_numeric(self):
        """histogram_bins must be 11 evenly-spaced edges for numeric columns."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        bins = stats["ints"]["histogram_bins"]
        assert isinstance(bins, list)
        assert len(bins) == 11
        assert bins[0] == stats["ints"]["min"]
        assert abs(bins[-1] - stats["ints"]["max"]) < 1e-9
        # evenly spaced
        widths = [bins[i + 1] - bins[i] for i in range(10)]
        assert all(abs(w - widths[0]) < 1e-9 for w in widths)

    def test_histogram_bins_non_numeric_empty(self):
        """histogram_bins must be empty for string columns."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        assert stats["strs"]["histogram_bins"] == []

    def test_histogram_bins_bool_empty(self):
        """histogram_bins must be empty for boolean columns."""
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        assert stats["bools"]["histogram_bins"] == []

    def test_histogram_bins_constant_empty(self):
        """Constant numeric column (min == max) must return empty histogram_bins."""
        table = xo.memtable(pd.DataFrame({"const": [7, 7, 7, 7, 7, 7, 7]}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        assert stats["const"]["histogram_bins"] == []

    def test_histogram_bins_low_cardinality_empty(self):
        """Numeric column with ≤ 5 distinct values must return empty histogram_bins."""
        table = xo.memtable(pd.DataFrame({"few": [1, 2, 3, 4, 5, 1, 2, 3]}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        assert stats["few"]["histogram_bins"] == []


# ============================================================
# Structured error capture — silent excepts must be gone
# ============================================================


class TestErrorCapture:
    def test_bad_expression_surfaces_as_error(self):
        """An intentionally broken @stat must produce a StatError, not silent loss."""

        class _Boom(Exception):
            pass

        @stat()
        def will_fail(col: XorqColumn) -> int:
            raise _Boom("intentional")

        pipeline = XorqStatPipeline([*XORQ_STATS_V2, will_fail])
        stats, errors = pipeline.process_table(_make_table())
        # At least one error must have been captured
        assert len(errors) > 0
        assert any(isinstance(e.error, _Boom) for e in errors)
        # And the rest of the pipeline should still work
        assert stats["ints"]["length"] == 7

    def test_bad_aggregate_execution_surfaces(self):
        """If a stat raises while building the expression, the error is reported."""

        @stat()
        def bad_agg(col: XorqColumn) -> int:
            # Building the expression itself raises.
            return col.cast("does_not_exist")

        pipeline = XorqStatPipeline([*XORQ_STATS_V2, bad_agg])
        stats, errors = pipeline.process_table(_make_table())
        assert any(e.stat_key == "bad_agg" for e in errors)
        # Other stats unaffected
        assert stats["ints"]["length"] == 7


# ============================================================
# Full pipeline + edges
# ============================================================


class TestFullPipeline:
    def test_mixed_types(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(_make_table())
        assert errors == []
        for col in ("ints", "floats", "strs", "bools"):
            assert "length" in stats[col]
            assert "null_count" in stats[col]
            assert "_type" in stats[col]
            assert "distinct_count" in stats[col]

        assert "mean" in stats["ints"]
        assert "mean" in stats["floats"]
        assert stats["strs"].get("mean") is None
        assert stats["bools"].get("mean") is None

    def test_empty_table(self):
        table = xo.memtable(pd.DataFrame({"a": pd.Series([], dtype="int64")}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(table)
        assert stats["a"]["length"] == 0

    def test_orig_col_name_pass_through(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert stats["ints"]["orig_col_name"] == "ints"

    def test_dag_validates_at_construction(self):
        """Constructing the pipeline should validate the DAG (no DAGConfigError)."""
        XorqStatPipeline(XORQ_STATS_V2)


# ============================================================
# Polish — _to_python_scalar handles pandas missing-data singletons
# ============================================================


class TestToPythonScalar:
    def test_handles_pd_na(self):
        """pd.NA / pd.NaT must coerce to None.

        These are pandas missing-data singletons that don't have ``.item()``
        and aren't valid scalar types — they'd fail the framework's
        isinstance type check downstream with a confusing TypeError.
        """
        from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (_to_python_scalar)

        assert _to_python_scalar(pd.NA) is None
        assert _to_python_scalar(pd.NaT) is None
        assert _to_python_scalar(None) is None

    def test_preserves_real_values(self):
        """Real scalars / numpy scalars come through unchanged (or coerced
        to native Python via .item())."""
        import numpy as np

        from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (_to_python_scalar)

        assert _to_python_scalar(np.int64(42)) == 42
        assert _to_python_scalar(np.float64(3.14)) == 3.14
        assert _to_python_scalar(0) == 0
        # NaN is a valid float — must NOT coerce to None
        assert math.isnan(_to_python_scalar(float("nan")))


# ============================================================
# Polish — typing_stats temporal classification
# ============================================================


class TestTypingStatsClassification:
    """Direct unit tests of the typing_stats function for edge cases.

    Avoids the per-column DAG plumbing — just exercises the dtype-string
    classification logic directly.
    """

    def _classify(self, dtype: str):
        from buckaroo.customizations.xorq_stats_v2 import typing_stats

        return typing_stats._stat_func.func(dtype=dtype)

    def test_temporal_dtypes_classified(self):
        for dt in ("timestamp[ns]", "date32", "time", "interval"):
            assert self._classify(dt)[
                "is_datetime"
            ], f"{dt!r} should be classified as datetime"

    def test_non_temporal_dtypes_not_misclassified(self):
        for dt in ("string", "int64", "boolean", "float64"):
            assert not self._classify(dt)[
                "is_datetime"
            ], f"{dt!r} must NOT be classified as datetime"


# ============================================================
# Smoke check — PERVERSE_DF-equivalent at construction time
# ============================================================


class TestUnitTestSmokeCheck:
    def test_passes_on_default_stats(self):
        """XorqStatPipeline must run an automatic smoke check at construction.

        Mirrors StatPipeline._unit_test_result — catches dumb stat bugs (e.g.
        a typo, a wrong dtype assumption) at pipeline construction rather
        than later when real data hits the pipeline.
        """
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        passed, errors = pipeline._unit_test_result
        assert passed, f"smoke check failed unexpectedly: {errors}"

    def test_fails_on_broken_stat(self):
        """A @stat that always raises must be caught by the smoke check."""

        @stat()
        def always_breaks(col: XorqColumn) -> int:
            raise RuntimeError("always broken")

        pipeline = XorqStatPipeline([*XORQ_STATS_V2, always_breaks])
        passed, errors = pipeline._unit_test_result
        assert not passed
        assert errors  # at least one StatError captured


# ============================================================
# Backend threading — every query must route through pipeline backend
# ============================================================


class TestBackendThreading:
    def test_histogram_uses_passed_in_backend(self):
        """All ibis queries (batch + histogram) must go through the pipeline's backend.

        Regression: histogram path called ``query.execute()`` directly, bypassing
        ``self._execute`` and any user-supplied backend.
        """

        class TrackingBackend:
            def __init__(self):
                self.calls = 0

            def execute(self, query):
                self.calls += 1
                return query.execute()

        backend = TrackingBackend()
        pipeline = XorqStatPipeline(XORQ_STATS_V2, backend=backend)
        pipeline.process_table(_make_table())

        # _make_table() has 4 columns: ints, floats (numeric → 2 histogram queries
        # each: bounds + bucket), strs, bools (categorical → 1 query each).
        # Plus 1 batch aggregate. So with full threading we expect well over 1.
        # Without the fix, only the batch query (1) goes through the backend.
        assert (
            backend.calls > 1
        ), f"histogram bypasses pipeline backend; saw only {backend.calls} call"

    def test_histogram_does_not_recompute_min_max(self):
        """Histogram must not issue its own bounds query — min/max already in batch.

        With 4 columns (2 numeric: ints/floats, 2 non-numeric: strs/bools), an
        optimal pipeline issues:
            1 batch aggregate (all batched stats incl. min/max)
            + 2 numeric histogram bucket queries
            + 2 categorical histogram queries (strs, bools)
            = 5 total

        Prior code added 2 redundant bounds queries (one per numeric col) for 7.
        """

        class TrackingBackend:
            def __init__(self):
                self.calls = 0

            def execute(self, query):
                self.calls += 1
                return query.execute()

        backend = TrackingBackend()
        pipeline = XorqStatPipeline(XORQ_STATS_V2, backend=backend)
        pipeline.process_table(_make_table())
        assert (
            backend.calls <= 5
        ), f"histogram is recomputing min/max; saw {backend.calls} queries"


class TestCacheStorageExecute:
    """_execute serves a cache HIT by reading the snapshot parquet directly
    rather than re-planning the expression through cache().execute()."""

    def test_cache_hit_reads_parquet_directly(self, tmp_path):
        import buckaroo.pluggable_analysis_framework.xorq_stat_pipeline as xsp
        from unittest.mock import patch

        cache = xo.ParquetSnapshotCache.from_kwargs(
            source=xo.connect(), base_path=str(tmp_path))
        con = xo.connect()
        df = pd.DataFrame({"k": range(20), "v": [float(i % 7) for i in range(20)]})
        t = con.create_table("ce_t", df)
        query = t.filter(t.v > 1)

        pipeline = XorqStatPipeline(XORQ_STATS_V2, cache_storage=cache)

        # First execute is a MISS: the snapshot doesn't exist yet, so the
        # parquet-read shortcut must NOT fire — it falls through to cache().
        with patch.object(xsp.pd, "read_parquet", wraps=pd.read_parquet) as miss_spy:
            result1 = pipeline._execute(query)
        assert miss_spy.call_count == 0, "read_parquet fired before the cache was populated"

        key = cache.calc_key(query)
        assert os.path.exists(cache.storage.get_path(key)), "miss did not populate the cache"

        # Second execute is a HIT: served by reading the snapshot parquet,
        # never re-planning through cache().execute().
        with patch.object(xsp.pd, "read_parquet", wraps=pd.read_parquet) as hit_spy:
            result2 = pipeline._execute(query)
        assert hit_spy.call_count == 1, "cache hit did not read the snapshot parquet"

        pd.testing.assert_frame_equal(
            result1.reset_index(drop=True), result2.reset_index(drop=True))


class TestSnapshotCacheRun:
    """Per-run snapshot-cache behaviour (#910).

    A cold run computes each stat query against the source and writes one
    snapshot per query; a fully-warm run reads those snapshots without
    re-scanning the source; every run with a cache configured logs a single
    summary line carrying the hit/miss/snapshot/byte/error counts."""

    _LOGGER = "buckaroo.pluggable_analysis_framework.xorq_stat_pipeline"

    @staticmethod
    def _cache(tmp_path):
        return xo.ParquetSnapshotCache.from_kwargs(
            source=xo.connect(), base_path=str(tmp_path))

    @staticmethod
    def _filter_chain_table():
        # Lazy filter chain with a numeric column (numeric histogram) and a
        # string column (categorical histogram), so both per-column query
        # shapes run through the cache.
        con = xo.connect()
        df = pd.DataFrame(
            {"n": list(range(40)), "cat": [c for c in "abcdefgh" for _ in range(5)]})
        t = con.create_table("snap_src", df)
        return t.filter(t.n > 1)

    def test_cold_run_writes_snapshots(self, tmp_path):
        pipeline = XorqStatPipeline(
            XORQ_STATS_V2, unit_test=False, cache_storage=self._cache(tmp_path))
        pipeline.process_table(self._filter_chain_table())
        s = pipeline._cache_stats
        assert s["misses"] > 0 and s["hits"] == 0, f"cold run should miss the cache: {s}"
        assert s["snapshots"] == s["misses"], "each miss should write exactly one snapshot"
        assert s["bytes"] > 0 and s["write_errors"] == 0
        files = [f for _, _, fs in os.walk(tmp_path) for f in fs if f.endswith(".parquet")]
        assert files, "expected snapshot parquet files under the cache dir"

    def test_warm_run_hits_cache(self, tmp_path):
        cache = self._cache(tmp_path)
        XorqStatPipeline(XORQ_STATS_V2, unit_test=False,
            cache_storage=cache).process_table(self._filter_chain_table())
        warm = XorqStatPipeline(XORQ_STATS_V2, unit_test=False, cache_storage=cache)
        warm.process_table(self._filter_chain_table())
        s = warm._cache_stats
        assert s["hits"] > 0 and s["misses"] == 0, f"warm run should hit the cache: {s}"
        assert s["snapshots"] == 0, "a fully-warm run should write nothing"

    def test_run_logs_one_cache_summary_line(self, tmp_path, caplog):
        pipeline = XorqStatPipeline(
            XORQ_STATS_V2, unit_test=False, cache_storage=self._cache(tmp_path))
        with caplog.at_level(logging.INFO, logger=self._LOGGER):
            pipeline.process_table(self._filter_chain_table())
        lines = [r.getMessage() for r in caplog.records
                 if r.name == self._LOGGER and r.getMessage().startswith("xorq stat cache")]
        assert len(lines) == 1, f"expected exactly one cache summary line, got {lines}"
        assert "miss(es)" in lines[0] and "snapshot(s) written" in lines[0]

    def test_cache_run_stats_reports_status_and_timing(self, tmp_path):
        """The public cache_run_stats() exposes the cold/warm outcome as a
        structured signal — status + timing — for telemetry consumers (#943)."""
        cache = self._cache(tmp_path)
        cold = XorqStatPipeline(XORQ_STATS_V2, unit_test=False, cache_storage=cache)
        cold.process_table(self._filter_chain_table())
        cs = cold.cache_run_stats()
        assert cs["cached"] is True
        assert cs["status"] == "miss"
        assert cs["misses"] > 0 and cs["hits"] == 0
        assert cs["secs"] >= 0.0

        warm = XorqStatPipeline(XORQ_STATS_V2, unit_test=False, cache_storage=cache)
        warm.process_table(self._filter_chain_table())
        ws = warm.cache_run_stats()
        assert ws["status"] == "hit"
        assert ws["hits"] > 0 and ws["misses"] == 0

    def test_cache_run_stats_uncached(self):
        """With no snapshot cache configured, the run reports status 'uncached'."""
        p = XorqStatPipeline(XORQ_STATS_V2, unit_test=False)
        p.process_table(self._filter_chain_table())
        s = p.cache_run_stats()
        assert s["cached"] is False
        assert s["status"] == "uncached"
        assert s["secs"] >= 0.0

    def test_internal_spans_emit_to_telemetry_sink_with_perf_off(self):
        """#944: the stat.xorq.* spans must reach a bound telemetry sink even
        when BUCKAROO_PERF logging is off — the same enabled-OR-sink decoupling
        perf_span already uses. Before the fix _span() gated on
        perf_log.enabled() alone and returned a no-op, so a telemetry-only run
        emitted firstpull.* spans but never the stat.xorq.* timeline."""
        records: list = []
        saved = perf_log._ENABLED
        perf_log._ENABLED = False
        try:
            pipeline = XorqStatPipeline(XORQ_STATS_V2, unit_test=False)
            with perf_log.telemetry_context("sess-stat-span", records.append):
                pipeline.process_table(self._filter_chain_table())
        finally:
            perf_log._ENABLED = saved
        names = [r["name"] for r in records]
        assert "stat.xorq.total" in names, (
            f"stat.xorq.total span must emit to the sink with perf logging off; "
            f"got {names}")

    def test_cache_outcome_rides_total_span_to_telemetry(self, tmp_path):
        """#951: the per-run snapshot-cache outcome — status, snapshots, bytes,
        write_errors — rides the stat.xorq.total telemetry span, so a telemetry
        consumer sees the write side without reading a server log.

        Before the fix _log_cache_stats emitted only a log.info line the server
        never surfaced, so a cache that stopped writing was invisible."""
        records: list = []
        saved = perf_log._ENABLED
        perf_log._ENABLED = False
        try:
            pipeline = XorqStatPipeline(
                XORQ_STATS_V2, unit_test=False, cache_storage=self._cache(tmp_path))
            with perf_log.telemetry_context("sess-cache-write", records.append):
                pipeline.process_table(self._filter_chain_table())
        finally:
            perf_log._ENABLED = saved
        total = next(r for r in records if r["name"] == "stat.xorq.total")
        attrs = total["attrs"]
        # Cold run against a fresh cache dir → a pure miss that writes snapshots.
        assert attrs["cache_status"] == "miss"
        assert attrs["cache_snapshots"] > 0
        assert attrs["cache_bytes"] > 0
        assert attrs["cache_write_errors"] == 0

    def test_cached_stats_match_uncached(self, tmp_path):
        """The cold (compute + write) and warm (snapshot-read) cache paths
        produce the same stats as a plain uncached run — the cache is a perf
        optimization, not a semantic change."""
        cache = self._cache(tmp_path)
        plain, _ = XorqStatPipeline(
            XORQ_STATS_V2, unit_test=False).process_table(self._filter_chain_table())
        cold, _ = XorqStatPipeline(
            XORQ_STATS_V2, unit_test=False,
            cache_storage=cache).process_table(self._filter_chain_table())
        warm, _ = XorqStatPipeline(
            XORQ_STATS_V2, unit_test=False,
            cache_storage=cache).process_table(self._filter_chain_table())
        # The warm run reads the exact parquet the cold run wrote, so its whole
        # SD (histogram row order included) must reproduce the cold run's.
        assert cold == warm, "warm run must reproduce the cold run's snapshot exactly"
        # Compare the tie-independent stats against the plain run.
        for col in plain:
            for key in ("length", "min", "max", "mean", "null_count", "distinct_count"):
                assert cold[col].get(key) == plain[col].get(key), (col, key)
