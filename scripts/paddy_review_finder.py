"""Scan git diff main..HEAD for "funky" paddy-format outputs and emit a
side-by-side review markdown to /tmp/paddy_review.md."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def git_show(ref: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout


def changed_files() -> list[str]:
    out = subprocess.run(["git", "diff", "main..HEAD", "--name-only"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    skip = {"tests/unit/test_paddy_format.py", "scripts/paddy_format.py",
        "scripts/paddy_review_finder.py"}
    return [f.strip() for f in out.splitlines()
        if f.strip().endswith(".py") and f.strip() not in skip]


def changed_hunks(path: str) -> list[tuple[int, int, int, int]]:
    out = subprocess.run(["git", "diff", "main..HEAD", "--unified=0", "--", path],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    hunks = []
    for line in out.splitlines():
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            os_, oc, ns, nc = m.groups()
            hunks.append((int(os_), int(oc or "1"), int(ns), int(nc or "1")))
    return hunks


def expand_to_block(lines: list[str], start: int, count: int,
    pad_above: int = 2, pad_below: int = 2, max_span: int = 40) -> tuple[int, int]:
    s = max(1, start - pad_above)
    e = min(len(lines), start + count - 1 + pad_below)
    if e - s + 1 > max_span:
        e = s + max_span - 1
    return s, e


def slice_lines(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1: end])


def funky_score(old_block: str, new_block: str) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    new_lines = new_block.splitlines()

    if re.search(r"^\s*def \w+\([^)]*$", new_block, re.MULTILINE):
        score += 3
        reasons.append("def signature wrapped")

    for i, line in enumerate(new_lines):
        m = re.match(r"^(\s*).*[\[\{\(](\S)", line)
        if m and i + 1 < len(new_lines):
            indent = len(m.group(1))
            next_line = new_lines[i + 1]
            next_indent = len(next_line) - len(next_line.lstrip())
            if next_indent > indent + 4:
                score += 2
                reasons.append(f"continuation at col {next_indent} (line_indent={indent})")
                break

    indents = []
    for line in new_lines:
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip())
        indents.append(ind)
    distinct = sorted(set(indents))
    if len(distinct) >= 4:
        score += 1
        reasons.append(f"{len(distinct)} distinct indents in block")

    long_lines = [ln for ln in new_lines if len(ln) > 100]
    if long_lines:
        score += 1
        reasons.append(f"{len(long_lines)} line(s) >100 chars")

    if any(ln.rstrip().endswith(",") for ln in new_lines[:-1]):
        commas_at_eol = sum(1 for ln in new_lines if ln.rstrip().endswith(","))
        if commas_at_eol >= 2:
            score += 1
            reasons.append(f"{commas_at_eol} lines end with comma")

    old_lines = old_block.splitlines()
    old_indents = [len(ln) - len(ln.lstrip()) for ln in old_lines if ln.strip()]
    if (len(set(old_indents)) <= 2 and len(old_lines) >= 4
        and len(set(indents)) > len(set(old_indents))):
        score += 2
        reasons.append("old layout was uniform; new layout has more indent variation")

    return score, reasons


def main() -> int:
    out_path = Path("/tmp/paddy_review.md")
    sections: list[tuple[int, str]] = []

    for path in changed_files():
        try:
            old_src = git_show("main", path)
            new_src = git_show("HEAD", path)
        except subprocess.CalledProcessError:
            continue
        old_lines = old_src.splitlines()
        new_lines = new_src.splitlines()
        for os_, oc, ns, nc in changed_hunks(path):
            if oc == 0 and nc == 0:
                continue
            if oc > 100 or nc > 100:
                continue
            old_s, old_e = expand_to_block(old_lines, os_, max(oc, 1))
            new_s, new_e = expand_to_block(new_lines, ns, max(nc, 1))
            old_block = slice_lines(old_lines, old_s, old_e) if oc else ""
            new_block = slice_lines(new_lines, new_s, new_e) if nc else ""
            score, reasons = funky_score(old_block, new_block)
            if score < 2:
                continue
            section = (
                f"## `{path}` lines {ns}–{ns + max(nc - 1, 0)}\n\n"
                f"score={score}: {', '.join(reasons)}\n\n"
                f"### before (main)\n```python\n{old_block}\n```\n\n"
                f"### after (rollout-2 / greedy)\n```python\n{new_block}\n```\n")
            sections.append((score, section))

    sections.sort(key=lambda x: -x[0])
    body = "\n---\n\n".join(s for _, s in sections[:30])

    out_path.write_text(
        "# paddy-format rollout review\n\n"
        f"Top {min(30, len(sections))} candidates flagged from "
        f"git diff main..HEAD ({len(sections)} total).\n\n"
        "Order: most-funky-first by automated score "
        "(def-wrap = 3, hanging-indent-deep = 2, "
        "old-was-uniform-new-isn't = 2, others = 1).\n\n"
        "---\n\n" + body + "\n")
    print(f"wrote {out_path} — {len(sections)} flagged, showing top {min(30, len(sections))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
