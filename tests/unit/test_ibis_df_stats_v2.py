"""End-to-end test for IbisDfStatsV2 — the DfStats-shaped wrapper that
makes the ibis pipeline reachable from buckaroo widget / DataFlow code.

Asserts the same surface contract as DfStatsV2: ``.sdf`` (SDType),
``.errs`` (ErrDict), and ``.ap.ordered_a_objs``.
"""

import pandas as pd
import pytest

ibis = pytest.importorskip("ibis")

from buckaroo.pluggable_analysis_framework.df_stats_v2 import (  # noqa: E402
    IbisDfStatsV2,
)
from buckaroo.customizations.ibis_stats_v2 import IBIS_STATS_V2  # noqa: E402


def _table():
    return ibis.memtable(
        pd.DataFrame(
            {
                "ints": [1, 2, 3, 4, 5],
                "strs": ["a", "b", "c", "a", "b"],
            }
        )
    )


class TestIbisDfStatsV2:
    def test_sdf_shape(self):
        stats = IbisDfStatsV2(_table(), IBIS_STATS_V2)
        assert "ints" in stats.sdf
        assert "strs" in stats.sdf
        assert stats.sdf["ints"]["length"] == 5
        assert stats.sdf["ints"]["mean"] == 3.0
        assert stats.errs == {}

    def test_errs_v1_compat_shape(self):
        """A failure surfaces in errs as {(col, stat): (Exception, kls)}."""
        from buckaroo.pluggable_analysis_framework.ibis_stat_pipeline import IbisColumn
        from buckaroo.pluggable_analysis_framework.stat_func import stat

        @stat()
        def will_fail(col: IbisColumn) -> int:
            raise RuntimeError("boom")

        stats = IbisDfStatsV2(_table(), [*IBIS_STATS_V2, will_fail])
        # At least one v1-shaped error key
        assert stats.errs
        for k, v in stats.errs.items():
            assert isinstance(k, tuple) and len(k) == 2
            assert isinstance(v, tuple) and len(v) == 2
            assert isinstance(v[0], Exception)

    def test_verify_analysis_objects_classmethod(self):
        """DataFlow calls this before processing; should not raise on a good list."""
        IbisDfStatsV2.verify_analysis_objects(IBIS_STATS_V2)

    def test_ordered_a_objs_round_trip(self):
        """DataFlow.add_analysis reads stats.ap.ordered_a_objs after add."""
        stats = IbisDfStatsV2(_table(), IBIS_STATS_V2)
        assert list(stats.ap.ordered_a_objs) == list(IBIS_STATS_V2)
