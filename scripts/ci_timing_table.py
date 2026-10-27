#!/usr/bin/env python3
"""Read JSON lines from ci_all_timings.sh and print a comparison table.

Usage:
    bash scripts/ci_all_timings.sh <id1> <id2> ... | python3 scripts/ci_timing_table.py

    # Or with labels:
    bash scripts/ci_all_timings.sh <id1> <id2> <id3> | python3 scripts/ci_timing_table.py --labels "GH warm 1" "GH warm 2" "GH warm 3"

    # Group by prefix for summary rows:
    bash scripts/ci_all_timings.sh <ids...> | python3 scripts/ci_timing_table.py --groups "GitHub warm:0,1,2" "Depot warm:3,4,5"
"""
import json
import sys
import argparse


def fmt(secs):
    if secs is None:
        return "?"
    return f"{secs // 60}m{secs % 60:02d}s"


def mean(vals):
    vals = [v for v in vals if v is not None]
    return int(sum(vals) / len(vals)) if vals else 0


def median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return 0
    n = len(vals)
    if n % 2:
        return vals[n // 2]
    return (vals[n // 2 - 1] + vals[n // 2]) // 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", nargs="*", help="Labels for each run")
    parser.add_argument(
        "--groups",
        nargs="*",
        help='Group runs for summary: "Label:0,1,2" (0-indexed)',
    )
    args = parser.parse_args()

    runs = []
    for line in sys.stdin:
        line = line.strip()
        if line:
            runs.append(json.loads(line))

    if not runs:
        print("No data on stdin. Pipe output from ci_all_timings.sh.")
        sys.exit(1)

    labels = args.labels or [r.get("branch", r["run_id"]) for r in runs]

    # Individual runs
    n = len(runs)
    col_w = max(12, max(len(l) for l in labels) + 2)

    header = f"{'':>30}" + "".join(f"{l:>{col_w}}" for l in labels)
    print(header)
    print("=" * len(header))

    print("Critical path (excl Windows):")
    vals = [r["critical_path"] for r in runs]
    print(f"  {'':>28}" + "".join(f"{fmt(v):>{col_w}}" for v in vals))

    print("Wave 1 stagger:")
    vals = [r["wave1_stagger"] for r in runs]
    print(
        f"  {'':>28}" + "".join(f"{str(v) + 's':>{col_w}}" for v in vals)
    )

    print("Cache read total:")
    vals = [r["cache_read_total"] for r in runs]
    print(
        f"  {'':>28}" + "".join(f"{str(v) + 's':>{col_w}}" for v in vals)
    )

    print("Cache read mean/step:")
    vals = [r["cache_read_mean"] for r in runs]
    print(
        f"  {'':>28}"
        + "".join(f"{str(v) + 's':>{col_w}}" for v in vals)
    )

    print("Cache write total:")
    vals = [r["cache_write_total"] for r in runs]
    print(
        f"  {'':>28}" + "".join(f"{str(v) + 's':>{col_w}}" for v in vals)
    )

    print("Cache write mean/step:")
    vals = [r["cache_write_mean"] for r in runs]
    print(
        f"  {'':>28}"
        + "".join(f"{str(v) + 's':>{col_w}}" for v in vals)
    )

    # Groups summary
    if args.groups:
        print()
        print("=" * 72)
        print("SUMMARY")
        print("=" * 72)
        print(
            f"{'Group':>30} {'Mean CP':>10} {'Med CP':>10} {'Stagger':>10} {'CR mean':>10} {'CW mean':>10}"
        )
        print("-" * 82)
        for group_spec in args.groups:
            label, indices_str = group_spec.split(":")
            indices = [int(i) for i in indices_str.split(",")]
            group_runs = [runs[i] for i in indices if i < len(runs)]

            cp_mean = mean([r["critical_path"] for r in group_runs])
            cp_med = median([r["critical_path"] for r in group_runs])
            stg_mean = mean([r["wave1_stagger"] for r in group_runs])
            cr_mean = round(
                mean([r["cache_read_mean"] for r in group_runs]), 1
            )
            cw_mean = round(
                mean([r["cache_write_mean"] for r in group_runs]), 1
            )

            print(
                f"{label:>30} {fmt(cp_mean):>10} {fmt(cp_med):>10} {str(stg_mean) + 's':>10} {str(cr_mean) + 's':>10} {str(cw_mean) + 's':>10}"
            )

    # Per-job breakdown if few runs
    if len(runs) <= 6:
        print()
        print("Per-job durations:")
        all_jobs = sorted(
            set(j for r in runs for j in r["jobs"].keys())
        )
        print(f"{'Job':>35}" + "".join(f"{l:>{col_w}}" for l in labels))
        print("-" * (35 + col_w * n))
        for job in all_jobs:
            vals = [r["jobs"].get(job) for r in runs]
            print(
                f"{job:>35}"
                + "".join(
                    f"{(str(v) + 's') if v is not None else '-':>{col_w}}"
                    for v in vals
                )
            )


if __name__ == "__main__":
    main()
