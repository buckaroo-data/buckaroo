"""Time the xorq server load path against the summary-stat cache (ADR-001).

Three numbers for the same entry:

* cold: empty cache, every stat computed and written.
* warm process: a second load in the same process.
* fresh process: a load in a new process over the warm cache, which is what
  a user opening an entry after a server restart pays.

Each load is ``load_expr_build_dir`` (timed apart, it's xorq's work) plus
``XorqServerDataflow`` construction (stats, styling) plus metadata. Nothing is
asserted; the numbers go in PR descriptions.

By default it builds an NFL-shaped entry (52,814 rows, 27 columns, a deferred
parquet read). ``--build-dir`` runs against an existing xorq build instead.

Usage:
    uv run python scripts/perf/perf_stat_cache.py
    uv run python scripts/perf/perf_stat_cache.py --build-dir <build> --runs 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402


def make_entry(root: Path, rows: int = 52_814) -> str:
    """Write an NFL-shaped parquet and build a xorq expression over it."""
    import xorq.api as xo  # noqa: PLC0415

    rng = np.random.default_rng(0)
    cols = {}
    for i in range(10):
        cols[f"int_{i}"] = pa.array(rng.integers(0, 10 ** (i % 6 + 1), rows), pa.int64())
    for i in range(8):
        vals = rng.normal(1e6, 3e5, rows)
        vals[rng.random(rows) < 0.05] = np.nan
        cols[f"float_{i}"] = pa.array(vals, from_pandas=True)
    for i in range(7):
        cols[f"str_{i}"] = pa.array([f"v{x}" for x in rng.integers(0, 20 * (i + 1) ** 2, rows)])
    cols["flag"] = pa.array(rng.random(rows) < 0.3)
    cols["signed"] = pa.array(np.datetime64("2010-01-01") + rng.integers(0, 5000, rows).astype("timedelta64[D]"))
    path = root / "entry.parquet"
    pq.write_table(pa.table(cols), path)
    expr = xo.deferred_read_parquet(str(path), table_name="entry")
    return str(xo.build_expr(expr, builds_dir=str(root / "builds")))


def load_once(build_dir: str, cache_dir: str) -> dict:
    from buckaroo.server import xorq_loading  # noqa: PLC0415

    t0 = time.perf_counter()
    expr = xorq_loading.load_expr_build_dir(build_dir)
    t1 = time.perf_counter()
    dataflow = xorq_loading.XorqServerDataflow(expr, skip_main_serial=True, cache_storage_path=cache_dir)
    t2 = time.perf_counter()
    xorq_loading.get_xorq_metadata(dataflow, build_dir)
    t3 = time.perf_counter()
    return {"expr_load_ms": (t1 - t0) * 1000, "dataflow_ms": (t2 - t1) * 1000,
        "metadata_ms": (t3 - t2) * 1000}


def fresh_process(build_dir: str, cache_dir: str) -> dict:
    out = subprocess.run([sys.executable, __file__, "--child", "--build-dir", build_dir, "--cache-dir", cache_dir],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def fmt(r: dict) -> str:
    stats = r["dataflow_ms"] + r["metadata_ms"]
    return (f"expr_load {r['expr_load_ms']:7.1f} ms   dataflow {r['dataflow_ms']:7.1f} ms   "
        f"metadata {r['metadata_ms']:6.1f} ms   stats+styling+metadata {stats:7.1f} ms")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir")
    parser.add_argument("--cache-dir")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()

    if args.child:
        print(json.dumps(load_once(args.build_dir, args.cache_dir)))
        return

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_dir = args.build_dir or make_entry(root)
        cache_dir = args.cache_dir or str(root / "stat_cache")
        print(f"build: {build_dir}\ncache: {cache_dir}\n")
        print(f"cold            {fmt(load_once(build_dir, cache_dir))}")
        for i in range(args.runs):
            print(f"warm process #{i} {fmt(load_once(build_dir, cache_dir))}")
        for i in range(args.runs):
            print(f"fresh process #{i} {fmt(fresh_process(build_dir, cache_dir))}")


if __name__ == "__main__":
    main()
