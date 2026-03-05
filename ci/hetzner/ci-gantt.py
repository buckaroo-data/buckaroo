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
                        jobs=jobs))
    return out


# ── animation ─────────────────────────────────────────────────────────────────

def make_image(runs, output_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # collect ordered job list across all runs
    seen = set()
    for r in runs:
        seen.update(r['jobs'].keys())
    ordered = [j for j in JOB_ORDER if j in seen]
    ordered += sorted(j for j in seen if j not in ordered)
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
            local_file = args[i + 1]; i += 2
        elif re.match(r'^[0-9a-f]{6,40}', args[i]):
            specs.append(parse_sha_arg(args[i])); i += 1
        else:
            sys.exit(f"Unknown argument: {args[i]!r}")

    if local_file:
        text     = open(local_file).read()
        all_parsed = [(parse_log(text, sha_hint=os.path.basename(local_file)),
                       os.path.basename(local_file), 1)]
    else:
        if not specs:
            sha = latest_sha()
            print(f"Latest SHA: {sha}")
            specs = [(sha, None, 1)]
        all_parsed = []
        for sha, label, run_idx in specs:
            print(f"Fetching {sha} …")
            all_parsed.append((parse_log(fetch_log(sha), sha_hint=sha),
                               label, run_idx))

    selected = []
    for sha_runs, label, run_idx in all_parsed:
        if not sha_runs:
            sys.exit("No runs found in log")
        idx = min(run_idx - 1, len(sha_runs) - 1)
        r   = dict(sha_runs[idx])   # copy so we can annotate
        r['label'] = label or r['sha']
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
