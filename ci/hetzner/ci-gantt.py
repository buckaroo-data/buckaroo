# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib", "pillow"]
# ///
"""
CI Gantt animated GIF generator.

Usage:
  uv run ci/hetzner/ci-gantt.py                    # latest SHA, run 1
  uv run ci/hetzner/ci-gantt.py SHA                # specific SHA, run 1
  uv run ci/hetzner/ci-gantt.py SHA --run N        # specific run (1-based)
  uv run ci/hetzner/ci-gantt.py SHA1 SHA2          # side-by-side (run 1 each)

Env:
  CI_SERVER=root@host    (default: root@137.220.56.81)
"""
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from datetime import datetime

SERVER = os.environ.get("CI_SERVER", "root@137.220.56.81")

JOB_ORDER = [
    "lint-python",
    "build-js",
    "test-js",
    "build-wheel",
    "jupyter-warmup",
    "test-python-3.11",
    "test-python-3.12",
    "test-python-3.13",
    "test-python-3.14",
    "test-mcp-wheel",
    "smoke-test-extras",
    "playwright-storybook",
    "playwright-wasm-marimo",
    "playwright-marimo",
    "playwright-server",
    "playwright-jupyter",
]

COLORS = {
    "PASS":    "#00e676",   # bright green
    "FAIL":    "#ff5252",   # bright red
    "SKIP":    "#546e7a",   # blue-gray
    "running": "#ffd740",   # amber
}

GATE_COLORS = {
    "build-js":    ("#38bdf8", "JS built"),      # sky blue
    "build-wheel": ("#c084fc", "Wheel built"),   # purple
}


# ── log fetching ───────────────────────────────────────────────────────────────

def fetch_log(sha):
    r = subprocess.run(["ssh", SERVER, f"cat /opt/ci/logs/{sha}/ci.log"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Cannot fetch log for {sha}: {r.stderr.strip()}")
    return r.stdout


def fetch_cpu_log(sha):
    r = subprocess.run(["ssh", SERVER, f"cat /opt/ci/logs/{sha}/cpu-fine.log"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def latest_sha():
    r = subprocess.run(
        ["ssh", SERVER,
         "ls -t /opt/ci/logs/ | grep -E '^[0-9a-f]{7,8}$' | head -1"],
        capture_output=True, text=True)
    sha = r.stdout.strip()
    if not sha:
        sys.exit("Cannot determine latest SHA from server")
    return sha


# ── log parsing ────────────────────────────────────────────────────────────────

def parse_log(text, sha_hint=""):
    runs, cur = [], None
    for line in text.splitlines():
        m = re.match(r'\[(\d{2}:\d{2}:\d{2})\] (.*)', line)
        if not m:
            continue
        ts   = datetime.strptime(m.group(1), '%H:%M:%S')
        rest = m.group(2)

        if rest.startswith('CI runner'):
            if cur:
                runs.append(cur)
            cur = dict(sha=sha_hint, start=ts, end=ts, result="?", jobs={})
            continue
        if cur is None:
            continue
        cur['end'] = ts

        co = re.match(r'Checkout (\w+)', rest)
        if co:
            cur['sha'] = co.group(1)

        je = re.match(r'(START|PASS|FAIL|SKIP)\s+(\S+)', rest)
        if je:
            ev, job = je.group(1), je.group(2)
            if ev == 'START':
                cur['jobs'][job] = dict(start=ts, end=ts, status='running')
            elif job in cur['jobs']:
                cur['jobs'][job]['end'] = ts
                cur['jobs'][job]['status'] = ev
            elif ev == 'SKIP':
                cur['jobs'][job] = dict(start=ts, end=ts, status='SKIP')

        if 'ALL JOBS PASSED' in rest:
            cur['result'] = 'PASS'
        elif 'SOME JOBS FAILED' in rest:
            cur['result'] = 'FAIL'

    if cur:
        runs.append(cur)

    out = []
    for run in runs:
        t0   = run['start']
        jobs = {}
        for name, j in run['jobs'].items():
            s = max(0, int((j['start'] - t0).total_seconds()))
            e = max(s, int((j['end']   - t0).total_seconds()))
            jobs[name] = dict(start=s, end=e, dur=e - s, status=j['status'])
        total = max((j['end'] for j in jobs.values()), default=0)
        out.append(dict(sha=run['sha'] or sha_hint,
                        result=run['result'],
                        total=total,
                        jobs=jobs,
                        t0=t0))
    return out


def parse_cpu_fine(text, t0):
    """Parse cpu-fine.log → list of (t_rel_s, cpu_pct, iowait_pct).

    Format (new): <unix_ts> <busy_jiffies> <total_jiffies> <iowait_jiffies>
    Format (old): <unix_ts> <busy_jiffies> <total_jiffies>
    Lines starting with '#' are run-boundary markers.

    The file may contain multiple runs (appended with # RUN markers).
    Returns points for the run whose start aligns most closely with t0.
    """
    import datetime as dt_mod

    # Split into per-run segments
    segments: list[list[tuple]] = []
    cur: list[tuple] = []
    for line in text.splitlines():
        if line.startswith('#'):
            if cur:
                segments.append(cur)
            cur = []
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                row = (float(parts[0]), int(parts[1]), int(parts[2]),
                       int(parts[3]) if len(parts) >= 4 else 0)
                cur.append(row)
            except ValueError:
                pass
    if cur:
        segments.append(cur)
    if not segments:
        return []

    def align_and_compute(rows, t0):
        if len(rows) < 2:
            return None, []
        first_unix = rows[0][0]
        cpu_start_utc = dt_mod.datetime.fromtimestamp(
            first_unix, tz=dt_mod.timezone.utc)
        t0_full = cpu_start_utc.replace(
            hour=t0.hour, minute=t0.minute, second=t0.second, microsecond=0)
        t0_unix = t0_full.timestamp()
        points = []
        for i in range(1, len(rows)):
            ts, busy, total, iow       = rows[i]
            _, pb,  pt,  piow          = rows[i - 1]
            d_total = total - pt
            d_busy  = busy  - pb
            d_iow   = iow   - piow
            if d_total > 0:
                cpu_pct = max(0.0, min(100.0, d_busy / d_total * 100))
                iow_pct = max(0.0, min(100.0, d_iow  / d_total * 100))
                points.append((ts - t0_unix, cpu_pct, iow_pct))
        return t0_unix, points

    # Pick the segment that best covers t0 (offset closest to 0)
    best_pts, best_offset = [], float('inf')
    for seg in segments:
        if len(seg) < 2:
            continue
        t0_unix, pts = align_and_compute(seg, t0)
        if pts:
            # How close is the first point to t=0?
            offset = abs(pts[0][0])
            if offset < best_offset:
                best_offset, best_pts = offset, pts

    return best_pts


# ── animation ─────────────────────────────────────────────────────────────────

def make_image(runs, output_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # collect ordered job list: sort by average start time across runs,
    # use JOB_ORDER index as stable tiebreaker within the same wave
    job_starts: dict[str, list[int]] = {}
    for r in runs:
        for name, j in r['jobs'].items():
            job_starts.setdefault(name, []).append(j['start'])
    avg_start = {name: sum(v) / len(v) for name, v in job_starts.items()}
    seen = set(job_starts)
    ordered = sorted(seen, key=lambda j: (
        avg_start.get(j, 9999),
        JOB_ORDER.index(j) if j in JOB_ORDER else 999,
    ))
    n_jobs = len(ordered)

    n_panels = len(runs)
    max_t    = max(r['total'] for r in runs)
    max_t    = max(max_t, 60)

    # stacked vertically: one panel per run, old on top → new on bottom
    label_inches  = 2.2
    bar_inches    = 13.0          # wide
    row_h_inches  = 0.26          # compact row height
    panel_h       = n_jobs * row_h_inches + 0.9   # tight: rows + title/axis
    fig_w         = label_inches + bar_inches
    fig_h         = panel_h * n_panels

    sharex = n_panels > 1
    fig, axes = plt.subplots(n_panels, 1, figsize=(fig_w, fig_h),
                             sharex=sharex)
    if n_panels == 1:
        axes = [axes]
    fig.patch.set_facecolor('#0b0f1a')

    left_frac = label_inches / fig_w
    fig.subplots_adjust(left=left_frac, right=0.98,
                        top=1 - 0.2 / fig_h,
                        bottom=0.35 / fig_h,
                        hspace=0.45)

    # compute tick step once so both panels use identical positions
    tick_step = 5 if max_t <= 40 else 10 if max_t <= 90 else 20
    xticks = list(range(0, int(max_t) + tick_step, tick_step))

    def setup_ax(ax, is_bottom):
        ax.set_facecolor('#0d1320')
        for sp in ax.spines.values():
            sp.set_color('#2d3748')
        ax.set_xlim(0, max_t)
        ax.set_ylim(-0.7, n_jobs - 0.3)
        ax.invert_yaxis()
        ax.set_yticks(range(n_jobs))
        ax.set_yticklabels(ordered, fontsize=9.5, fontfamily='monospace',
                           color='#94a3b8')
        # explicit identical ticks so grid columns align across panels
        ax.set_xticks(xticks)
        ax.tick_params(colors='#94a3b8', labelsize=9.5, length=3)
        if not is_bottom:
            ax.tick_params(labelbottom=False)
        ax.grid(axis='x', color='#1e293b', linewidth=0.7, zorder=0)
        if is_bottom:
            ax.set_xlabel('seconds', fontsize=9, color='#64748b')

    for pi, (ax, run) in enumerate(zip(axes, runs)):
        setup_ax(ax, is_bottom=(pi == n_panels - 1))

        # ── y-label colours: red for failed jobs ─────────────────────────────
        for lbl, job_name in zip(ax.get_yticklabels(), ordered):
            j = run['jobs'].get(job_name)
            if j and j['status'] == 'FAIL':
                lbl.set_color(COLORS['FAIL'])

        # ── gate lines ───────────────────────────────────────────────────────
        gate_label_y = [0.5, 2.0]
        for gi, (gate_job, (gate_color, gate_label)) in \
                enumerate(GATE_COLORS.items()):
            j = run['jobs'].get(gate_job)
            if j is None:
                continue
            gx = j['end']
            ax.axvline(gx, color=gate_color, alpha=0.6,
                       linewidth=1.4, linestyle='--', zorder=4)
            ax.text(gx + max_t * 0.008, gate_label_y[gi],
                    gate_label, color=gate_color,
                    fontsize=8, fontfamily='monospace',
                    va='top', ha='left', zorder=5)

        # ── job bars ─────────────────────────────────────────────────────────
        for i, job_name in enumerate(ordered):
            j = run['jobs'].get(job_name)
            if j is None:
                continue
            c = COLORS.get(j['status'], '#475569')
            ax.barh(i, j['dur'], left=j['start'], height=0.62,
                    color=c, alpha=0.22, linewidth=0, zorder=2)
            ax.barh(i, min(2.5, max(j['dur'], 0.5)), left=j['start'],
                    height=0.62, color=c, alpha=1.0, linewidth=0, zorder=3)
            if j['dur'] >= 4:
                ax.text(j['start'] + j['dur'] / 2, i,
                        f"{j['dur']}s", ha='center', va='center',
                        fontsize=8, color=c, fontfamily='monospace',
                        fontweight='bold', zorder=4)

        # ── CPU overlay (bottom 1/3 of panel) ────────────────────────────────
        cpu_pts = run.get('cpu_data') or []
        if cpu_pts:
            cpu_ax = ax.inset_axes([0, 0, 1, 0.33])
            cpu_ax.set_facecolor((0, 0, 0, 0))
            ts_cpu, cpu_pct, iow_pct = zip(*cpu_pts)
            # CPU fill + line (blue)
            cpu_ax.fill_between(ts_cpu, cpu_pct, alpha=0.30,
                                color='#38bdf8', linewidth=0)
            cpu_ax.plot(ts_cpu, cpu_pct, color='#7dd3fc',
                        linewidth=0.8, alpha=0.9)
            # IO wait line (orange) — only if data has non-zero iowait
            if any(w > 0 for w in iow_pct):
                cpu_ax.plot(ts_cpu, iow_pct, color='#fb923c',
                            linewidth=0.8, alpha=0.85)
            cpu_ax.set_xlim(0, max_t)
            cpu_ax.set_ylim(0, 100)
            cpu_ax.set_yticks([50, 100])
            cpu_ax.set_yticklabels(['50%', '100%'])
            cpu_ax.tick_params(labelsize=6.5, colors='#4b7090',
                               length=2, pad=1)
            cpu_ax.set_xticks([])
            for sp in ['top', 'right', 'bottom']:
                cpu_ax.spines[sp].set_visible(False)
            cpu_ax.spines['left'].set_color('#1e293b')
            cpu_ax.text(max_t * 0.99, 92, 'CPU%', ha='right', va='top',
                        fontsize=6.5, color='#4b7090',
                        fontfamily='monospace')

        # ── title ────────────────────────────────────────────────────────────
        result_color = COLORS.get(run['result'], '#94a3b8')
        label = run.get('label') or run['sha']
        ax.set_title(
            f"{label}   {run['result']}   {run['total']}s wall-clock",
            fontsize=10.5, fontfamily='monospace',
            color=result_color, pad=7
        )

    print("Saving image …")
    fig.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)


# ── main ───────────────────────────────────────────────────────────────────────

# Fixed output path so we always overwrite the same file (no old-GIF confusion)
OUT_PATH = os.path.join(tempfile.gettempdir(), 'ci-gantt-latest.jpg')


def parse_sha_arg(arg):
    """Accept 'SHA', 'SHA:label', or 'SHA:label:runN'. Returns (sha, label, run_idx)."""
    parts   = arg.split(':', 2)
    sha     = parts[0]
    label   = parts[1] if len(parts) > 1 else None
    run_idx = int(parts[2].lstrip('run')) if len(parts) > 2 else 1
    return sha, label, run_idx


def main():
    specs      = []   # list of (sha, label, run_idx)
    local_file = None
    args       = sys.argv[1:]
    i          = 0
    while i < len(args):
        if args[i] == '--file' and i + 1 < len(args):
            local_file = args[i + 1]
            i += 2
        elif re.match(r'^[0-9a-f]{6,40}', args[i]):
            specs.append(parse_sha_arg(args[i]))
            i += 1
        else:
            sys.exit(f"Unknown argument: {args[i]!r}")

    if local_file:
        text     = open(local_file).read()
        all_parsed = [(parse_log(text, sha_hint=os.path.basename(local_file)),
                       os.path.basename(local_file), 1, None)]
    else:
        if not specs:
            sha = latest_sha()
            print(f"Latest SHA: {sha}")
            specs = [(sha, None, 1)]
        all_parsed = []
        for sha, label, run_idx in specs:
            print(f"Fetching {sha} …")
            ci_runs = parse_log(fetch_log(sha), sha_hint=sha)
            cpu_text = fetch_cpu_log(sha)
            all_parsed.append((ci_runs, label, run_idx, cpu_text))

    selected = []
    for sha_runs, label, run_idx, cpu_text in all_parsed:
        if not sha_runs:
            sys.exit("No runs found in log")
        idx = min(run_idx - 1, len(sha_runs) - 1)
        r   = dict(sha_runs[idx])   # copy so we can annotate
        r['label'] = label or r['sha']
        if cpu_text:
            cpu_pts = parse_cpu_fine(cpu_text, r['t0'])
            # Only keep points that fall within this run's time window.
            in_range = [(t, c, w) for t, c, w in cpu_pts
                        if -5 <= t <= r['total'] + 30]
            if in_range:
                r['cpu_data'] = in_range
        print(f"  {r['label']}  ({r['sha']} run {idx+1})  {r['result']}  {r['total']}s")
        selected.append(r)

    # delete old output so browser always reloads fresh
    if os.path.exists(OUT_PATH):
        os.remove(OUT_PATH)

    make_image(selected, OUT_PATH)
    print(f"Opening {OUT_PATH}")
    webbrowser.open(f"file://{OUT_PATH}")


if __name__ == '__main__':
    main()
