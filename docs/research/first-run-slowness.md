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

1. `uv pip install` writes `.so` files — by default as APFS clones (new inodes)
2. Python imports trigger `dlopen()` on native extensions
3. macOS syspolicyd intercepts each `dlopen()` of an unseen inode
4. Since pip packages aren't code-signed, syspolicyd logs `errSecCSUnsigned`
   and performs full assessment
5. Results are cached per-inode — subsequent loads are instant
6. A fresh install creates new inodes, resetting the cache

### The uv link-mode factor

uv supports four `--link-mode` values: `clone` (default), `copy`, `hardlink`,
`symlink`. On macOS APFS, the default `clone` uses `clonefile()` — this shares
underlying storage blocks but **creates a new inode** for each file. Since
syspolicyd caches per-inode, every reinstall with clone mode triggers a full
rescan of all `.so` files.

**Hardlink mode preserves inodes.** With `--link-mode hardlink`, the venv's
`.so` files are hardlinks to uv's global cache. Deleting and recreating the
venv reuses the same cache entry and the same inodes — so syspolicyd sees them
as already scanned.

Verified experimentally:

```
Link mode   Reinstall inode matches original?   syspolicyd rescan?
clone       NO  (new inode each time)            YES — full scan every install
hardlink    YES (same inode as cache)             NO — cached as already scanned
```

This means `UV_LINK_MODE=hardlink` (or `--link-mode hardlink`) eliminates the
~12s syspolicyd overhead on all reinstalls after the first, as long as the uv
cache is warm.

## Related Issues & Prior Art

### Two overlapping problems in uv

1. **Bytecode compilation** — uv doesn't compile `.pyc` files by default
   (unlike pip). This accounts for ~1.3s of first-run overhead. Fix:
   `uv pip install --compile-bytecode`.
   - [uv #9666](https://github.com/astral-sh/uv/issues/9666) — first
     `import pandas` ~19.7s vs ~0.4s, attributed to missing bytecache.
   - [uv #12904](https://github.com/astral-sh/uv/issues/12904) — even with
     `--compile-bytecode`, first run still slow, suggesting additional overhead.

2. **macOS Gatekeeper / code signing** — unsigned binaries from
   python-build-standalone get rejected or scanned by syspolicyd.
   - [uv #16726](https://github.com/astral-sh/uv/issues/16726) — SIGKILL on
     first execution due to `com.apple.provenance` xattr + adhoc signing.
   - [uv #16003](https://github.com/astral-sh/uv/issues/16003) — same issue,
     workaround: `codesign --force -s - <binary>`.
   - [uv PR #18280](https://github.com/astral-sh/uv/pull/18280) — proper
     Apple Developer ID signing of release binaries (in progress).

### macOS syspolicyd scanning behavior

- syspolicyd uses YARA rules to scan executables and linked libraries on
  first launch ([lapcatsoftware.com, 2024](https://lapcatsoftware.com/articles/2024/2/3.html)).
- Results cached per-inode; new files (fresh install) reset the cache.
- `spctl --master-disable` does NOT help — syspolicyd still performs checks.
- Adding your terminal to Developer Tools in System Settings bypasses the
  checks ([HN discussion](https://news.ycombinator.com/item?id=23273247)).

### What's novel in our findings

No existing issue documents syspolicyd scanning individual `.so` extension
modules within Python site-packages at `dlopen()` time. The known scanning
behavior targets executables and their statically-linked libraries. Our
syspolicyd log capture (~3,300 entries during first import) is direct evidence
that `dlopen()` of `.so` files in site-packages also triggers the scan.

## Practical Implications

- **Not a buckaroo bug.** Any Python environment with native extensions
  (polars, numpy, pandas, etc.) will have this on macOS.
- **One-time cost.** Only happens once per install, not per kernel restart.
- **Linux unaffected.** No Gatekeeper on Linux — CI/servers won't see this.

### Workarounds

| Workaround | Effect |
|---|---|
| `UV_LINK_MODE=hardlink` or `--link-mode hardlink` | Preserves inodes across reinstalls — syspolicyd only scans once. **Best option for uv users.** |
| Add terminal to Developer Tools (System Settings > Privacy & Security) | Bypasses syspolicyd checks entirely. Best option if you can change system settings. |
| `uv pip install --compile-bytecode` | Eliminates ~1.3s pyc compilation overhead (not the ~12s syspolicyd part) |
| `python -c "import polars, buckaroo"` after install | Pre-warms syspolicyd cache before opening JupyterLab |
| `codesign --force -s - <binary>` | Fixes SIGKILL; must be done per-binary after every install |

## Test Scripts

- `scripts/test_syspolicyd.sh` — creates a fresh venv, installs packages,
  times imports while monitoring syspolicyd, and prints a summary.
- `scripts/test_hardlink_vs_clone.sh` — compares clone (default) vs hardlink
  link modes across reinstalls, tracking inodes and syspolicyd activity to
  verify that hardlink mode avoids rescans.
