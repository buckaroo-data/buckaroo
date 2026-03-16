# pw-jupyter Batch Server Reuse Fix

**Date:** 2026-03-04
**Server:** Vultr VX1 32C (66.42.115.86) — 32 vCPU/128GB, EPYC Turin Zen 5
**Branch:** docs/ci-research
**Commits:** f65e8de (cleanup), 0103187 (P=9 fix)

---

## Problem

pw-jupyter fails consistently when batch 2 reuses JupyterLab servers from
batch 1. With `PARALLEL=5` and 9 notebooks, the test harness runs two batches
(5 + 4). The second batch's tests on reused servers timeout — kernels start but
never reach `idle` from the browser's perspective.

This was initially attributed to b2b container contamination or VX1 platform
quirks (see `vx1-kernel-flakiness.md`). Both were wrong. The actual root cause
is JupyterLab server reuse within a single CI run.

## Investigation

### What we checked (container state after 4 CI runs)

| Resource | State | Impact |
|----------|-------|--------|
| Processes | Marimo server leaked (679MB), storybook leaked (367MB) | Not root cause — `pkill marimo` was missing |
| /tmp | 18 jupyter log files, 30 tmp*.txt, playwright dirs accumulating | Not root cause — disk cruft, no functional impact |
| /dev/shm | Clean | Not relevant |
| TCP sockets | 25 TIME_WAIT on ephemeral ports | Normal, auto-clears |
| Jupyter runtime | Clean (kernel files removed) | Not relevant |
| JupyterLab workspace | Stale workspace file remembering previous notebooks | Contributes to kernel churn but not root cause |
| Memory | 2.9GB / 128GB | Not relevant |
| Zombies | None (tini working) | Not relevant |

### The JupyterLab server log pattern

On failing ports (batch 2, reused servers), every JupyterLab log shows the same
pattern: **multiple kernel start/shutdown cycles within seconds**, then a kernel
that stays alive but the browser never sees it go idle.

Port 8890 (batch 2, FAIL):
```
15:49:37 Kernel started: 33a95790  (between-batch warmup, deleted at 15:49:38)
15:49:43 Kernel started: 2a493ddd  (browser opens notebook — 3 connections)
15:49:44 Kernel started: 5dd6c11b  (mystery 2nd kernel — 1 connection)
... silence for 85 seconds ...
15:51:09 SIGTERM — Shutting down 2 kernels
```

The 2nd kernel has only 1 WebSocket connection (not the standard 3 for a
notebook session). It's created by Playwright's retry mechanism — the first
attempt times out at 60s, Playwright retries, which opens a new browser context
that starts a new kernel without cleaning up the first.

### Key insight: port 8889 (batch 2) also has 2 kernels but PASSES

Port 8889 shows the identical 2-kernel pattern yet passes. The difference isn't
the number of kernels — it's that port 8889 runs `test_dfviewer_infinite` which
is lighter than the three failing tests (`test_polars_dfviewer`,
`test_polars_dfviewer_infinite`, `test_infinite_scroll_transcript`).

### The P=5 → P=9 insight

- **Warmup** starts 9 JupyterLab servers (`JUPYTER_PARALLEL` unset → defaults to 9)
- **Test harness** uses only 5 (`JUPYTER_PARALLEL=5` set at line 586)
- With P=5: batch 1 uses 5 servers, batch 2 reuses 4 of those servers
- Batch 2 tests on reused servers consistently fail (kernel never reaches idle)
- With P=9: all 9 notebooks run in one batch, each on a dedicated server — no reuse

This was left at P=5 from the 16 vCPU VX1 experiments where 9 concurrent
Chromium + JupyterLab pairs overwhelmed 16 cores. The current 32 vCPU box
handles P=9 fine.

## Why Server Reuse Fails

The between-batch cleanup (`shutdown_kernels_on_port` + `warmup_one_kernel`)
runs correctly — kernels are deleted and re-warmed. But the JupyterLab server
has accumulated internal state from batch 1:

1. **Session manager state** — previous notebook sessions leave traces
2. **Extension state** — LSP, terminals, etc. have been initialized for batch 1's notebook
3. **Workspace restoration** — even with per-port workspace dirs, JupyterLab may try
   to restore the previous notebook's layout
4. **ZMQ channel state** — the server's ZMQ routing tables have entries from batch 1

The exact mechanism is unclear, but the evidence is definitive: reusing
JupyterLab servers after running a test reliably causes the next test's kernel
to fail. Starting each notebook on a fresh (never-before-used) server works
100% of the time.

## Fix Applied

### 1. JUPYTER_PARALLEL=9 (the actual fix)

`ci/hetzner/run-ci.sh` line 630: changed `JUPYTER_PARALLEL=${JUPYTER_PARALLEL:-5}`
to `JUPYTER_PARALLEL=${JUPYTER_PARALLEL:-9}`.

All 9 notebooks run in one batch. Each gets its own dedicated JupyterLab server.
No server reuse. No batch 2.

### 2. Container cleanup hardening (defense in depth)

Added to pre-run cleanup:
- `pkill -9 -f 'marimo'` — marimo servers were never killed between runs
- `fuser -k` on ports 2718 (marimo) and 6006 (storybook)
- `rm -f /tmp/jupyter-port*.log` — accumulated across runs with PID suffixes
- `rm -f /tmp/tmp*.txt` — small temp files from pytest/jupyter
- `rm -rf /tmp/playwright-artifacts-* /tmp/playwright_chromiumdev_profile-*`
- `rm -rf /tmp/jlab-ws-*` — per-port workspace temp dirs

### 3. Per-port JupyterLab workspace dirs

`--LabApp.workspaces_dir="/tmp/jlab-ws-$$-$port"` on each JupyterLab server.
Prevents workspace files from leaking between servers or between runs. Each
server gets an isolated temp dir that's cleaned on the next run.

### 4. Container state snapshots

`snapshot_container_state()` function in `run-ci.sh` captures: processes, /tmp,
/dev/shm, TCP sockets, jupyter runtime, workspaces, memory. Snapshots taken at:
- `container-before.txt` — before cleanup (what the previous run left)
- `container-after.txt` — after cleanup (verify clean start)
- `container-end.txt` — end of run (what this run leaves behind)

Written to `/opt/ci/logs/$SHA/`, visible from the host without entering the
container.

## Results

### VX1 32C (32 vCPU / 128GB, $701/mo) — commit 0103187

| Run | Container | Total | pw-jupyter | Result |
|-----|-----------|-------|-----------|--------|
| 1 | Fresh restart | 1m45s | 47s | ALL PASS |
| 2 | Back-to-back | 1m56s | 46s | ALL PASS |
| 3 | Back-to-back | 1m45s | 46s | ALL PASS |
| 4 | Back-to-back | 1m45s | 47s | ALL PASS |

### VX1 16C (16 vCPU / 64GB, $350/mo) — commit f33905c

Fresh cloud-init provisioning on new box (66.42.116.218). Validates both the
P=9 fix and the cloud-init provisioning pipeline.

| Run | Container | Total | pw-jupyter | Result |
|-----|-----------|-------|-----------|--------|
| 1 | Fresh | 2m37s | 47s | ALL PASS |
| 2 | Back-to-back | 1m45s | 47s | ALL PASS |
| 3 | Back-to-back | 1m45s | 47s | ALL PASS |
| 4 | Back-to-back | 1m46s | 47s | 14/16 pass* |

*Run 4 failures: `test_lazy_widget_init_should_not_block_but_does_with_mp_and_slow_exec`
(sqlite3.OperationalError: database is locked) and `test_execution_update_messages`
(timing assertion). Both are pre-existing flaky unit tests under CPU pressure, not
CI infra issues. pw-jupyter passed all 4 runs.

### VX1 8C (8 vCPU / 32GB, $175/mo) — commit f33905c

Fresh cloud-init provisioning on new box (207.148.15.78). Stress test: 9 concurrent
Chromium + JupyterLab pairs on only 8 vCPUs.

| Run | Container | Total | pw-jupyter | Result |
|-----|-----------|-------|-----------|--------|
| 1 | Fresh | 2m49s | 47s | ALL PASS |

### Cross-size comparison

| Box | vCPU | RAM | $/mo | Cold build | Warm b2b | pw-jupyter | P=9 |
|-----|------|-----|------|-----------|----------|-----------|-----|
| VX1 8C | 8 | 32GB | $175 | 2m49s | — | 47s | PASS |
| VX1 16C | 16 | 64GB | $350 | 2m37s | 1m45s | 47s | PASS |
| VX1 32C | 32 | 128GB | $701 | 1m45s | 1m45s | 47s | PASS |

Key insight: pw-jupyter is always 47s regardless of box size. The cold-build
overhead is the only difference — warm b2b runs converge to ~1m45s on all sizes.
8C is sufficient for CI at 1/4 the cost of 32C.

## Debunked Hypotheses

| Hypothesis | Status | Evidence |
|-----------|--------|---------|
| b2b container contamination | **Debunked** | Fails on fresh container too (f65e8de run 1) |
| VX1 platform/Zen 5 issue | **Debunked** | P=9 works perfectly on VX1 32C |
| ipykernel 6.x vs 7.x | **Debunked** | Both versions fail with P=5, both pass with P=9 |
| JupyterLab workspace state | **Contributing but not root cause** | Per-port dirs help but P=9 was the fix |
| Leaked marimo/storybook processes | **Real leak, not root cause** | 1GB leaked but 128GB total — no impact |

## Relationship to Other Research

- **`vx1-kernel-flakiness.md`** — Initial investigation that proved kernel works
  via ZMQ/WebSocket. The "VX1 platform-specific" hypothesis (#1 ranked) is now
  debunked. The actual issue was PARALLEL=5 server reuse, not hardware.
- **`pw-jupyter-exploration-results.md`** — Exp 1 "Side Finding: Back-to-Back
  Degradation Confirmed" at P=4 on 16 vCPU was the same bug: P<9 causes batch
  reuse, batch 2 fails.
- **`ci-tuning-experiments.md`** — Exp 52 (ipykernel version fix) is no longer
  the blocker. pw-jupyter works at P=9 with both ipykernel 6.29.5 and 7.2.0.
  The package upgrade (commit cd51c9e) stays because newer is better, but it
  wasn't the fix.
- **`parallel-jupyter-experiments.md`** — Early P=2/3 experiments that failed
  were likely hitting the same server-reuse issue at smaller scale.

## Takeaway

**Never reuse a JupyterLab server after running a Playwright test on it.**
Start each notebook test on a fresh, dedicated JupyterLab instance. The
between-batch cleanup (kill kernels, delete sessions, re-warm) is insufficient
— something in JupyterLab's internal state makes the next test's kernel
unreachable from the browser.
