# Screenshot Compare Approach

## The method

When working on visual/styling changes, write the failing test first — as a Storybook story that reproduces the problem — then use automated screenshot capture and a generated comparison webpage to evaluate whether changes actually improved things.

The loop is:

1. **Write stories that expose the bug** — create Storybook stories with specific data shapes that trigger the visual problem. Cover the combinatorial space (few/many columns, short/long headers, short/long data, with/without pinned rows).

2. **Capture "before" screenshots** — run Playwright against the stories at the baseline commit to record what the bug looks like.

3. **Make the fix** — change the code.

4. **Capture "after" screenshots** — run Playwright again on the new code.

5. **Generate comparison webpage** — a Python script reads both screenshot directories, embeds images as base64, and produces a self-contained HTML file with before/after stacked per story, sidebar navigation, zoom/pan, and keyboard nav.

6. **Review visually** — open the HTML, click through each story, judge whether the change helped or hurt. No pixel-diff automation — human eyes are the test.

7. **Iterate** — if the fix helped some cases but hurt others, adjust and re-capture.

## Why this instead of pixel-diff testing

Visual correctness for a data grid is subjective and context-dependent. A column being 80px vs 60px isn't "wrong" in a way a pixel diff can catch — it depends on what's in the column. The generated comparison page lets you rapidly scan all scenarios and make a judgment call, which is what you actually need for styling work.

## Why stories as the test harness

- Stories are the **specification** — they encode the exact data shape, column config, and displayer that triggers the issue.
- They're reusable — once written, they work for any future before/after comparison, not just the current fix.
- They run in the real rendering pipeline (ShadowDomWrapper + DFViewerInfinite + AG-Grid), so what you see is what users get.
- They're combinatorial — covering the matrix of dimensions (column count x header width x data width x pinned rows) systematically catches regressions that spot-checking misses.

## CI integration

CI captures screenshots automatically on every PR, so you always have a fresh "after" set. The "before" baseline is a fixed commit. Screenshots are uploaded as artifacts — never committed to the repo. A download script pulls them locally, then the comparison generator produces the HTML viewer.

This keeps the repo clean (no PNGs in git) while making the visual evidence reproducible and accessible to anyone reviewing the PR.
