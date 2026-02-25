# Buckaroo Infinite Testing Improvement Plan

Last updated: 2026-02-25

## 1) Goals

1. Prevent stale or out-of-order datasource responses from ever winning the UI.
2. Increase confidence in `outside_df_params` + infinite row model behavior under rapid state changes.
3. Add CI gates that catch correctness and regression issues early, with low flake.
4. Follow AG Grid's proven split: deterministic behavior tests first, browser-realistic lanes second.

## 2) Testing strategy

1. **Deterministic behavior lane** — unit/component tests that disable non-essential UI variability and validate state transitions. Fast, no browser needed.
2. **Browser E2E lane** — Playwright against Storybook for integration realism, especially async races and user-visible correctness.
3. **Performance monitoring** — focused on high-risk update paths, run on schedule (not per-PR).
4. **CI gating** — merge on fast correctness checks; run heavier perf suites nightly.

## 3) Coverage gaps to close

These are the specific gaps that remain after existing test work:

1. **No out-of-order response test** — need `A(slow) -> B(fast) -> A arrives late` assertion that only B's callback fires.
2. **No stale-key rejection test** — need assertion that a late response for a previous `sourceName+sort` key does not invoke the active-key waiter.
3. **No rapid multi-toggle stress tests** while requests are in-flight.
4. **No sort/filter + outside-param interaction tests** in infinite mode.
5. **No `getDs` unit test** — the AG Grid datasource factory connecting `outside_df_params` to `sourceName` is untested.
6. **No remount assertion** — no test that changing `outside_df_params` produces a new `key` on `AgGridReact`.
7. **No `getRowId` namespace test** — no test that `getRowId` output changes with `outside_df_params` for the same row index.
8. **No performance regression signal** for repeated outside-param toggles.

## 4) Workstreams

### Workstream A: Unit tests — callback ordering and cache lifecycle (P0)

Files:
- `packages/buckaroo-js-core/src/components/DFViewerParts/SmartRowCache.test.ts` (exists — extend)
- `packages/buckaroo-js-core/src/components/DFViewerParts/gridUtils.test.ts` (exists — extend)

**Existing coverage:** `SmartRowCache` and `KeyAwareSmartRowCache` basics (segment math, trim, short-data boundary, sentinel-length clamping). `gridUtils` covers `dfToAgrid`, `extractPinnedRows`, `extractSDFT`, `getHeightStyle2`, `getAutoSize`.

**Still needed:**
1. `getRequestRows` with two overlapping requests where responses arrive out of order — assert only the matching callback key resolves each waiter.
2. Late response for a previous source key does not invoke the active-key waiter.
3. `addErrorResponse` removes waiter and does not leak callback entries.
4. Repeated same-key requests do not leave duplicate waiters after success/failure.
5. `getDs` unit test — mock `KeyAwareSmartRowCache`, verify that datasource reads `outside_df_params` from AG Grid context and passes it as `sourceName`.

Acceptance criteria:
- New tests assert waiter map cleanup and callback invocation counts via `jest.fn()`.
- No test relies on real timeouts; use controlled fake request dispatchers.

### Workstream B: Component tests — `DFViewerInfinite` remount/context semantics (P0)

File:
- `packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerInfinite.test.tsx` (exists — extend)

**Existing coverage:** error display, Raw mode rowData, DataSource mode rowModelType, pinned rows.

**Still needed:**
1. Changing `outside_df_params` causes a distinct `key` prop on the rendered `AgGridReact` (confirms remount).
2. `getRowId` output changes with `outside_df_params` for the same row index.
3. DataSource mode preserves infinite row model options (`maxConcurrentDatasourceRequests`, cache settings) after param changes.
4. Sort-change handler calls `ensureIndexVisible(0)` after outside-param toggle.

Acceptance criteria:
- Assertions target public props/behavior, not internals.
- Tests stay deterministic with mocked `AgGridReact`.

### Workstream C: Playwright race matrix for outside-params scenarios (P0)

Files:
- `packages/buckaroo-js-core/pw-tests/outside-params.spec.ts` (exists — 2 tests, extend)
- `packages/buckaroo-js-core/src/stories/OutsideParamsInconsistency.stories.tsx` (exists — 2 variants, extend)

**Existing coverage:** `Primary` story (delay=0) and `WithDelay` story (delay=150ms), basic Playwright assertions for each.

**Story extensions needed:**
1. Asymmetric delay variants (A slow / B fast, B slow / A fast).
2. Rapid toggle helper button (toggles 3–5 times quickly).
3. Optional sort preset to combine with toggle behavior.

**Playwright tests needed:**
1. `A(slow) -> B(fast)` — assert B rows remain visible after A's late response arrives.
2. Rapid toggle stress (`A->B->A->B`) with in-flight requests — final visible state matches last toggle.
3. Sort then toggle then sort again — visible rows and sort indicator align with the active source.
4. Retry wrapper for initial grid readiness only; no broad retries around core assertions.

Acceptance criteria:
- Each test validates both row cell values and param indicator text.
- Suite stable across 5+ consecutive local runs.

### Workstream D: Performance regression lane (P1)

Files:
- `packages/buckaroo-js-core/pw-tests/outside-params-perf.spec.ts` (new)
- `.github/workflows/checks.yml` (add nightly cron job)

Add:
1. Scripted scenario: repeated outside-param toggles + scroll + sort over a fixed data volume.
2. Measure p95/p99 time-to-first-correct-row after toggle.
3. Store baseline artifact and compare drift on nightly runs.

Acceptance criteria:
- Perf job is non-blocking on PRs; blocking only on severe regression after baseline matures.
- Report includes run metadata (browser, workers, dataset size).

### Workstream E: CI shaping and quality gates (P0/P1)

Current CI (`checks.yml`): `TestJS` (jest) and `TestStorybook` (full Playwright suite) run on every push/PR. No nightly schedule. No fast/slow split.

**Changes needed:**
1. PR required checks (already covered, but verify):
   - `TestJS` — covers Workstreams A+B automatically.
   - `TestStorybook` — currently runs all pw-tests; consider tagging outside-params specs for a fast subset.
2. Add nightly cron schedule to `checks.yml` (or a separate workflow):
   - Full race matrix (all Workstream C scenarios).
   - Performance lane (Workstream D).
3. Flake control:
   - Single worker (`--workers=1`) for race-sensitive specs.
   - Deterministic test dataset and delay values in stories.

Acceptance criteria:
- Clear required vs. informational check distinction in CI config.
- Playwright failures identify scenario names (not generic timeout messages).

## 5) Delivery sequence

### Phase 1: Close correctness blind spots
1. Extend `SmartRowCache.test.ts` with out-of-order and stale-key tests (Workstream A items 1–4).
2. Add `getDs` unit test (Workstream A item 5).
3. Extend `DFViewerInfinite.test.tsx` with remount and `getRowId` tests (Workstream B items 1–2).
4. Add first Playwright stale-response test from Workstream C.

Exit gate: the stale-display bug class (`outside_df_params` showing wrong data) has at least one test that would catch it.

### Phase 2: Expand race matrix
1. Add story variants (asymmetric delays, rapid toggle button, sort preset).
2. Implement remaining Playwright scenarios (Workstream C items 2–4).
3. Stabilize flake behavior; confirm 5+ clean consecutive runs.
4. Tag fast correctness subset for PR gating if needed.

Exit gate: rapid toggle and sort/toggle race cases covered in CI.

### Phase 3: Add performance signal
1. Implement Workstream D perf spec.
2. Add nightly cron schedule to CI.
3. Capture baseline over several nightly runs, then tune regression thresholds.

Exit gate: nightly perf trend is visible and actionable.

## 6) Definition of done

1. All eight coverage gaps listed in section 3 are covered by explicit tests.
2. PR pipeline blocks on deterministic correctness tests for outside-param/infinite synchronization.
3. Nightly pipeline reports perf drift for repeated outside-param flows.
4. Test scenarios document their expected invariants (in test descriptions or comments).

## 7) Risks and mitigations

1. **Flaky async tests** — use deterministic delays in stories, single Playwright worker for race specs, poll on explicit row content rather than timers.
2. **Overfitting to Storybook-only behavior** — keep unit/component assertions in parallel with E2E to catch logic bugs without a browser.
3. **Slow PR feedback** — keep PR suite minimal (existing `TestJS` + fast Playwright subset); move broad race matrix and perf to nightly.
4. **Mocked AgGridReact drift** — if AG Grid updates change prop shape, component tests may pass while real behavior diverges. Mitigate by running the full Playwright E2E suite nightly against real AG Grid.
