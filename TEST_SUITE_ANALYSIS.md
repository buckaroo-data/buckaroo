# Buckaroo Test Suite Analysis & Recommendations

## Executive Summary

- **Total Tests**: 323 passing, 5 skipped
- **Overall Coverage**: 71% (1894 lines missing out of 6616 total)
- **Test Files**: 56+ test files across unit, integration, and E2E tests

## Coverage by Module

### Modules with Zero Coverage (Priority 1)

| Module | Lines | Description |
|--------|-------|-------------|
| `buckaroo/file_cache/bisector.py` | 316 | Bisection algorithm for isolating problematic data |
| `buckaroo/contrib/buckaroo_pandera.py` | 78 | Pandera integration (requires optional dep) |
| `buckaroo/customizations/order_columns.py` | 66 | Column ordering logic |
| `buckaroo/file_cache/threaded_executor.py` | 46 | Threaded execution for file cache |
| `buckaroo/solara_buckaroo.py` | 35 | Solara framework integration |
| `buckaroo/marimo_utils.py` | 31 | Marimo notebook integration |
| `buckaroo/trait_utils.py` | 23 | Trait/traitlets utilities |
| `buckaroo/customizations/analysis_utils.py` | 12 | Analysis helper utilities |
| `buckaroo/widget_class_utils.py` | 11 | Widget class utilities |

### Modules with Low Coverage (<50%)

| Module | Coverage | Missing Lines | Notes |
|--------|----------|---------------|-------|
| `buckaroo/__init__.py` | 30% | 53/76 | Entry point, import guards |
| `buckaroo/mp_timeout_decorator.py` | 36% | 91/142 | Multiprocessing timeout |
| `buckaroo/extension_utils.py` | 38% | 18/29 | Extension utilities |
| `buckaroo/widget_utils.py` | 46% | 64/118 | Widget utilities |
| `buckaroo/pandas_commands.py` | 49% | 185/360 | Many command handlers |
| `buckaroo/geopandas_buckaroo.py` | 0% | 59/59 | GeoPandas integration |

### Modules with Good Coverage (>90%)

| Module | Coverage |
|--------|----------|
| `buckaroo/customizations/pandas_cleaning_commands.py` | 100% |
| `buckaroo/file_cache/sqlite_log.py` | 100% |
| `buckaroo/jlisp/configure_utils.py` | 100% |
| `buckaroo/dataflow/abc_dataflow.py` | 100% |
| `buckaroo/auto_clean/heuristic_lang.py` | 97% |
| `buckaroo/customizations/styling.py` | 97% |
| `buckaroo/file_cache/cache_utils.py` | 98% |
| `buckaroo/dataflow/dataflow.py` | 96% |
| `buckaroo/dataflow/styling_core.py` | 95% |
| `buckaroo/customizations/histogram.py` | 95% |

## Recommendations

### 1. High-Priority: Add Tests for Zero-Coverage Modules

#### `buckaroo/file_cache/bisector.py` (316 lines)
This module implements critical bisection logic for isolating problematic data. Tests exist in `bisector_test.py` but require the optional `pl_series_hash` dependency.

**Recommendation**: Create a separate test file that doesn't require `pl_series_hash`:
```python
# tests/unit/file_cache/bisector_core_test.py
# Test core bisection logic with mock executors
```

#### `buckaroo/customizations/order_columns.py` (66 lines)
Column ordering is user-facing functionality that should be tested.

**Recommendation**: Add `tests/unit/customizations/order_columns_test.py`

#### `buckaroo/file_cache/threaded_executor.py` (46 lines)
Alternative executor implementation without tests.

**Recommendation**: Add `tests/unit/file_cache/threaded_executor_test.py`

### 2. Medium-Priority: Improve Low-Coverage Modules

#### `buckaroo/customizations/pandas_commands.py` (49% coverage)
Many command handlers are untested. The module has 185 missing lines.

**Recommendation**: Expand `tests/unit/commands/` with tests for:
- `sort_index`, `query`, `round`, `drop_duplicates` commands
- Error handling paths in existing commands

#### `buckaroo/widget_utils.py` (46% coverage)
Widget utilities have significant untested code paths.

**Recommendation**: Add `tests/unit/widget_utils_test.py`

#### `buckaroo/mp_timeout_decorator.py` (36% coverage)
Many execution paths untested, particularly around process management.

**Recommendation**: Several tests are skipped as "diagnostic tests". Consider:
- Enabling more tests in non-CI environments
- Adding tests for the pickling/unpickling paths

### 3. Test Consolidation Opportunities

#### Similar Test Patterns in `file_cache/`

The following test files have overlapping setup code:
- `mp_timeout_decorator_test.py`
- `mp_test_utils.py`
- `basic_file_cache_test.py`

**Recommendation**: Create shared test fixtures in `conftest.py`:
```python
# tests/unit/file_cache/conftest.py
@pytest.fixture
def mp_timeout_config():
    return {"timeout": 0.8 if IS_LOCAL else 1.0}
```

#### Duplicate DataFrame Setup

Multiple test files create similar test DataFrames:
- `command_test.py`
- `cleaning_command2_test.py`
- `auto_clean_test.py`

**Recommendation**: Create a shared test data module:
```python
# tests/fixtures/test_dataframes.py
DIRTY_DF = pd.DataFrame({...})
DT_STRS = ['2024-06-24 09:32:00-04:00', ...]
```

### 4. Test Organization Improvements

#### Current Structure Issues

1. **Inconsistent naming**: Mix of `*_test.py` and `test_*.py` patterns
2. **Deep nesting**: Some tests are 3+ levels deep
3. **Missing `__init__.py`**: Some test directories lack proper Python package markers

**Recommendation**: Standardize on `test_*.py` naming convention (pytest default)

#### Suggested New Test Files

| File | Purpose |
|------|---------|
| `tests/unit/test_widget_utils.py` | Widget utility functions |
| `tests/unit/test_trait_utils.py` | Trait utilities |
| `tests/unit/customizations/test_order_columns.py` | Column ordering |
| `tests/unit/file_cache/test_threaded_executor.py` | Threaded execution |
| `tests/unit/integrations/test_marimo.py` | Marimo integration (mock-based) |
| `tests/unit/integrations/test_solara.py` | Solara integration (mock-based) |

### 5. Test Quality Improvements

#### Deprecation Warnings
Several tests trigger deprecation warnings:
- `is_categorical_dtype` usage in `auto_clean.py`
- `fillna` downcasting in `all_transforms.py`

**Recommendation**: Fix the underlying code or add `filterwarnings` markers

#### Resource Warnings
Multiple tests leave SQLite connections unclosed:
- `cache_utils_test.py`
- `mp_timeout_decorator_test.py`

**Recommendation**: Add proper teardown fixtures or context managers

#### Flaky Tests
Several tests are marked as skipped due to flakiness:
- `test_mp_crash_exit` - subprocess crash detection timing
- `test_mp_polars_crash` - Polars crash detection timing
- `test_sys_exit_is_execution_failed` - sys.exit handling

**Recommendation**: Either:
1. Mark with `@pytest.mark.flaky` and use pytest-rerunfailures
2. Refactor to be deterministic using mocks
3. Move to a separate "diagnostic" test suite

### 6. CI/CD Recommendations

#### Optional Dependency Testing
Tests for optional integrations fail when dependencies aren't installed:
- `pandera` tests
- `pl_series_hash` tests

**Recommendation**: Use pytest markers and CI matrix:
```python
@pytest.mark.requires_pandera
def test_pandera_integration():
    ...
```

```yaml
# CI matrix
- python: 3.12
  extras: "pandera"
```

#### Coverage Thresholds
Current overall coverage is 71%.

**Recommendation**: Set minimum thresholds:
```ini
# pyproject.toml
[tool.coverage.report]
fail_under = 70
```

## Action Items Summary

| Priority | Item | Effort |
|----------|------|--------|
| High | Add tests for `order_columns.py` | Small |
| High | Add tests for `threaded_executor.py` | Small |
| High | Add mock-based tests for `bisector.py` | Medium |
| Medium | Improve `pandas_commands.py` coverage | Large |
| Medium | Add tests for `widget_utils.py` | Medium |
| Medium | Fix deprecation warnings | Small |
| Medium | Fix resource warnings (unclosed DBs) | Small |
| Low | Consolidate test fixtures | Medium |
| Low | Standardize test naming | Small |
| Low | Add coverage thresholds to CI | Small |

## Appendix: Full Coverage Report

```
Overall: 71% (1894/6616 lines missing)

Zero Coverage:
- buckaroo/file_cache/bisector.py: 0% (316 lines)
- buckaroo/contrib/buckaroo_pandera.py: 0% (78 lines)
- buckaroo/customizations/order_columns.py: 0% (66 lines)
- buckaroo/geopandas_buckaroo.py: 0% (59 lines)
- buckaroo/file_cache/threaded_executor.py: 0% (46 lines)
- buckaroo/solara_buckaroo.py: 0% (35 lines)
- buckaroo/marimo_utils.py: 0% (31 lines)
- buckaroo/trait_utils.py: 0% (23 lines)
- buckaroo/customizations/analysis_utils.py: 0% (12 lines)
- buckaroo/widget_class_utils.py: 0% (11 lines)
```

---
*Generated: 2026-01-28*
