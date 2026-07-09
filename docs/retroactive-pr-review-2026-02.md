# Retroactive Code Review Plan (Last 15 Merged PRs)

## Scope reviewed
The most recent 15 PR-associated commits (by `git log --oneline` with `(#NNN)` tags):
#570, #564, #547, #551, #562, #563, #567, #566, #565, #568, #550, #545, #542, #537, #533.

## Draft Issue

**Title:** Retroactive QA findings: `no_browser` request parsing bug + cross-platform test blind spots

**Problem summary**
A retroactive review of the last 15 merged PRs found one likely behavioral bug and multiple test coverage gaps:

1. **Likely bug in `/load` request parsing for `no_browser`:**
   - `no_browser` is parsed as `bool(body.get("no_browser", False))`.
   - Any non-empty string (including `"false"`) becomes `True`, so API clients sending JSON strings can unintentionally suppress browser launch.

2. **Windows coverage is intentionally non-blocking and reduced (runtime tradeoff):**
   - CI marks Windows tests as `continue-on-error: true` because those runs are currently ~8–12 minutes versus ~4 minutes for the rest of the suite.
   - Windows runs only `-m "not slow"` and multiple server/cache test modules are skipped on Windows.
   - This is a reasonable throughput optimization, but it leaves a platform-risk blind spot for file-locking, process handling, and temp-file lifecycle behavior.

3. **Regression coverage gaps for recent fixes:**
   - The pandas 3.0 compatibility fix in `get_mode()` changed to `is_numeric_dtype(ser)` but no dedicated regression test was added.
   - New `/load` `no_browser` behavior has no explicit unit/integration tests for accepted input types (`true/false`, missing key, malformed types).

**Why this matters**
- The `no_browser` bug can silently invert behavior for API clients.
- Windows stability may drift because failures do not block merges.
- Recent compatibility fixes can regress without targeted tests.

**Acceptance criteria**
- [ ] Fix `no_browser` parsing to support strict booleans and reject ambiguous values.
- [ ] Add `/load` tests covering `no_browser` permutations and response behavior.
- [ ] Add pandas 3.0+ regression tests for `get_mode()`.
- [ ] Introduce a Windows hardening plan that preserves CI throughput.

---

## Related PR Draft (planning-only PR)

**Title:** docs: add retroactive review findings and QA hardening plan for recent merged PRs

**Body:**

### What this planning PR contains
- Documents retroactive findings from the last 15 merged PRs.
- Proposes an implementation sequence for bug fixes and test hardening.
- Defines testing methodology and quality gates for follow-up fix PRs.

### Key findings
1. `/load` `no_browser` parsing likely treats string values like `"false"` as truthy.
2. Windows CI is intentionally non-blocking due to runtime cost, but currently excludes multiple risk-heavy paths.
3. Recent compatibility fixes need durable regression tests.

### Proposed implementation plan (for follow-up fix PRs)
1. **Hotfix-level:** normalize/validate `no_browser` input and add tests.
2. **Short-term:** add pandas 3.0 regression tests in analysis unit tests.
3. **Mid-term:** reduce Windows skips by refactoring temp-file/process cleanup and SQLite lifecycle handling.
4. **Policy:** when a bugfix PR merges, require at least one reproducer test in the same PR.

## Specific test plan (what to write and what to assert)

### A) `/load` and `no_browser` handler contract tests
**File target:** `tests/unit/server/test_server.py` (or split into a new `test_load_contract.py`).

**Implementation guidance**
- Use table-driven tests (`pytest.mark.parametrize`) for request payload variants.
- In tests, monkeypatch `LoadHandler._handle_browser_window` to a spy/mock so assertions are deterministic.
- Assert both HTTP status and JSON `browser_action` in the `/load` response.

**Test cases to add**
1. `no_browser` omitted → `browser_action != "skipped"` (normal behavior).
2. `no_browser: true` (JSON bool) → `browser_action == "skipped"`.
3. `no_browser: false` (JSON bool) → browser handler invoked; not skipped.
4. `no_browser: "false"` (string) → **either** 400 validation error **or** explicitly coerced false by contract (choose one and lock with test).
5. `no_browser: "true"` (string) → same contract choice as above.
6. `no_browser: 0/1` (numbers) → rejected or explicitly mapped by contract.
7. `no_browser: null` → defaults to false or rejected (decide contract + test).
8. `no_browser: {}` / `[]` → rejected with 400.
9. malformed JSON body → 400 (already exists, keep coverage).
10. missing required fields (`session`, `path`) → 400 (already exists, keep coverage).

**Regression objective**
- Prevent future truthy-coercion bugs from silently changing API behavior.

### B) pandas 3.0 `get_mode()` regression tests
**File target:** create `tests/unit/customizations/analysis_test.py` (or nearest existing analysis test module).

**Implementation guidance**
- Keep tests focused on behavior, not internal pandas API names.
- Include both numeric and non-numeric series, plus null-heavy edge cases.

**Test cases to add**
1. Numeric series with clear mode `[1,1,2]` → returns `1`.
2. Numeric series all-unique `[1,2,3]` → returns first mode semantics (document expected behavior).
3. Float series with NaNs `[1.0, 1.0, np.nan]` → returns `1.0`.
4. Non-numeric series `['a','a','b']` → returns `np.nan` per current contract.
5. Datetime/categorical series → confirm current intended behavior (`np.nan` unless design says otherwise).
6. Empty series → returns `np.nan`.
7. Ensure function does not raise on pandas 3.x types that used to trigger `is_numeric` breakage.

**Regression objective**
- Guarantee the pandas 3.0 compatibility path remains stable.

### C) Windows-risk tests without making main CI slower
**Goal:** improve signal while preserving current non-blocking runtime strategy.

**Implementation guidance**
- Keep current non-blocking Windows job for PR latency.
- Add a **scheduled/nightly blocking Windows job** with broader coverage (`slow` + currently skipped candidates where feasible).
- Add a lightweight PR Windows smoke subset focused on file-lock/process-lifecycle hotspots.

**Concrete additions**
1. New marker `@pytest.mark.windows_smoke` for fast, deterministic Windows-critical tests.
2. PR Windows job runs `-m "windows_smoke or not slow"` (or separate step for clarity).
3. Nightly Windows job runs fuller suite and fails loudly.
4. Add timing budget tracking in CI summary (report per-job duration) to monitor regressions.

**Regression objective**
- Catch Windows-only breakages earlier without turning every PR into a 10+ minute bottleneck.

### D) Extras smoke tests: expand from import checks to behavior checks
**File target:** `scripts/smoke_test.py`.

**Implementation guidance**
- Keep quick import checks, but add one representative behavior assertion per extra.

**Examples**
1. `mcp` extra: instantiate app via `make_app()` and assert routes include `/load` + `/ws`.
2. `marimo` extra: instantiate a minimal `BuckarooDataFrame` and verify expected attribute/method availability.
3. `jupyterlab/notebook` extras: verify minimum major versions + one lightweight runtime call.
4. `polars` extra: serialize + deserialize roundtrip shape/value check (not just byte-length > 0).

---

## Prioritized execution plan

1. **P0 — Fix and test the `no_browser` request contract.**
2. **P1 — Add targeted pandas `get_mode()` regression tests.**
3. **P1 — Add Windows nightly/expanded coverage while keeping PR Windows non-blocking for speed.**
4. **P2 — Expand extras smoke tests from import-level checks to behavior-level checks.**

## Should we look at anything else in this process?
Yes—add these checkpoints to future retro reviews:

- **Rollback readiness:** ensure every risky behavior change has an easy revert path or feature flag.
- **Observability checks:** verify new code paths emit logs/metrics that make regressions detectable.
- **Contract drift audits:** check API handler type expectations against real client payload examples.
- **CI gate integrity:** ensure required jobs actually cover the changed subsystem (avoid all-green but irrelevant checks).
- **Flake accounting:** maintain a known-flaky registry with owners and target dates, not ad-hoc skips.
- **Perf-vs-signal review:** document why a job is non-blocking and what alternate gate (nightly/release) carries the risk.
