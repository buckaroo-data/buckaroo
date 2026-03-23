#!/usr/bin/env python3
"""Generate an HTML page comparing current branch screenshots to the last release.

Images are loaded from GitHub Pages URLs — nothing is embedded or downloaded.
The page is written to docs/extra-html/screenshot-compare/ for RTD to serve.

Usage:
    python scripts/generate_screenshot_compare_page.py <screenshots_dir> <version>

    screenshots_dir: path to freshly captured screenshots (e.g. packages/buckaroo-js-core/screenshots/)
    version: the last release version to compare against (e.g. 0.13.2)
"""
import sys
import shutil
from pathlib import Path

GHPAGES_BASE = "https://buckaroo-data.github.io/buckaroo/screenshots"

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screenshot Comparison — current vs %(version)s</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #111; color: #eee; padding: 1rem 2rem; }
  h1 { margin-bottom: 0.5rem; }
  .subtitle { color: #888; margin-bottom: 1.5rem; }
  .nav { margin-bottom: 1.5rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .nav a { color: #58a6ff; text-decoration: none; font-size: 0.85rem;
           background: #1a1a1a; padding: 4px 8px; border-radius: 4px; }
  .nav a:hover { background: #252525; }
  .comparison { margin-bottom: 3rem; border: 1px solid #333; border-radius: 8px;
                overflow: hidden; background: #1a1a1a; }
  .comparison h2 { padding: 0.75rem 1rem; background: #222; font-size: 1rem;
                    border-bottom: 1px solid #333; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; }
  .side { padding: 0.5rem; }
  .side h3 { font-size: 0.8rem; color: #888; margin-bottom: 0.25rem; text-transform: uppercase; }
  .side img { width: 100%%; display: block; border: 1px solid #333; border-radius: 4px;
              background: #000; }
  .side .missing { color: #666; font-style: italic; padding: 2rem; text-align: center;
                   border: 1px dashed #333; border-radius: 4px; }
  @media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>Screenshot Comparison</h1>
<p class="subtitle">Current branch vs release <strong>%(version)s</strong></p>
<div class="nav">%(nav)s</div>
%(comparisons)s
</body>
</html>
"""

COMPARISON_TEMPLATE = """\
<div class="comparison" id="%(anchor)s">
<h2>%(name)s</h2>
<div class="pair">
<div class="side">
<h3>Current (this branch)</h3>
<img src="%(current_url)s" alt="current %(name)s" loading="lazy"
     onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
<div class="missing" style="display:none">Not captured</div>
</div>
<div class="side">
<h3>Release %(version)s</h3>
<img src="%(release_url)s" alt="release %(name)s" loading="lazy"
     onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
<div class="missing" style="display:none">Not available for this release</div>
</div>
</div>
</div>
"""


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <screenshots_dir> <version>", file=sys.stderr)
        sys.exit(1)

    screenshots_dir = Path(sys.argv[1])
    version = sys.argv[2]

    if not screenshots_dir.is_dir():
        print(f"Not a directory: {screenshots_dir}", file=sys.stderr)
        sys.exit(1)

    pngs = sorted(p.name for p in screenshots_dir.iterdir() if p.suffix == '.png')
    if not pngs:
        print(f"No .png files in {screenshots_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path("docs/extra-html/screenshot-compare")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy current screenshots so they're served alongside the page
    current_dir = output_dir / "current"
    current_dir.mkdir(exist_ok=True)
    for png in pngs:
        shutil.copy2(screenshots_dir / png, current_dir / png)

    nav_links = []
    comparisons = []

    for png in pngs:
        name = png.replace('.png', '')
        anchor = name.replace(' ', '-')
        # The release images use the naming convention: name--version.png
        release_png = f"{name}--{version}.png"
        release_url = f"{GHPAGES_BASE}/{version}/{release_png}"
        current_url = f"current/{png}"

        nav_links.append(f'<a href="#{anchor}">{name}</a>')
        comparisons.append(COMPARISON_TEMPLATE % {
            'anchor': anchor,
            'name': name,
            'current_url': current_url,
            'release_url': release_url,
            'version': version,
        })

    html = PAGE_TEMPLATE % {
        'version': version,
        'nav': '\n'.join(nav_links),
        'comparisons': '\n'.join(comparisons),
    }

    index = output_dir / "index.html"
    index.write_text(html)
    print(f"Wrote {index} ({len(pngs)} comparisons vs {version})")


if __name__ == '__main__':
    main()
