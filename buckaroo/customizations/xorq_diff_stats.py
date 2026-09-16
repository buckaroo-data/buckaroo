"""Xorq diff analysis klasses — pinned-row stats + styling for keyed-diff frames.

Summary stats and a styling klass for tables carrying ``{col}`` / ``{col}_v2``
/ ``{col}_pct_delta`` triples — the shape built by a keyed diff view. Three
phase-2 summary stats tell the story of the diff per column:

  - ``diff_histogram`` — distribution of per-row change in log2-ratio space,
    with a bin edge pinned at zero change.
  - ``diff_line`` — new/old as a percent (100 = unchanged), in key order.
  - ``left_right`` — the before series (``lineGray``) and after series
    (``lineRed``) on one chart, so both share a scale.

All three resample to at most 100 points by averaging position-ordered
buckets (``floor(row_number * min(100, n) / n)``), so they stay readable at
any row count; at <= 100 rows this degenerates to one point per row. Columns
that are not the ``_v2`` side of a triple return ``[]`` without issuing a
query.

Not wired into ``XORQ_STATS_V2`` defaults — opt in via ``extra_klasses``.

Usage::

    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2
    from buckaroo.customizations.xorq_diff_stats import XORQ_DIFF_STATS
    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline

    pipeline = XorqStatPipeline(XORQ_STATS_V2 + XORQ_DIFF_STATS)
    stats, errors = pipeline.process_table(ibis_table)
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from buckaroo.customizations.styling import DefaultMainStyling
from buckaroo.pluggable_analysis_framework.stat_func import MultipleProvides, stat
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqExecute, XorqExpr

# ============================================================
# diff_histogram bin geometry — log2-ratio space, edge pinned at zero
# ============================================================

_DIFF_BIN_PCT_EDGES: Tuple[float, ...] = (
    -0.50, -0.33, -0.20, -0.10, -0.01, 0.01, 0.10, 0.25, 0.50, 1.00)

DIFF_HISTOGRAM_LABELS: List[str] = [
    "<-50%", "-50..-33%", "-33..-20%", "-20..-10%", "-10..-1%",
    "~0%", "+1..10%", "+10..25%", "+25..50%", "+50..100%", ">+100%"]

# log2(1 + pct) for each edge — monotonic since log2 and (1 + pct) both are.
_DIFF_BIN_LOG2_EDGES: Tuple[float, ...] = tuple(math.log2(1.0 + p) for p in _DIFF_BIN_PCT_EDGES)


def _log2_ratio(pct: float) -> float:
    """log2(1 + pct), safe at pct == -1 (new value 0) and beyond.

    ``1 + pct`` is the new/old ratio. A ratio <= 0 (pct <= -1, i.e. the new
    value crossed to zero or below) has no real log2 — treat it as the most
    extreme decrease rather than raising or propagating NaN.
    """
    ratio = 1.0 + pct
    if ratio <= 0:
        return -math.inf
    return math.log2(ratio)


def _build_diff_histogram(pct_values: List[float]) -> list:
    counts = [0] * len(DIFF_HISTOGRAM_LABELS)
    valid = 0
    for pct in pct_values:
        if pct is None or (isinstance(pct, float) and math.isnan(pct)):
            continue
        idx = bisect.bisect_right(_DIFF_BIN_LOG2_EDGES, _log2_ratio(float(pct)))
        counts[idx] += 1
        valid += 1
    if valid == 0:
        return []
    return [{"name": label, "population": counts[i] / valid * 100.0}
        for i, label in enumerate(DIFF_HISTOGRAM_LABELS)]


# ============================================================
# Resampling — position-ordered bucket means, capped at 100 points
# ============================================================


def _resample(values_by_col: Dict[str, List[float]], n: int) -> Tuple[List[str], Dict[str, List[float]]]:
    """Bucket ``n`` position-ordered rows into at most 100 buckets, averaging.

    Bucket assignment is ``floor(row_number * min(100, n) / n)`` — at
    ``n <= 100`` every row gets its own bucket (one point per row). Bucket
    names are the first row position landing in that bucket, so labels stay
    in ascending position order.
    """
    cap = min(100, n)
    buckets = np.array([int(i * cap / n) for i in range(n)], dtype=np.int64)
    _, first_idx = np.unique(buckets, return_index=True)
    names = [str(int(idx)) for idx in first_idx]
    bucket_series = pd.Series(buckets)
    out = {}
    for col, vals in values_by_col.items():
        out[col] = pd.Series(vals, dtype="float64").groupby(bucket_series).mean().tolist()
    return names, out


def _safe_pct(old: float, new: float) -> Any:
    if old is None or new is None or old == 0:
        return None
    if isinstance(old, float) and math.isnan(old):
        return None
    return new / old * 100.0


# ============================================================
# diff_histogram / diff_line / left_right — one query, three outputs
# ============================================================


class DiffTripleStats(MultipleProvides):
    diff_histogram: list
    diff_line: list
    left_right: list


_DIFF_EMPTY: DiffTripleStats = {"diff_histogram": [], "diff_line": [], "left_right": []}


def _diff_base(orig_col_name: str, expr: Any) -> Any:
    """The base name if ``orig_col_name`` is the ``_v2`` side of a diff triple."""
    if not isinstance(orig_col_name, str) or not orig_col_name.endswith("_v2"):
        return None
    base = orig_col_name[:-len("_v2")]
    cols = set(expr.columns)
    if base not in cols or f"{base}_pct_delta" not in cols:
        return None
    return base


@stat()
def diff_triple(expr: XorqExpr, execute: XorqExecute, orig_col_name: str) -> DiffTripleStats:
    base = _diff_base(orig_col_name, expr)
    if base is None:
        return _DIFF_EMPTY

    try:
        query = expr.select(
            __old=expr[base].cast("float64"),
            __new=expr[orig_col_name].cast("float64"),
            __pct=expr[f"{base}_pct_delta"].cast("float64"))
        df = execute(query)
    except Exception:
        return _DIFF_EMPTY

    n = len(df)
    if n == 0:
        return _DIFF_EMPTY

    names, agg = _resample({"old": df["__old"].tolist(), "new": df["__new"].tolist()}, n)
    diff_line = [{"name": name, "lineRed": _safe_pct(o, nw)}
        for name, o, nw in zip(names, agg["old"], agg["new"])]
    left_right = [{"name": name, "lineGray": o, "lineRed": nw}
        for name, o, nw in zip(names, agg["old"], agg["new"])]

    return {
        "diff_histogram": _build_diff_histogram(df["__pct"].tolist()),
        "diff_line": diff_line,
        "left_right": left_right}


XORQ_DIFF_STATS = [diff_triple]


# ============================================================
# DiffStyling — hide helper columns, rename _v2, color + tooltip from siblings
# ============================================================


def _diff_bases(sd) -> Tuple[List[str], Dict[str, str], Dict[Any, str]]:
    """Diff triple base names present in ``sd`` (a ``{col}_v2`` with a
    ``{col}_cellcolor`` sibling), plus the v2-col -> base mapping and the
    orig_col_name -> col lookup used to detect siblings."""
    present: Dict[Any, str] = {}
    for col, col_meta in sd.items():
        present[col_meta.get("orig_col_name", col)] = col

    bases: List[str] = []
    v2_col_for_base: Dict[str, str] = {}
    for orig, col in present.items():
        if isinstance(orig, str) and orig.endswith("_v2"):
            base = orig[:-len("_v2")]
            if f"{base}_cellcolor" in present:
                bases.append(base)
                v2_col_for_base[col] = base
    return bases, v2_col_for_base, present


class DiffStyling(DefaultMainStyling):
    """Styling for keyed-diff frames.

    Hides the ``_pct_delta`` / ``_abs_delta`` / ``_eq`` / ``_cellcolor``
    helper columns, ``membership``, and the old-value column; renames the
    ``_v2`` column to the bare metric name; paints it via
    ``color_from_column`` from the precomputed ``{col}_cellcolor`` column;
    and shows the old value on hover. Inert on frames without any
    ``_cellcolor`` column — falls through to ``DefaultMainStyling`` unchanged,
    so it can safely serve as a ``main`` override.
    """

    requires_summary = DefaultMainStyling.requires_summary + [
        "diff_histogram", "diff_line", "left_right"]
    pinned_rows = [
        {"primary_key_val": "diff_histogram", "displayer_args": {"displayer": "histogram"}},
        {"primary_key_val": "diff_line", "displayer_args": {"displayer": "chart"}},
        {"primary_key_val": "left_right", "displayer_args": {"displayer": "chart"}}]

    @classmethod
    def style_column(cls, col: str, column_metadata: Any) -> Any:
        base_config = super().style_column(col, column_metadata)
        base = column_metadata.get("_diff_base")
        if base:
            base_config["color_map_config"] = {
                "color_rule": "color_from_column", "val_column": f"{base}_cellcolor"}
            base_config["tooltip_config"] = {"tooltip_type": "simple", "val_column": base}
        return base_config

    @classmethod
    def style_columns(cls, sd, df):
        bases, v2_col_for_base, present = _diff_bases(sd)
        if not bases:
            return super().style_columns(sd, df)

        hidden = set()
        for base in bases:
            hidden.update({base, f"{base}_pct_delta", f"{base}_abs_delta", f"{base}_eq", f"{base}_cellcolor"})
        if "membership" in present:
            hidden.add("membership")

        new_sd = {}
        for col, col_meta in sd.items():
            orig = col_meta.get("orig_col_name", col)
            if orig in hidden:
                # Excluded outright (not flagged via merge_rule): the base
                # StylingAnalysis.style_columns cross-references a hidden
                # entry's dict key against every other row's orig_col_name,
                # and the renamed _v2 entry's new orig_col_name (the base
                # name) collides with the hidden old-value column's own key.
                continue
            elif col in v2_col_for_base:
                new_meta = dict(col_meta)
                base = v2_col_for_base[col]
                new_meta["orig_col_name"] = base
                new_meta["_diff_base"] = base
                new_sd[col] = new_meta
            else:
                new_sd[col] = col_meta
        return super().style_columns(new_sd, df)
