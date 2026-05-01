#!/usr/bin/env python3
"""Generate an index.html for the screenshots gallery on gh-pages.

Reads the screenshots/ directory structure and produces a browsable page
listing all releases with their screenshots.

Usage:
    python scripts/generate_screenshots_index.py <screenshots_dir>

The screenshots_dir should contain subdirectories named by version
(e.g. screenshots/0.13.3/) each containing .png files.
"""
import sys
from pathlib import Path

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Buckaroo Screenshots</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #111; color: #eee; padding: 2rem; }
  h1 { margin-bottom: 1rem; }
  h2 { margin: 2rem 0 1rem; border-bottom: 1px solid #333; padding-bottom: 0.5rem; }
  .release { margin-bottom: 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 1rem; }
  .card { background: #1a1a1a; border-radius: 8px; overflow: hidden; }
  .card img { width: 100%%; display: block; cursor: pointer; }
  .card .label { padding: 0.5rem; font-size: 0.85rem; color: #aaa; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .nav { margin-bottom: 2rem; }
  .nav a { margin-right: 1rem; }
</style>
</head>
<body>
<h1>Buckaroo Screenshots</h1>
<div class="nav">%(nav)s</div>
%(releases)s
</body>
</html>
"""

RELEASE_TEMPLATE = """\
<div class="release" id="%(version)s">
<h2>%(version)s</h2>
<div class="grid">
%(cards)s
</div>
</div>
"""

CARD_TEMPLATE = """\
<div class="card">
<a href="%(url)s" target="_blank"><img src="%(url)s" alt="%(name)s" loading="lazy"></a>
<div class="label">%(name)s</div>
</div>
"""


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <screenshots_dir>", file=sys.stderr)
        sys.exit(1)

    screenshots_dir = Path(sys.argv[1])
    if not screenshots_dir.is_dir():
        print(f"Not a directory: {screenshots_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect versions (sorted newest first by semver)
    versions = sorted([d.name for d in screenshots_dir.iterdir() if d.is_dir() and not d.name.startswith('.')],
        key=lambda v: [int(x) for x in v.split('.')], reverse=True)

    nav_links = []
    release_blocks = []

    for version in versions:
        version_dir = screenshots_dir / version
        pngs = sorted(p.name for p in version_dir.iterdir() if p.suffix == '.png')
        if not pngs:
            continue

        nav_links.append(f'<a href="#{version}">{version}</a>')

        cards = []
        for png in pngs:
            name = png.replace('.png', '')
            url = f"{version}/{png}"
            cards.append(CARD_TEMPLATE % {'url': url, 'name': name})

        release_blocks.append(RELEASE_TEMPLATE % {'version': version, 'cards': '\n'.join(cards)})

    html = HTML_TEMPLATE % {'nav': ' '.join(nav_links), 'releases': '\n'.join(release_blocks)}

    output = screenshots_dir / 'index.html'
    output.write_text(html)
    print(f"Wrote {output} ({len(versions)} releases)")


if __name__ == '__main__':
    main()
