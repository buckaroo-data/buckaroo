# Browser Focus: Primitives and Rubrics

This document separates two concerns:

- **A) Primitives** — the atomic browser manipulations we can perform
- **B) Rubrics** — policies for combining primitives to achieve a desired UX

Different users (or contexts) will want different rubrics. The primitives are
fixed capabilities of the platform; the rubrics are opinion about how to use
them.

---

## A. Primitives

Each primitive is an atomic operation. "Verified" means we have confirmed it
works in our AppleScript/System Events implementation. "Available" means the
API exists but we haven't wired it up yet.

### Tab Discovery

| # | Primitive | Scope | Status |
|---|-----------|-------|--------|
| T1 | **Find tab by URL fragment** | All windows of a Chromium browser | Verified |
| T2 | **Find window by title** | All processes via System Events | Verified (app-mode) |
| T3 | **Get active tab URL** | Front window | Available |
| T4 | **List all tab URLs** | All windows | Available |

### Tab Manipulation

| # | Primitive | Effect | Status |
|---|-----------|--------|--------|
| T5 | **Select tab in its window** | `set active tab index of w to i` — makes tab visible but doesn't touch window z-order | Verified |
| T6 | **Reload tab** | `set URL of t to (URL of t)` — full page reload | Verified |
| T7 | **Create tab in existing window** | `make new tab` in a target window | Available |
| T8 | **Close tab** | `close tab i of window w` | Available |

### Window Manipulation

| # | Primitive | Effect | Status |
|---|-----------|--------|--------|
| W1 | **Raise single window** | System Events `AXRaise of window` — raises ONE window to top of z-order, other browser windows stay where they are | Verified |
| W2 | **Set window to index 1** | `set index of w to 1` — makes window frontmost among browser's own windows | Verified |
| W3 | **Activate application** | `activate` — brings ALL browser windows in front of all other apps' windows. Disruptive when multiple browser windows exist | Verified (problematic) |
| W4 | **Set process frontmost** | System Events `set frontmost to true` — brings browser process to front without reordering its windows | Verified |
| W5 | **Create new window** | `make new window` + set URL | Verified |
| W6 | **Minimize window** | `set miniaturized of w to true` | Available |
| W7 | **Un-minimize window** | `set miniaturized of w to false` | Available |
| W8 | **Check if minimized** | `miniaturized of w` | Available |
| W9 | **Get window bounds** | `bounds of w` → `{x, y, w, h}` | Available |

### Data Update (non-focus)

| # | Primitive | Effect | Status |
|---|-----------|--------|--------|
| D1 | **WebSocket push initial_state** | Server pushes full display state to connected WS clients; JS updates UI without page reload | Verified |
| D2 | **Page reload via AppleScript** | T6 above — forces full page reload including fresh WS connection | Verified |

### Platform Constraints

- **macOS + Chromium**: Full primitive set via AppleScript + System Events
- **macOS + Firefox/Safari**: No tab-level AppleScript API; limited to `open location` and `activate`
- **Linux/Windows**: No AppleScript; only `webbrowser.open()` and WebSocket push (D1)
- **Chrome --app mode**: Separate process, discoverable by window title (T2), no tab API needed (one tab per window)

---

## B. Rubrics

A rubric is a named policy that combines primitives to achieve a specific UX
goal. The rubric is selected by configuration (env var, CLI flag, or
server setting) — not hardcoded.

### Rubric 1: "Focused Session" (current default)

**Goal:** The target session's window comes to the front. Other browser windows
are not disturbed — they stay exactly where they were in the z-order.

**When to use:** Developer with multiple Buckaroo sessions tiled or overlapping.
Each Claude Code window is paired with a specific browser window. Switching
data in Session A should never move Session B's window.

| Step | Primitive | Why |
|------|-----------|-----|
| Find tab | T1 | Locate the session's tab by URL |
| Select tab | T5 | Make it the active tab in its window |
| Reload | T6 (if new data) | Pick up newly loaded dataset |
| Reorder within browser | W2 | Ensure it's browser's window 1 so W1 targets it |
| Bring browser forward | W4 | Browser comes to front of other apps |
| Raise single window | W1 | Only our window goes on top |
| *If not found:* create | W5 | New window with session URL |

**Key property:** Uses W1+W4 (AXRaise + frontmost), never W3 (activate).
Other browser windows don't move.

### Rubric 2: "Bring Everything Forward"

**Goal:** The browser app comes fully to the front, with the target session's
window on top. Acceptable if the user treats the browser as a single workspace
and doesn't mind all browser windows jumping forward.

| Step | Primitive | Why |
|------|-----------|-----|
| Find tab | T1 | |
| Select tab | T5 | |
| Reload | T6 (if new data) | |
| Reorder within browser | W2 | |
| Activate app | W3 | All windows come forward |
| *If not found:* create | W5 | |

**Key property:** Uses W3 (activate). Simpler, but disruptive with multiple
windows.

### Rubric 3: "Silent Update"

**Goal:** Data is updated in the background via WebSocket. No window focus
changes at all. The user looks at the browser when they're ready.

**When to use:** User doesn't want focus stolen. They're reading Claude's text
response and will glance at the browser on their own. Good for large-monitor
setups where the browser is always visible.

| Step | Primitive | Why |
|------|-----------|-----|
| Push data | D1 | WebSocket initial_state push updates the page |
| *If not found:* create | W5 | Only create a window if none exists |

**Key property:** No focus manipulation. Relies entirely on D1 for data
freshness.

### Rubric 4: "Silent Update + Notify"

**Goal:** Like Silent Update, but if the tab isn't visible (minimized, or
behind other tabs), bounce the dock icon or use a macOS notification so the
user knows something changed.

| Step | Primitive | Why |
|------|-----------|-----|
| Push data | D1 | |
| Check if visible | W8 + T5 check | Is tab active and window not minimized? |
| If hidden: notify | macOS `display notification` or dock bounce | Non-intrusive signal |
| *If not found:* create | W5 | |

**Key property:** Never steals focus. Uses OS notifications for visibility.

### Rubric 5: "App Mode"

**Goal:** Each session runs in a dedicated Chrome `--app` window with its own
profile. Clean separation — no tabs, no browser chrome. Behaves like a native
app.

| Step | Primitive | Why |
|------|-----------|-----|
| Find by title | T2 | App-mode windows found by `<title>` via System Events |
| Raise window | W1 | |
| Bring process forward | W4 | |
| Push data | D1 | Update content via WebSocket |
| *If not found:* launch | Chrome `--app=URL --user-data-dir=...` | New app window |

**Key property:** No tab management needed. Each session is one window.

---

## C. Choosing a Rubric

Proposed configuration:

```
BUCKAROO_FOCUS_RUBRIC=focused_session  (default)
BUCKAROO_FOCUS_RUBRIC=bring_all
BUCKAROO_FOCUS_RUBRIC=silent
BUCKAROO_FOCUS_RUBRIC=silent_notify
BUCKAROO_FOCUS_RUBRIC=app_mode
```

Or via `~/.buckaroo/config.toml`:

```toml
[browser]
focus_rubric = "focused_session"
```

---

## D. What We Can't Do (Known Limitations)

| Limitation | Impact |
|------------|--------|
| No Firefox/Safari tab API via AppleScript | Can't find or select specific tabs in non-Chromium browsers. Fallback is `webbrowser.open()` which opens a new tab every time. |
| `activate` is all-or-nothing | Can't activate one window without all windows jumping forward. System Events AXRaise (W1) can raise a single window, but requires Accessibility permissions that osascript may not have. Current workaround: `activate` then `set index of w to 1` — correct window ends up on top, but other browser windows briefly jump forward. |
| No cross-app z-order query | Can't ask "is this window currently visible to the user?" (could be behind Terminal, etc.). We can only check minimized state. |
| System Events requires Accessibility permission | First run may trigger a macOS permission prompt for the terminal/IDE running the server. |
| AXRaise may not un-minimize | A minimized window might need explicit `set miniaturized to false` before AXRaise works. Needs testing. |
| Linux/Windows have no equivalent to AppleScript | Focus management is limited to `webbrowser.open()` + WebSocket push. Consider `wmctrl` on Linux as future work. |
