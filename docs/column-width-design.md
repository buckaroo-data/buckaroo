# Column Width: Problems, Levers, and Approaches

## The Core Tension

A data grid must assign pixel widths to columns. The "right" width depends on context:
- A column of 2-digit integers needs ~40px of data space
- A column header "customer_lifetime_value" needs ~150px
- A histogram pinned row needs ~100px to be legible
- The viewport might be 800px wide with 25 columns (32px each if divided equally)

There is no single correct answer. Different users looking at the same data want different things:
one wants every column readable without scrolling; another wants compact data with a scrollbar.
This means we need **multiple levers** that can be composed into different **sizing strategies**.

---

## The Problems (by issue)

### #595 / #599 / #600 — Columns crushed to unreadable widths
**Scenario:** 25+ columns in an 800px viewport with `fitGridWidth` or `fitCellContents`.
AG-Grid divides space equally → 32px per column → data shows "..." truncation.

**Root cause:** No minimum width floor. AG-Grid will shrink columns to nothing.

### #596 — Header vs data width contention
**Scenario:** Long headers ("customer_lifetime_value") on columns with short data (integers 1-99),
or short headers ("a") on columns with long data (formatted floats with 6+ digits).
The column should be as wide as the *wider* of the two, but AG-Grid's auto-sizing
may not see the header or the data correctly (especially with formatted values).

**Root cause:** Need to predict width from *both* header and formatted data, not just one.

### #597 / #601 — Large numbers waste space
**Scenario:** Values like 5,700,000,000 displayed as floats consume ~15 characters.
With `compact_number` displayer they become "5.7B" (4 chars) — 3x narrower.

**Root cause:** The displayer choice dramatically affects needed column width.

### #602 — Compact numbers lose precision on clustered values
**Scenario:** All values between 5.60B and 5.68B. Compact format shows "5.6B" for all of them —
you lose the distinguishing digits. Float format "5,600,000,000" vs "5,680,000,000" preserves them.

**Root cause:** Compact notation is lossy. Some datasets need full precision.
This is a displayer choice, not a width problem, but it interacts with width.

### #587 — Pinned row / index column alignment
**Scenario:** Left-pinned index column scrolls out of view when there are many columns.
Summary stats rows misalign with data columns.

**Root cause:** Was a code bug (using `lcc2` instead of `lcc3` in `dfToAgrid`). Fixed.
But the visual interaction of pinned rows with narrow columns remains relevant —
a histogram pinned row in a 40px-wide column is unreadable.

---

## The Levers (what exists today)

### Per-column levers (set via `ag_grid_specs` in Python `column_config`)

These flow from Python through `column_config[i].ag_grid_specs` and get spread
into the AG-Grid `ColDef` at `baseColToColDef()` (gridUtils.ts:120):

| Property | Effect | Example |
|----------|--------|---------|
| `minWidth` | Floor — column never narrower than this | `{'minWidth': 85}` |
| `maxWidth` | Ceiling — column never wider than this | `{'maxWidth': 200}` |
| `width` | Fixed width (ignores auto-sizing) | `{'width': 150}` |
| `flex` | Relative weight for distributing leftover space | `{'flex': 2}` |

**Current state:** Python's `estimate_min_width_px()` sets only `minWidth`.
The other three (`maxWidth`, `width`, `flex`) are available but unused.

### Grid-level levers (set via `extra_grid_config` in Python or stories)

These flow through `DFViewerConfig.extra_grid_config` and get merged into AG-Grid `GridOptions`:

| Property | Effect | Example |
|----------|--------|---------|
| `autoSizeStrategy` | Controls how AG-Grid distributes column widths | See table below |

**`autoSizeStrategy` options (AG-Grid 32+):**

| Strategy | Behavior | Good for | Bad for |
|----------|----------|----------|---------|
| `fitCellContents` | Each column sized to fit its widest cell | General use — respects content | Can create wide grids with scrollbar |
| `fitGridWidth` | Columns stretched/compressed to fill viewport exactly | No horizontal scrollbar | Crushes columns when there are many |
| `fitProvidedWidth` | Like fitGridWidth but to a specified pixel width | Embedding at known width | Same crushing problem |

**Current default:** `fitCellContents` (for 1+ columns), set in `getAutoSize()` (gridUtils.ts:539).
Override via `extra_grid_config.autoSizeStrategy`.

### Default column lever (`defaultColDef`)

Set in `DFViewerInfinite.tsx:245`. Applied to ALL columns as a base.
Currently contains `sortable`, `type`, `cellStyle`, `cellRendererSelector` — **no width properties**.

Could add `minWidth`, `maxWidth`, etc. here as a blanket floor, but we removed `minWidth: 80`
because it was too blunt (wasted space on narrow-data columns like single-digit integers).

### Displayer choice (affects needed width)

The displayer determines how values are formatted, which determines character count:

| Displayer | Example output | Char count | Notes |
|-----------|---------------|------------|-------|
| `float` (3 frac digits) | "5,700,000,000.000" | ~18 | Widest for large numbers |
| `float` (0 frac digits) | "5,700,000,000" | ~13 | Integers formatted as float |
| `integer` | "5700000000" | ~10 | No commas in current impl |
| `compact_number` | "5.7B" | ~4 | Lossy but very compact |
| `string` | "hello world..." | up to 20 | Capped by max_length |
| `datetimeLocaleString` | "12/31/2024, 11:59 PM" | ~18 | Fixed format |
| `obj` | varies | ~8 | Fallback |

Python's `_formatted_char_count()` estimates this per-displayer.

### Theme parameters (affect pixel calibration)

Set in `gridUtils.ts:555`:
```
spacing: 5
cellHorizontalPaddingScale: 0.3
fontSize: 12
headerFontSize: 14
iconSize: 10
```

The Python constants (`_CHAR_PX_DATA=7`, `_CHAR_PX_HEADER=8`, `_CELL_PAD=16`, `_SORT_ICON=14`)
are calibrated to these theme values. If the theme changes, the constants need recalibration.

---

## Width Approaches (valid strategies for different goals)

Given the same data, there are multiple valid ways to assign column widths.
Each is a combination of the levers above.

### Approach 1: "Readable" — every column wide enough for its content

**Goal:** No truncation. Every value and header fully visible. Histogram pinned rows legible.
Horizontal scrollbar is acceptable.

**Lever settings:**
- `autoSizeStrategy`: `fitCellContents` (default)
- Per-column `minWidth`: computed by `estimate_min_width_px()` from data range + header + histogram
- No `maxWidth` or `flex`

**When it works well:** Few columns, or wide viewport. Data exploration.
**When it fails:** 25+ columns — grid becomes very wide, lots of scrolling.

### Approach 2: "Compact" — minimize horizontal space

**Goal:** See as many columns as possible without scrolling. Accept that some values truncate.
Histograms may be cut off. Headers may truncate.

**Lever settings:**
- `autoSizeStrategy`: `fitGridWidth`
- Per-column `minWidth`: small floor (30-50px) based on data only, ignore header width
- Possibly `maxWidth` to prevent any single column from hogging space

**When it works well:** Overview/scanning mode, many columns.
**When it fails:** Values unreadable if columns get too narrow.

### Approach 3: "Balanced" — fit viewport but enforce minimums

**Goal:** Fill the viewport width (no scrollbar) but ensure no column drops below
a content-aware minimum. If total minimums exceed viewport, allow scrollbar.

**Lever settings:**
- `autoSizeStrategy`: `fitGridWidth`
- Per-column `minWidth`: computed by `estimate_min_width_px()` (content-aware floor)
- Per-column `flex`: proportional to content width (wider content gets more space)

**When it works well:** Moderate column counts (5-15).
**When it fails:** Many columns where minimums already exceed viewport → degrades to scrollbar.

### Approach 4: "Data-priority" — size to data, ignore headers

**Goal:** Column exactly as wide as its data needs. Long headers get truncated/tooltipped.

**Lever settings:**
- `autoSizeStrategy`: `fitCellContents`
- Per-column `minWidth`: based on data width only (not header)
- Per-column `maxWidth`: same as minWidth (fixed to data width)
- Header truncation via AG-Grid's built-in `headerClass` or `autoHeaderHeight`

**Not currently possible:** AG-Grid header truncation needs additional CSS/config work.

---

## What's Implemented vs What's Missing

### Implemented (levers that work today)

| Lever | Status | Where |
|-------|--------|-------|
| Per-column `minWidth` from Python | Working | `styling.py:96-97` → `gridUtils.ts:120` |
| Per-column `maxWidth` from Python | **Available** (unused) | Same pipeline, just set `ag_grid_specs.maxWidth` |
| Per-column `width` from Python | **Available** (unused) | Same pipeline |
| Per-column `flex` from Python | **Available** (unused) | Same pipeline |
| Grid `autoSizeStrategy` override | Working | `extra_grid_config.autoSizeStrategy` → `DFViewerInfinite.tsx:306` |
| Content-aware char count estimation | Working | `_formatted_char_count()` in `styling.py` |
| Histogram min width (100px) | Working | `_HISTOGRAM_MIN_PX` in `styling.py` |
| Displayer choice affects width | Working | `compact_number` vs `float` etc. |

### Missing (levers we don't have yet)

| Lever | What it would do | Difficulty |
|-------|-----------------|------------|
| **Multiple StylingAnalysis configs** | Let user switch between "readable" and "compact" | Medium — Python `df_display_klasses` already supports multiple classes; need UI toggle |
| **Header truncation / tooltip** | Truncate long headers with CSS, show full name on hover | Easy — AG-Grid supports `headerClass` and `headerTooltip` |
| **`defaultColDef.minWidth` as context-dependent floor** | Different floor per sizing strategy | Easy — set in `defaultColDef` based on strategy choice |
| **`flex` distribution** | Proportional space allocation when using `fitGridWidth` | Easy — Python can compute and set `flex` per column |

### Missing (tests / visual proof)

| Gap | Impact |
|-----|--------|
| No unit tests for `estimate_min_width_px()` | Can't verify char count logic for edge cases |
| No stories exercise Python-computed `ag_grid_specs` | All 17 stories construct configs in TypeScript, bypass Python |
| No histogram + narrow columns story | Can't see if 100px minimum actually helps |

---

## Key Insight: The JS Side Already Has All the Levers

The `ag_grid_specs` spread at `gridUtils.ts:120` (`...f.ag_grid_specs`) is a **pass-through
for any AG-Grid ColDef property**. Since `AGGrid_ColDef = ColDef`, Python can set:

- `minWidth`, `maxWidth`, `width`, `flex`
- `suppressSizeToFit`, `resizable`, `lockPosition`
- `headerClass`, `headerTooltip`
- Any other ColDef property

Similarly, `extra_grid_config` at `DFViewerInfinite.tsx:306` is a pass-through for
any AG-Grid `GridOptions`, including `autoSizeStrategy` with all its sub-options.

**The JS side doesn't need new code to support different sizing strategies.**
All the work is in Python: computing the right values and offering the user a way to switch.

The one thing the JS side *would* need for a full solution is a **UI control to switch
between sizing strategies** — but that's a React component concern, not an AG-Grid lever issue.

---

## Recommended Next Steps

1. **Unit tests for `estimate_min_width_px()`** — verify the math for each displayer type
2. **Stories with `ag_grid_specs.minWidth` set** — visual proof the lever works in the grid
3. **Story combining histogram pinned rows + narrow columns** — verify the 100px floor
4. **Prototype "compact" StylingAnalysis** — a second Python class that uses different
   width constants (smaller minWidth, ignore header, smaller histogram floor)
5. **Header truncation** — add `headerTooltip` to `ag_grid_specs` when header is wider
   than data, so users can hover to see full column name
