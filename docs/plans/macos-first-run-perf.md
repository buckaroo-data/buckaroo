# macOS First-Run Performance: syspolicyd / XProtect Scanning

## Findings

### Timings

| Run | Time | syspolicyd lines |
|-----|------|-----------------|
| A: fresh install, first execution | 16.19s | 3,307 |
| B: second execution (warm) | 0.98s | 1 |
| C: fresh install again | 14.99s | 3,306 |

### Root Cause

The ~15s first-run penalty is entirely macOS Gatekeeper (syspolicyd/XProtect/taskgated) scanning every file in the installation before allowing execution. On second run, the verdicts are cached and scanning is skipped (1 log line vs 3,300+).

A fresh install invalidates the cache, causing the full scan again.

### Actual application performance

~1s (Run B) — the warm baseline is the true startup time.
