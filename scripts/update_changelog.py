#!/usr/bin/env python3
"""Insert a changelog entry after the first line of CHANGELOG.md.

Usage:
    python scripts/update_changelog.py <changelog_entry_file> [changelog_path]
"""

import sys


def update_changelog(entry_path: str, changelog_path: str = "CHANGELOG.md") -> None:
    entry = open(entry_path).read().strip()
    if not entry:
        print(f"Error: entry file '{entry_path}' is empty", file=sys.stderr)
        sys.exit(1)

    changelog = open(changelog_path).read()
    lines = changelog.split("\n", 1)
    header = lines[0]
    rest = lines[1] if len(lines) > 1 else ""
    with open(changelog_path, "w") as f:
        f.write(header + "\n\n" + entry + "\n" + rest)


def main():
    if len(sys.argv) < 2:
        print("Usage: update_changelog.py <changelog_entry_file> [changelog_path]", file=sys.stderr)
        sys.exit(1)

    entry_path = sys.argv[1]
    changelog_path = sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md"

    try:
        open(entry_path)
    except FileNotFoundError:
        print(f"Error: entry file '{entry_path}' not found", file=sys.stderr)
        sys.exit(1)

    update_changelog(entry_path, changelog_path)


if __name__ == "__main__":
    main()
