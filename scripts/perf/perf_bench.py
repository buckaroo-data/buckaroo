"""Buckaroo perf bench — pandas vs polars stats pipeline.

Runs the v2 stat pipeline on synthetic dataframes (100k, 500k rows), times
each (column, stat_func) pair, and prints summary tables. Also times the
full BuckarooWidget construction so we capture serialization/styling costs.

Usage:
    .venv/bin/python scripts/perf/perf_bench.py
    .venv/bin/python scripts/perf/perf_bench.py --rows 100000
    .venv/bin/python scripts/perf/perf_bench.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Make scripts/perf importable when running as a script.
sys.path.insert(0, str(Path(__file__).parent))
from perf_data import COL_KIND_LABELS, make_pandas, make_polars  # noqa: E402

from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2  # noqa: E402
from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework.df_stats_v2 import (  # noqa: E402
    DfStatsV2,
    PlDfStatsV2)
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline  # noqa: E402


def time_pipeline(df, stat_funcs, label):
    """Run a StatPipeline directly on df with timings recorded."""
    pipe = StatPipeline(stat_funcs, unit_test=False, record_timings=True)
    t0 = time.perf_counter()
    sd, errs = pipe.process_df(df)
    total = time.perf_counter() - t0
    return {"label": label, "total": total, "errors": len(errs), "timings": list(pipe.timings), "n_cols": len(sd)}


def time_dfstats(df, klass, klasses, label):
    """Time DfStatsV2 / PlDfStatsV2 (includes downsampling decision)."""
    t0 = time.perf_counter()
    s = klass(df, klasses)
    total = time.perf_counter() - t0
    return {"label": label, "total": total, "errors": len(s.errs), "n_cols": len(s.sdf)}


def time_widget_construction(df, widget_cls, label):
    """End-to-end BuckarooWidget(df) construction time."""
    t0 = time.perf_counter()
    w = widget_cls(df)
    total = time.perf_counter() - t0
    return {"label": label, "total": total,
        "n_cols": len(w.df_data_dict.get("main", [{}])[0]) if w.df_data_dict.get("main") else 0}


def aggregate_by_stat(timings):
    """Sum per-stat-func across columns."""
    out = defaultdict(float)
    for col, name, secs in timings:
        out[name] += secs
    return dict(out)


def aggregate_by_column(timings):
    out = defaultdict(float)
    for col, name, secs in timings:
        out[col] += secs
    return dict(out)


def print_table(rows, headers):
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*[str(c) for c in r]))


def fmt_ms(secs):
    return f"{secs * 1000:.1f}"


def _rewritten_to_orig(df_columns):
    """Mirror buckaroo.df_util.old_col_new_col: index 0 → 'a', 1 → 'b', ..."""
    from buckaroo.df_util import old_col_new_col
    import pandas as pd
    if hasattr(df_columns, "columns"):
        df_columns = list(df_columns.columns)
    fake = pd.DataFrame({c: [] for c in df_columns})
    return {new: old for old, new in old_col_new_col(fake)}


def run_pipeline_comparison(n_rows: int):
    print(f"\n{'=' * 70}")
    print(f"Pipeline timings @ {n_rows:,} rows  (StatPipeline.process_df only)")
    print(f"{'=' * 70}")

    pdf = make_pandas(n_rows)
    plf = make_polars(n_rows)

    rewrite_map = _rewritten_to_orig(pdf.columns)

    pd_result = time_pipeline(pdf, PD_ANALYSIS_V2, f"pandas {n_rows:,}")
    pl_result = time_pipeline(plf, PL_ANALYSIS_V2, f"polars {n_rows:,}")

    print(
        f"\npandas total: {pd_result['total'] * 1000:.1f} ms"
        f"   polars total: {pl_result['total'] * 1000:.1f} ms"
        f"   ratio (polars/pandas): {pl_result['total'] / pd_result['total']:.2f}x")

    # Per-column comparison
    pd_by_col = aggregate_by_column(pd_result["timings"])
    pl_by_col = aggregate_by_column(pl_result["timings"])
    cols = sorted(set(pd_by_col) | set(pl_by_col))
    rows = []
    for c in cols:
        pd_t = pd_by_col.get(c, 0.0)
        pl_t = pl_by_col.get(c, 0.0)
        ratio = (pl_t / pd_t) if pd_t else float("nan")
        orig = rewrite_map.get(c, c)
        kind = COL_KIND_LABELS.get(orig, "?")
        rows.append([c, orig, kind, fmt_ms(pd_t), fmt_ms(pl_t), f"{ratio:.2f}x" if ratio == ratio else "-"])
    print("\nPer-column total time (ms):")
    print_table(rows, ["col", "orig", "kind", "pandas ms", "polars ms", "polars/pandas"])

    # Per stat func comparison
    pd_by_stat = aggregate_by_stat(pd_result["timings"])
    pl_by_stat = aggregate_by_stat(pl_result["timings"])
    print("\nPandas — per stat func (ms, summed across cols):")
    rows_pd = sorted(pd_by_stat.items(), key=lambda x: -x[1])
    print_table([[k, fmt_ms(v)] for k, v in rows_pd], ["stat", "ms"])

    print("\nPolars — per stat func (ms, summed across cols):")
    rows_pl = sorted(pl_by_stat.items(), key=lambda x: -x[1])
    print_table([[k, fmt_ms(v)] for k, v in rows_pl], ["stat", "ms"])

    # Per (column, stat) for polars — find the hot cells
    print("\nPolars — slowest 10 (column, stat) cells:")
    slow = sorted(pl_result["timings"], key=lambda t: -t[2])[:10]
    print_table([[c, rewrite_map.get(c, c), n, fmt_ms(s)] for c, n, s in slow], ["col", "orig", "stat", "ms"])

    return {"pandas": pd_result, "polars": pl_result, "n_rows": n_rows}


def run_widget_comparison(n_rows: int):
    """Time the full widget construction (DfStats + serialization)."""
    from buckaroo.buckaroo_widget import BuckarooWidget
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget

    print(f"\n{'=' * 70}")
    print(f"DfStats + widget timings @ {n_rows:,} rows")
    print(f"{'=' * 70}")

    pdf = make_pandas(n_rows)
    plf = make_polars(n_rows)

    pd_stats = time_dfstats(pdf, DfStatsV2, list(PD_ANALYSIS_V2), f"pandas DfStatsV2 {n_rows:,}")
    pl_stats = time_dfstats(plf, PlDfStatsV2, list(PL_ANALYSIS_V2), f"polars PlDfStatsV2 {n_rows:,}")
    print(f"\nDfStatsV2(pandas):   {pd_stats['total'] * 1000:.1f} ms")
    print(f"PlDfStatsV2(polars): {pl_stats['total'] * 1000:.1f} ms")
    print(f"  (DfStats includes the >1M-cell downsample-to-50k path)")

    pd_w = time_widget_construction(pdf, BuckarooWidget, f"BuckarooWidget {n_rows:,}")
    pl_w = time_widget_construction(plf, PolarsBuckarooWidget, f"PolarsBuckarooWidget {n_rows:,}")
    print(f"\nBuckarooWidget(pandas):       {pd_w['total'] * 1000:.1f} ms")
    print(f"PolarsBuckarooWidget(polars): {pl_w['total'] * 1000:.1f} ms")
    return {"pandas_dfstats": pd_stats, "polars_dfstats": pl_stats,
        "pandas_widget": pd_w, "polars_widget": pl_w, "n_rows": n_rows}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, nargs="+", default=[100_000, 500_000])
    p.add_argument("--json", type=str, default=None,
        help="Write detailed results as JSON to this path")
    p.add_argument("--skip-widget", action="store_true",
        help="Skip the end-to-end widget construction timing")
    args = p.parse_args()

    all_results = {"pipeline": [], "widget": []}
    for n in args.rows:
        all_results["pipeline"].append(run_pipeline_comparison(n))
        if not args.skip_widget:
            all_results["widget"].append(run_widget_comparison(n))

    if args.json:
        # Strip non-JSON-serializable bits (timings tuples are fine)
        Path(args.json).write_text(json.dumps(all_results, indent=2, default=str))
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
