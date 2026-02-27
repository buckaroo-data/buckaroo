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
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SCREENSHOTS_DIR = REPO_ROOT / "packages" / "buckaroo-js-core" / "screenshots"
BEFORE_DIR = SCREENSHOTS_DIR / "before"
AFTER_DIR = SCREENSHOTS_DIR / "after"
OUTPUT = SCREENSHOTS_DIR / "compare.html"

# Stories in display order, with section headings and issue labels
STORIES = [
    # Section A
    ("A – Width / Contention  (#595, #596, #599, #600)", [
        ("A1_FewCols_ShortHdr_ShortData",  "#599 baseline"),
        ("A2_FewCols_ShortHdr_LongData",   "few cols, long data"),
        ("A3_FewCols_LongHdr_ShortData",   "few cols, long headers"),
        ("A4_FewCols_LongHdr_LongData",    "few cols, both wide"),
        ("A5_ManyCols_ShortHdr_ShortData", "#595 #599 primary bug"),
        ("A6_ManyCols_ShortHdr_LongData",  "#596 data contention"),
        ("A7_ManyCols_LongHdr_ShortData",  "#596 header contention"),
        ("A8_ManyCols_LongHdr_LongData",   "#596 worst case"),
    ]),
    # Section B
    ("B – Large Numbers / compact_number  (#597, #602)", [
        ("B9_LargeNumbers_Float",         "#597 – float displayer (before)"),
        ("B10_LargeNumbers_Compact",      "#597 – compact_number (after)"),
        ("B11_ClusteredBillions_Float",   "#602 – clustered, float"),
        ("B12_ClusteredBillions_Compact", "#602 – clustered, compact (precision loss)"),
    ]),
    # Section C
    ("C – Pinned Row / Index Alignment  (#587)", [
        ("C13_PinnedIndex_FewCols",  "#587 – 5 cols"),
        ("C14_PinnedIndex_ManyCols", "#587 – 15 cols"),
    ]),
    # Section D
    ("D – Mixed Scenarios", [
        ("D15_Mixed_ManyNarrow_WithPinned", "#595 #587 #599"),
        ("D16_Mixed_FewWide_WithPinned",    "#587 baseline"),
    ]),
]


def img_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def build_html() -> str:
    sections_html = []

    for section_title, stories in STORIES:
        cards_html = []
        for name, label in stories:
            before_uri = img_data_uri(BEFORE_DIR / f"{name}.png")
            after_uri = img_data_uri(AFTER_DIR / f"{name}.png")

            def img_block(uri: str | None, slot: str) -> str:
                if uri is None:
                    return f'<div class="missing">{slot}: screenshot not found</div>'
                return (
                    f'<div class="slot-label">{slot}</div>'
                    f'<img src="{uri}" alt="{slot} – {name}"'
                    f' onclick="openLightbox(this.src, \'{name} [{slot}]\')" />'
                )

            cards_html.append(f"""
<div class="card">
  <h3>{name}</h3>
  <div class="label">{label}</div>
  {img_block(before_uri, "before")}
  {img_block(after_uri, "after")}
</div>""")

        sections_html.append(f"""
<section>
  <h2>{section_title}</h2>
  <div class="grid">{''.join(cards_html)}</div>
</section>""")

    sections = "\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Styling Issues: Before / After Screenshots</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #f0f0f0; color: #222; padding: 24px; }}
  h1   {{ font-size: 1.5rem; margin-bottom: 24px; }}
  h2   {{ font-size: 1.1rem; color: #444; margin: 32px 0 12px; border-bottom: 2px solid #ccc; padding-bottom: 6px; }}
  h3   {{ font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; word-break: break-all; }}
  .label {{ font-size: 0.75rem; color: #666; margin-bottom: 8px; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }}

  .card {{
    background: #fff;
    border-radius: 8px;
    padding: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.15);
  }}
  .card img {{
    width: 100%;
    height: auto;
    display: block;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: zoom-in;
    margin-bottom: 8px;
  }}
  .slot-label {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
                 color: #888; margin: 6px 0 2px; letter-spacing: .05em; }}
  .missing {{ font-size: 0.8rem; color: #b00; background: #fff0f0;
              padding: 8px; border-radius: 4px; margin-bottom: 8px; }}

  /* Lightbox */
  #lightbox {{
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.85); z-index: 9999;
    flex-direction: column; align-items: center; justify-content: center;
  }}
  #lightbox.open {{ display: flex; }}
  #lightbox img {{ max-width: 95vw; max-height: 88vh; object-fit: contain;
                   border-radius: 4px; box-shadow: 0 4px 32px rgba(0,0,0,.6); }}
  #lightbox-caption {{ color: #fff; margin-top: 12px; font-size: 0.9rem; }}
  #lightbox-close {{
    position: absolute; top: 16px; right: 20px;
    font-size: 2rem; color: #fff; cursor: pointer; line-height: 1;
    background: none; border: none;
  }}
</style>
</head>
<body>
<h1>Styling Issues: Before / After Screenshots</h1>
{sections}

<!-- Lightbox overlay -->
<div id="lightbox" onclick="closeLightbox()">
  <button id="lightbox-close" onclick="closeLightbox()">&times;</button>
  <img id="lightbox-img" src="" alt="" />
  <div id="lightbox-caption"></div>
</div>

<script>
function openLightbox(src, caption) {{
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox-caption').textContent = caption;
  document.getElementById('lightbox').classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closeLightbox() {{
  document.getElementById('lightbox').classList.remove('open');
  document.body.style.overflow = '';
}}
document.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') closeLightbox(); }});
</script>
</body>
</html>"""


if __name__ == "__main__":
    if not BEFORE_DIR.exists() and not AFTER_DIR.exists():
        print(
            f"No screenshots found.\n"
            f"Run:\n"
            f"  ./scripts/download_styling_screenshots.sh\n"
            f"or capture locally with:\n"
            f"  cd packages/buckaroo-js-core && "
            f"SCREENSHOT_DIR=screenshots/after npx playwright test pw-tests/styling-issues-screenshots.spec.ts",
            file=sys.stderr,
        )
        sys.exit(1)

    html = build_html()
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")

    # Count available screenshots
    before_count = len(list(BEFORE_DIR.glob("*.png"))) if BEFORE_DIR.exists() else 0
    after_count  = len(list(AFTER_DIR.glob("*.png")))  if AFTER_DIR.exists()  else 0
    print(f"  before: {before_count} screenshots")
    print(f"  after:  {after_count} screenshots")
