"""Side-by-side comparison of histogram optimizations.

Toggles each optimization independently to show its contribution against
baseline (no changes). Run from the repo root via:

    .venv/bin/python scripts/perf/perf_histogram_compare.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
from perf_data import make_pandas, make_numeric_heavy  # noqa: E402

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

import xorq.api as xo  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.customizations.pl_stats_v2 import PL_ANALYSIS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline)
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline  # noqa: E402


def time_n(fn, n=3):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def make_filter_chain(table):
    schema = table.schema()
    nums = [c for c in table.columns
            if "int" in str(schema[c]) or "float" in str(schema[c])]
    if not nums:
        return table
    e = table.filter(table[nums[0]] > -0.5)
    for c in nums:
        e = e.mutate(**{c: e[c].fill_null(0)})
    return e


def run_variant(table, *, materialize, batch_cat, batch_num, cache):
    """Toggle each optimization independently."""
    p = XorqStatPipeline(XORQ_STATS_V2, unit_test=False)
    if not materialize:
        p._maybe_materialize = lambda t: (t, None)
    if not batch_cat:
        p._batch_categorical_histograms = lambda *a, **k: None
    if not batch_num:
        p._batch_numeric_histograms = lambda *a, **k: None
    if not cache:
        p._cache_key = "__never_match__"
        # also disable cache writes
        orig_pt = p.process_table
        def no_cache_pt(t):
            p._cache_key = None
            return orig_pt(t)
        p.process_table = no_cache_pt

    p.process_table(table)  # warm
    return time_n(lambda: p.process_table(table))


def bench(label, df: pd.DataFrame, also_filt=True):
    print(f"\n=== {label} ({len(df):,} rows × {len(df.columns)} cols) ===")
    con = xo.connect()
    t = con.create_table("t", df)
    targets = [("RAW", t)]
    if also_filt:
        targets.append(("FILT", make_filter_chain(t)))

    # Polars reference
    pl_df = pl.from_pandas(df)
    pl_pipe = StatPipeline(PL_ANALYSIS_V2, unit_test=False)
    pl_pipe.process_df(pl_df)  # warm
    pl_t = time_n(lambda: pl_pipe.process_df(pl_df))
    print(f"  polars reference                             {pl_t*1000:7.1f} ms")

    for scope_name, expr in targets:
        print(f"  --- {scope_name} ---")
        cfg_baseline = dict(materialize=False, batch_cat=False, batch_num=False, cache=False)
        baseline = run_variant(expr, **cfg_baseline)
        print(f"    [a] baseline (main)                        {baseline*1000:7.1f} ms")

        mat = run_variant(expr, materialize=True, batch_cat=False, batch_num=False, cache=False)
        print(f"    [b] + materialize                          {mat*1000:7.1f} ms  ({baseline/mat:.2f}x)")

        cat = run_variant(expr, materialize=True, batch_cat=True, batch_num=False, cache=False)
        print(f"    [c] + UNION ALL cat (topk)                 {cat*1000:7.1f} ms  ({baseline/cat:.2f}x)")

        num = run_variant(expr, materialize=True, batch_cat=True, batch_num=True, cache=False)
        print(f"    [d] + UNION ALL num                        {num*1000:7.1f} ms  ({baseline/num:.2f}x)")

        cache = run_variant(expr, materialize=True, batch_cat=True, batch_num=True, cache=True)
        print(f"    [e] + cache (final)                        {cache*1000:7.1f} ms  ({baseline/cache:.2f}x)")


def main():
    print("xorq histogram optimization comparison\n")

    for n in (10_000, 100_000):
        bench(f"synthetic mixed {n:,}", make_pandas(n))

    for n in (10_000, 100_000):
        bench(f"numeric-heavy {n:,} (24 float + 2 cat)",
              make_numeric_heavy(n, n_cols=24))

    boston = Path.home() / "Downloads/tmpzyxhlh1w.csv"
    if boston.exists():
        print(f"\nloading {boston.name}...")
        bench(boston.name, pd.read_csv(boston, low_memory=False))


if __name__ == "__main__":
    main()
