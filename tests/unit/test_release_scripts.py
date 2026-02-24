"""Unit tests for release scripts (no gh CLI or Anthropic API needed)."""

import os
import sys
import tempfile

# Add scripts/ to path so we can import directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from generate_release_notes import classify_pr, group_prs, generate_plain_notes
from update_changelog import update_changelog


# ---------------------------------------------------------------------------
# classify_pr
# ---------------------------------------------------------------------------

def test_classify_pr_conventional_commit_fix():
    assert classify_pr("fix: correct off-by-one error", []) == "fix"


def test_classify_pr_conventional_commit_feat_with_scope():
    assert classify_pr("feat(scope): add dark mode toggle", []) == "feat"


def test_classify_pr_deps_label():
    labels = [{"name": "dependencies"}]
    assert classify_pr("Bump lodash from 4.17.20 to 4.17.21", labels) == "deps"


def test_classify_pr_other():
    assert classify_pr("Update some internal docs", []) == "other"


# ---------------------------------------------------------------------------
# group_prs
# ---------------------------------------------------------------------------

def test_group_prs():
    prs = [
        {"number": 1, "title": "fix: null pointer", "labels": []},
        {"number": 2, "title": "feat: new chart type", "labels": []},
        {"number": 3, "title": "Bump requests to 2.31", "labels": [{"name": "dependencies"}]},
        {"number": 4, "title": "fix: another crash", "labels": []},
    ]
    groups = group_prs(prs)
    assert len(groups["fix"]) == 2
    assert len(groups["feat"]) == 1
    assert len(groups["deps"]) == 1


# ---------------------------------------------------------------------------
# generate_plain_notes — normal case
# ---------------------------------------------------------------------------

def test_generate_plain_notes_normal():
    grouped = {
        "feat": [{"number": 10, "title": "feat: add export button"}],
        "fix": [{"number": 11, "title": "fix: tooltip overflow"}],
    }
    release_notes, changelog_entry = generate_plain_notes(grouped, "1.2.3", "2026-02-24")

    assert "## Features" in release_notes
    assert "## Bug Fixes" in release_notes
    assert "#10" in release_notes
    assert "#11" in release_notes
    assert "## Install" in release_notes
    assert "pip install buckaroo==1.2.3" in release_notes

    assert "## 1.2.3 — 2026-02-24" in changelog_entry
    assert "### Features" in changelog_entry
    assert "### Bug Fixes" in changelog_entry


# ---------------------------------------------------------------------------
# generate_plain_notes — empty case (zero PRs)
# ---------------------------------------------------------------------------

def test_generate_plain_notes_empty():
    release_notes, changelog_entry = generate_plain_notes({}, "1.2.3", "2026-02-24")

    assert "No notable changes" in release_notes
    assert "No notable changes" in changelog_entry
    assert "## Install" in release_notes
    assert "pip install buckaroo==1.2.3" in release_notes
    # Should not crash — implicit assertion by reaching here


# ---------------------------------------------------------------------------
# update_changelog — inserts entry after header line
# ---------------------------------------------------------------------------

def test_update_changelog_inserts_after_header():
    with tempfile.TemporaryDirectory() as tmpdir:
        changelog_path = os.path.join(tmpdir, "CHANGELOG.md")
        entry_path = os.path.join(tmpdir, "entry.md")

        with open(changelog_path, "w") as f:
            f.write("# Changelog\n\n## 0.1.0 — 2025-01-01\n- Initial release\n")

        with open(entry_path, "w") as f:
            f.write("## 1.2.3 — 2026-02-24\n- Add export button (#10)\n")

        update_changelog(entry_path, changelog_path)

        result = open(changelog_path).read()
        lines = result.split("\n")

        # First line must still be the header
        assert lines[0] == "# Changelog"
        # Entry should appear before old content
        assert result.index("## 1.2.3") < result.index("## 0.1.0")
