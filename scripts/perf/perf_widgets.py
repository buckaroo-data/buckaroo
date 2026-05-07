"""Smoke-test all widget variants on a few real datasets.

Times: widget instantiation (cold, then 3x warm), and an infinite-style
data pull (200-row parquet slice). Reports byte sizes of the serialized
payloads. No buckaroo internals are instrumented — this is just
black-box before/after timing on the public API.

Usage:
    .venv/bin/python scripts/perf/perf_widgets.py
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent))
from perf_data import make_pandas, make_polars  # noqa: E402

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from buckaroo.buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget  # noqa: E402
from buckaroo.polars_buckaroo import (  # noqa: E402
    PolarsBuckarooWidget,
    PolarsBuckarooInfiniteWidget,
    to_parquet as pl_to_parquet)
from buckaroo.serialization_utils import pd_to_obj  # noqa: E402


REAL_CSVS = [Path.home() / "Downloads/lahman_1871-2025_csv/Fielding.csv", Path.home() / "Downloads/tmpzyxhlh1w.csv"]


def time_call(fn, n=3):
    """Best of n + average of n. Returns (best_secs, avg_secs)."""
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


def df_data_dict_size(w):
    """Best-effort serialized-size estimate of df_data_dict."""
    import json
    try:
        return len(json.dumps(w.df_data_dict, default=str))
    except Exception:
        return -1


def widget_summary_bytes(w):
    """Pull the all_stats blob — that's parquet-b64 already."""
    d = w.df_data_dict.get("all_stats")
    if isinstance(d, dict) and "data" in d:
        # parquet_b64 tagged dict
        return len(d.get("data", ""))
    if isinstance(d, list):
        # JSON list path (plain pandas)
        import json
        return len(json.dumps(d, default=str))
    return -1


def smoke_pandas(label, df):
    print(f"\n--- pandas: {label} ({len(df):,} rows × {len(df.columns)} cols) ---")

    # Cold: first widget construction in this process for this datum
    t0 = time.perf_counter()
    w_cold = BuckarooWidget(df)
    cold = time.perf_counter() - t0
    main_size = df_data_dict_size(w_cold)
    stats_size = widget_summary_bytes(w_cold)
    print(f"  BuckarooWidget               cold={fmt(cold)} (1x)"
          f"   main+stats payload≈{fmt_bytes(main_size)}  stats≈{fmt_bytes(stats_size)}")

    best, avg = time_call(lambda: BuckarooWidget(df))
    print(f"  BuckarooWidget               warm={fmt(best)} best / {fmt(avg)} avg")

    # Infinite variant
    t0 = time.perf_counter()
    iw = BuckarooInfiniteWidget(df)
    inf_cold = time.perf_counter() - t0
    print(f"  BuckarooInfiniteWidget       cold={fmt(inf_cold)} (skip_main_serial=True)")
    best, avg = time_call(lambda: BuckarooInfiniteWidget(df))
    print(f"  BuckarooInfiniteWidget       warm={fmt(best)} best / {fmt(avg)} avg")

    # Pull a real data slice through serialization (simulate frontend request)
    _, processed_df, _ = iw.dataflow.widget_args_tuple
    if processed_df is None:
        print("  [skip pull — processed_df missing]")
        return
    end = min(200, len(processed_df))

    def pull_slice():
        slice_df = processed_df[0:end]
        return pd_to_obj(slice_df)

    best, avg = time_call(pull_slice)
    payload = pull_slice()
    import json
    payload_size = len(json.dumps(payload, default=str))
    print(f"  pull 200-row pd_to_obj       {fmt(best)} best / {fmt(avg)} avg   payload={fmt_bytes(payload_size)}")


def smoke_polars(label, df):
    print(f"\n--- polars: {label} ({len(df):,} rows × {len(df.columns)} cols) ---")

    t0 = time.perf_counter()
    w_cold = PolarsBuckarooWidget(df)
    cold = time.perf_counter() - t0
    main_size = df_data_dict_size(w_cold)
    stats_size = widget_summary_bytes(w_cold)
    print(f"  PolarsBuckarooWidget         cold={fmt(cold)} (1x)"
          f"   payload≈{fmt_bytes(main_size)}  stats≈{fmt_bytes(stats_size)}")

    best, avg = time_call(lambda: PolarsBuckarooWidget(df))
    print(f"  PolarsBuckarooWidget         warm={fmt(best)} best / {fmt(avg)} avg")

    t0 = time.perf_counter()
    iw = PolarsBuckarooInfiniteWidget(df)
    inf_cold = time.perf_counter() - t0
    print(f"  PolarsBuckarooInfiniteWidget cold={fmt(inf_cold)} (skip_main_serial=True)")
    best, avg = time_call(lambda: PolarsBuckarooInfiniteWidget(df))
    print(f"  PolarsBuckarooInfiniteWidget warm={fmt(best)} best / {fmt(avg)} avg")

    _, processed_df, _ = iw.dataflow.widget_args_tuple
    if processed_df is None:
        print("  [skip pull — processed_df missing]")
        return
    end = min(200, len(processed_df))

    def pull_slice():
        slice_df = processed_df.with_row_index()[0:end]
        return pl_to_parquet(slice_df)

    best, avg = time_call(pull_slice)
    payload_bytes = pull_slice()
    print(f"  pull 200-row to_parquet      {fmt(best)} best / {fmt(avg)} avg   payload={fmt_bytes(len(payload_bytes))}")


def main():
    # --- Warmup: instantiate each widget once on tiny data so subsequent
    # cold-numbers reflect dataset cost, not module-import cost.
    print("warming up imports + first-DAG-build...")
    tiny_pd = make_pandas(1000)
    tiny_pl = make_polars(1000)
    BuckarooWidget(tiny_pd)
    BuckarooInfiniteWidget(tiny_pd)
    PolarsBuckarooWidget(tiny_pl)
    PolarsBuckarooInfiniteWidget(tiny_pl)
    print("(import warmup done)\n")

    # --- Synthetic
    for n in (100_000, 500_000):
        pdf = make_pandas(n)
        plf = make_polars(n)
        smoke_pandas(f"synthetic {n:,}", pdf)
        smoke_polars(f"synthetic {n:,}", plf)

    # --- Real CSVs
    for path in REAL_CSVS:
        if not path.exists():
            print(f"\n[skip {path} — not present]")
            continue
        print(f"\nloading {path.name}...")
        pdf = pd.read_csv(path, low_memory=False)
        plf = pl.read_csv(path, infer_schema_length=10_000, ignore_errors=True)
        smoke_pandas(path.name, pdf)
        smoke_polars(path.name, plf)


if __name__ == "__main__":
    main()
