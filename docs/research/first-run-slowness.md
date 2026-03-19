# First-Run Slowness After Fresh Install

## Problem

When running buckaroo in JupyterLab, the first cell execution after a fresh
install takes 5–15 seconds. Killing the kernel and re-executing takes <1s.

## Test Setup

Script: `scripts/test_pyc_impact.sh`

Imports `jupyterlab`, `buckaroo`, and `polars` under controlled conditions,
varying whether pyc files exist, whether the OS filesystem cache is warm,
and whether the venv is freshly installed.

## Results

```
Run 1: cold fs + no pyc (first ever)                  14.39s
Run 2: warm fs + pyc                                   1.11s
Run 3: warm fs + no pyc (pyc deleted)                  2.43s
Run 4: warm fs + pyc (confirmation)                    0.97s
Run 5: purged fs + no pyc                              2.99s
Run 6: warm fs + pyc (confirmation)                    0.97s
cat prime: read all files into fs cache                1.54s
Run 7: fresh venv, cat-primed fs + no pyc             13.75s
Run 8: warm fs + pyc (confirmation)                    0.97s
```

Non-pyc file count was **identical** (12,138) across all steps. No extra
files are being created on first run. Venv size: 522M without pyc, 552M with.

## Hypotheses Eliminated

### 1. PYC file creation — NOT the primary cause

- Run 3 (warm fs, no pyc) = 2.43s vs Run 2 (warm fs, pyc) = 1.11s
- PYC creation adds ~1.3s, not ~13s
- Confirms pyc is a minor factor

### 2. OS filesystem cache — NOT the cause

- **Run 5 (purged fs cache + no pyc) = 2.99s** — If cold fs cache caused the
  14s, this should also be ~14s. It's 3s.
- **Run 7 (fresh venv + cat-primed fs cache) = 13.75s** — If fs cache was the
  cause, pre-reading all files should fix it. It didn't.
- The fs cache is irrelevant to the 14s penalty.

### 3. Extra file creation on first run — NOT the cause

- Non-pyc file count is exactly 12,138 at every step
- No hidden files, caches, or configs are being generated

## What the Data Shows

The slowness is **specific to the first Python process in a freshly-installed
venv**. Key observations:

| Condition | Time | Notes |
|-----------|------|-------|
| Fresh install, first run | ~14s | Always slow |
| Same venv, purged fs cache, no pyc | ~3s | Fast! Same files, different venv "age" |
| Fresh install, cat-primed cache | ~14s | Still slow despite warm cache |
| Any subsequent run | ~1s | Fast once "broken in" |

The critical difference is between Run 5 and Run 7:
- **Run 5**: Same venv (already executed once), pyc deleted, fs cache purged → 3s
- **Run 7**: Fresh venv (never executed), fs cache primed → 14s
- Same file contents, same file count — but one has been executed before.

From the original `time` output (Run 1): `real 14.5s, user 2.6s, sys 0.5s`.
~11 seconds are unaccounted for — the process is **blocked waiting on
something external**, not doing CPU work.

## Leading Theory: macOS Code Signing / Gatekeeper Scanning

macOS scans new executable code (`.so`, `.dylib` files) the first time they're
loaded via `dlopen()`. This scan is performed by XProtect/Gatekeeper and the
result is cached per-inode. This fits every observation:

- **Fresh install → slow**: New `.so` files have never been scanned. macOS
  scans each one on first `dlopen()`. Polars alone has large native libraries.
- **Same venv after purge → fast**: The `.so` inodes haven't changed. macOS
  remembers they were already scanned.
- **Cat priming doesn't help**: `cat` reads file contents but doesn't trigger
  `dlopen()`, so macOS doesn't scan them as executable code.
- **~11s wall time with only ~3s CPU**: Process is blocked waiting on the
  security daemon, not doing computation.
- **Fresh venv = new inodes**: Even with identical content, `uv pip install`
  creates new files with new inodes, so macOS treats them as unseen.

## Next Steps to Confirm

1. **Count `.so`/`.dylib` files in the venv** and estimate scan overhead
2. **Test with `PYTHONDONTWRITEBYTECODE=1`** to isolate pyc from the equation
3. **Monitor `syspolicyd`** during first run: `log stream --predicate 'process == "syspolicyd"'`
4. **Test with SIP assessment disabled** (if possible in test env): `spctl --master-disable`
5. **Pre-import just polars** (largest native dep) to see if it accounts for most of the 14s
6. **Try `python -B -S -c "import polars"`** to skip site.py and pyc, isolating native load time

## Practical Implications

If confirmed, this is a macOS platform issue, not a buckaroo bug. Mitigations:
- Users only pay this cost once per install (not per kernel restart)
- Pre-warming: run a throwaway `python -c "import polars, buckaroo"` after install
- This may not affect Linux CI/servers at all (no Gatekeeper)
