"""Smoke-test XorqBuckarooWidget on datafusion and duckdb backends.

Mirrors perf_widgets.py's structure: instantiate, time, pull 200 rows.
Comparable to the pandas/polars numbers it produces.

Usage:
    .venv/bin/python scripts/perf/perf_xorq.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent))
from perf_data import make_pandas  # noqa: E402

import pandas as pd  # noqa: E402

import xorq.api as xo  # noqa: E402
from buckaroo.xorq_buckaroo import (  # noqa: E402
    XorqBuckarooWidget, XorqBuckarooInfiniteWidget)


REAL_CSVS = [Path.home() / "Downloads/lahman_1871-2025_csv/Fielding.csv", Path.home() / "Downloads/tmpzyxhlh1w.csv"]


BACKENDS = {"datafusion": lambda: xo.connect(), "duckdb": lambda: xo.duckdb.connect()}


def make_expr(backend_name: str, df: pd.DataFrame, table_name: str = "t"):
    """Create a fresh connection on the named backend and register df as table_name."""
    con = BACKENDS[backend_name]()
    return con.create_table(table_name, df)


def time_call(fn, n=3):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times), sum(times) / len(times)


def fmt(secs):
    return f"{secs * 1000:7.1f} ms"


def fmt_bytes(b):
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f}KB"
    return f"{b/1024/1024:.1f}MB"


def smoke_xorq(label: str, backend: str, df: pd.DataFrame):
    print(f"\n--- xorq[{backend}]: {label} ({len(df):,} rows × {len(df.columns)} cols) ---")

    # Register once — that's what a real user does. Time it separately.
    t0 = time.perf_counter()
    expr = make_expr(backend, df)
    register_t = time.perf_counter() - t0
    print(f"  create_table (one-time)          {fmt(register_t)}")

    # Cold widget construction on the registered expr
    t0 = time.perf_counter()
    XorqBuckarooWidget(expr)
    cold = time.perf_counter() - t0
    print(f"  XorqBuckarooWidget               cold={fmt(cold)} (1x)")

    best, avg = time_call(lambda: XorqBuckarooWidget(expr))
    print(f"  XorqBuckarooWidget               warm={fmt(best)} best / {fmt(avg)} avg")

    # Infinite variant on the same expr
    t0 = time.perf_counter()
    iw = XorqBuckarooInfiniteWidget(expr)
    inf_cold = time.perf_counter() - t0
    print(f"  XorqBuckarooInfiniteWidget       cold={fmt(inf_cold)} (skip_main_serial=True)")

    best, avg = time_call(lambda: XorqBuckarooInfiniteWidget(expr))
    print(f"  XorqBuckarooInfiniteWidget       warm={fmt(best)} best / {fmt(avg)} avg")

    # Pull a 200-row slice through serialization (simulate frontend request).
    # Reuse the iw whose widget_args_tuple is already populated.
    _, processed_df, _ = iw.dataflow.widget_args_tuple
    if processed_df is None:
        print("  [skip pull — processed_df missing]")
        return
    end = min(200, len(df))

    # processed_df is an ibis expression here. Mirror what _handle_payload_args
    # does: limit + execute, then pd_to_obj.
    from buckaroo.serialization_utils import pd_to_obj

    def pull_slice():
        slice_df = processed_df.limit(end, offset=0).execute()
        return pd_to_obj(slice_df)

    best, avg = time_call(pull_slice)
    payload = pull_slice()
    import json
    payload_size = len(json.dumps(payload, default=str))
    print(f"  pull 200-row execute+pd_to_obj   {fmt(best)} best / {fmt(avg)} avg   payload={fmt_bytes(payload_size)}")


def main():
    # Warmup: tiny df through both backends so first-DAG cost is amortized
    print("warming up xorq imports + DAG build for both backends...")
    tiny = make_pandas(1000)
    for b in BACKENDS:
        try:
            XorqBuckarooWidget(make_expr(b, tiny))
            XorqBuckarooInfiniteWidget(make_expr(b, tiny))
        except Exception as e:
            print(f"  [{b} warmup error: {e}]")
    print("(warmup done)\n")

    # Synthetic
    for n in (100_000, 500_000):
        pdf = make_pandas(n)
        for b in BACKENDS:
            try:
                smoke_xorq(f"synthetic {n:,}", b, pdf)
            except Exception as e:
                print(f"\n[xorq[{b}] synthetic {n:,} failed: {type(e).__name__}: {e}]")

    # Real CSVs
    for path in REAL_CSVS:
        if not path.exists():
            print(f"\n[skip {path} — not present]")
            continue
        print(f"\nloading {path.name}...")
        pdf = pd.read_csv(path, low_memory=False)
        for b in BACKENDS:
            try:
                smoke_xorq(path.name, b, pdf)
            except Exception as e:
                print(f"\n[xorq[{b}] {path.name} failed: {type(e).__name__}: {e}]")


if __name__ == "__main__":
    main()
