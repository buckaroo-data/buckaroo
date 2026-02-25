# Buckaroo Infinite Testing Improvement Plan

Snapshot date: 2026-02-25

Input documents:
- `docs/research/ag-grid-testing-approach-research.md`
- `docs/research/buckaroo-infinite-testing-assessment.md`

## 1) Goals

1. Prevent stale or out-of-order datasource responses from ever winning the UI.
2. Increase confidence in `outside_df_params` + infinite row model behavior under rapid state changes.
3. Add CI gates that catch correctness and regression issues early, with low flake.
4. Follow AG Grid's proven split: deterministic behavior tests first, browser-realistic lanes second.

## 2) Testing strategy to adopt (from AG Grid research)

1. Build a deterministic behavior lane that disables non-essential UI variability and validates state transitions.
2. Keep browser E2E for integration realism, especially for async races and user-visible correctness.
3. Add focused performance monitoring for high-risk update paths, run on schedule (not just on PR).
4. Gate merges on fast correctness checks; run heavier perf suites on nightly/cron.

## 3) Highest-priority coverage gaps to close

1. No explicit stale-response ordering assertions (`A(slow) -> B(fast) -> A late`).
2. No rapid multi-toggle stress tests while requests are in flight.
3. No sort/filter + outside param interaction tests in infinite mode.
4. No callback lifecycle tests for `KeyAwareSmartRowCache.waitingCallbacks`.
5. No dedicated regression/perf signal for repeated outside-param toggles.

## 4) Workstreams

### Workstream A: Deterministic unit tests for callback ordering and cache lifecycle (P0)

Files:
- `packages/buckaroo-js-core/src/components/DFViewerParts/SmartRowCache.test.ts`
- `packages/buckaroo-js-core/src/components/DFViewerParts/gridUtils.test.ts`

Add tests for:
1. `getRequestRows` with two overlapping requests where responses arrive out of order; ensure only matching callback key resolves each waiter.
2. Late response for previous source key does not invoke active key waiter.
3. `addErrorResponse` removes waiter and does not leak callback entries.
4. Repeated same-key requests do not leave duplicate waiters after success/failure.
5. Boundary behavior where `resp.data.length < requested segment` clamps correctly.

Acceptance criteria:
1. New tests explicitly assert waiter map cleanup and callback invocation counts.
2. No test relies on real timeouts; use controlled fake request dispatchers.

### Workstream B: Component-level tests for `DFViewerInfinite` remount/context semantics (P0)

Files:
- `packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerInfinite.test.tsx`

Add tests for:
1. Changing `outside_df_params` causes distinct `AgGridReact` key and context values.
2. `getRowId` output changes with `outside_df_params` for same row index.
3. DataSource mode keeps infinite row model options (`maxConcurrentDatasourceRequests`, cache settings) intact after param changes.
4. Sort-change callback behavior still ensures row 0 visible after outside param toggles.

Acceptance criteria:
1. Assertions target public props/behavior, not internals.
2. Tests stay deterministic with mocked `AgGridReact`.

### Workstream C: Playwright race matrix for outside-params scenarios (P0)

Files:
- `packages/buckaroo-js-core/pw-tests/outside-params.spec.ts`
- `packages/buckaroo-js-core/src/stories/OutsideParamsInconsistency.stories.tsx`

Extend Storybook scenario controls:
1. Add variants with asymmetric delays (A slow, B fast; B slow, A fast).
2. Add rapid toggle helper UI button (e.g., toggles 3-5 times quickly).
3. Add optional sort preset in story to combine with toggle behavior.

Add Playwright tests:
1. `A(slow) -> B(fast) -> assert B remains after A completes late`.
2. Rapid toggle stress (`A->B->A->B`) with in-flight requests; final visible state matches last toggle.
3. Sort then toggle then sort again; visible rows and sort indicator align with active source.
4. Retry wrapper for initial grid readiness only; no broad retries around core assertions.

Acceptance criteria:
1. Each test validates both row values and param indicator text.
2. Suite demonstrates stability across repeated local runs.

### Workstream D: Lightweight performance regression lane for this path (P1)

Files:
- `packages/buckaroo-js-core/pw-tests/` (new perf-focused spec or benchmark helper)
- CI workflow files (project-specific workflow directory)

Add:
1. A scripted scenario: repeated outside-param toggles + scroll + sort over fixed data volume.
2. Track p95/p99 time to first correct row after toggle.
3. Store baseline artifact and compare drift on nightly run.

Acceptance criteria:
1. Performance job is non-blocking on PRs, blocking only on clear severe regression thresholds after baseline matures.
2. Report includes run metadata (browser, workers, dataset size).

### Workstream E: CI shaping and quality gates (P0/P1)

Add or update CI targets:
1. PR required checks:
   - Unit/component lane (Workstreams A+B)
   - Fast Playwright correctness subset (critical outside-param races)
2. Nightly checks:
   - Full race matrix
   - Performance lane from Workstream D
3. Flake control:
   - Single worker for race-sensitive specs
   - Explicit deterministic test dataset and delays

Acceptance criteria:
1. Clear required vs informational checks in CI.
2. Failures identify scenario names directly (no generic timeout-only failures).

## 5) Delivery sequence

### Phase 1 (week 1): Close correctness blind spots
1. Implement Workstream A.
2. Implement Workstream B.
3. Add first P0 Playwright stale-response test from Workstream C.

Exit gate:
1. Repro bug class (`outside_df_params` stale display) has at least one failing test before fix and passing test after fix.

### Phase 2 (week 2): Expand race matrix
1. Implement remaining Workstream C scenarios.
2. Stabilize runtime and flake behavior.
3. Wire PR CI subset + nightly full matrix.

Exit gate:
1. Rapid toggle and sort/toggle race cases covered in CI.

### Phase 3 (week 3): Add performance signal
1. Implement Workstream D.
2. Capture baseline for at least several nightly runs.
3. Tune thresholds, then enforce regression policy.

Exit gate:
1. Nightly perf trend is visible and actionable.

## 6) Definition of done

1. All five known deficiency areas in `buckaroo-infinite-testing-assessment.md` are covered by explicit tests.
2. PR pipeline blocks on deterministic correctness tests for outside-param/infinite synchronization.
3. Nightly pipeline reports perf drift for repeated outside-param flows.
4. Test docs include "scenario -> expected invariant" mapping for maintainability.

## 7) Risks and mitigations

1. Risk: Flaky async tests.
   Mitigation: deterministic delays, fixed workers, strict polling on explicit row content and state labels.
2. Risk: Overfitting to Storybook-only behavior.
   Mitigation: keep component/unit assertions in parallel with E2E.
3. Risk: Slow PR feedback.
   Mitigation: keep PR suite minimal and move broad matrix/perf to nightly runs.
