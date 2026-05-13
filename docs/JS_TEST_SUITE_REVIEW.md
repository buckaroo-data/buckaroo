# JS Test Suite and Coverage Review

_Date: 2026-02-24_

## Scope reviewed

- Package: `packages/buckaroo-js-core`
- Unit test runner/configuration: Jest (`package.json`, `jest.config.ts`)
- Browser/integration test inventory: Playwright specs under `pw-tests/`
- Coverage source: `pnpm test -- --coverage`

## Current test suite snapshot

- Jest is configured with `testMatch` as:
  - `!**/*.spec.ts`
  - `**/*.test.ts`
- Existing test files in `src/`:
  - `OperationsList.test.tsx`
  - `Operations.test.tsx`
  - `DFViewerParts/gridUtils.test.ts`
  - `DFViewerParts/SmartRowCache.test.ts`
- Result: only **2 of 4** unit test files currently match Jest config (the `.test.ts` files), while the two `.test.tsx` files are silently excluded.
- Playwright has 23 `*.spec.ts` files under `pw-tests/`, giving broad E2E/integration surface coverage.

## Coverage results (from Jest run)

Overall (Jest unit tests):

- Statements: **54.85%**
- Branches: **29.83%**
- Functions: **37.01%**
- Lines: **53.89%**

Notable by-module highlights:

- Strong:
  - `SmartRowCache.ts`: ~91.5% statements / ~81.25% branches
  - `DFWhole.ts` and `baked_data/colorMap.ts`: 100%
- Weak / high-risk:
  - `DFViewerInfinite.tsx`: ~12.66% statements
  - `ChartCell.tsx`: ~21.81% statements
  - `HistogramCell.tsx`: ~17.94% statements
  - `Styler.tsx`: ~11.26% statements
  - `Displayer.ts`: ~37.31% statements
  - `useColorScheme.ts`: ~33.33% statements

## Key findings

1. **Jest glob likely excludes intended React tests (`.test.tsx`).**
   - This is the highest-value immediate fix because coverage and confidence are currently understated for component behavior already having test files.

2. **Coverage is concentrated in utility/cache logic, not rendering-heavy components.**
   - `SmartRowCache` and `gridUtils` are tested reasonably well; UI-heavy modules that drive user behavior are mostly untested at unit level.

3. **Branch coverage is the main gap (29.83%).**
   - Suggests limited exercise of error paths, conditional rendering, and edge-case prop/state combinations.

4. **E2E inventory is large, but unit coverage is narrow.**
   - Many Playwright specs exist; however, they do not replace fast deterministic unit-level tests for view/model boundary logic.

## Suggested improvement plan (for follow-up implementation)

### Priority 0 (quick wins)

1. Update Jest `testMatch` to include `.test.tsx` (and optionally `.test.jsx/.test.js` if desired).
2. Add/enable coverage thresholds in Jest (start pragmatic, raise gradually), e.g.:
   - global lines/stmts ≥ 60
   - branch ≥ 40
3. Add `test:coverage` script for CI consistency.

### Priority 1 (high-impact module tests)

1. Add focused RTL tests for:
   - `DFViewerInfinite.tsx` (loading transitions, pagination/infinite callbacks, empty/error states)
   - `HistogramCell.tsx` and `ChartCell.tsx` (data-shape handling, fallback rendering)
   - `Styler.tsx` (style mapping edge cases)
2. Add branch-focused tests to `Displayer.ts` for display-mode switching and malformed payload handling.

### Priority 2 (suite structure + maintainability)

1. Split Jest projects/config by test type (pure unit vs component DOM tests) to keep feedback fast.
2. Reduce console noise in tests (`console.log` in core classes) with explicit debug flags/mocks to improve signal.
3. Map Playwright specs to explicit risk areas (smoke/regression/visual/theme) and run tiers in CI (smoke on PR, full nightly).

## Suggested PR checklist for implementation agent

- [ ] Fix Jest `testMatch` glob(s) and verify `.test.tsx` suites execute.
- [ ] Add `test:coverage` script + initial thresholds.
- [ ] Add at least one new test file targeting one low-coverage module (`DFViewerInfinite.tsx` preferred).
- [ ] Re-run coverage and compare deltas.
- [ ] Document CI strategy for Jest vs Playwright lanes.
