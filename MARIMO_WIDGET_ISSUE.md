# Marimo Widget Rendering Issue

## Problem

Playwright tests for Buckaroo widgets in marimo notebooks timeout waiting for widget elements to appear in the DOM. All 6 marimo tests fail with:

```
TimeoutError: locator.waitFor: Timeout 30000ms exceeded.
- waiting for locator('.buckaroo_anywidget').first() to be visible
```

## Root Cause Analysis

### What Works ✅
- **Python side**: Widget instantiation and dataflow execution work perfectly
- **Static assets**: widget.js (2.3MB) and compiled.css (8.3KB) are built and present
- **Marimo server**: Starts without errors and serves HTML correctly
- **Notebook execution**: All cells execute successfully without Python errors

### What Doesn't Work ❌
- **Widget rendering in browser**: The `.buckaroo_anywidget` elements never appear in the DOM
- **Marimo integration**: Marimo logs "This notebook has errors, saving may lose data" warning
- **Minimal anywidget test**: Even a simple inline anywidget fails to render in marimo

### Investigation Results

1. **Tested Python execution directly**:
   - `BuckarooWidget(small_df)` and `BuckarooInfiniteWidget(large_df)` instantiate successfully
   - Static files load properly into `_esm` and `_css` attributes

2. **Tested marimo server**:
   - HTML is served correctly
   - No Python errors in execution
   - CSS includes `.buckaroo_anywidget` selector

3. **Tested minimal anywidget**:
   - Even a simple inline anywidget with no external files fails to render
   - Marimo shows the same "notebook has errors" warning

## Hypothesis

Marimo's anywidget support appears to be incomplete or broken in version 0.17.6/0.18.4. The widgets are instantiated in Python but not rendered by the marimo frontend/anywidget integration layer.

## Possible Solutions

1. **Version Update**: Try upgrading marimo to a newer version (0.20.1+ mentioned in recent commits)
   - Recent commits mention updating to marimo 0.20.1
   - Current lockfile has 0.17.6/0.18.4

2. **Marimo API Usage**: Check if marimo requires special handling for anywidgets
   - May need to use `mo.output()` or similar to explicitly display widgets
   - May require version-specific configuration

3. **Anywidget Compatibility**: Check if anywidget 0.9.13 is compatible with marimo 0.17.6
   - Version mismatch could cause integration failure

## Files Affected

- `/Users/paddy/buckaroo/buckaroo/static/widget.js` - Frontend code (added)
- `/Users/paddy/buckaroo/buckaroo/static/compiled.css` - Styles (added)
- `/Users/paddy/buckaroo/tests/notebooks/marimo_pw_test.py` - Test notebook
- `/Users/paddy/buckaroo/packages/buckaroo-js-core/pw-tests/marimo.spec.ts` - Playwright tests

## Next Steps

1. Investigate marimo 0.20.1 compatibility
2. Check for marimo API changes related to anywidget rendering
3. Consider whether to skip marimo tests until issue is resolved (add `continue-on-error: true` to CI)
