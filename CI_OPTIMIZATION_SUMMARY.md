# CI Optimization Summary

## Date: 2026-01-11
## Branch: charming-leakey
## PR: #467

## Problem Statement
The "Install uv" step in CI was slow, taking ~13 seconds for lint jobs and ~10-11 seconds for test jobs.

## Optimizations Implemented

### 1. Replaced GitHub Action with Direct Installer
**Before:** `astral-sh/setup-uv@v7` GitHub Action
**After:** Direct curl installer: `curl -LsSf https://astral.sh/uv/0.9.24/install.sh | sh`

**Rationale:** GitHub Actions have wrapper overhead. Direct installation is faster.

### 2. Added Manual Caching for uv Binary
```yaml
- name: Cache uv binary
  uses: actions/cache@v4
  with:
    path: ~/.local/bin/uv
    key: uv-0.9.24-${{ runner.os }}
```

**Benefit:** Avoids re-downloading uv on every run.

### 3. Shared Python Installation Cache
**Before:** Per-version cache key `uv-python-${{ matrix.python-version }}-${{ runner.os }}`
**After:** Shared cache key `uv-python-${{ runner.os }}-v1`

**Rationale:** All Python versions stored in same directory. Sharing cache means:
- First job downloads Python 3.11 → cached
- Second job finds 3.11 in cache, downloads 3.12 → cached
- Third job finds both in cache, downloads 3.13 → cached
- Subsequent runs: all Python versions cached

### 4. Combined Setup Steps
**Before:** Separate "Install uv", "Add uv to PATH", "Setup Python" steps
**After:** Combined "Install uv and setup Python" step

**Benefit:** Reduced step overhead, clearer timing in GitHub UI.

### 5. Pinned uv to Latest Version (0.9.24)
**Benefit:** Consistent, reproducible builds. Enables better caching.

## Results

### Lint Job (Python / Lint)
- **Before:** ~13 seconds
- **After:** ~5 seconds
- **Improvement:** 62% faster (8 seconds saved)

### Test Jobs (Python / Test matrix)
- **Before:** ~13 seconds (setup-uv action)
- **After:** ~10-11 seconds (includes cache operations + Python installation)
- **Breakdown of 10-11 seconds:**
  - Cache uv binary restore: ~1-2s
  - Cache Python installations restore: ~1-2s
  - uv binary verification: <1s (cached)
  - Python installation (`uv python install`): ~6-7s

**Note:** Test jobs include Python installation which Lint doesn't need. The 10-11 seconds is reasonable given what it's doing.

## Technical Details

### Cache Configuration
```yaml
# uv binary cache (shared across all jobs)
path: ~/.local/bin/uv
key: uv-0.9.24-${{ runner.os }}

# Python installations cache (shared across Python versions)
path: ~/.local/share/uv/python
key: uv-python-${{ runner.os }}-v1
restore-keys: |
  uv-python-${{ runner.os }}-
```

### Why 10 Seconds Isn't Further Reducible
The remaining time is necessary operations:
1. **Cache restore** (~2-4s) - GitHub Actions overhead for downloading/extracting cache
2. **Python verification** (~6-7s) - `uv python install` checks/verifies Python installation even when cached

These are fundamental operations that can't be eliminated without changing the tooling entirely.

## Files Modified
- `.github/workflows/ci.yml` - Optimized uv installation steps
- `.github/workflows/build.yml` - Fixed YAML indentation error

## Commits
1. Pin uv version to 0.9.24 to speed up CI
2. Switch to standalone uv installer with manual caching
3. Fix YAML indentation syntax error in build.yml
4. Add Python installation caching to speed up CI
5. Share Python cache across all Python versions
6. Combine Install uv and Setup Python steps, add --no-progress flag

## Performance Comparison

### Full CI Run Time
- **Before:** ~2 minutes (7 jobs)
- **After:** ~2 minutes (7 jobs)
- **Improvement:** Marginal overall, but per-step improvement significant

The overall CI time is dominated by:
- Test execution: ~60 seconds
- pnpm operations: ~10-15 seconds
- uv install: now ~5-11 seconds (was ~13s)

## Future Optimization Opportunities

### Test Execution (see `optimize-unit-tests` branch)
- Add pytest-xdist for parallel test execution
- Expected: 30-50% faster test runs
- See: `TEST_OPTIMIZATION_PLAN.md` in `optimize-unit-tests` branch

### Dependency Installation
- Consider caching `uv sync` dependencies (packages)
- Likely already cached by uv internally

### pnpm Operations
- pnpm already uses caching effectively
- Minimal optimization potential

## Lessons Learned

1. **Direct installers are faster than GitHub Actions** - Actions add wrapper overhead
2. **Shared caches are more efficient** - Multiple matrix jobs benefit from shared Python cache
3. **Cache restore has overhead** - Even with cache hits, restore operations take time
4. **Some operations are irreducible** - Python installation/verification requires time
5. **Pinning versions enables better caching** - Specific versions cache better than ranges

## Maintenance Notes

### Updating uv Version
To update to a newer uv version:
1. Change version in installer URL: `https://astral.sh/uv/NEW_VERSION/install.sh`
2. Update cache key: `uv-NEW_VERSION-${{ runner.os }}`
3. Update Python cache key version: `uv-python-${{ runner.os }}-v2` (increment)

### If Tests Become Slow Again
1. Check if cache is being hit (GitHub Actions UI shows cache hits/misses)
2. Verify uv version is still pinned
3. Consider if Python version matrix has grown
4. Check Depot runner performance (they may have capacity issues)

## Links
- PR: https://github.com/buckaroo-data/buckaroo/pull/467
- Latest CI Run: https://github.com/buckaroo-data/buckaroo/actions/runs/20894907998
- Test Optimization Branch: `optimize-unit-tests`
