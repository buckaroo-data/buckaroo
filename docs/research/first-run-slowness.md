# First-Run Slowness After Fresh Install

## Problem

When running buckaroo in JupyterLab, the first cell execution after a fresh
install takes 5–15 seconds. Killing the kernel and re-executing takes <1s.

## Root Cause: macOS Gatekeeper / syspolicyd

**Confirmed.** macOS scans every unsigned `.so`/`.dylib` the first time it's
loaded via `dlopen()`. The scan is performed by `syspolicyd` and the result is
cached per-inode. This is a macOS platform behavior, not a buckaroo bug.

### Proof

Monitoring `syspolicyd` during import runs:

```
Run A: fresh install, first execution                      16.19s   (3307 syspolicyd log lines)
Run B: second execution (warm baseline)                     0.98s   (1 syspolicyd log line)
Run C: fresh install again (confirmation)                  14.99s   (3306 syspolicyd log lines)
```

The slow runs produce ~3,300 syspolicyd log entries. The fast run produces 1.
The logs contain `errSecCSUnsigned` (`-67062`) — the native extensions from
pip packages are not code-signed, so syspolicyd performs a full assessment
on each one.

## How We Got Here

### Hypotheses eliminated

| Hypothesis | Test | Result |
|---|---|---|
| PYC file creation | Delete pyc, re-run (warm cache) | 2.4s, not 14s. PYC adds ~1.3s |
| OS filesystem cache | Purge cache, re-run same venv | 3s, not 14s. Cache irrelevant |
| Hidden file creation | Diff non-pyc file listings | 12,138 files at every step, identical |
| Filesystem cache (primed) | Fresh venv, cat all files, then run | 13.75s — still slow |

### Key observation

The critical test was comparing two runs with identical file contents:

- **Same venv** (executed before), pyc deleted, fs cache purged → **3s**
- **Fresh venv** (never executed), fs cache primed with cat → **14s**

Same files, same cache state — but one had been `dlopen()`'d before
(syspolicyd cache warm) and one hadn't.

### Wall time vs CPU time

From `time` output on first run: `real 14.5s, user 2.6s, sys 0.5s`.
~11 seconds blocked waiting on syspolicyd, not doing CPU work.

## Why It Happens

1. `uv pip install` writes `.so` files with new inodes
2. Python imports trigger `dlopen()` on native extensions
3. macOS syspolicyd intercepts each `dlopen()` of an unseen inode
4. Since pip packages aren't code-signed, syspolicyd logs `errSecCSUnsigned`
   and performs full assessment
5. Results are cached per-inode — subsequent loads are instant
6. A fresh install creates new inodes, resetting the cache

## Practical Implications

- **Not a buckaroo bug.** Any Python environment with native extensions
  (polars, numpy, pandas, etc.) will have this on macOS.
- **One-time cost.** Only happens once per install, not per kernel restart.
- **Linux unaffected.** No Gatekeeper on Linux — CI/servers won't see this.
- **Mitigation**: Run a throwaway `python -c "import polars, buckaroo"` after
  install to pre-warm the syspolicyd cache before opening JupyterLab.

## Test Script

`scripts/test_pyc_impact.sh` — creates a fresh venv, installs packages,
times imports while monitoring syspolicyd, and prints a summary.
