# Follow-up: restore the dropped phase-divergence assertion on #787

> PR #787 (rows-first state_change spike) open question, called out in
> the PR body as **the most important item to resolve before
> un-gating**. The two spike tests currently assert the wire shape (two
> ``initial_state`` frames per state_change, infinite_request services
> in between) but do *not* assert that phase 2's stats payload differs
> from phase 1's. Without that assertion the spike test would still
> pass if ``recompute_summary_sd()`` were a no-op — we can't detect
> regression of the spike's whole point. The original draft of the
> test had this assertion; it was dropped because it failed on xorq.

## What "stats differ between phases" means

Phase 1 of the spike emits an ``initial_state`` *before* the analysis
pipeline runs, with ``_defer_summary_sd = True`` short-circuiting the
``_summary_sd`` observer. ``self.summary_sd`` therefore stays at its
prior value. Phase 2 lifts the gate via ``recompute_summary_sd()``,
re-runs the pipeline against the *new* ``processed_df``, and emits a
second ``initial_state``.

If the protocol works, phase 1's ``merged_sd`` is the **previous**
state's stats and phase 2's is the **current** state's stats. The
dropped assertion was something like:

```python
self.assertNotEqual(
    phase1["df_data_dict"]["all_stats"],
    phase2["df_data_dict"]["all_stats"])
```

The reason it failed on xorq is not yet established — the PR body
flags this as TBD. This file proposes how to investigate and what
shape the restored assertion should take.

## Hypotheses for the xorq failure

Ranked rough-to-likely:

1. **Phase 1 emits empty/initial stats on xorq.** The xorq path may
   reach phase 1 before *any* ``summary_sd`` has been computed — the
   prior value is the initial empty dict. Phase 2 then computes real
   stats. ``phase1.stats != phase2.stats`` would pass for that case,
   so this can't be the failure mode unless the *phase 2* stats are
   also empty.
2. **`recompute_summary_sd()` is a no-op on xorq.** ``XorqDataflow``
   inherits ``_summary_sd`` and ``_defer_summary_sd`` from
   ``DataFlow``, but its ``_get_summary_sd`` overrides the base
   (``xorq_buckaroo.py:137``). If the overridden path early-exits when
   the gate flag has already done its job, phase 2 produces nothing
   new and the assertion fails because the payloads are equal.
3. **Both phases emit the same ``processed_df`` payload because xorq
   evaluates ``processed_result`` lazily.** The cascade
   ``processed_result → summary_sd → merged_sd`` may not have fully
   landed by phase 1 send time, so phase 1's broadcast already
   includes phase-2-like stats. The 10ms ``call_later`` is too short
   to matter.
4. **The xorq summary cache is hot.** Phase 1 and phase 2 read the
   same cached SD because the cache invalidation didn't fire between
   them. Less likely given the ``_defer_summary_sd`` gate, but worth
   checking.

The instrumentation to disambiguate: log
``id(self.summary_sd)`` and ``self.summary_sd.get('a', {}).get('mean')``
at three points — before phase 1 broadcast, before
``recompute_summary_sd()``, after ``recompute_summary_sd()``. Run the
test once on pandas and once on xorq and diff the logs.

## What the restored assertion should pin

Not just "the dicts differ." That's too coarse — it passes when phase
1 is empty *and* phase 2 is real, which masks "phase 1 is real and
phase 2 is a no-op" (the actual failure mode the assertion is meant
to catch).

The robust form: pick a stat whose value is **observable and
deterministic** under the spike's state_change, and assert both
phases:

```python
# Test setup: load 10-row dataframe, state change adds a search filter
# that keeps 4 rows.
phase1_stats = phase1["df_data_dict"]["all_stats"]
phase2_stats = phase2["df_data_dict"]["all_stats"]

# Phase 1 carries the prior (no-filter) length: 10.
self.assertEqual(phase1_stats["idx"]["length"], 10)

# Phase 2 carries the filtered length: 4.
self.assertEqual(phase2_stats["idx"]["filtered_length"], 4)
```

This pins both phases to concrete values, not just "they differ." On
xorq specifically, ``filtered_length`` is the load-bearing value —
it's the only stat the spike's state_change actually causes to
change, since the filter is what moves it.

## Recommended sequence

1. **Add instrumentation** (the three log points above). Run both
   pandas and xorq variants of the existing test under verbose logging
   and diff. This is throwaway code, doesn't ship.
2. **Identify the specific failure mode** from the diff.
3. **Decide whether the failure is a bug in ``XorqDataflow`` or a
   limitation of the spike's protocol.** If the former, fix the
   dataflow (likely a missed observer override or a cache-key bug). If
   the latter, the spike is xorq-incompatible and that's a design
   verdict, not a test-coverage gap.
4. **Restore the assertion** in the load-bearing form above. Add it
   to *both* spike tests (the second test currently only asserts wire
   order, not stat divergence).

## What if the failure is structural and unfixable?

The PR body's "Open questions" section also notes inter-phase race
issues and 10ms delay tuning. If the xorq path is structurally
incompatible — e.g. xorq's lazy evaluation makes "compute stats after
emitting rows" meaningless because the rows themselves trigger the
stats compute — the right outcome is to **scope the spike to pandas
only**. The env flag would gate-by-backend (e.g.
``_ROWS_FIRST_SPIKE and isinstance(dataflow, ServerDataflow)``) and the
xorq path would keep today's single-frame rebroadcast. Document it as
a known limitation rather than blocking the spike on xorq parity.

## Out of scope here

- Inter-phase ``state_change`` race (a second state_change between
  phases). Separate plan — needs a serialise / cancel-previous
  strategy.
- Delay tuning for non-localhost RTT.
- Cache-hit fast path (skip phase 2 when ``filt_sd_key`` is already
  cached).
- Phase-2 message type (``stats_update`` vs second ``initial_state``).
  Worth doing but independent of the assertion-coverage gap this plan
  addresses.

## Estimated scope

- Instrumentation + diagnosis: ~1 hour.
- Fix or scope decision: depends on root cause.
- Test restoration: ~30 lines, both spike tests.
