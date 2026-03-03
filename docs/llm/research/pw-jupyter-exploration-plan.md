# pw-jupyter Exploration Plan

**Branch:** docs/ci-research
**Harness:** `run-pw-jupyter.sh` (on server at `/repo/ci/hetzner/run-pw-jupyter.sh`)
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Baseline:** P=4, 96s, 100% pass rate (commit 4a7fefc)
**Cached wheel:** `4a7fefc` (confirmed on server)
**Rule:** Max 4 iterations per experiment path. Fix syntax/obvious errors, but only 4 real runs.
**Timeout:** 180s (down from 240s — the harness shouldn't need more than 2.5 min)

---

## How to Use the Harness

```bash
ssh root@45.76.230.100
docker exec buckaroo-ci bash /repo/ci/hetzner/run-pw-jupyter.sh <WHEEL_SHA> <TEST_SHA> [SETTLE_TIME]
# Results at /opt/ci/logs/<TEST_SHA>-pwj/
# Env overrides: JUPYTER_PARALLEL=N, CI_TIMEOUT=180
```

The harness does: cleanup -> checkout TEST_SHA -> load cached wheel -> create venv -> start P servers -> WebSocket warmup -> settle -> run playwright-jupyter -> cleanup.

---

## Experiment 1: Settle Time — Find What Works, Then Optimize

### Context
- Current default: 15s settle after warmup, before Playwright runs
- Settle was introduced in Exp 8-9 era when REST-only warmup couldn't reach idle
- Now we have WebSocket warmup that actually reaches `idle` — is settle still needed?
- We don't know if 15s is right, too much, or too little

### Approach
Start HIGH (40s) to establish a known-good baseline, then work down. Working first, then fast.

### Per-Process Monitoring
Every run must capture **per-process CPU/memory**, not just vmstat aggregate. We need to see which process (jupyter, kernel, chromium) is bottlenecked. Add instrumentation script:

```bash
# Run alongside harness — targeted per-process capture every 2s
while true; do
  echo "=== $(date +%H:%M:%S.%N) ==="
  # Jupyter servers
  ps -C jupyter-lab -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null
  # Python kernels
  ps -C python -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null | grep -i kernel
  # Chromium (top 5 by CPU)
  ps -C chromium -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null | head -5
  # Memory pressure
  free -m | grep -E 'Mem|Swap'
  # Network connections per port
  for p in 8889 8890 8891 8892 8893 8894; do
    echo "port $p: $(ss -tnp | grep -c ":$p ") connections"
  done
  sleep 2
done > /opt/ci/logs/<SHA>-pwj/per-process.log 2>&1 &
```

### Runs

**Run S1 — SETTLE_TIME=40 (1 of 4)**
- Restart container first (clean state)
- `CI_TIMEOUT=180 docker exec buckaroo-ci bash /repo/ci/hetzner/run-pw-jupyter.sh 4a7fefc 4a7fefc 40`
- Start per-process monitor in a parallel `docker exec`
- Expected: PASS (if 15s works, 40s definitely works)
- Captures: total time, per-notebook timing, per-process CPU/mem

**Run S2 — SETTLE_TIME=20 (2 of 4)**
- No container restart (back-to-back is fine for settle time tests)
- Same instrumentation
- Comparing: does reducing settle by 20s affect pass/fail? Any notebook slower?

**Run S3 — SETTLE_TIME=10 (3 of 4)**
- If S2 passed: try 10s
- If S2 failed: try 30s (somewhere between 20 and 40)

**Run S4 — SETTLE_TIME=5 or 0 (4 of 4)**
- If S3 passed at 10s: try 5 or 0
- If S3 failed: settle on 15-20s as the floor

### Success Criteria
- Find minimum settle time where 1/1 harness runs pass
- Per-process data shows WHICH process benefits from settle time (or none do)
- If settle=0 works: immediate 15s savings per run

---

## Experiment 2: Understand P=4 Deeply — Per-Process Profiling

### Context
P=4 works but we don't understand WHY it works and P=5/6 doesn't. Before pushing to higher parallelism, instrument P=4 to understand which process is the bottleneck during each phase:
- **Warmup phase:** 4 JupyterLab servers starting sequentially — is one slow?
- **Test execution phase:** 4 Chromium + 4 JupyterLab + 4 kernels — who's CPU-starved?
- **Between-batch gap:** What happens during kernel shutdown + re-warmup?
- **Batch 3 (1 notebook):** Machine nearly idle, but how fast is the single notebook?

The key question from earlier research: **which process deserves CPU priority — the browser, the kernel, or the server?** Probably the kernel or the server (they do the actual work), but we need data.

### Ideas for Higher Parallelism (recovered from tabled P=9 notes)
These inform what to try once we understand the P=4 profile:
1. **`renice` the browser, kernel, or server** — give CPU priority to the bottleneck process. Probably kernel or server since they do the real work, while Chromium is mostly waiting on network.
2. **Single shared JupyterLab server** — we abandoned shared-server early (Exp 2-5) due to ZMQ socket contention. But now we have `window.jupyterapp` reliable kernel detection. Worth revisiting if the per-process data shows server startup is the bottleneck.
3. **Stagger only the last N starts** — don't stagger all servers equally. Start the first 4 fast, then delay the last 1-2 by 5-10s so they don't compete during startup.
4. **Reduced reproduction** — if P=5/6 fails, build a minimal repro on the same server (e.g., just 2 servers + 2 notebooks) to isolate the failure without burning full-run iterations.

### Monitoring Script
Extend per-process capture from Exp 1 with:
```bash
# Per-process breakdown every 1s during test phase
while true; do
  echo "=== $(date +%H:%M:%S) ==="
  # Jupyter servers
  ps -C jupyter-lab -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null
  # Python kernels
  ps -C python -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null | grep -i kernel
  # Chromium (top 5 by CPU)
  ps -C chromium -o pid,pcpu,pmem,etime,args --no-headers 2>/dev/null | head -5
  # Memory pressure — check for swap usage (if swapping, bottleneck is memory not CPU)
  free -m | grep -E 'Mem|Swap'
  # Network connections per port
  for p in 8889 8890 8891 8892 8893 8894; do
    echo "port $p: $(ss -tnp | grep -c ":$p ") connections"
  done
  sleep 1
done
```

### Runs

**Run P1 — Instrumented P=4 baseline (1 of 4)**
- Restart container
- Best settle time from Exp 1 (or 15s if Exp 1 hasn't run yet)
- Full per-process monitoring
- Capture: which process peaks when, any idle gaps, kernel startup latency
- Answer: what % of CPU goes to jupyter vs kernel vs chromium during each phase?

**Run P2 — P=5 first attempt (2 of 4)**
- `JUPYTER_PARALLEL=5`
- Same instrumentation
- Key question: does the 5th server/notebook cause any of the other 4 to degrade?
- Watch for: longer kernel warmup on port 8893, slower batch-1 execution
- If fails: try staggering only port 8893's start by 5-10s extra

**Run P3 — P=5 adjusted or repeated (3 of 4)**
- If P2 passed: run P=5 again (need 2/2 to trust it)
- If P2 failed: apply targeted fix based on per-process data:
  - If kernel is bottleneck: `renice -5` kernel processes
  - If chromium is bottleneck: `renice 5` chromium processes (deprioritize)
  - If server startup is bottleneck: stagger last server start by 10s

**Run P4 — P=5 confirmed or P=6 first attempt (4 of 4)**
- If P=5 is 2/2: try P=6
- If P=5 fix worked: run P=5 again to confirm
- If P=5 is dead: document the limit and move on

### Success Criteria
- Per-process CPU breakdown during each phase (warmup / batch-1 / between-batch / batch-2 / batch-3)
- Identify THE bottleneck process: jupyter? kernel? chromium?
- Determine if P=5 is viable
- If not: clear data on WHY (not guessing)

---

## Experiment 2B: Test Reordering — Are Infinite Notebooks Heavier?

### Context
Current ordering puts 2 infinite + 2 non-infinite notebooks per batch. But we don't know if infinite notebooks are actually heavier (more kernel computation, more data transfer, longer widget render). If they are, the current even spread might be masking the real contention — or making it worse by pairing heavy with heavy.

Current batching:
- **Batch 1:** buckaroo, buckaroo_infinite, polars, polars_infinite
- **Batch 2:** dfviewer, dfviewer_infinite, polars_dfviewer, polars_dfviewer_infinite
- **Batch 3:** infinite_scroll_transcript (alone)

Also: `test_lazy_infinite_polars_widget.ipynb` exists but is NOT in the test list. If "lazy infinite" is tougher than regular infinite, adding it would stress-test the setup.

### Approach
Use per-process data from Exp 2 (P1) to measure per-notebook CPU cost. Then reorder to test whether batching strategy matters.

### Runs (own budget of 4 — only run after Exp 2 P1 data is analyzed)

**Run R1 — All-infinite batch (1 of 2)**
- Reorder NOTEBOOKS array: put all 4 infinite notebooks in Batch 1, all 4 non-infinite in Batch 2
- Same P=4, same settle time from Exp 1
- Compare: is the all-infinite batch slower? Higher CPU? More kernel contention?
- This isolates whether notebook weight matters or all notebooks cost roughly the same

**Run R2 — Add lazy infinite notebook (2 of 2)**
- Add `test_lazy_infinite_polars_widget.ipynb` to the test list (10 notebooks total → batches of 4+4+2)
- If lazy infinite is heavier, this tells us where the ceiling is
- If it passes fine: we know the notebook itself isn't the bottleneck, it's process count

### Success Criteria
- Quantify per-notebook CPU cost (from Exp 2 P1 data)
- Determine if notebook ordering/grouping affects pass rate or timing
- Decide if lazy infinite should be added permanently to the test suite

---

## Experiment 3: Chromium Pre-Warming (Handoff to Tests)

### Context
Currently, every Playwright test launches a fresh Chromium instance. Chromium startup is expensive (100-200MB RSS, initial render pipeline, JIT warmup). The idea: **start Chromium during the kernel warmup phase (Wave 0), then hand the running browser to Playwright tests**.

This would eliminate Chromium cold-start from the test execution critical path. The browser would already be warmed, JIT'd, and memory-mapped when the first notebook test fires.

### How Playwright Browser Reuse Works
Playwright supports connecting to an already-running browser:

1. **`browserType.launchServer()`** — starts a browser and returns a `BrowserServer` with a WebSocket endpoint
2. **`browserType.connect(wsEndpoint)`** — connects to an already-running browser from a test
3. The `wsEndpoint` URL can be passed via env var to test processes

Alternatively, Playwright's `--reuse-browser` or `browserType.connectOverCDP()` for Chromium's DevTools Protocol.

### Technical Questions
1. **Does `test_playwright_jupyter_parallel.sh` launch browsers?** Or does Playwright's test runner handle it? Need to check if we can intercept the browser launch.
2. **Can we pre-launch N browsers (one per parallel slot)?** Each slot needs its own browser to avoid the same ZMQ-style contention we saw with shared JupyterLab.
3. **How much time does Chromium startup actually cost?** Per-process data from Exp 2 will tell us. If it's only 1-2s, this optimization isn't worth the complexity.
4. **Does Playwright's `--workers` already reuse browsers across tests?** If tests within a batch share a browser context, pre-warming might not help.

### Runs

**Run C1 — Measure Chromium startup cost (1 of 1, gate for C2-C4)**
- Use per-process data from Exp 2 (P1 run) — no separate server run needed
- Extract: time from `chromium` process spawn to first test assertion
- If < 3s: SKIP this experiment entirely (not enough savings to justify complexity). Reallocate remaining 3 runs to whatever Exp 2 reveals as the actual bottleneck.
- If > 3s: proceed to C2-C4

**Run C2 — Prototype browser pre-launch (only if C1 > 3s)**
- During warmup phase, launch N Chromium instances via `npx playwright launch-server`
- Capture the WebSocket endpoints
- Pass endpoints to test harness via env var
- Modify `test_playwright_jupyter_parallel.sh` to use `connect()` instead of `launch()`

**Run C3 — Test pre-launched browsers with P=4 (only if C1 > 3s)**
- Full harness run with pre-launched browsers
- Compare timing vs baseline

**Run C4 — Pre-launched browsers with P=5 or P=6 (only if C1 > 3s)**
- If C3 worked: test at higher parallelism
- Pre-warmed browsers might be what makes P=6 viable (eliminates Chromium startup burst)

### Success Criteria
- Quantify Chromium startup overhead (from Exp 2 data)
- If overhead > 3s: working prototype of browser handoff
- If overhead < 3s: documented as "not worth it", 3 runs reallocated to actual bottleneck

---

## Experiment 4: Back-to-Back Run Degradation (Lower Priority)

### Context
- "Back-to-back" = two complete pw-jupyter harness runs in the same container without restart
- Runs 1-2 pass, run 3+ sometimes fails
- NOT zombies (tini confirmed 0 zombies)
- Workaround exists: restart container
- Lower priority because single runs always pass

### Runs

**Run B1 — Instrumented consecutive runs (1 of 4)**
- Restart container
- Run harness 3x consecutively
- Between each: capture fd count, memory, /tmp files, runtime files, open sockets, `ss -s` (socket summary — TIME_WAIT accumulation is a common culprit for port-based services)
- Goal: identify what accumulates

**Run B2 — 4th consecutive run (2 of 4)**
- Continue from B1 (no restart)
- If B1's run 3 failed: we have the diff data
- If B1's run 3 passed: push to run 4-5

**Run B3 — Targeted cleanup fix (3 of 4)**
- Based on what B1/B2 found accumulating: add cleanup step
- Restart container, run 3x again to verify

**Run B4 — Confirm fix (4 of 4)**
- Run 4-5x to confirm the fix holds

### Success Criteria
- Identify what accumulates across runs (or prove the harness doesn't have this problem)
- If harness-specific: fix the cleanup
- If full-CI-only: document and defer

---

## Priority & Execution Order

| # | Experiment | Potential Impact | Why This Order |
|---|-----------|-----------------|----------------|
| 1 | Settle Time | Save 10-15s/run | Quick, establishes baseline, informs all other experiments |
| 2 | P=4/5 Profiling | Understand bottleneck | Must understand P=4 before pushing to P=5/6 |
| 2B | Test Reordering | Reveals if notebook weight matters | Own budget, runs after Exp 2 P1 data analyzed |
| 3 | Chromium Pre-Warm | Potentially enables P=6 | C1 is a gate (data-only); C2-C4 only if Chromium > 3s startup |
| 4 | Back-to-Back | Eliminate restart need | Low priority — workaround exists |

Total: 20 runs max across 5 experiment tracks (4+4+4+4+4). Exp 3 likely yields 3 runs back to the actual bottleneck.

---

## Data Capture Checklist (Every Run)

- [ ] `ci.log` — harness timestamps
- [ ] `playwright-jupyter.log` — per-notebook pass/fail + timing
- [ ] `cpu.log` — vmstat 1s aggregate CPU
- [ ] `per-process.log` — per-process CPU/mem/connections every 1-2s
- [ ] Screenshot the per-process data at key moments (warmup, batch-1, between-batch, batch-2)

---

## Ideas Parked for Later (from tabled P=9 notes, commit 5996d8c)

These are worth revisiting if Experiments 1-3 don't get us to P=6+:

1. **Single shared JupyterLab server** — Exp 2-5 showed ZMQ socket contention killed shared-server at P=3. But that was before `window.jupyterapp` kernel detection (Exp 21). With reliable kernel-ready checks, a single server might handle P=4-6 if the ZMQ issue was really about timing, not fundamental contention. Would eliminate N-1 server processes and their memory/CPU overhead.

2. **Reduced reproduction** — Build a minimal test case: 1-2 servers, 2-3 notebooks, on the same Vultr server. Isolate whether failures are from process count, memory, port contention, or something else entirely. Useful if P=5/6 failures are hard to diagnose from full-run logs.

3. **P=9 revisited** — Conclusively dead at 16 vCPU with current architecture. Would need either (a) single shared server reducing process count from 27 to 11, or (b) more CPU cores, or (c) browser pre-warming eliminating the Chromium startup burst.

---

## Notes

- P=6 failure logs from ef53834 were overwritten by a subsequent P=4 run. The archive says "3-6/6 kernel timeouts on later ports (8892-8894)." Experiment 2 will reproduce and capture properly.
- 180s harness timeout: P=4 passing run takes ~96s for test phase. 180s gives ~80s headroom. If we're burning 3 minutes, something is broken — fail fast.
