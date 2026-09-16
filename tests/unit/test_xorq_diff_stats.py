"""Tests for the xorq diff analysis klasses.

Summary stats + styling for keyed-diff frames — tables carrying
``{col}``, ``{col}_v2`` and ``{col}_pct_delta`` triples (the shape built
by keyed diff views). Three pinned-row stats tell the story of the diff
per column:

- ``diff_histogram`` — distribution of per-row change in log2-ratio
  space, with a bin edge pinned at zero change
- ``diff_line`` — new/old as a percent (100 = unchanged), in key order
- ``left_right`` — the before series (lineGray) and after series
  (lineRed) on one chart, so both share a scale

All three resample to at most 100 points by averaging position-ordered
buckets, so they stay readable at any row count. On columns that are not
the ``_v2`` side of a diff triple they return ``[]``.

Uses ``xo.memtable`` (xorq's vendored ibis, datafusion-backed). Skipped
if xorq is not installed.
"""

import math

import pandas as pd
import pytest

xo = pytest.importorskip("xorq.api")

from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline)
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.customizations.xorq_diff_stats import (  # noqa: E402
    DIFF_HISTOGRAM_LABELS,
    XORQ_DIFF_STATS,
    DiffStyling)


def _diff_frame():
    """24-row diff triple: every hour drops 25%, hour 6 drops 80%."""
    hours = list(range(24))
    old = [float(100 + h) for h in hours]
    factors = [0.75] * 24
    factors[6] = 0.2
    new = [o * f for o, f in zip(old, factors)]
    pct = [(n - o) / abs(o) for o, n in zip(old, new)]
    return pd.DataFrame(
        {"pickup_hour": hours, "num_trips": old, "num_trips_v2": new,
         "num_trips_pct_delta": pct, "plain": hours})


def _run_pipeline(df):
    pipeline = XorqStatPipeline(XORQ_STATS_V2 + XORQ_DIFF_STATS)
    stats, errors = pipeline.process_table(xo.memtable(df))
    assert errors == []
    return stats


class TestDiffHistogram:
    def test_bins_and_labels(self):
        stats = _run_pipeline(_diff_frame())
        bars = stats["num_trips_v2"]["diff_histogram"]
        assert [b["name"] for b in bars] == DIFF_HISTOGRAM_LABELS
        assert len(bars) == 11

    def test_all_decreases_land_left_of_zero(self):
        stats = _run_pipeline(_diff_frame())
        bars = stats["num_trips_v2"]["diff_histogram"]
        pops = {b["name"]: b["population"] for b in bars}
        # -25% is log2(0.75) = -0.415 -> the "-33..-20%" bin; -80% -> "<-50%"
        assert pops["-33..-20%"] == pytest.approx(100 * 23 / 24)
        assert pops["<-50%"] == pytest.approx(100 * 1 / 24)
        # nothing changed upward: every right-of-zero bin is empty
        for label in ("~0%", "+1..10%", "+10..25%", "+25..50%", "+50..100%", ">+100%"):
            assert pops[label] == 0.0
        assert sum(pops.values()) == pytest.approx(100.0)

    def test_empty_for_non_diff_columns(self):
        stats = _run_pipeline(_diff_frame())
        for col in ("num_trips", "num_trips_pct_delta", "plain", "pickup_hour"):
            assert stats[col]["diff_histogram"] == []


class TestDiffLine:
    def test_one_point_per_row_under_cap(self):
        stats = _run_pipeline(_diff_frame())
        points = stats["num_trips_v2"]["diff_line"]
        assert len(points) == 24
        assert [p["name"] for p in points] == [str(h) for h in range(24)]
        assert points[6]["lineRed"] == pytest.approx(20.0)
        assert points[0]["lineRed"] == pytest.approx(75.0)

    def test_empty_for_non_diff_columns(self):
        stats = _run_pipeline(_diff_frame())
        assert stats["plain"]["diff_line"] == []


class TestLeftRight:
    def test_before_and_after_series(self):
        stats = _run_pipeline(_diff_frame())
        points = stats["num_trips_v2"]["left_right"]
        assert len(points) == 24
        assert points[0]["lineGray"] == pytest.approx(100.0)
        assert points[0]["lineRed"] == pytest.approx(75.0)
        assert points[6]["lineGray"] == pytest.approx(106.0)
        assert points[6]["lineRed"] == pytest.approx(106.0 * 0.2)

    def test_empty_for_non_diff_columns(self):
        stats = _run_pipeline(_diff_frame())
        assert stats["num_trips"]["left_right"] == []


class TestResampling:
    def test_caps_at_100_points_by_bucket_mean(self):
        n = 1440
        df = pd.DataFrame(
            {"minute": list(range(n)), "x": [100.0] * n,
             "x_v2": [75.0] * n, "x_pct_delta": [-0.25] * n})
        stats = _run_pipeline(df)
        line = stats["x_v2"]["diff_line"]
        assert len(line) == 100
        assert all(p["lineRed"] == pytest.approx(75.0) for p in line)
        # bucket labels are the first key value of each bucket, in order
        assert line[0]["name"] == "0"
        assert [int(p["name"]) for p in line] == sorted(int(p["name"]) for p in line)

        lr = stats["x_v2"]["left_right"]
        assert len(lr) == 100
        assert all(p["lineGray"] == pytest.approx(100.0) for p in lr)
        assert all(p["lineRed"] == pytest.approx(75.0) for p in lr)


def _mk_sd(cols):
    return {c: {"orig_col_name": c, "_type": t} for c, t in cols}


class TestDiffStyling:
    DIFF_COLS = [
        ("pickup_hour", "integer"), ("num_trips", "float"), ("num_trips_v2", "float"),
        ("num_trips_pct_delta", "float"), ("num_trips_abs_delta", "float"),
        ("num_trips_eq", "integer"), ("membership", "integer"),
        ("num_trips_cellcolor", "string")]

    def test_pinned_rows_and_requires(self):
        keys = [pr["primary_key_val"] for pr in DiffStyling.pinned_rows]
        for stat_key in ("diff_histogram", "diff_line", "left_right"):
            assert stat_key in keys
            assert stat_key in DiffStyling.requires_summary

    def test_diff_frame_hides_helpers_renames_and_colors(self):
        sd = _mk_sd(self.DIFF_COLS)
        df = pd.DataFrame({c: [1] for c, _ in self.DIFF_COLS})
        configs = DiffStyling.style_columns(sd, df)
        by_header = {c["header_name"]: c for c in configs}
        # helper columns and the old-value column are hidden
        assert set(by_header) == {"pickup_hour", "num_trips"}
        # the _v2 column is renamed to the bare metric...
        v2 = by_header["num_trips"]
        assert v2["col_name"] == "num_trips_v2"
        # ...painted from the precomputed color column...
        assert v2["color_map_config"] == {
            "color_rule": "color_from_column", "val_column": "num_trips_cellcolor"}
        # ...with the old value on hover
        assert v2["tooltip_config"] == {
            "tooltip_type": "simple", "val_column": "num_trips"}

    def test_inert_without_cellcolor_columns(self):
        cols = [(c, t) for c, t in self.DIFF_COLS if not c.endswith("_cellcolor")]
        sd = _mk_sd(cols)
        df = pd.DataFrame({c: [1] for c, _ in cols})
        configs = DiffStyling.style_columns(sd, df)
        headers = {c["header_name"] for c in configs}
        # no _cellcolor columns -> default styling, nothing hidden or renamed
        assert headers == {c for c, _ in cols}


def test_diff_stats_are_nan_safe():
    """A pct_delta of exactly -1 (new value 0) must not blow up the log."""
    df = pd.DataFrame(
        {"k": [0, 1, 2], "x": [10.0, 20.0, 30.0], "x_v2": [0.0, 15.0, 30.0],
         "x_pct_delta": [-1.0, -0.25, 0.0]})
    stats = _run_pipeline(df)
    bars = stats["x_v2"]["diff_histogram"]
    pops = {b["name"]: b["population"] for b in bars}
    # the -25% row lands in a bin; the to-zero row is uncountable in log
    # space and the unchanged row sits in the dead zone
    assert pops["-33..-20%"] > 0
    assert not any(math.isnan(b["population"]) for b in bars if b["population"] is not None)
