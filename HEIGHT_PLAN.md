# Buckaroo Height Handling: Analysis & Plan

## Current State: How Height Works Today

### The Height Calculation Engine (`gridUtils.ts:452-513`)

The central function `heightStyle()` computes a `HeightStyleI` object that controls AG Grid's sizing:

```
window.innerHeight / height_fraction (default 2) = regularCompHeight

if (numRows + pinnedRows) < maxRowsWithoutScrolling → "short mode"
    domLayout: "autoHeight", style: { minHeight: 50, maxHeight: dfvHeight }

else → "regular mode"
    domLayout: "normal", style: { height: dfvHeight, overflow: "hidden" }
```

### Current Implicit Height Strategies (unnamed)

Today `heightStyle()` has several behaviors baked into one function with if/else chains:

| Environment | Behavior | Detection |
|---|---|---|
| **Jupyter / Marimo** | `window.innerHeight / 2` — takes half the screen. Works well with maximized notebooks. | Default path (no special detection) |
| **Google Colab** | Fixed 500px. Colab's iframe environment is funky and this was the most expedient solution. | `location.host.indexOf("colab.googleusercontent.com")` |
| **VSCode** | Fixed 500px. Same situation — VSCode's ipywidget rendering is its own thing. | `window.vscIPyWidgets !== undefined` |
| **iframe generic** | CSS override: `.in-iframe .ag-center-cols-viewport { min-height: 450px }` | `window.parent !== window` |
| **MCP standalone** | Gets the Jupyter behavior (half screen) by accident. Container is `100vh` but grid only uses `innerHeight / 2`. **Results in black space filling the bottom half.** | No detection — falls through to default |

### Short Mode (orthogonal to the above)

When the table has fewer rows than fit in the computed height, short mode kicks in:
- `domLayout: "autoHeight"` — AG Grid sizes to fit content
- No wasted vertical space for a 3-row table
- This works correctly and doesn't need to change.

### The Component Tree

```
standalone.tsx:  <div style={{ height: "100vh" }}>
  BuckarooWidgetInfinite: <div style={{ height: "100%" }}>
    <div class="orig-df" style={{ overflow: "hidden" }}>
      <StatusBar />                                        ← autoHeight, always 1 header + 1 data row
      <DFViewerInfinite>
        <div class="df-viewer regular-mode">
          <div class="theme-hanger" style={{ height: N px }}>  ← FIXED PIXELS (the problem)
            <AgGridReact domLayout="normal" />
          </div>
        </div>
      </DFViewerInfinite>
    </div>
  </div>
</div>
```

The outer container says "fill the viewport" but the inner grid gets a fixed pixel height computed once at render. No resize listener, no flex-grow.

---

## Problem Statement

1. **MCP standalone**: Table uses half the window. Should fill all available space.
2. **No resize handling**: Height is computed once. Resizing the browser window doesn't reflow.
3. **Environment detection lives in the frontend**: `heightStyle()` sniffs Colab, VSCode, iframes. This should be the Python side's job — it knows what environment it's running in.
4. **Strategies are implicit**: The different height behaviors are tangled in one function. They should be named, explicit, and independently testable.

---

## Design: Named Height Strategies

Replace the implicit if/else chains with an explicit `heightMode` on `ComponentConfig`. Each mode is a named, testable strategy. The Python side detects the environment and sets the mode. The frontend just executes it.

### The Modes

```typescript
type HeightMode =
    | "fraction"   // window.innerHeight / height_fraction. Default for Jupyter, Marimo.
    | "fixed"      // Explicit pixel height (dfvHeight). Colab, VSCode.
    | "fill"       // CSS flex: fill all available container space. MCP standalone.
```

| Mode | Used By | Behavior |
|---|---|---|
| `"fraction"` | Jupyter, Marimo | `window.innerHeight / (height_fraction \|\| 2)`. Half the screen. Existing behavior. |
| `"fixed"` | Colab, VSCode | `dfvHeight` pixels (default 500). Existing behavior. |
| `"fill"` | MCP standalone | CSS `flex: 1` — fills whatever parent container provides. Responsive to resize. |

Short mode still applies on top of any of these: if the table has fewer rows than fit, it uses `domLayout: "autoHeight"` regardless of `heightMode`.

### Updated Types

**TypeScript (`DFWhole.ts`):**
```typescript
type HeightMode = "fraction" | "fixed" | "fill";

type ComponentConfig = {
    heightMode?: HeightMode;       // NEW — which height strategy to use
    height_fraction?: number;      // for "fraction" mode (default: 2)
    dfvHeight?: number;            // for "fixed" mode (default: 500)
    layoutType?: "autoHeight" | "normal";
    shortMode?: boolean;
    selectionBackground?: string;
    className?: string;
};
```

**Python (`styling_core.py`):**
```python
ComponentConfig = TypedDict('ComponentConfig', {
    'heightMode': NotRequired[Literal["fraction", "fixed", "fill"]],
    'height_fraction': NotRequired[float],
    'dfvHeight': NotRequired[int],
    'layoutType': NotRequired[Literal["autoHeight", "normal"]],
    'shortMode': NotRequired[bool],
    'selectionBackground': NotRequired[str],
    'className': NotRequired[str]
})
```

### Backward Compatibility

When `heightMode` is not set (existing code, old configs):
- The frontend defaults to `"fraction"` — the current Jupyter behavior.
- Colab/VSCode environment sniffing in `heightStyle()` stays as a fallback but only triggers when `heightMode` is unset. Once the Python side sets `heightMode` explicitly, the frontend trusts it.

This means existing notebooks that don't set `heightMode` work exactly as before.

---

## How Each Mode Works

### `"fraction"` mode (Jupyter, Marimo)

Existing behavior, now explicitly named:
```typescript
const dfvHeight = window.innerHeight / (compC?.height_fraction || 2);
// regular: { height: dfvHeight, overflow: "hidden" }
// short:   { minHeight: 50, maxHeight: dfvHeight, overflow: "hidden" }
```
No CSS flex needed. This is "take half the screen" and it's the right call for notebooks where cells live above and below.

### `"fixed"` mode (Colab, VSCode)

Existing behavior, now explicitly named:
```typescript
const dfvHeight = compC?.dfvHeight || 500;
// always: { height: dfvHeight, overflow: "hidden" }
// domLayout: "normal"
```
These environments are funky. A fixed pixel height is the practical answer.

### `"fill"` mode (MCP standalone)

New behavior. The grid fills whatever space its parent container provides.

**How resize works — pure CSS, no JS listeners:**

AG Grid with `domLayout: "normal"` has internal resize detection. From the [AG Grid docs](https://www.ag-grid.com/react-data-grid/grid-size/):

> "If the width and / or height change after the grid is initialised, the grid will automatically resize to fill the new area."

So the mechanism is:

1. `html, body, #root` are `height: 100vh` (set by `handlers.py`)
2. The entire div chain down to `.theme-hanger` is an unbroken CSS flex column (`flex: 1; min-height: 0`)
3. When the user resizes the browser window, `100vh` changes → CSS flex reflows the entire chain → `.theme-hanger` gets a new computed height
4. AG Grid detects its container changed size (it watches internally) and re-renders its rows

No `ResizeObserver`, no `window.addEventListener("resize")`, no JS resize code on our side. Pure CSS flexbox propagation + AG Grid's built-in container size monitoring.

**The flex chain for "fill" mode:**

```
html, body, #root     → height: 100vh
.buckaroo_anywidget   → height: 100%; display: flex; flex-direction: column
.dcf-root             → flex: 1; min-height: 0; display: flex; flex-direction: column
.orig-df              → flex: 1; min-height: 0; display: flex; flex-direction: column
.status-bar           → flex-shrink: 0  (always 1 header row + 1 data row, takes its content height)
.df-viewer            → flex: 1; min-height: 0; display: flex; flex-direction: column
.theme-hanger         → flex: 1; min-height: 0  (AG Grid fills this)
```

**StatusBar in "fill" mode:** The StatusBar is always just a header row and one data row. It uses `domLayout: "autoHeight"` so its height is content-determined (~40-50px). In the flex column, it gets `flex-shrink: 0` — it takes exactly its natural content height and never gets compressed. The data grid (DFViewerInfinite) gets `flex: 1` and receives ALL remaining space. No fudge factors needed — flex handles the subtraction exactly.

**`applicableStyle` for "fill" mode:**
```typescript
// regular (many rows):
{ flex: 1, minHeight: 0, overflow: "hidden" }
// domLayout: "normal" — AG Grid scrolls internally

// short (few rows):
{ minHeight: 50, maxHeight: containerHeight, overflow: "hidden" }
// domLayout: "autoHeight" — AG Grid sizes to content
// (short tables should NOT stretch to fill the screen)
```

**Short mode in "fill":** Still uses `domLayout: "autoHeight"`. A 3-row table should render at content height, not stretch. For short-mode detection, `maxRowsWithoutScrolling` uses `window.innerHeight / rowHeight` as a reasonable upper bound (the actual available space may be smaller, but we only need to detect "clearly short" tables).

---

## Where Environment Detection Happens

### Current: Frontend sniffs the environment

`heightStyle()` checks `location.host` for Colab, `window.vscIPyWidgets` for VSCode, `window.parent !== window` for iframes.

### New: Python side sets `heightMode`

The Python side already knows what environment it's in:

**Jupyter / Marimo (default):** `heightMode` is unset → frontend defaults to `"fraction"`. Or explicitly: `component_config = {'heightMode': 'fraction'}`.

**Colab:** Detected in Python (e.g., `"google.colab" in sys.modules`). Sets `component_config = {'heightMode': 'fixed', 'dfvHeight': 500}`.

**VSCode:** Detected similarly. Sets `component_config = {'heightMode': 'fixed', 'dfvHeight': 500}`.

**MCP standalone server:** The standalone server controls its own display state. Sets `component_config = {'heightMode': 'fill'}` when building the display args.

This centralizes environment detection in Python. The frontend becomes a pure renderer of the chosen strategy.

### Migration path for frontend environment detection

The Colab/VSCode checks in `heightStyle()` become fallbacks:
```typescript
// Only sniff environment if heightMode is not explicitly set
if (!compC?.heightMode) {
    if (isGoogleColab || inVSCcode()) {
        effectiveMode = "fixed";
    } else {
        effectiveMode = "fraction";
    }
} else {
    effectiveMode = compC.heightMode;
}
```

This preserves behavior for anyone using older Python-side code that doesn't set `heightMode` yet.

---

## Frontend Testability

Each mode can be tested independently in Storybook by passing `component_config`. No environment sniffing in tests:

```typescript
// Story: "Fraction Mode (Jupyter)" — in a fixed-size container
component_config: { heightMode: "fraction", height_fraction: 2 }

// Story: "Fixed Mode (Colab/VSCode)"
component_config: { heightMode: "fixed", dfvHeight: 500 }

// Story: "Fill Mode (MCP Standalone)" — in a flex container
component_config: { heightMode: "fill" }

// Story: "Short Table" — short mode overrides any heightMode
component_config: { heightMode: "fill" }  // with 3-row data
```

---

## Implementation Plan

### Step 1: Add `HeightMode` type and update `ComponentConfig`

**Files:**
- `packages/buckaroo-js-core/src/components/DFViewerParts/DFWhole.ts` — add `HeightMode` type, add `heightMode` to `ComponentConfig`
- `buckaroo/dataflow/styling_core.py` — add `heightMode` to Python `ComponentConfig`

### Step 2: Refactor `heightStyle()` to dispatch on `heightMode`

**File:** `packages/buckaroo-js-core/src/components/DFViewerParts/gridUtils.ts`

- When `heightMode` is set, use it directly
- When unset, fall back to current environment-sniffing logic (backward compat)
- `"fraction"`: existing `window.innerHeight / height_fraction` path
- `"fixed"`: existing `dfvHeight || 500` path
- `"fill"`: return `applicableStyle: { flex: 1, minHeight: 0, overflow: "hidden" }`
- Short mode still applies on top regardless of mode

### Step 3: Update component structure for "fill" mode

**Files:**
- `packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerInfinite.tsx` — when heightMode is "fill", `.df-viewer` and `.theme-hanger` use flex styles
- `packages/buckaroo-js-core/src/components/BuckarooWidgetInfinite.tsx` — `.orig-df` gets flex column layout
- `packages/buckaroo-js-core/src/style/dcf-npm.css` — add CSS rules for fill mode flex chain

### Step 4: MCP standalone sets `heightMode: "fill"`

**Files:**
- `packages/js/standalone.tsx` — inject `heightMode: "fill"` into component_config before passing to components
- `buckaroo/server/handlers.py` — update page CSS for unbroken flex chain from `html` to `.theme-hanger`

### Step 5: Python-side environment detection (future / optional)

**Files:**
- `buckaroo/buckaroo_widget.py` or environment detection module — detect Colab, VSCode, set `heightMode` in `component_config`
- This can be done incrementally. The frontend fallback preserves existing behavior.

### Step 6: Storybook stories for each mode

**Files:**
- `packages/buckaroo-js-core/src/stories/HeightMode.stories.tsx` — stories for each mode with different data sizes

---

## Files to Change

| File | Change |
|---|---|
| `packages/buckaroo-js-core/src/components/DFViewerParts/DFWhole.ts` | Add `HeightMode` type, add `heightMode` to `ComponentConfig` |
| `packages/buckaroo-js-core/src/components/DFViewerParts/gridUtils.ts` | Refactor `heightStyle()` to dispatch on `heightMode`, add `"fill"` path |
| `packages/buckaroo-js-core/src/components/DFViewerParts/DFViewerInfinite.tsx` | Support flex styles from `"fill"` mode |
| `packages/buckaroo-js-core/src/components/BuckarooWidgetInfinite.tsx` | Flex column layout on `.orig-df` for fill mode |
| `packages/buckaroo-js-core/src/style/dcf-npm.css` | CSS rules for fill-mode flex chain |
| `packages/js/standalone.tsx` | Inject `heightMode: "fill"` into component_config |
| `buckaroo/server/handlers.py` | Page CSS: unbroken flex chain |
| `buckaroo/dataflow/styling_core.py` | Add `heightMode` to Python `ComponentConfig` |

---

## Testing Strategy

### Test-first approach

Tests are written before implementation. They initially fail, then pass as each step is implemented.

### 1. Unit Tests (`gridUtils.test.ts`)

New test cases in the existing `getHeightStyle` describe block:

| Test | Asserts |
|---|---|
| `heightMode: "fraction"` with 100 rows | `classMode: "regular-mode"`, `domLayout: "normal"`, `applicableStyle.height` is a pixel number |
| `heightMode: "fraction"` with 3 rows | `classMode: "short-mode"`, `domLayout: "autoHeight"` |
| `heightMode: "fixed"` with dfvHeight 500 | `applicableStyle.height === 500`, `domLayout: "normal"` |
| `heightMode: "fixed"` with 3 rows | still `domLayout: "normal"` (fixed mode ignores short mode) |
| `heightMode: "fill"` with 100 rows | `applicableStyle.flex === 1`, `applicableStyle.minHeight === 0`, `domLayout: "normal"` |
| `heightMode: "fill"` with 3 rows | `classMode: "short-mode"`, `domLayout: "autoHeight"` (short overrides fill) |
| No `heightMode` set, 100 rows | Same as `"fraction"` (backward compat) |
| No `heightMode` set, 3 rows | Same as fraction short mode (backward compat) |

### 2. Storybook Stories (`HeightMode.stories.tsx`)

| Story | Setup | Expected Visual |
|---|---|---|
| `FractionMode` | 300 rows, `heightMode: "fraction"`, container 800x600 | Grid fills ~half of 600px container, scrolls |
| `FractionModeShort` | 3 rows, `heightMode: "fraction"`, container 800x600 | Grid shrinks to fit 3 rows |
| `FixedMode` | 300 rows, `heightMode: "fixed"`, `dfvHeight: 400` | Grid is exactly 400px |
| `FixedModeShort` | 3 rows, `heightMode: "fixed"`, `dfvHeight: 400` | Grid is 400px (fixed ignores short) |
| `FillMode` | 300 rows, `heightMode: "fill"`, flex container 800x600 | Grid fills full 600px container |
| `FillModeShort` | 3 rows, `heightMode: "fill"`, flex container 800x600 | Grid shrinks to fit 3 rows |

### 3. Playwright Integration Tests

**Storybook-based (`pw-tests/height-mode.spec.ts`):**

| Test | What it checks |
|---|---|
| Fill mode fills container | `.theme-hanger` height ≈ container height (within tolerance) |
| Fraction mode uses half | `.theme-hanger` height ≈ container height / 2 |
| Fixed mode uses explicit height | `.theme-hanger` height ≈ dfvHeight |
| Short table in fill mode | `.theme-hanger` height < 200px (content-sized, not stretched) |

**Server-based (`pw-tests/height-mode-server.spec.ts`):**

| Test | What it checks |
|---|---|
| Server fill mode, 100 rows | Grid fills viewport, no black gap at bottom |
| Server fill mode, 5 rows (short) | Grid content-sized, background visible only below content |
| Server fill mode, resize | Set viewport to 800x600, screenshot, resize to 800x400, screenshot, verify grid height changed |

**Screenshot capture for comparison viewer:**

All Playwright tests capture before/after screenshots into `screenshots/height-mode/` directory for the comparison viewer.

### 4. Screenshot Comparison Viewer (`screenshots/compare.html`)

A self-contained HTML page that:
- Scans the screenshots directory (via a generated manifest)
- Shows before/after pairs side by side
- Supports slider overlay (drag to reveal before vs after)
- Supports toggle view (click to flip)
- Groups screenshots by test scenario
- Works by opening `file://` in a browser — no server needed

The Playwright test script generates a `manifest.json` listing all screenshot pairs. The comparison viewer reads it.
