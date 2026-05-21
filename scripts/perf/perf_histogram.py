"""Benchmark xorq histogram performance against xorq-datafusion.

Tests two scenarios:
  1. RAW: base table → measures per-query overhead.
  2. FILT: lazy filter chain → measures the re-execution cost that
     filt/clean scopes pay in the buckaroo dataflow.

Each histogram query goes through the wrapped execute() so we can
count queries and per-query latency.

Usage:
    .venv/bin/python scripts/perf/perf_histogram.py
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

import xorq.api as xo  # noqa: E402
from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2  # noqa: E402
from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import (  # noqa: E402
    XorqStatPipeline)


REAL_CSVS = [
    Path.home() / "Downloads/tmpzyxhlh1w.csv",  # boston
]


class CountingBackend:
    def __init__(self, conn):
        self.conn = conn
        self.calls = []

    def execute(self, expr):
        t0 = time.perf_counter()
        try:
            return self.conn.execute(expr)
        finally:
            self.calls.append(time.perf_counter() - t0)

    def reset(self):
        self.calls = []


def make_table(df: pd.DataFrame, table_name: str = "t"):
    return xo.connect().create_table(table_name, df)


def fmt(secs):
    return f"{secs * 1000:7.1f} ms"


def time_pipeline(pipeline, table, label, runs=3):
    backend = pipeline.backend
    totals, batch_q, histo_q, histo_total, histo_count = [], [], [], [], []
    for _ in range(runs):
        backend.reset()
        t0 = time.perf_counter()
        pipeline.process_table(table)
        elapsed = time.perf_counter() - t0
        totals.append(elapsed)
        calls = backend.calls
        if calls:
            batch_q.append(calls[0])
            histo_q.extend(calls[1:])
            histo_total.append(sum(calls[1:]))
            histo_count.append(len(calls) - 1)

    best_total = min(totals)
    best_batch = min(batch_q) if batch_q else 0.0
    best_histo_total = min(histo_total) if histo_total else 0.0
    n_histo = histo_count[0] if histo_count else 0
    avg_per_histo = (sum(histo_q) / len(histo_q)) if histo_q else 0
    print(f"  {label:30s} total={fmt(best_total)} "
          f"batch={fmt(best_batch)} "
          f"histo_total={fmt(best_histo_total)} "
          f"n_histo={n_histo} avg_q={fmt(avg_per_histo)}")
    return best_total


def make_filter_chain(table, drop_threshold=-0.5):
    """Simulate a filt+clean pipeline: filter + fillna mutates."""
    schema = table.schema()
    numeric_cols = [c for c in table.columns
                    if "int" in str(schema[c]) or "float" in str(schema[c])]
    if not numeric_cols:
        return table
    e = table.filter(table[numeric_cols[0]] > drop_threshold)
    for col in numeric_cols:
        e = e.mutate(**{col: e[col].fill_null(0)})
    return e


def bench(label: str, df: pd.DataFrame):
    print(f"\n=== {label} ({len(df):,} rows × {len(df.columns)} cols) ===")
    table = make_table(df)
    backend = CountingBackend(table._find_backend())
    pipeline = XorqStatPipeline(XORQ_STATS_V2, backend=backend, unit_test=False)

    # warmup
    pipeline.process_table(table)
    time_pipeline(pipeline, table, "RAW scope (base table)")

    filt = make_filter_chain(table)
    pipeline.process_table(filt)  # warmup
    time_pipeline(pipeline, filt, "FILT scope (lazy filter)")


def main():
    print("xorq-datafusion histogram benchmark\n")
    for n in (10_000, 100_000):
        df = make_pandas(n)
        bench(f"synthetic mixed {n:,}", df)

    # Numeric-heavy: 24 float cols + 2 cat — mirrors boston's column count
    # but stresses the numeric histogram path instead of categorical.
    for n in (10_000, 100_000):
        df = make_numeric_heavy(n, n_cols=24)
        bench(f"numeric-heavy {n:,} (24 float + 2 cat)", df)

    for path in REAL_CSVS:
        if path.exists():
            print(f"\nloading {path.name}...")
            df = pd.read_csv(path, low_memory=False)
            bench(path.name, df)
        else:
            print(f"\n[skip {path.name} — not present]")


if __name__ == "__main__":
    main()
