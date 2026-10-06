"""End-to-end test for XorqDfStatsV2 — the DfStats-shaped wrapper that
makes the xorq pipeline reachable from buckaroo widget / DataFlow code.

Asserts the same surface contract as DfStatsV2: ``.sdf`` (SDType),
``.errs`` (ErrDict), and ``.ap.ordered_a_objs``.
"""

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

import xorq.vendor.ibis.expr.types.core as ibis_core  # noqa: E402

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqDfStatsV2)
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402


def _table():
    return xo.memtable(
        pd.DataFrame(
            {"ints": [1, 2, 3, 4, 5], "strs": ["a", "b", "c", "a", "b"]}))


class TestXorqDfStatsV2:
    def test_sdf_shape(self):
        stats = XorqDfStatsV2(_table(), XORQ_STATS_V2)
        assert "ints" in stats.sdf
        assert "strs" in stats.sdf
        assert stats.sdf["ints"]["length"] == 5
        assert stats.sdf["ints"]["mean"] == 3.0
        assert stats.errs == {}

    def test_errs_v1_compat_shape(self):
        """A failure surfaces in errs as {(col, stat): (Exception, kls)}."""
        from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqColumn
        from buckaroo.pluggable_analysis_framework.stat_func import stat

        @stat()
        def will_fail(col: XorqColumn) -> int:
            raise RuntimeError("boom")

        stats = XorqDfStatsV2(_table(), [*XORQ_STATS_V2, will_fail])
        # At least one v1-shaped error key
        assert stats.errs
        for k, v in stats.errs.items():
            assert isinstance(k, tuple) and len(k) == 2
            assert isinstance(v, tuple) and len(v) == 2
            assert isinstance(v[0], Exception)

    def test_verify_analysis_objects_classmethod(self):
        """DataFlow calls this before processing; should not raise on a good list."""
        XorqDfStatsV2.verify_analysis_objects(XORQ_STATS_V2)

    def test_ordered_a_objs_round_trip(self):
        """DataFlow.add_analysis reads stats.ap.ordered_a_objs after add."""
        stats = XorqDfStatsV2(_table(), XORQ_STATS_V2)
        assert list(stats.ap.ordered_a_objs) == list(XORQ_STATS_V2)

    def test_add_analysis_appends_and_reprocesses(self):
        """add_analysis must rebuild the DAG and surface the new key in sdf.

        DfStatsV2 / PlDfStatsV2 implement this for interactive stat injection;
        XorqDfStatsV2 needs to match the contract.
        """
        from buckaroo.pluggable_analysis_framework.stat_func import stat

        @stat()
        def double_length(length: int) -> int:
            return length * 2

        stats = XorqDfStatsV2(_table(), XORQ_STATS_V2)
        stats.add_analysis(double_length)
        assert stats.sdf["ints"]["double_length"] == 10
        assert stats.sdf["strs"]["double_length"] == 10

    def test_add_analysis_keeps_skip_columns_skipped(self):
        """A column skipped at construction (its stats come from elsewhere) stays
        unscanned when add_analysis reruns the pipeline (#1060)."""
        from buckaroo.pluggable_analysis_framework.stat_func import XorqColumn, stat

        @stat()
        def non_null(col: XorqColumn) -> int:
            return col.count()

        stats = XorqDfStatsV2(_table(), XORQ_STATS_V2, skip_columns=["strs"])
        skipped_keys = set(stats.sdf["strs"])
        stats.add_analysis(non_null)
        assert stats.sdf["ints"]["non_null"] == 5
        assert set(stats.sdf["strs"]) == skipped_keys

    def test_add_analysis_refreshes_length(self, monkeypatch):
        """``length`` is the row count of the last run. A first run that couldn't
        count the table leaves it None, and add_analysis's rerun fills it in
        (#1060)."""
        from buckaroo.pluggable_analysis_framework.stat_func import stat

        @stat()
        def double_length(length: int) -> int:
            return length * 2

        def backend_down(expr, *args, **kwargs):
            raise ConnectionError("backend down")

        with monkeypatch.context() as m:
            m.setattr(ibis_core.Expr, "execute", backend_down)
            stats = XorqDfStatsV2(_table(), XORQ_STATS_V2)
        assert stats.length is None
        stats.add_analysis(double_length)
        assert stats.length == 5
