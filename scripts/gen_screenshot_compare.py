#!/usr/bin/env python3
"""
Generate a self-contained before/after screenshot comparison HTML page.

Usage:
    python scripts/gen_screenshot_compare.py

Reads screenshots from:
    packages/buckaroo-js-core/screenshots/before/*.png
    packages/buckaroo-js-core/screenshots/after/*.png

Writes:
    packages/buckaroo-js-core/screenshots/compare.html
"""
import base64
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SCREENSHOTS_DIR = REPO_ROOT / "packages" / "buckaroo-js-core" / "screenshots"
BEFORE_DIR = SCREENSHOTS_DIR / "before"
AFTER_DIR = SCREENSHOTS_DIR / "after"
OUTPUT = SCREENSHOTS_DIR / "compare.html"

# Stories in display order: (name, issue_label, status)
# status: "diff" = visible difference confirmed, "no-diff" = no visible difference,
#          "wip" = still iterating on test setup
STORIES = [
    # Section A — defaultMinWidth fix doesn't produce visible change for these cases
    ("A – Width / Contention  (#595, #596, #599, #600)", [
        ("A1_FewCols_ShortHdr_ShortData",  "#599 baseline",       "no-diff"),
        ("A2_FewCols_ShortHdr_LongData",   "few cols, long data", "no-diff"),
        ("A3_FewCols_LongHdr_ShortData",   "few cols, long hdrs", "no-diff"),
        ("A4_FewCols_LongHdr_LongData",    "few cols, both wide", "no-diff"),
        ("A5_ManyCols_ShortHdr_ShortData", "#595 #599 primary",   "no-diff"),
        ("A6_ManyCols_ShortHdr_LongData",  "#596 data contention","no-diff"),
        ("A7_ManyCols_LongHdr_ShortData",  "#596 hdr contention", "no-diff"),
        ("A8_ManyCols_LongHdr_LongData",   "#596 worst case",     "no-diff"),
        ("A9_ManyCols_LongHdr_YearData",  "#595 primary repro",  "diff"),
    ]),
    # Section B — compact_number displayer shows clear before/after difference
    ("B – Large Numbers / compact_number  (#597, #602)", [
        ("B9_LargeNumbers_Float",         "#597 – float",           "no-diff"),
        ("B10_LargeNumbers_Compact",      "#597 – compact_number",  "diff"),
        ("B11_ClusteredBillions_Float",   "#602 – clustered float", "no-diff"),
        ("B12_ClusteredBillions_Compact", "#602 – clustered compact","diff"),
    ]),
    # Section C — index column pinned vs scrolled away (#587)
    ("C – Pinned Row / Index Alignment  (#587)", [
        ("C13_PinnedIndex_FewCols",  "#587 – 10 cols scrolled", "diff"),
        ("C14_PinnedIndex_ManyCols", "#587 – 20 cols scrolled", "diff"),
    ]),
    # Section D — mixed pinned + width contention
    ("D – Mixed Scenarios", [
        ("D15_Mixed_ManyNarrow_WithPinned", "#595 #587 #599", "diff"),
        ("D16_Mixed_FewWide_WithPinned",    "#587 baseline",  "diff"),
    ]),
]


def img_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def build_html() -> str:
    # Build flat story list with embedded images for JS consumption
    flat: list[dict] = []
    for section_title, stories in STORIES:
        for name, label, status in stories:
            flat.append({
                "name": name,
                "label": label,
                "status": status,
                "section": section_title,
                "before": img_data_uri(BEFORE_DIR / f"{name}.png"),
                "after":  img_data_uri(AFTER_DIR  / f"{name}.png"),
            })

    stories_json = json.dumps(flat)

    # Build nav items HTML (section headers + story entries)
    nav_items = []
    current_section = None
    for i, entry in enumerate(flat):
        if entry["section"] != current_section:
            current_section = entry["section"]
            nav_items.append(
                f'<div class="nav-section">{current_section}</div>'
            )
        short = entry["name"].split("_", 1)[1].replace("_", " ") if "_" in entry["name"] else entry["name"]
        status = entry["status"]
        status_class = f"status-{status}"
        status_label = {"diff": "DIFF", "no-diff": "NO DIFF", "wip": "WIP"}[status]
        nav_items.append(
            f'<div class="nav-item {status_class}" data-idx="{i}" onclick="loadStory({i})">'
            f'<span class="nav-idx">{entry["name"][:3]}</span>'
            f'<span class="nav-tag tag-{status}">{status_label}</span>'
            f'<span class="nav-label">{short}</span>'
            f'<span class="nav-issue">{entry["label"]}</span>'
            f'</div>'
        )
    nav_html = "\n".join(nav_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Styling Issues: Before / After</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  html, body {{
    height: 100%;
    overflow: hidden;
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 13px;
    background: #1a1a1a;
    color: #e0e0e0;
  }}

  /* ── Layout ─────────────────────────────────────────── */
  #app {{
    display: flex;
    height: 100vh;
    width: 100vw;
  }}

  /* ── Sidebar ─────────────────────────────────────────── */
  #sidebar {{
    width: 20%;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: #111;
    border-right: 1px solid #333;
    overflow: hidden;
  }}

  #sidebar-header {{
    padding: 10px 12px 8px;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }}
  #sidebar-header h1 {{
    font-size: 0.85rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 8px;
    line-height: 1.3;
  }}

  #nav-arrows {{
    display: flex;
    gap: 6px;
  }}
  #nav-arrows button {{
    flex: 1;
    padding: 5px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #ccc;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    transition: background 0.1s;
  }}
  #nav-arrows button:hover {{ background: #3a3a3a; color: #fff; }}
  #nav-arrows button:active {{ background: #4a4a4a; }}

  #nav-list {{
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
  }}
  #nav-list::-webkit-scrollbar {{ width: 4px; }}
  #nav-list::-webkit-scrollbar-track {{ background: #111; }}
  #nav-list::-webkit-scrollbar-thumb {{ background: #444; border-radius: 2px; }}

  .nav-section {{
    padding: 8px 12px 4px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #666;
    margin-top: 4px;
  }}

  .nav-item {{
    padding: 6px 12px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 1px;
    border-left: 3px solid transparent;
    transition: background 0.1s;
  }}
  .nav-item:hover {{ background: #1e1e1e; }}
  .nav-item.active {{
    background: #1e3a5f;
    border-left-color: #4a9eff;
  }}
  .nav-idx {{
    font-size: 0.65rem;
    font-weight: 700;
    color: #666;
    letter-spacing: 0.05em;
  }}
  .nav-item.active .nav-idx {{ color: #4a9eff; }}
  .nav-label {{
    font-size: 0.75rem;
    font-weight: 600;
    color: #ccc;
    line-height: 1.3;
  }}
  .nav-item.active .nav-label {{ color: #fff; }}
  .nav-issue {{
    font-size: 0.65rem;
    color: #888;
    line-height: 1.2;
  }}
  .nav-tag {{
    font-size: 0.55rem;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    display: inline-block;
    margin-bottom: 2px;
  }}
  .tag-diff {{ background: #2d5a2d; color: #6fcf6f; }}
  .tag-no-diff {{ background: #3a3a3a; color: #999; }}
  .tag-wip {{ background: #5a4a1a; color: #e0c040; }}

  /* ── Controls (bottom of sidebar) ───────────────────── */
  #controls {{
    flex-shrink: 0;
    border-top: 1px solid #333;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: #0d0d0d;
  }}
  .ctrl-row {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .ctrl-row label {{
    font-size: 0.7rem;
    color: #888;
    width: 42px;
    flex-shrink: 0;
  }}
  .ctrl-row input[type=range] {{
    flex: 1;
    height: 4px;
    accent-color: #4a9eff;
    cursor: pointer;
  }}
  .ctrl-val {{
    font-size: 0.7rem;
    color: #aaa;
    width: 36px;
    text-align: right;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }}
  #btn-reset {{
    padding: 5px 10px;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #ccc;
    cursor: pointer;
    font-size: 0.7rem;
    width: 100%;
    transition: background 0.1s;
  }}
  #btn-reset:hover {{ background: #3a3a3a; color: #fff; }}

  /* ── Main content ────────────────────────────────────── */
  #main {{
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}

  #story-header {{
    flex-shrink: 0;
    padding: 6px 14px;
    background: #161616;
    border-bottom: 1px solid #2a2a2a;
    display: flex;
    align-items: baseline;
    gap: 10px;
  }}
  #story-name {{
    font-size: 0.8rem;
    font-weight: 700;
    color: #fff;
  }}
  #story-label {{
    font-size: 0.72rem;
    color: #4a9eff;
  }}

  /* ── Image slots ─────────────────────────────────────── */
  #images {{
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }}

  .img-slot {{
    flex: 1;
    min-height: 0;
    position: relative;
    overflow: hidden;
    border-bottom: 1px solid #2a2a2a;
  }}
  .img-slot:last-child {{ border-bottom: none; }}

  .slot-badge {{
    position: absolute;
    top: 6px;
    left: 8px;
    z-index: 10;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 2px 7px;
    border-radius: 3px;
    pointer-events: none;
  }}
  .slot-badge.before {{ background: #5a3a00; color: #ffba40; }}
  .slot-badge.after  {{ background: #003a20; color: #40ffa0; }}

  .img-slot img {{
    position: absolute;
    top: 0;
    left: 0;
    width: auto;
    height: auto;
    max-width: none;
    max-height: none;
    display: block;
    transform-origin: 0 0;
    image-rendering: -webkit-optimize-contrast;
    image-rendering: crisp-edges;
  }}

  .slot-missing {{
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    color: #666;
    font-style: italic;
  }}
</style>
</head>
<body>
<div id="app">

  <!-- ── Sidebar ──────────────────────────────────────── -->
  <div id="sidebar">
    <div id="sidebar-header">
      <h1>Before / After<br>Styling Issues</h1>
      <div id="nav-arrows">
        <button id="btn-prev" title="Previous (↑)" onclick="navigate(-1)">↑</button>
        <button id="btn-next" title="Next (↓)"     onclick="navigate(1)">↓</button>
      </div>
    </div>

    <div id="nav-list">
{nav_html}
    </div>

    <div id="controls">
      <div class="ctrl-row">
        <label for="zoom">Zoom</label>
        <input type="range" id="zoom" min="50" max="500" value="100" step="5">
        <span class="ctrl-val" id="zoom-val">100%</span>
      </div>
      <div class="ctrl-row">
        <label for="panx">Pan X</label>
        <input type="range" id="panx" min="0" max="100" value="0" step="1">
        <span class="ctrl-val" id="panx-val">0%</span>
      </div>
      <div class="ctrl-row">
        <label for="pany">Pan Y</label>
        <input type="range" id="pany" min="0" max="100" value="0" step="1">
        <span class="ctrl-val" id="pany-val">0%</span>
      </div>
      <button id="btn-reset" onclick="resetView()">Reset view</button>
    </div>
  </div>

  <!-- ── Main ─────────────────────────────────────────── -->
  <div id="main">
    <div id="story-header">
      <span id="story-name">–</span>
      <span id="story-label"></span>
    </div>

    <div id="images">
      <div class="img-slot" id="slot-before">
        <span class="slot-badge before">before</span>
        <img id="img-before" src="" alt="before" />
        <div class="slot-missing" id="miss-before" style="display:none">screenshot not found</div>
      </div>
      <div class="img-slot" id="slot-after">
        <span class="slot-badge after">after</span>
        <img id="img-after" src="" alt="after" />
        <div class="slot-missing" id="miss-after" style="display:none">screenshot not found</div>
      </div>
    </div>
  </div>

</div><!-- #app -->

<script>
const STORIES = {stories_json};

let currentIdx = 0;
const imgBefore  = document.getElementById('img-before');
const imgAfter   = document.getElementById('img-after');
const missBefore = document.getElementById('miss-before');
const missAfter  = document.getElementById('miss-after');
const storyName  = document.getElementById('story-name');
const storyLabel = document.getElementById('story-label');
const zoomIn  = document.getElementById('zoom');
const panxIn  = document.getElementById('panx');
const panyIn  = document.getElementById('pany');
const zoomVal = document.getElementById('zoom-val');
const panxVal = document.getElementById('panx-val');
const panyVal = document.getElementById('pany-val');

function loadStory(idx, pushHash) {{
  currentIdx = idx;
  const s = STORIES[idx];

  storyName.textContent  = s.name;
  storyLabel.textContent = s.label;

  // Update URL hash (default: push)
  if (pushHash !== false) {{
    history.replaceState(null, '', '#' + s.name);
  }}

  // before image
  if (s.before) {{
    imgBefore.src = s.before;
    imgBefore.style.display = 'block';
    missBefore.style.display = 'none';
  }} else {{
    imgBefore.src = '';
    imgBefore.style.display = 'none';
    missBefore.style.display = 'flex';
  }}

  // after image
  if (s.after) {{
    imgAfter.src = s.after;
    imgAfter.style.display = 'block';
    missAfter.style.display = 'none';
  }} else {{
    imgAfter.src = '';
    imgAfter.style.display = 'none';
    missAfter.style.display = 'flex';
  }}

  // Highlight nav
  document.querySelectorAll('.nav-item').forEach(el => {{
    el.classList.toggle('active', parseInt(el.dataset.idx) === idx);
  }});
  const activeEl = document.querySelector('.nav-item.active');
  if (activeEl) activeEl.scrollIntoView({{ block: 'nearest' }});

  applyTransform();
}}

function navigate(delta) {{
  const next = (currentIdx + delta + STORIES.length) % STORIES.length;
  loadStory(next);
}}

function applyTransform() {{
  const zoom = parseFloat(zoomIn.value) / 100;
  const panX = parseFloat(panxIn.value) / 100;  // 0–1
  const panY = parseFloat(panyIn.value) / 100;  // 0–1

  zoomVal.textContent = Math.round(zoom * 100) + '%';
  panxVal.textContent = Math.round(panX * 100) + '%';
  panyVal.textContent = Math.round(panY * 100) + '%';

  [imgBefore, imgAfter].forEach(img => {{
    const container = img.parentElement;
    const cw = container.offsetWidth;
    const ch = container.offsetHeight;

    // Natural size of the image (fall back to container if not loaded yet)
    const nw = img.naturalWidth  || cw;
    const nh = img.naturalHeight || ch;

    // Scaled size
    const sw = nw * zoom;
    const sh = nh * zoom;

    img.style.width  = sw + 'px';
    img.style.height = sh + 'px';

    // Pan: 0% = top-left corner, 100% = bottom-right corner
    const maxPanX = Math.max(0, sw - cw);
    const maxPanY = Math.max(0, sh - ch);

    img.style.left = (-maxPanX * panX) + 'px';
    img.style.top  = (-maxPanY * panY) + 'px';
  }});
}}

function resetView() {{
  zoomIn.value = 100;
  panxIn.value = 0;
  panyIn.value = 0;
  applyTransform();
}}

// Slider events
[zoomIn, panxIn, panyIn].forEach(el => {{
  el.addEventListener('input', applyTransform);
}});

// Keyboard navigation
document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowDown' || e.key === 'j') navigate(1);
  if (e.key === 'ArrowUp'   || e.key === 'k') navigate(-1);
  if (e.key === 'r') resetView();
}});

// Re-apply transform when images finish loading (natural size changes)
imgBefore.addEventListener('load', applyTransform);
imgAfter.addEventListener('load', applyTransform);

// Re-apply on window resize
window.addEventListener('resize', applyTransform);

// Hash routing: load story from URL hash
function loadFromHash() {{
  const hash = location.hash.slice(1);
  if (hash) {{
    const idx = STORIES.findIndex(s => s.name === hash);
    if (idx >= 0) {{ loadStory(idx, false); return; }}
  }}
  loadStory(0, false);
}}

window.addEventListener('hashchange', loadFromHash);

// Init
loadFromHash();
</script>
</body>
</html>"""


if __name__ == "__main__":
    if not BEFORE_DIR.exists() and not AFTER_DIR.exists():
        print(
            "No screenshots found.\n"
            "Run:\n"
            "  ./scripts/download_styling_screenshots.sh\n"
            "or capture locally with:\n"
            "  cd packages/buckaroo-js-core && "
            "SCREENSHOT_DIR=screenshots/after npx playwright test pw-tests/styling-issues-screenshots.spec.ts",
            file=sys.stderr,
        )
        sys.exit(1)

    html = build_html()
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")

    before_count = len(list(BEFORE_DIR.glob("*.png"))) if BEFORE_DIR.exists() else 0
    after_count  = len(list(AFTER_DIR.glob("*.png")))  if AFTER_DIR.exists()  else 0
    print(f"  before: {before_count} screenshots")
    print(f"  after:  {after_count} screenshots")
