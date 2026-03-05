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
    "PASS":    "#22c55e",
    "FAIL":    "#ef4444",
    "SKIP":    "#334155",
    "running": "#f59e0b",
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

def abbrev(name):
    return (name
            .replace('playwright-', 'pw-')
            .replace('test-python-', 'py-')
            .replace('smoke-test-extras', 'smoke')
            .replace('jupyter-warmup', 'warmup')
            .replace('build-wheel', 'bld-wheel')
            .replace('build-js', 'bld-js'))


def make_gif(runs, output_path, n_frames=60, fps=12, hold_frames=15):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
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

    fig_w = 9 * n_panels
    fig_h = max(4, n_jobs * 0.4 + 1.5)
    fig, axes = plt.subplots(1, n_panels, figsize=(fig_w, fig_h), sharey=True)
    if n_panels == 1:
        axes = [axes]

    fig.patch.set_facecolor('#0b0f1a')
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    for ax in axes:
        ax.set_facecolor('#0d1320')
        for sp in ax.spines.values():
            sp.set_color('#1e293b')
        ax.tick_params(colors='#64748b', labelsize=9)
        ax.set_xlim(0, max_t)
        ax.set_ylim(-0.7, n_jobs - 0.3)
        ax.invert_yaxis()
        ax.set_yticks(range(n_jobs))
        ax.set_yticklabels([abbrev(j) for j in ordered],
                           fontsize=9, fontfamily='monospace', color='#64748b')
        ax.grid(axis='x', color='#1e293b', linewidth=0.6, zorder=0)
        ax.set_xlabel('seconds', fontsize=9, color='#475569')

    total_frames = n_frames + hold_frames

    def draw_frame(frame):
        t = min(max_t, (frame / n_frames) * max_t)

        for ax, run in zip(axes, runs):
            # clear bars only (keep axes ticks etc)
            for p in list(ax.patches):
                p.remove()
            for txt in list(ax.texts):
                txt.remove()
            for line in ax.lines:
                line.set_xdata([t, t])

            for i, job_name in enumerate(ordered):
                j = run['jobs'].get(job_name)
                if j is None:
                    continue

                if t < j['start']:
                    # future — ghost outline
                    ax.barh(i, j['dur'], left=j['start'], height=0.55,
                            color='#0f172a', linewidth=0.8,
                            edgecolor='#1e293b', zorder=2)
                elif t >= j['end']:
                    # complete
                    c = COLORS.get(j['status'], '#475569')
                    ax.barh(i, j['dur'], left=j['start'], height=0.55,
                            color=c, alpha=0.25, linewidth=0, zorder=2)
                    ax.barh(i, min(2, max(j['dur'], 0.5)), left=j['start'],
                            height=0.55, color=c, alpha=0.9, linewidth=0, zorder=3)
                    if j['dur'] >= 5:
                        ax.text(j['start'] + j['dur'] / 2, i,
                                f"{j['dur']}s", ha='center', va='center',
                                fontsize=8, color=c, fontfamily='monospace',
                                zorder=4)
                else:
                    # running — partial bar
                    visible = t - j['start']
                    c = COLORS['running']
                    ax.barh(i, visible, left=j['start'], height=0.55,
                            color=c, alpha=0.35, linewidth=0, zorder=2)
                    ax.barh(i, min(2, max(visible, 0.5)), left=j['start'],
                            height=0.55, color=c, alpha=0.9, linewidth=0, zorder=3)

            result_color = COLORS.get(run['result'], '#94a3b8') if t >= run['total'] else '#64748b'
            result_str   = run['result'] if t >= run['total'] else '…'
            ax.set_title(
                f"{run['sha']}   {result_str}   {run['total']}s",
                fontsize=10, fontfamily='monospace',
                color=result_color, pad=6
            )

    # initialise time lines
    time_lines = [ax.axvline(0, color='#38bdf8', alpha=0.5, linewidth=1.5,
                             linestyle='--', zorder=5)
                  for ax in axes]

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
