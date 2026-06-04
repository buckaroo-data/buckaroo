"""Benchmark the stat pipeline over a diff-shaped (cache + join) expression.

Catalog-diff comparisons feed the pipeline an ``a.cache() ⋈ b.cache()``
expression. The ``cache()`` wrapper inserts a ``CachedNode``, which has no
SQL translation — so ``_maybe_materialize``'s ``create_table(expr)`` path
raises and (before the CachedNode fallback) silently no-ops. Every
per-column histogram then re-runs the whole outer join.

This measures the pipeline with materialization defeated (what the bare
per-column path costs) against materialization succeeding via the fallback.

Usage:
    .venv/bin/python scripts/perf/perf_diff_cachednode.py
"""
from __future__ import annotations

import tempfile
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xorq.api as xo  # noqa: E402

from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline)


def make_diff_expr(n_rows, n_cols, base_path):
    """An ``a.cache() ⋈ b.cache()`` comparison over n_rows × n_cols."""
    rng = np.random.default_rng(0)
    cols = {"group_pk": np.arange(n_rows)}
    for i in range(n_cols):
        cols[f"m{i}"] = rng.normal(100, 15, n_rows)
    df = pd.DataFrame(cols)
    cache = xo.ParquetSnapshotCache.from_kwargs(
        source=xo.connect(), base_path=base_path)
    con = xo.connect()
    a = con.create_table("a", df).cache(cache=cache)
    shifted = df.assign(**{f"m{i}": df[f"m{i}"] * 1.05 for i in range(n_cols)})
    b = (con.create_table("b", shifted)
         .cache(cache=cache)
         .rename({f"m{i}_v2": f"m{i}" for i in range(n_cols)}))
    joined = a.join(b, "group_pk")
    return joined.select(
        "group_pk",
        *[c for i in range(n_cols) for c in (f"m{i}", f"m{i}_v2")])


def time_pipeline(expr, materialize):
    pipe = XorqStatPipeline(list(XORQ_STATS_V2), unit_test=False)
    t0 = time.perf_counter()
    if materialize:
        pipe.process_table(expr)            # fix: materialize once, scan base table
    else:
        pipe._process_table_impl(expr)      # bare path: re-run the join per histogram
    return time.perf_counter() - t0


def main():
    print(f"{'rows':>9} {'cols':>4} | {'no-mat':>10} | {'fix':>10} | speedup")
    for n_rows, n_cols in [(1_000, 6), (100_000, 6), (1_000_000, 6), (100_000, 24)]:
        base = tempfile.mkdtemp()
        make_diff_expr(n_rows, n_cols, base).execute()  # warm on-disk caches
        before = min(time_pipeline(make_diff_expr(n_rows, n_cols, base), False)
                     for _ in range(2))
        after = min(time_pipeline(make_diff_expr(n_rows, n_cols, base), True)
                    for _ in range(2))
        print(f"{n_rows:>9} {n_cols:>4} | {before * 1000:>7.0f} ms | "
              f"{after * 1000:>7.0f} ms | {before / after:>4.1f}x")


if __name__ == "__main__":
    main()
