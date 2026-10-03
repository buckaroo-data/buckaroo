# Scoped summary stats (raw / cleaned / filtered) and async stats

## Status

- **V1 (this doc)** — scoped sds (raw + cleaned + filtered) with declarative
  `?`-optional pinned rows. Sync compute, no protocol changes. Ships in two PRs
  (JS first, then backend). This is the load-bearing change.
- **V2 (future, separate issue)** — async stats over WebSocket (two-message
  protocol, `asyncio.to_thread`, state-change keys, stale-response handling).
  Original motivation for this file; see "V2: async stats (deferred)" below.

## V1 — scoped summary stats

### Problem

Today the dataflow computes `merged_sd` against `processed_df`, which is the
df after cleaning AND search filter are applied. When the user types in the
search box, the existing stats are replaced. There is no way to compare "stats
on what I searched" with "stats on what I started with" — the unfiltered view
is gone.

We want both visible at once, especially histograms, so a user can see how
their search restricts the distribution.

While we're at it: when auto-cleaning is active, the cleaned view is also
distinct from the raw input — comparing those is useful too. So three scopes,
not two:

- **raw** — stats on `sampled_df` (the input, post-sampling).
- **cleaned** — stats on the cleaned-but-unfiltered df. Only meaningful when
  `cleaning_method != ""`.
- **filtered** — stats on the cleaned-and-filtered df. Only meaningful when
  the search/quick_command produces non-empty quick_ops.

### Data model

Three sd traits on the dataflow, each with its own observer chain and cache
key, conditionally emitted:

| Trait | Source df | Emitted when |
|-------|-----------|--------------|
| `summary_sd_raw` | `sampled_df` | always |
| `summary_sd_cleaned` | new `cleaned_df_unfiltered` | `cleaning_method != ""` |
| `summary_sd_filtered` | new `cleaned_df_filtered` | quick_ops non-empty |

A merge step flattens the active scopes into a single `merged_sd` whose
row-key prefixes encode scope: bare stat names (`mean`, `histogram_bins`) come
from raw; `cleaned_*` and `filtered_*` prefixed keys come from the respective
scopes. Scope keys are absent when the scope isn't emitted.

This is a **deliberate breaking change** to bare-name semantics. Today,
`merged_sd["col"]["mean"]` is the post-everything mean; after this change it
is the raw mean. Tests touching `dataflow.merged_sd` after applying cleaning
or filter need to be updated to assert on `cleaned_*` / `filtered_*` keys.
Document in CHANGELOG.

### `handle_ops_and_clean` signature change

Today: `[cleaned_df, cleaning_sd, generated_code, merged_operations]`. Today's
`cleaned_df` is actually post-cleaning *and* post-search — the name is
misleading.

New: `[cleaned_df_unfiltered, cleaned_df_filtered_or_None, cleaning_sd,
generated_code, merged_operations]`.

Implementation: run the df interpreter once on `cleaning_ops` to get
`cleaned_df_unfiltered`. If `quick_ops` is non-empty, run the interpreter
again on `cleaned_df_unfiltered` with `quick_ops` to get `cleaned_df_filtered`.
Otherwise `cleaned_df_filtered = None`.

When `cleaning_ops` is empty, `cleaned_df_unfiltered` is `sampled_df` by
reference (preserving the existing short-circuit identity invariant; see
`feedback_short_circuit_identity` memory).

The existing `cleaned_df` property on the dataflow returns "filtered if
present, else unfiltered" so downstream callers continue to see the visible
df they expect.

### Wire format

No top-level change to `df_data_dict`. The `all_stats` wide DF inside it
gains rows with prefixed indices:

```text
mean, min, max, histogram_bins, ...                  # raw  (always present)
cleaned_mean, cleaned_histogram_bins, ...            # cleaned (when active)
filtered_mean, filtered_histogram_bins, ...          # filtered (when active)
```

`df_data_dict` continues to re-sync as a whole trait. **No new WebSocket
message types, no deltas, no state-change keys, no stale-response handling
in V1.** The cost of re-sending unchanged scope rows on state change is
negligible relative to the simplicity of avoiding frontend/backend
divergence in a delta protocol. This is reversible if V2 needs it.

### Pinned rows config — `?` optional marker

The `pinned_rows` config gains a `?` prefix marker on `primary_key_val`. An
entry whose `primary_key_val` starts with `?` is **rendered iff the
unprefixed key exists in `all_stats`**:

```jsonc
pinned_rows: [
  { "primary_key_val": "histogram_bins", ... },             // required: always rendered
  { "primary_key_val": "?cleaned_histogram_bins", ... },    // optional: rendered only when key exists
  { "primary_key_val": "?filtered_histogram_bins", ... }
]
```

The `?` lives only in the config; data keys in `all_stats` are always bare
(`cleaned_histogram_bins`, not `?cleaned_histogram_bins`).

Default pinned_rows configs ship with `?cleaned_*` / `?filtered_*` entries
so the feature lights up automatically when scopes activate. Custom configs
opt in by adding their own `?`-prefixed entries.

This same mechanism handles the **categorical↔numerical column-type case**:
if cleaning converts a column from categorical to numerical, the raw sd has
`value_counts` for that column but the cleaned sd has `cleaned_histogram_bins`.
A config listing all four (`?value_counts`, `?cleaned_value_counts`,
`?histogram_bins`, `?cleaned_histogram_bins`) renders the right combination
per column without any branching.

### Quick op tagging

Quick (search) ops are not currently tagged in `generate_quick_ops`
(`autocleaning.py:83-104`); the comment in `dataflow.py:146` that says they
are is aspirational. Either:

- Tag them with `meta:{'quick_command': True}` for symmetry with cleaning
  ops (one-line addition), or
- Skip the tagging and rely on source provenance — `produce_cleaning_ops`
  and `generate_quick_ops` are the only producers, and `handle_ops_and_clean`
  knows which is which at call-site.

Either works. Pick the lighter one when implementing.

### Cost

Worst case is initial load with cleaning active: two stats-pipeline runs
(raw + cleaned) instead of today's one. On xorq this is one extra Snowflake
query batch. **Acceptable because**:

- Cost is only paid when cleaning is opted into; default (`cleaning_method
  = ""`) sees no change.
- xorq query caching (separate workstream) absorbs the redundancy across
  calls.
- State changes after the initial load only recompute the filtered scope;
  raw and cleaned are cached.

If this turns out to bite, the future opt-out is "pinned_rows-driven
selective compute" (server scans config for `cleaned_*` / `filtered_*`
references and only computes the referenced scopes). Don't build this in
V1.

### PR sequencing

1. **`plans/` → `docs/plans/` move + this doc.** Mechanical, ships first.
2. **JS PR — `?` prefix support in `pinned_rows`.** Strict superset of
   today's behavior since no `?` keys exist anywhere yet. Safe to merge
   alone — no observable change. Bakes in CI before the backend PR.
3. **Backend PR — dual return from `handle_ops_and_clean`, three sd traits,
   conditional scope emission, prefixed row keys in `all_stats`, default
   pinned_rows entries with `?cleaned_*` / `?filtered_*`, test updates
   for the bare-name semantic change.**

Either of the latter two can land first; backend without JS leaves the
scoped rows present in data but unrendered (silent), and JS without backend
adds an unused mechanism (silent). Combined, the feature lights up.

## V2 — async stats (deferred)

The original motivation for this file. Rough shape preserved here:

`XorqServerDataflow(expr, skip_main_serial=True)` runs the stats pipeline
synchronously inside the Tornado IO loop. The worst case is search /
state change: every keystroke into the search box re-runs the stats
pipeline against the filtered expression. On a remote backend that's
"user types `foo`" → six Snowflake aggregate queries stacked. Even
sub-second per query is sluggish.

Once V1 ships and we want responsive xorq filtering:

- **Two-message protocol per state change.** Message 1 (immediate):
  new `df_meta`, `df_data_dict.main = []`, `all_stats` containing only
  the unchanged raw + cleaned scope rows (`filtered_*` absent). Message 2
  (when filtered scope finishes computing): full `df_data_dict`
  replacement with `filtered_*` rows added. State-change key
  round-tripped on both messages, just like `infinite_request` round-trips
  `payload_args`.
- **`asyncio.to_thread` (or `IOLoop.run_in_executor`)** for the filtered
  scope's compute between the two messages. Bounded concurrency via a
  global semaphore; per-session "latest only" coordinator can come later
  if pre-flight stale-key checks aren't enough.
- **Cancellation = pre-flight stale check.** At the start of computing
  filtered_sd, check whether the state-change key is still current. If
  not, drop. No real cancellation needed; computes are short relative to
  typing cadence.
- **Session-liveness check** before pushing message 2.

V2 reuses V1's data model and wire format verbatim — the only changes are
WebSocket protocol additions. V1 ships sync; V2 is purely an optimization
on top.

## Separate issues to file

- **Histogram bin-edge sharing across scopes.** Filtered/cleaned
  histograms should share the raw scope's bin edges so the histograms are
  visually comparable across scopes (otherwise the x-axes differ). Requires
  the Histogram `ColAnalysis` to accept an optional `bins_override` input
  threaded from upstream. Both `DfStatsV2` and `XorqStatPipeline` need to
  support "given bin edges, count rows per bin."
- **Categorical↔numerical column-type handling in histograms.** The `?`
  optional mechanism already handles this declaratively (different stat
  keys exist per scope per column), but the displayer config + Histogram
  analysis behavior across type changes deserves explicit tests and
  documentation.
- **`depends_on_order: bool` on `ColAnalysis`.** Sort doesn't need to
  recompute order-independent stats; today's stats are all order-independent
  (monotonicity testing isn't in the summary set). Adding the flag lets
  future order-dependent stats opt in to recompute-on-sort, and lets the
  sort path skip stat recompute entirely for the default case.

## Related

- #700 (closed) — `XorqStatPipeline` single-round-trip per phase. Sets the
  floor for how fast sync stats can ever be; foundational for V2.
- #773 — the load-expr handler this file branched off of. Ships with the
  v1-equivalent (sync stats, single scope) per its v1 decision.
