# pw-jupyter Exploration Results

**Started:** 2026-03-03
**Server:** Vultr 16 vCPU / 32 GB (45.76.230.100)
**Baseline:** P=4, 96s, 100% pass rate (commit 4a7fefc)

---

## Experiment 1: Settle Time

**Conclusion: Settle time is unnecessary. SETTLE_TIME=0 works.**
WebSocket warmup reaches `idle` on all kernels before settle starts.
The 15s default settle adds pure waste. Saves 15s/run.

### Results

| Run | Settle | Result | Test Phase | Container State |
|-----|--------|--------|-----------|-----------------|
| S1 | 40s | PASS | 90s | Fresh |
| S2 | 20s | PASS | 91s | Back-to-back (2nd) |
| S3 | 10s | FAIL (timeout) | — | Back-to-back (3rd) — degradation bug, not settle |
| S3b | 10s | PASS | 91s | Fresh — confirms 10s works |
| S4 | 0s | PASS | 92s | Fresh |

### Per-Process Data (S1, settle=40s)
- At settle start (t+0s): Jupyter servers at 14-22% CPU — `ps` cumulative average high from startup burst
- By t+15s: Down to 6-12% (cumulative average declining)
- By t+25s: Down to 4-8% (servers genuinely idle)
- Chromium/kernels: not present during settle (no tests running)
- Memory: 2.1GB of 32GB used, 0 swap — not memory-constrained

### Side Finding: Back-to-Back Degradation Confirmed
S3 (10s, 3rd consecutive run) timed out — batch 1 passed (4/4), batch 2 hung on polars_dfviewer and polars_dfviewer_infinite. Retry with fresh container passed immediately. This confirms the Exp 4 issue is real and surfaces on 3rd run.

---

## Experiment 2: P=4/5 Profiling

*Status: in progress — using SETTLE_TIME=0 from Exp 1*

### Run P1 — Instrumented P=4 baseline

*Status: pending*

### Run P2 — P=5 first attempt

*Status: pending*

### Run P3 — P=5 adjusted or repeated

*Status: pending*

### Run P4 — P=5 confirmed or P=6 first attempt

*Status: pending*

---

## Experiment 2B: Test Reordering

*Status: pending (after Exp 2 P1)*

---

## Experiment 3: Chromium Pre-Warming

*Status: pending (gate on Exp 2 data)*

---

## Experiment 4: Back-to-Back Degradation

*Status: pending (low priority — but confirmed real from Exp 1 S3)*
