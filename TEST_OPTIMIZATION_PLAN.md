# Unit Test Optimization Plan

## Date: 2026-01-11
## Branch: optimize-unit-tests

## Current Situation

The unit tests, particularly those using `mp_timeout` decorator, take significant time due to:
1. Sleep operations in timeout tests
2. Sequential test execution
3. Multiprocessing overhead

### Current Test Timing (from CI)
- Total test time: ~60-63 seconds per Python version
- mp_timeout tests use `SPEEDUP_FACTOR = 30` already implemented
- Tests run sequentially

## Investigation Results

### Files Analyzed
- `tests/unit/file_cache/mp_timeout_decorator_test.py` - Main timeout decorator tests
- `tests/unit/file_cache/mp_test_utils.py` - Test utilities with `fast_sleep()` function

### Current Optimizations Already in Place
1. **SPEEDUP_FACTOR = 30**: Tests already use `fast_sleep()` which divides sleep times by 30
2. **Environment-specific timeouts**: Different TIMEOUT values for local vs CI
   - LOCAL_TIMEOUT = 0.8s
   - CI_TIMEOUT = 1.0s

### Test Structure
The mp_timeout tests include:
- `test_mp_timeout_pass()` - Basic functionality (fast)
- `test_mp_timeout_fail()` - Timeout test (requires actual timeout, ~1s)
- `test_mp_polars_timeout()` - Polars timeout test (~1s)
- `test_mp_fail_then_normal()` - Sequential timeout then normal (~1s)
- Multiple edge case tests (some skipped)

## Proposed Optimizations

### 1. Parallel Test Execution with pytest-xdist ⭐ RECOMMENDED
**Impact**: High (30-50% faster on multi-core machines)
**Effort**: Low
**Risk**: Low

```bash
# Install pytest-xdist
uv add --dev pytest-xdist

# Run tests in parallel (auto-detect CPUs)
pytest -n auto

# Or specific number of workers
pytest -n 4
```

**Benefits:**
- Tests run in parallel across CPU cores
- Works with existing test structure
- No code changes needed
- Compatible with multiprocessing tests

**Configuration** (add to pyproject.toml):
```toml
[tool.pytest.ini_options]
addopts = "-n auto"  # Enable by default in CI
```

### 2. Further Reduce Sleep Times (Marginal)
**Impact**: Low (tests already use SPEEDUP_FACTOR=30)
**Effort**: Low
**Risk**: Medium (might cause flaky tests)

Current: `SPEEDUP_FACTOR = 30`
Proposed: `SPEEDUP_FACTOR = 50` or `100`

**Risks:**
- Tests might become flaky on slower CI runners
- Timeout tests need actual timeouts to verify functionality
- Already near the practical limit

### 3. Mark Slow Tests for Conditional Execution
**Impact**: Medium (can skip slow tests in development)
**Effort**: Low
**Risk**: Low

```python
@pytest.mark.slow
def test_mp_timeout_fail():
    ...

# Run without slow tests
pytest -m "not slow"

# Run only slow tests
pytest -m slow
```

### 4. Optimize Multiprocessing Overhead
**Impact**: Low-Medium
**Effort**: High
**Risk**: Medium

Ideas:
- Reuse multiprocessing pools across tests
- Use threading instead of multiprocessing where possible
- Reduce subprocess startup overhead

**Not recommended**: High complexity for limited gains

## Recommended Implementation Plan

### Phase 1: Quick Win (5 minutes) ✅
1. Add pytest-xdist to dev dependencies
2. Update CI to use `pytest -n auto`
3. Test locally and in CI

### Phase 2: Marking & Organization (15 minutes)
1. Mark genuinely slow tests with `@pytest.mark.slow`
2. Add pytest markers configuration
3. Document test running options in README

### Phase 3: Benchmark & Document (10 minutes)
1. Run tests with and without parallelization
2. Document actual speedup achieved
3. Update this document with results

## Expected Results

**Before:**
- Sequential execution: ~60s per Python version
- 3 Python versions: ~180s total

**After (with pytest-xdist on 4 cores):**
- Parallel execution: ~30-40s per Python version
- 3 Python versions in parallel: ~40-50s total
- **Overall speedup: 60-70% faster**

## Commands to Test

```bash
# Baseline timing
time uv run pytest tests/unit --durations=10

# With parallelization
time uv run pytest tests/unit -n auto --durations=10

# Skip slow tests (development)
pytest tests/unit -m "not slow"

# Only slow tests (verification)
pytest tests/unit -m slow
```

## Files to Modify

1. `pyproject.toml` - Add pytest-xdist, configure pytest
2. `.github/workflows/ci.yml` - Update pytest command to use `-n auto`
3. `tests/unit/file_cache/mp_timeout_decorator_test.py` - Add @pytest.mark.slow to timeout tests
4. `README.md` or `CONTRIBUTING.md` - Document test running options

## Risks & Mitigations

### Risk 1: Parallel tests interfere with multiprocessing tests
**Mitigation**: pytest-xdist is designed to handle this, uses separate processes
**Likelihood**: Low

### Risk 2: Flaky tests on slower CI runners
**Mitigation**: Keep current SPEEDUP_FACTOR, don't reduce further
**Likelihood**: Low

### Risk 3: Cache/file conflicts in parallel execution
**Mitigation**: Use pytest fixtures with temp directories (already in place)
**Likelihood**: Very Low

## Next Steps

1. Implement Phase 1 (pytest-xdist)
2. Run CI to validate
3. Measure actual speedup
4. Document results
5. Consider Phase 2 if more optimization needed

## References

- pytest-xdist: https://github.com/pytest-dev/pytest-xdist
- pytest markers: https://docs.pytest.org/en/stable/example/markers.html
- Current test code: `tests/unit/file_cache/mp_timeout_decorator_test.py`
