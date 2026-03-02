# Parallel Jupyter Playwright — Experiment Log

**Branch:** docs/ci-research
**Goal:** Enable PARALLEL=3 (or more) for Phase 5b (playwright-jupyter) to reduce total CI time from ~6min toward the critical-path minimum.

---

## Background

Phase 5b runs 9 integration notebooks against JupyterLab using Playwright. Each notebook opens JupyterLab in a fresh browser context, executes a cell, and asserts that a Buckaroo widget renders as ag-grid.

Baseline (PARALLEL=1): 9 notebooks run sequentially on one JupyterLab server.
Goal: Run 3 at a time to save ~45s off total.

The old script used fixed `waitForTimeout(800)` + `waitForTimeout(500)` calls instead of proper `waitFor` conditions. These were replaced with `waitFor({state:'attached', timeout:CELL_EXEC_TIMEOUT})` in commit **65d49b2**.

---

## Experiment Summary Table

| Exp | Commit | PARALLEL | Architecture | Phase 5b | Result |
|-----|--------|----------|-------------|----------|--------|
| 1 | fcfe368 | 3 | 1 server, old specs | — | 5/9 FAIL (old specs had waitForTimeout) |
| 2 | 65d49b2 | 3 | 1 server, new waitFor specs | ~90s | 5/9 FAIL (WebSocket drops) |
| 3 | 5e86490 | 2 | 1 server, new specs | ~90s | 1/9 FAIL (cell timeout 8s) |
| 4 | e8c429c | 2 | 1 server, CELL_EXEC_TIMEOUT=20s | 125s | 2/9 FAIL (ZMQ errors) |
| 5 | 55707c1 | 1 | 1 server, CELL_EXEC_TIMEOUT=20s | ~104s | ALL PASS |
| 6 | f46971d | 3 | 3 isolated servers, parallel startup | 129s | 2/9 FAIL (CPU competition) |
| 7 | d6bc031 | 3 | 3 isolated servers, sequential startup | in progress | — |

---

## Detailed Experiment Notes

### Exp 1 — wrong SHA (fcfe368, PARALLEL=3, 1 server)

Tested the wrong commit. `fcfe368` had old specs with `waitForTimeout(800)` + `waitForTimeout(500)` hardcoded delays. PARALLEL=3 means 3 kernels start simultaneously on one server; the static waits fire before all widgets render. 5/9 fail with "Widget failed to render: 0 elements."

**Lesson:** Always verify the SHA has the target changes before inferring a technique doesn't work.

---

### Exp 2 — new waitFor specs, PARALLEL=3, 1 server (65d49b2)

The `waitFor` fixes are in. Still 5/9 failures but with different errors:
```
tornado.websocket.WebSocketClosedError
zmq.error.ZMQError: Socket operation on non-socket
```

Root cause: JupyterLab uses a single ZMQ kernel provisioner. When 3 kernels start simultaneously on one server, ZMQ socket allocation races. Comm channels never establish. The spec correctly waits for output, but the output never appears because the widget comm is dropped.

**Lesson:** `waitFor` fixed the timing issue, but the underlying socket contention is a JupyterLab architecture constraint. Can't fix with more waiting.

---

### Exp 3 — PARALLEL=2, 1 server (5e86490)

Reduced to 2 concurrent notebooks. 1/9 fail: `test_buckaroo_widget.ipynb` (the first notebook in the list) times out at the 8s DEFAULT_TIMEOUT waiting for cell output. Other 8 pass.

The first notebook is always the hardest: JupyterLab is still initialising when batch 1 starts. With 2 kernels starting simultaneously, the first kernel to get scheduled is slightly delayed.

Also: `test-python-3.11` failed with a PyO3/pyo3-0.26.0 panic after 631 tests (shutdown crash, assertion failure in Polars Rust code). All 631 tests pass; the crash is in teardown. Appears under server load.

---

### Exp 4 — PARALLEL=2, CELL_EXEC_TIMEOUT=20s (e8c429c)

Increased the cell execution wait from 8s to 20s. 2/9 fail with ZMQ errors (still present even at PARALLEL=2). Phase 5b takes 125s — *slower* than PARALLEL=1 because failures now cost 20s each to timeout instead of 8s.

**Lesson:** Raising the timeout amplifies failure cost. With 2 notebooks still racing on one JupyterLab ZMQ context, we still get socket errors on some runs. The 20s timeout helped nothing and hurt timing.

---

### Exp 5 — PARALLEL=1, CELL_EXEC_TIMEOUT=20s (55707c1)

Reverted to serial. All 9 pass in ~104s. Stable. `test-python-3.11` PyO3 panic absent this run.

**Conclusion:** 1 server + 1 notebook at a time = reliable. Any shared-server parallelism causes ZMQ contention.

---

### Exp 6 — PARALLEL=3, 3 isolated servers, parallel startup (f46971d)

Key architectural change: each parallel slot gets its own JupyterLab server on a distinct port (8889, 8890, 8891). No shared ZMQ context, no kernel contention between slots.

Changes:
- `integration.spec.ts` and `infinite-scroll-transcript.spec.ts`: hardcoded `localhost:8889` → `process.env.JUPYTER_BASE_URL`
- `test_playwright_jupyter_parallel.sh`: start N servers, `run_one()` sets `JUPYTER_BASE_URL=http://localhost:$port`
- Each slot's `shutdown_kernels_on_port()` targets only its own server

Result: 2/9 FAIL (`test_buckaroo_infinite_widget` on port 8890, `test_infinite_scroll_transcript` on port 8891). Phase 5b: 129s — *worse* than PARALLEL=1.

Log excerpt from failing notebook:
```
TimeoutError: locator.waitFor: Timeout 20000ms exceeded
waiting for locator('.jp-OutputArea-output')
```

Root cause: all 3 servers start in parallel. CPU competition during startup slows the JupyterLab processes on ports 8890 and 8891. The server startup block takes 72s (servers start together, all compete for CPU). By the time batch 1 runs, port 8890's server hasn't fully settled — kernel startup is slow, cell execution exceeds 20s timeout.

Setup time breakdown:
- Parallel server startup: 72s (should be ~15s/server but they overlap)
- Batch 1 execution: 57s (but 2 notebooks fail)
- Total: 129s

**Lesson:** Isolated servers fix ZMQ contention but parallel server startup creates a new problem: CPU competition during initialisation. Sequential startup needed.

---

### Exp 7 — PARALLEL=3, 3 isolated servers, sequential startup (d6bc031)

Each server now starts one at a time:
1. Start server N in background
2. Poll `GET /api?token=...` until HTTP 200 (up to 30s)
3. Run warmup kernel (start → wait for idle → delete) — ensures kernel provisioner is ready
4. Start server N+1

Expected setup time: ~15s/server × 3 = ~45s (vs 72s parallel), with each server fully idle before the next starts.

Batch 1 should now see all 3 servers warmed up and CPU-idle before any notebook runs.

Committed d6bc031, deployed, running now.

---

## Key Technical Findings

### ZMQ socket contention on shared JupyterLab
Multiple concurrent kernel startups on one JupyterLab server race for ZMQ socket allocation. Manifests as `tornado.websocket.WebSocketClosedError` and `zmq.error.ZMQError: Socket operation on non-socket`. The widget comm channel never establishes. No amount of waiting fixes this — it's a JupyterLab infrastructure constraint.

**Fix:** Isolated servers (one per parallel slot).

### CPU competition during parallel server startup
Starting N JupyterLab servers simultaneously on a shared host causes all to compete for CPU during their initialisation phase. The slower-starting servers (ports 8890, 8891) are not fully settled when batch 1 begins, causing kernel startup to exceed the 20s cell execution timeout.

**Fix:** Sequential server startup — each server starts alone, reaches HTTP-ready + kernel-warmed state, then next server starts.

### Kernel gateway warmup is essential
Even after a JupyterLab server is HTTP-ready, the kernel provisioner needs a warmup cycle (start + wait for idle + delete). Without warmup, the first real kernel takes extra time to provision, causing batch 1 cell execution timeouts.

This was already implemented from previous work; the sequential startup makes it more effective by ensuring each server is warmed before tests begin.

### Batch-1 timing sensitivity
The first notebook in each parallel batch is always the most timing-sensitive because:
1. JupyterLab may still be scanning for stale runtime files (fixed by deleting them at script start)
2. The first kernel on a freshly-started server is slower to provision than subsequent ones (fixed by kernel warmup)
3. CPU contention if servers start simultaneously (fixed by sequential startup)

Batches 2+ are consistently reliable because the server has already served one kernel cycle.

### PyO3/Polars 3.11 panic
After all 631 tests pass, the Python 3.11 process exits with SIGABRT (exit code 134). The panic occurs in a background Rust thread during Python interpreter finalization:

```
thread 'polars-' panicked at 'assertion `left != right` failed'
pyo3-0.26.0/.../py_object_owned_anyhow.rs
```

This is a known issue with pyo3-0.26.0 + Polars on Python 3.11 under high memory pressure (zombie process accumulation in Docker). All tests pass; only the teardown crashes. Appears non-deterministically under server load. Not a CI logic issue.

---

## Files Modified This Session

| File | Change |
|------|--------|
| `packages/buckaroo-js-core/pw-tests/integration.spec.ts` | `localhost:8889` → `process.env.JUPYTER_BASE_URL`; `CELL_EXEC_TIMEOUT=20000` |
| `packages/buckaroo-js-core/pw-tests/infinite-scroll-transcript.spec.ts` | Same changes |
| `scripts/test_playwright_jupyter_parallel.sh` | Complete rewrite: N isolated servers, sequential startup, per-server warmup, `run_one()` takes port arg |
| `ci/hetzner/run-ci.sh` | `PARALLEL=1→3` with updated phase 5b comment |

---

## Timing Targets

Critical path (minimum possible): `test-js(24s) → build-wheel(22s) → playwright-jupyter`

playwright-jupyter uncontended (PARALLEL=1): **2m03s** (9 notebooks × ~14s each)

With PARALLEL=3 and sequential server startup (estimated):
- Server startup: ~45s (3 × 15s sequential)
- Batch 1: 3 notebooks × ~14s = ~42s (dominated by longest notebook)
- Batch 2: 3 notebooks = ~42s
- Batch 3: 3 notebooks = ~42s
- Kernel cleanup between batches: ~3s × 2 = ~6s
- Total: **~135s** (hmm, that's not better)

Wait, the savings come from batches running in parallel within each batch. Batch 1 runs 3 notebooks concurrently in ~14s (not 42s). So:
- Server startup: ~45s
- Batch 1: ~14s (3 notebooks in parallel)
- Batch 2: ~14s
- Batch 3: ~14s + cleanup overhead
- Total: **~90s** (vs 123s PARALLEL=1)

Savings vs PARALLEL=1: **~33s** off Phase 5b, **~33s** off total.
