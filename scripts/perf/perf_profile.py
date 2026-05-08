"""cProfile widget construction paths to find the real hotspots.

Profiles the constructions that the smoke test flagged as slow:
- BuckarooInfiniteWidget(pandas) on Boston restaurants (711 ms)
- BuckarooWidget(pandas) on Boston (758 ms)
- PolarsBuckarooInfiniteWidget for comparison (96 ms)
- Synthetic 100k for the polars _pl_vc_to_pd path

Each target is run after a warmup so import + first-DAG-build aren't in
the trace. We dump pstats and print the top-N cumulative-time lines
filtered to in-tree functions.
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
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
    PolarsBuckarooInfiniteWidget)

BOSTON = Path.home() / "Downloads/tmpzyxhlh1w.csv"


def profile(label, fn, top=25, filter_substr="buckaroo"):
    """Run fn under cProfile, print top-N cumulative time."""
    pr = cProfile.Profile()
    pr.enable()
    fn()
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumulative")
    ps.print_stats(top * 4)  # over-fetch so the filter still hits N rows
    raw = s.getvalue()

    print(f"\n{'=' * 78}")
    print(f"PROFILE: {label}")
    print(f"{'=' * 78}")
    # Total runtime line
    for ln in raw.splitlines()[:8]:
        if "function calls" in ln or "Ordered by" in ln:
            print(ln)

    # Header + filtered rows
    lines = raw.splitlines()
    header_idx = next((i for i, ln in enumerate(lines)
                        if ln.lstrip().startswith("ncalls")), None)
    if header_idx is None:
        print(raw)
        return
    print(lines[header_idx])

    shown = 0
    for ln in lines[header_idx + 1:]:
        if not ln.strip():
            continue
        if filter_substr and filter_substr not in ln:
            continue
        print(ln)
        shown += 1
        if shown >= top:
            break

    # Plus tottime view (where time is actually spent, not just where it's accumulated)
    s2 = io.StringIO()
    ps2 = pstats.Stats(pr, stream=s2).strip_dirs().sort_stats("tottime")
    ps2.print_stats(top * 2)
    print("\n  --- top tottime (any module) ---")
    raw2 = s2.getvalue().splitlines()
    h2 = next((i for i, ln in enumerate(raw2)
               if ln.lstrip().startswith("ncalls")), None)
    if h2 is not None:
        print(raw2[h2])
        for ln in raw2[h2 + 1:h2 + 1 + top]:
            if ln.strip():
                print(ln)


def warmup():
    print("warmup...")
    tiny_pd = make_pandas(1000)
    tiny_pl = make_polars(1000)
    BuckarooWidget(tiny_pd)
    BuckarooInfiniteWidget(tiny_pd)
    PolarsBuckarooWidget(tiny_pl)
    PolarsBuckarooInfiniteWidget(tiny_pl)
    print("(done)\n")


def main():
    warmup()

    if BOSTON.exists():
        print(f"loading {BOSTON.name}...")
        pdf_boston = pd.read_csv(BOSTON, low_memory=False)
        plf_boston = pl.read_csv(BOSTON, infer_schema_length=10_000, ignore_errors=True)

        profile("BuckarooInfiniteWidget — Boston 883k×26 (pandas)",
                lambda: BuckarooInfiniteWidget(pdf_boston))
        profile("BuckarooWidget — Boston 883k×26 (pandas)",
                lambda: BuckarooWidget(pdf_boston))
        profile("PolarsBuckarooInfiniteWidget — Boston 883k×26 (polars)",
                lambda: PolarsBuckarooInfiniteWidget(plf_boston))
        profile("PolarsBuckarooWidget — Boston 883k×26 (polars)",
                lambda: PolarsBuckarooWidget(plf_boston))
    else:
        print(f"skip — {BOSTON} not present")

    # Synthetic 100k for the polars value_counts hotspot
    pdf = make_pandas(100_000)
    plf = make_polars(100_000)
    profile("PolarsBuckarooWidget — synthetic 100k×8 (polars)",
            lambda: PolarsBuckarooWidget(plf))
    profile("BuckarooWidget — synthetic 100k×8 (pandas)",
            lambda: BuckarooWidget(pdf))


if __name__ == "__main__":
    main()
