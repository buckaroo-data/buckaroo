"""Tests for ``load_project_display_klasses`` — scan a project's
``display/<name>.py`` directory, exec each file in a restricted sandbox,
and return ``ColAnalysis`` subclasses that carry a ``df_display_name``
attribute. These slot into ``extra_klasses`` on ``XorqServerDataflow``
and override or extend the built-in display configs (``DefaultMainStyling``,
etc.) for that session only.

Mirrors ``test_project_post_processing.py`` for the display channel.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from buckaroo.server.xorq_loading import load_project_display_klasses

MINIMAL_DISPLAY = (
    "class MyDisplay(ColAnalysis):\n"
    "    df_display_name = 'my_display'\n"
)

MAIN_OVERRIDE = (
    "class MainOverride(DefaultMainStyling):\n"
    "    df_display_name = 'main'\n"
)


def test_returns_empty_when_display_dir_missing(tmp_path: Path):
    assert load_project_display_klasses(tmp_path) == []


def test_returns_empty_when_display_dir_empty(tmp_path: Path):
    (tmp_path / "display").mkdir()
    assert load_project_display_klasses(tmp_path) == []


def test_picks_up_one_display_klass(tmp_path: Path):
    d = tmp_path / "display"
    d.mkdir()
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1
    assert klasses[0].df_display_name == "my_display"


def test_skips_file_without_qualifying_class(tmp_path: Path):
    """A file with no ColAnalysis subclass carrying df_display_name is
    not an error — it's just ignored. A file that does qualify still loads."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "no_display.py").write_text("x = 42\n")
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1
    assert klasses[0].df_display_name == "my_display"


def test_skips_class_without_df_display_name(tmp_path: Path):
    """A ColAnalysis subclass without df_display_name is not collected —
    only named display configs are returned."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "unnamed.py").write_text(
        "class Unnamed(ColAnalysis):\n"
        "    pass\n")
    assert load_project_display_klasses(tmp_path) == []


def test_skips_underscore_prefixed_files(tmp_path: Path):
    d = tmp_path / "display"
    d.mkdir()
    (d / "_disabled.py").write_text(MINIMAL_DISPLAY)
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1


def test_skips_non_identifier_filename(tmp_path: Path):
    """A filename stem that is not a valid Python identifier (e.g.
    ``my-display.py``) is logged and skipped, matching the stat and
    post-processing loaders."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "my-display.py").write_text(MINIMAL_DISPLAY)
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1


def test_skips_file_that_tries_to_import(tmp_path: Path):
    """The sandbox strips __import__ so ``import os`` raises; the file is
    logged and skipped; other files in the same dir still load."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "evil.py").write_text(
        "import os\n"
        "class Evil(ColAnalysis):\n"
        "    df_display_name = 'evil'\n")
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1
    assert klasses[0].df_display_name == "my_display"


def test_base_classes_are_not_returned_as_user_klasses(tmp_path: Path):
    """ColAnalysis and the styling base classes are injected into the
    sandbox as context; they must not appear in the returned list even
    though they are present in the exec'd namespace."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "my_display.py").write_text(MINIMAL_DISPLAY)
    klasses = load_project_display_klasses(tmp_path)
    names = {k.__name__ for k in klasses}
    assert "ColAnalysis" not in names
    assert "DefaultMainStyling" not in names
    assert "DefaultSummaryStatsStyling" not in names
    assert "StylingAnalysis" not in names


def test_subclass_of_default_main_styling_is_collected(tmp_path: Path):
    """A display file may subclass DefaultMainStyling (injected into scope)
    to override the built-in 'main' display for this session."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "main_override.py").write_text(MAIN_OVERRIDE)
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1
    assert klasses[0].df_display_name == "main"


def test_super_is_available_in_display_klass_methods(tmp_path: Path):
    """super() must be accessible inside methods of loaded display klasses.
    Without it in the sandbox, super()-using overrides load successfully
    but raise NameError at render time — a confusing late failure."""
    d = tmp_path / "display"
    d.mkdir()
    (d / "super_display.py").write_text(
        "class SuperDisplay(DefaultMainStyling):\n"
        "    df_display_name = 'main'\n"
        "    @classmethod\n"
        "    def style_column(cls, col, sd):\n"
        "        return super().style_column(col, sd)\n")
    klasses = load_project_display_klasses(tmp_path)
    assert len(klasses) == 1
    # Trigger the method to confirm super() resolves at call time, not just
    # at class-definition time.
    klasses[0].style_column("a", {})


def test_multiple_files_all_collected(tmp_path: Path):
    d = tmp_path / "display"
    d.mkdir()
    for name in ("alpha", "beta", "gamma"):
        (d / f"{name}.py").write_text(
            f"class D(ColAnalysis):\n"
            f"    df_display_name = '{name}'\n")
    klasses = load_project_display_klasses(tmp_path)
    display_names = sorted(k.df_display_name for k in klasses)
    assert display_names == ["alpha", "beta", "gamma"]
