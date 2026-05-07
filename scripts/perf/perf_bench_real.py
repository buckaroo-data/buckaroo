"""Run the instrumented stat pipeline on a real CSV — pandas vs polars.

Usage:
    .venv/bin/python scripts/perf/perf_bench_real.py path/to/file.csv

Loads once with each engine, runs StatPipeline with timings on, then prints
per-column and per-stat-func tables side by side. Useful for testing the
synthetic findings against real-world data shapes.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from perf_bench import (  # noqa: E402
    aggregate_by_column,
    aggregate_by_stat,
    fmt_ms,
    print_table,
    time_pipeline)

from buckaroo.customizations.pd_stats_v2 import PD_ANALYSIS_V2  # noqa: E402
from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2  # noqa: E402
from buckaroo.df_util import old_col_new_col  # noqa: E402


def load_pair(path: Path):
    """Return (pandas_df, polars_df) loaded from the same CSV."""
    import pandas as pd
    import polars as pl

    t0 = time.perf_counter()
    pdf = pd.read_csv(path, low_memory=False)
    pd_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    plf = pl.read_csv(path, infer_schema_length=10_000, ignore_errors=True)
    pl_load = time.perf_counter() - t0

    return pdf, plf, pd_load, pl_load


def kind_label(orig_name: str, dtype_str: str) -> str:
    s = dtype_str.lower()
    if "int" in s:
        return "int"
    if "float" in s:
        return "float"
    if "bool" in s:
        return "bool"
    if any(k in s for k in ("date", "time")):
        return "datetime"
    if any(k in s for k in ("object", "string", "utf8", "str")):
        return "string"
    return s


def run(path: Path):
    print(f"\nLoading: {path}")
    pdf, plf, pd_load, pl_load = load_pair(path)
    print(f"  pandas: {len(pdf):,} rows × {len(pdf.columns)} cols  load={pd_load*1000:.0f} ms")
    print(f"  polars: {len(plf):,} rows × {len(plf.columns)} cols  load={pl_load*1000:.0f} ms")

    # Build rewritten -> orig map for nicer column display
    rewrite_map = {new: old for old, new in old_col_new_col(pdf)}
    pd_dtypes = {c: str(pdf[c].dtype) for c in pdf.columns}

    # Run pipelines (warmup once each, then measure)
    print("  warmup...")
    time_pipeline(pdf, PD_ANALYSIS_V2, "warm-pd")
    time_pipeline(plf, PL_ANALYSIS_V2, "warm-pl")

    pd_runs = [time_pipeline(pdf, PD_ANALYSIS_V2, f"pandas {len(pdf):,}") for _ in range(3)]
    pl_runs = [time_pipeline(plf, PL_ANALYSIS_V2, f"polars {len(plf):,}") for _ in range(3)]

    pd_best = min(pd_runs, key=lambda r: r["total"])
    pl_best = min(pl_runs, key=lambda r: r["total"])

    print(f"\n{'=' * 72}")
    print(f"{path.name}  ({len(pdf):,} rows × {len(pdf.columns)} cols)  best of 3")
    print(f"{'=' * 72}")
    print(
        f"pandas total: {pd_best['total'] * 1000:.1f} ms"
        f"   polars total: {pl_best['total'] * 1000:.1f} ms"
        f"   ratio (polars/pandas): {pl_best['total'] / pd_best['total']:.2f}x")

    pd_by_col = aggregate_by_column(pd_best["timings"])
    pl_by_col = aggregate_by_column(pl_best["timings"])
    cols = sorted(set(pd_by_col) | set(pl_by_col))
    rows = []
    for c in cols:
        orig = rewrite_map.get(c, c)
        kind = kind_label(orig, pd_dtypes.get(orig, ""))
        pd_t = pd_by_col.get(c, 0.0)
        pl_t = pl_by_col.get(c, 0.0)
        ratio = (pl_t / pd_t) if pd_t else float("nan")
        rows.append([c, orig[:32], kind, fmt_ms(pd_t), fmt_ms(pl_t), f"{ratio:.2f}x" if ratio == ratio else "-"])
    print("\nPer-column total time (ms):")
    print_table(rows, ["col", "orig", "kind", "pd ms", "pl ms", "pl/pd"])

    pd_by_stat = aggregate_by_stat(pd_best["timings"])
    pl_by_stat = aggregate_by_stat(pl_best["timings"])
    print("\nPer stat func — pandas (ms):")
    print_table([[k, fmt_ms(v)] for k, v in sorted(pd_by_stat.items(), key=lambda x: -x[1])], ["stat", "ms"])
    print("\nPer stat func — polars (ms):")
    print_table([[k, fmt_ms(v)] for k, v in sorted(pl_by_stat.items(), key=lambda x: -x[1])], ["stat", "ms"])

    print("\nPolars — slowest 10 (column, stat) cells:")
    slow = sorted(pl_best["timings"], key=lambda t: -t[2])[:10]
    print_table([[c, rewrite_map.get(c, c)[:32], n, fmt_ms(s)] for c, n, s in slow], ["col", "orig", "stat", "ms"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+", type=Path)
    args = p.parse_args()

    for path in args.paths:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        run(path)


if __name__ == "__main__":
    main()
