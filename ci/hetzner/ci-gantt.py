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

def make_gif(runs, output_path, n_frames=60, fps=12, hold_frames=15):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    # collect ordered job list
    seen = set()
    for r in runs:
        seen.update(r['jobs'].keys())
    ordered = [j for j in JOB_ORDER if j in seen]
    ordered += sorted(j for j in seen if j not in ordered)
    n_jobs = len(ordered)

    n_panels = len(runs)
    max_t    = max(r['total'] for r in runs)
    max_t    = max(max_t, 60)

    # wide enough for full labels + bars; tall enough for all rows
    label_inches = 2.2        # fixed left space for job names
    bar_inches   = 7.5        # chart area per panel
    fig_w = label_inches + bar_inches * n_panels
    fig_h = max(4.5, n_jobs * 0.42 + 1.8)

    fig, axes = plt.subplots(1, n_panels, figsize=(fig_w, fig_h))
    if n_panels == 1:
        axes = [axes]
    fig.patch.set_facecolor('#0b0f1a')

    # left margin sized for the longest label
    left_frac = label_inches / fig_w
    fig.subplots_adjust(left=left_frac, right=0.97, top=0.88, bottom=0.10,
                        wspace=0.08)

    def setup_ax(ax):
        ax.set_facecolor('#0d1320')
        for sp in ax.spines.values():
            sp.set_color('#2d3748')
        ax.tick_params(colors='#94a3b8', labelsize=9.5, length=3)
        ax.set_xlim(0, max_t)
        ax.set_ylim(-0.7, n_jobs - 0.3)
        ax.invert_yaxis()
        ax.set_yticks(range(n_jobs))
        ax.set_yticklabels(ordered, fontsize=9.5, fontfamily='monospace',
                           color='#94a3b8')
        ax.grid(axis='x', color='#1e293b', linewidth=0.7, zorder=0)
        ax.set_xlabel('seconds', fontsize=9, color='#64748b')

    total_frames = n_frames + hold_frames

    def draw_frame(frame):
        t = min(max_t, (frame / n_frames) * max_t)

        for ax, run in zip(axes, runs):
            ax.cla()
            setup_ax(ax)

            # ── gate lines ───────────────────────────────────────────────────
            gate_label_y = [0.5, 2.0]   # stagger if two gates are close
            for gi, (gate_job, (gate_color, gate_label)) in \
                    enumerate(GATE_COLORS.items()):
                j = run['jobs'].get(gate_job)
                if j is None:
                    continue
                gx = j['end']
                ax.axvline(gx, color=gate_color, alpha=0.55,
                           linewidth=1.4, linestyle='--', zorder=4)
                ax.text(gx + max_t * 0.008, gate_label_y[gi],
                        gate_label, color=gate_color,
                        fontsize=8, fontfamily='monospace',
                        va='top', ha='left', zorder=5)

            # ── job bars ─────────────────────────────────────────────────────
            for i, job_name in enumerate(ordered):
                j = run['jobs'].get(job_name)
                if j is None:
                    continue

                if t < j['start']:
                    # future — faint ghost
                    ax.barh(i, j['dur'], left=j['start'], height=0.56,
                            color='#0f1729', linewidth=0.6,
                            edgecolor='#1e293b', zorder=2)

                elif t >= j['end']:
                    # complete
                    c = COLORS.get(j['status'], '#475569')
                    ax.barh(i, j['dur'], left=j['start'], height=0.56,
                            color=c, alpha=0.22, linewidth=0, zorder=2)
                    ax.barh(i, min(2.5, max(j['dur'], 0.5)), left=j['start'],
                            height=0.56, color=c, alpha=1.0,
                            linewidth=0, zorder=3)
                    if j['dur'] >= 4:
                        ax.text(j['start'] + j['dur'] / 2, i,
                                f"{j['dur']}s", ha='center', va='center',
                                fontsize=8.5, color=c,
                                fontfamily='monospace',
                                fontweight='bold', zorder=4)

                else:
                    # running — growing bar
                    visible = t - j['start']
                    c = COLORS['running']
                    ax.barh(i, visible, left=j['start'], height=0.56,
                            color=c, alpha=0.30, linewidth=0, zorder=2)
                    ax.barh(i, min(2.5, max(visible, 0.5)), left=j['start'],
                            height=0.56, color=c, alpha=1.0,
                            linewidth=0, zorder=3)

            # ── time cursor ──────────────────────────────────────────────────
            ax.axvline(t, color='#ffffff', alpha=0.45,
                       linewidth=1.2, zorder=6)

            # ── title ────────────────────────────────────────────────────────
            done = t >= run['total']
            result_color = COLORS.get(run['result'], '#94a3b8') if done else '#64748b'
            result_str   = run['result'] if done else f"{t:.0f}s…"
            ax.set_title(
                f"{run['sha']}   {result_str}   (wall-clock {run['total']}s)",
                fontsize=10, fontfamily='monospace',
                color=result_color, pad=7
            )

    def animate(frame):
        draw_frame(frame)

    anim = FuncAnimation(fig, animate, frames=total_frames, interval=1000 // fps)

    print(f"Saving GIF ({total_frames} frames @ {fps}fps) …")
    anim.save(output_path, writer=PillowWriter(fps=fps), dpi=100)
    plt.close(fig)


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    shas       = []
    local_file = None
    run_idx    = 1      # 1-based
    args       = sys.argv[1:]
    i          = 0
    while i < len(args):
        if args[i] == '--file' and i + 1 < len(args):
            local_file = args[i + 1]; i += 2
        elif args[i] == '--run' and i + 1 < len(args):
            run_idx = int(args[i + 1]); i += 2
        elif re.match(r'^[0-9a-f]{6,40}$', args[i]):
            shas.append(args[i]); i += 1
        else:
            sys.exit(f"Unknown argument: {args[i]!r}")

    if local_file:
        text     = open(local_file).read()
        all_runs = [parse_log(text, sha_hint=os.path.basename(local_file))]
    else:
        if not shas:
            sha = latest_sha()
            print(f"Latest SHA: {sha}")
            shas = [sha]
        all_runs = []
        for sha in shas:
            print(f"Fetching {sha} …")
            all_runs.append(parse_log(fetch_log(sha), sha_hint=sha))

    # pick the requested run from each SHA
    selected = []
    for sha_runs in all_runs:
        if not sha_runs:
            sys.exit("No runs found in log")
        idx = min(run_idx - 1, len(sha_runs) - 1)
        r   = sha_runs[idx]
        print(f"  {r['sha']}  run {idx+1}/{len(sha_runs)}  {r['result']}  {r['total']}s")
        selected.append(r)

    out = tempfile.NamedTemporaryFile(suffix='.gif', delete=False)
    out.close()

    make_gif(selected, out.name)
    print(f"Opening {out.name}")
    webbrowser.open(f"file://{out.name}")


if __name__ == '__main__':
    main()
