#!/usr/bin/env python3
"""Generate release notes using Claude API from merged PRs since last release.

Usage:
    python scripts/generate_release_notes.py \
        --tag-from 0.12.4 --version 0.13.0 --date 2026-02-24

Requires:
    - ANTHROPIC_API_KEY environment variable
    - gh CLI authenticated with repo access
"""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

CATEGORY_ORDER = [
    ("feat", "Features"),
    ("fix", "Bug Fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactoring"),
    ("ci", "CI/CD"),
    ("chore", "Chores"),
    ("deps", "Dependencies"),
    ("other", "Other"),
]

CATEGORY_MAP = {label: display for label, display in CATEGORY_ORDER}


def get_tag_date(tag: str) -> str:
    """Get the ISO date a tag was created."""
    result = subprocess.run(
        ["git", "tag", "-l", tag, "--format=%(creatordate:iso-strict)"],
        capture_output=True,
        text=True,
        check=True,
    )
    date_str = result.stdout.strip()
    if not date_str:
        print(f"Error: tag '{tag}' not found", file=sys.stderr)
        sys.exit(1)
    # gh search wants YYYY-MM-DD
    return date_str[:10]


def gather_prs(since_date: str) -> list[dict]:
    """Fetch merged PRs since a date using gh CLI."""
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--state", "merged",
            "--search", f"merged:>{since_date}",
            "--json", "number,title,body,labels,mergedAt",
            "--limit", "200",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def classify_pr(title: str, labels: list[dict]) -> str:
    """Classify a PR by its conventional commit prefix or labels."""
    title_lower = title.lower().strip()

    # Check for dependabot / dependency PRs
    label_names = {lbl.get("name", "").lower() for lbl in labels}
    if "dependencies" in label_names or "dependabot" in title_lower:
        return "deps"

    # Match conventional commit prefix (feat:, fix:, feat(scope):)
    for prefix in ("feat", "fix", "perf", "refactor", "ci", "chore"):
        if title_lower.startswith(prefix + ":") or title_lower.startswith(prefix + "("):
            return prefix

    # Match branch-style prefixes (feat/, fix/)
    for prefix in ("feat", "fix", "perf", "refactor", "ci", "chore"):
        if title_lower.startswith(prefix + "/"):
            return prefix

    # Match natural language prefixes
    if title_lower.startswith("add ") or title_lower.startswith("add:"):
        return "feat"
    if title_lower.startswith("fix ") or title_lower.startswith("fix:"):
        return "fix"

    return "other"


def group_prs(prs: list[dict]) -> dict[str, list[dict]]:
    """Group PRs by category."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for pr in prs:
        category = classify_pr(pr["title"], pr.get("labels", []))
        groups[category].append(pr)
    return groups


def build_prompt(grouped_prs: dict[str, list[dict]], version: str, date: str) -> str:
    """Build the Claude prompt with grouped PR data."""
    sections = []
    for key, display_name in CATEGORY_ORDER:
        prs = grouped_prs.get(key, [])
        if not prs:
            continue
        lines = [f"### {display_name}"]
        for pr in prs:
            body_preview = (pr.get("body") or "")[:300]
            lines.append(f"- #{pr['number']}: {pr['title']}")
            if body_preview.strip():
                lines.append(f"  Body: {body_preview}")
        sections.append("\n".join(lines))

    pr_text = "\n\n".join(sections)

    return f"""You are writing release notes for buckaroo version {version} (released {date}).
Buckaroo is a GUI data-wrangling tool for pandas and polars DataFrames in Jupyter notebooks.

Below are the merged PRs grouped by category. Generate TWO outputs separated by the exact
marker line "---CHANGELOG---".

**Output 1 — GitHub Release Notes** (markdown):
- Start with "## Highlights" containing 1-2 sentences summarizing the most important user-facing changes
- Then add sections for each category that has user-facing changes: "## New Features", "## Bug Fixes", "## Performance", etc.
- Each bullet should be a concise, user-readable summary referencing the PR number as (#NNN)
- Skip purely internal CI/infra PRs unless they represent a significant change (e.g., new test infrastructure)
- End with an "## Install" section showing: ```bash\\npip install buckaroo=={version}\\n```

**Output 2 — CHANGELOG.md Entry** (markdown):
- Start with: ## {version} — {date}
- Follow with a one-line summary
- Then subsections (### Features, ### Fixes, ### Performance, ### CI/CD, etc.) — only include sections that have entries
- Each bullet is a short description referencing (#NNN)

Be concise. Don't editorialize. Use active voice ("Add X", "Fix Y", not "Added X", "Fixed Y").

---

{pr_text}"""


def call_claude(prompt: str) -> str:
    """Call Claude API and return the response text."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Generate release notes with Claude")
    parser.add_argument("--tag-from", required=True, help="Previous release tag (e.g., 0.12.4)")
    parser.add_argument("--version", required=True, help="New version being released (e.g., 0.13.0)")
    parser.add_argument("--date", required=True, help="Release date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="/tmp", help="Directory for output files")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt without calling Claude")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        print("Error: ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        sys.exit(1)

    # Get date of the previous tag
    since_date = get_tag_date(args.tag_from)
    print(f"Gathering PRs merged since {since_date} (tag {args.tag_from})...", file=sys.stderr)

    # Gather and group PRs
    prs = gather_prs(since_date)
    if not prs:
        print("No merged PRs found since last release.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(prs)} merged PRs", file=sys.stderr)

    grouped = group_prs(prs)
    for key, display in CATEGORY_ORDER:
        count = len(grouped.get(key, []))
        if count:
            print(f"  {display}: {count}", file=sys.stderr)

    # Build prompt
    prompt = build_prompt(grouped, args.version, args.date)

    if args.dry_run:
        print("\n=== PROMPT ===\n", file=sys.stderr)
        print(prompt)
        return

    # Call Claude
    print("Generating release notes with Claude...", file=sys.stderr)
    response = call_claude(prompt)

    # Split response into two outputs
    if "---CHANGELOG---" not in response:
        print("Warning: Claude response missing ---CHANGELOG--- separator", file=sys.stderr)
        print("Full response written to release_notes.md", file=sys.stderr)
        release_notes = response
        changelog_entry = ""
    else:
        parts = response.split("---CHANGELOG---", 1)
        release_notes = parts[0].strip()
        changelog_entry = parts[1].strip()

    # Write output files
    release_path = os.path.join(args.output_dir, "release_notes.md")
    changelog_path = os.path.join(args.output_dir, "changelog_entry.md")

    with open(release_path, "w") as f:
        f.write(release_notes)
    print(f"GitHub release notes written to {release_path}", file=sys.stderr)

    if changelog_entry:
        with open(changelog_path, "w") as f:
            f.write(changelog_entry)
        print(f"CHANGELOG entry written to {changelog_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
