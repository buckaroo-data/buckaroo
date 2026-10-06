# Follow-up: actually consume the `pushdown=` metadata

> PR #788 follow-up note. #788 lands the *metadata*
> (`StatFunc.pushdown: Tuple[str, ...]`) and the decorator kwarg. No
> code reads the field yet. This file maps out what "reading it" looks
> like, picks a recommended shape, and lists the open questions to
> answer before we ship the consumer.

## What's in #788

- `StatFunc.pushdown: Tuple[str, ...]`, default `()`.
- `@stat(pushdown=("xorq", "polars"))` plumbs into that field.
- Bare-string special case so `@stat(pushdown="xorq")` doesn't become
  `('x','o','r','q')` (Codex P2, fixed in this branch).

Three tests pin the metadata round-trip. Nothing reads `sf.pushdown`.

## The decision the consumer has to make

For each `(stat_func, column)` pair the pipeline is about to evaluate
on a non-pandas backend (today: xorq), choose one of:

- **Materialize-then-call.** Today's behaviour. Pull the column into a
  pandas Series, call the stat function. Cost: a full column round-trip
  through pandas memory for every stat.
- **Push down.** Substitute the stat's body for the engine-native form
  of the same operation. Cost: an extra entry in the batched
  `table.aggregate(...)`. Won't work for stats whose body uses
  pandas-only ops (`value_counts`, `groupby`, scipy calls, …).

`pushdown=` is the marker that says "the substitution is safe for this
function on these backends." It is *not* a per-call dispatcher — the
consumer needs to know how to produce the engine-side form.

## Two interpretations of "knows how to produce the engine-side form"

### Interp A: trust-the-author duck typing

The function body uses only ops that exist on both `pandas.Series` and
`ibis.Column`. The pipeline rebinds the `RawSeries` parameter to the
table column expression and re-runs the function. `ser.mean()` returns
a float on pandas, an ibis aggregate expression on xorq — fold the
latter into the batch aggregate.

Pros: zero code per stat. The `pushdown=` tuple is the *only* contract
the author writes.

Cons: silently wrong for ops that exist on both APIs but have
different semantics (timezone handling, null propagation, sort
stability). Hard to test exhaustively.

### Interp B: separate registered xorq form

The author writes two `@stat` functions (or one with two bodies). The
`pushdown=` tuple is the link: the consumer looks up a stat with the
same `name` in the xorq registry and prefers that one. Today the
distinction is already there in `_is_batch_func` — `XorqColumn` vs
`RawSeries`.

Pros: explicit semantics. Each backend's form is tested independently.

Cons: doubles authoring overhead. Asks the author to maintain two
forms.

**Recommendation: Interp A**, opt-in per stat. The author who flips
`pushdown=("xorq",)` is asserting "I read my body and the operations
I use are semantically identical on `ibis.Column`." That's a smaller
ask than "write a second function" and matches the existing
`XorqColumn` mechanism (which already trusts the author to return an
ibis expression).

## Recommended consumer shape

`XorqStatPipeline._build_batch_aggregate(table)` currently folds in
every `_is_batch_func` stat. Extend it to also fold in
`pushdown_eligible_for("xorq")` stats:

```python
def _pushdown_eligible_for(sf: StatFunc, backend_id: str) -> bool:
    """Stat is pushdown-marked for this backend, with all-raw deps."""
    if backend_id not in sf.pushdown:
        return False
    # Same all-raw-deps constraint as _is_batch_func — derived stats
    # can't run in the pre-aggregate phase.
    for r in sf.requires:
        if r.type in RAW_MARKER_TYPES:
            continue
        return False
    return True
```

In the batch-aggregate loop, when a stat is pushdown-eligible:

1. Synthesize a `XorqColumn` binding for every `RawSeries` /
   `SampledSeries` parameter (rebind to `table[col_name]`).
2. Call the original function body. It returns an ibis expression
   (because every op the body invokes is overloaded the same way).
3. Fold that expression into the batch aggregate under the stat's
   `provides` key, same as `_is_batch_func` does today.

Failure mode: the function body invokes an op that doesn't exist on
`ibis.Column` (e.g. `ser.value_counts()`). The exception fires at
batch-build time, in `_unit_test_result`. The unit_test against
`PERVERSE_DF` already catches construction-time bugs; this extends
that coverage to "the pushdown-marked stat actually pushes down."

## What about `pushdown=("polars",)`?

Polars has no `XorqStatPipeline` analogue today. The metadata is
load-bearing for future expansion but unused at consume time. Wire the
consumer through a `BACKEND_REGISTRY` keyed on backend id; xorq is the
only entry today. Polars lands when there's a polars pipeline (#769
is the natural home).

## Open questions for the implementer

1. **Pipeline construction vs per-process-table eligibility.** Today
   `_is_batch_func` is evaluated at pipeline-build time. Pushdown
   eligibility could be the same — `pushdown` is static metadata. But
   the substitution requires a `table` reference (for `table[col]`).
   Defer the substitution to `process_table` and treat the metadata
   check as build-time only.

2. **Backward compat with `XorqColumn`-typed stats.** If a stat
   already takes `XorqColumn` *and* declares `pushdown=("xorq",)`, the
   pushdown path would synthesize a re-binding even though the stat
   already accepts the engine-side column. Decide: ignore pushdown on
   stats that already speak xorq natively (return `False` from
   `_pushdown_eligible_for` when any param is `XorqColumn`), or treat
   it as a no-op.

3. **Error attribution.** A pushdown stat that fails at execute time
   (because the synthesized expression is malformed, not because the
   stat function body raised) should surface as a `StatError` for
   that stat's name, not as a generic batch-aggregate failure.

4. **Should the unit_test cover both paths?** A stat with
   `pushdown=("xorq",)` has two execution modes: pandas and xorq. The
   xorq unit_test runs against `PERVERSE_DF` wrapped as a memtable;
   the pandas unit_test runs against `PERVERSE_DF` directly. Both
   should succeed before we trust the marker.

5. **Telemetry.** Worth logging which stats actually pushed down vs
   fell back, especially during rollout. A pipeline-level counter
   per `process_table` call is probably enough.

## Test plan for the consumer PR

- **Failing test pre-fix (one CI run):** an `@stat(pushdown=("xorq",))
  def mean(ser: RawSeries) -> float: return float(ser.mean())` is
  applied to an `xo.memtable`. Without the consumer, the test asserts
  the stat ran via pandas materialization (probe: count of
  `table.execute()` calls, or a sentinel). With the consumer, the
  stat should appear in the batch aggregate (probe: inspect the
  compiled aggregate's column refs).
- **Fix commit:** the `_pushdown_eligible_for` check + the
  `XorqStatPipeline` integration.
- **Regression coverage:** `value_counts`-style stat marked
  `pushdown=("xorq",)` raises at unit_test time (catches "author
  marked a stat as pushdown-safe when it isn't").

## Estimated scope

~150 lines of pipeline code + ~80 lines of tests. The metadata is
already in place; this is just the read path.
