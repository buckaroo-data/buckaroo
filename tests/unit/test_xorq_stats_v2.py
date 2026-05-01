"""Tests for the v2 xorq stat pipeline.

Uses ``xo.memtable`` (xorq's vendored ibis, datafusion-backed) — no raw
ibis-framework or remote backend required. Skipped if xorq is not
installed.
"""

import math

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline,
    XorqColumn)
from buckaroo.pluggable_analysis_framework.stat_func import stat  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import (  # noqa: E402
    XORQ_STATS_V2)


def _make_table():
    return xo.memtable(
        pd.DataFrame(
            {"ints": [1, 2, 3, 4, 5], "floats": [1.1, 2.2, 3.3, 4.4, 5.5], "strs": ["a", "b", "c", "d", "e"],
             "bools": [True, False, True, False, True]}))


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
        assert stats["ints"]["length"] == 5
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
        assert stats["ints"]["max"] == 5.0

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
        assert stats["ints"]["distinct_count"] == 5
        assert stats["strs"]["distinct_count"] == 5


# ============================================================
# Numeric-only stats: mean, std, median
# ============================================================


class TestNumericStats:
    def test_int_column_has_mean(self):
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, _ = pipeline.process_table(_make_table())
        assert "mean" in stats["ints"]
        assert abs(stats["ints"]["mean"] - 3.0) < 0.01

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
        assert stats["ints"]["non_null_count"] == 5
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
        assert "cat_pop" in h[0]
        # cat_pops should sum to ~1.0
        total_pop = sum(b["cat_pop"] for b in h)
        assert abs(total_pop - 1.0) < 1e-6

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
            pd.DataFrame({"vals": [1.0, None, 3.0, None, 5.0, 7.0, 9.0]}))
        pipeline = XorqStatPipeline(XORQ_STATS_V2)
        stats, errors = pipeline.process_table(table)
        assert errors == []
        h = stats["vals"]["histogram"]
        assert isinstance(h, list)
        assert len(h) > 0, "histogram should not be empty for a numeric column with nulls"
        total_pop = sum(b["cat_pop"] for b in h)
        assert abs(total_pop - 1.0) < 1e-6


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
        assert stats["ints"]["length"] == 5

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
        assert stats["ints"]["length"] == 5


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
