#!/usr/bin/env python3
"""Generate static embed HTML pages for the column-config styling article.

Produces one HTML file per displayer / color rule example in
docs/extra-html/styling/, drawn from the same data and configs as the
Marimo styling gallery (docs/example-notebooks/Styling-Gallery-*.ipynb).
"""

import sys
import os

# Ensure the repo root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from buckaroo.artifact import (prepare_buckaroo_artifact, artifact_to_json, _HTML_TEMPLATE)
from buckaroo.styling_helpers import obj_, float_, pinned_histogram, inherit_


OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "extra-html", "styling")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Fixtures — one DataFrame + column_config_overrides pair per example.
# Kept in sync with ~/Downloads/marimo.py so the article reads as the
# same gallery shown in the Marimo WASM build.
# ---------------------------------------------------------------------------

def datetime_fixture():
    ts = ["2020-01-01 01:00Z", "2020-01-01 02:00Z", "2020-02-28 02:00Z",
        "2020-03-15 02:00Z", None]
    df = pd.DataFrame({"timestamp": ts, "obj": ts, "default": ts, "en-US": ts, "en-US-long": ts, "en-GB": ts})

    def loc(locale, args=None):
        out = {"displayer": "datetimeLocaleString", "locale": locale}
        if args is not None:
            out["args"] = args
        return {"displayer_args": out}

    cfg = {"obj": {"displayer_args": {"displayer": "obj"}},
        "default": {"displayer_args": {"displayer": "datetimeDefault"}}, "en-US": loc("en-US"),
        "en-US-long": loc("en-US", {"weekday": "long"}), "en-GB": loc("en-GB")}
    return df, cfg


def string_fixture():
    col = ["asdf", "qwerty", "really long string, much much longer", None, "A"]
    df = pd.DataFrame({"string_max_len_35": col, "obj_displayer": col, "string_displayer": col})
    cfg = {"string_max_len_35": {"displayer_args": {"displayer": "string", "max_length": 35}},
        "obj_displayer": {"displayer_args": {"displayer": "obj"}},
        "string_displayer": {"displayer_args": {"displayer": "string"}}}
    return df, cfg


def float_fixture():
    col = [5, -8, 13.23, -8.01, -999.345245234, None]
    df = pd.DataFrame({"obj_displayer": col, "float_1_3": col, "float_0_3": col, "float_3_3": col, "float_3_13": col})

    def fc(min_d, max_d):
        return {"displayer_args": {"displayer": "float",
            "min_fraction_digits": min_d, "max_fraction_digits": max_d}}

    cfg = {"obj_displayer": {"displayer_args": {"displayer": "obj"}}, "float_1_3": fc(1, 3), "float_0_3": fc(0, 3),
        "float_3_3": fc(3, 3), "float_3_13": fc(3, 13)}
    return df, cfg


def link_fixture():
    df = pd.DataFrame({
        "raw": ["https://github.com/paddymul/buckaroo",
            "https://github.com/pola-rs/polars"],
        "linkify": ["https://github.com/paddymul/buckaroo",
            "https://github.com/pola-rs/polars"],
    })
    cfg = {"linkify": {"displayer_args": {"displayer": "linkify"}}}
    return df, cfg


def histogram_fixture():
    data = [[{"name": "NA", "NA": 100.0}], [{"name": 1, "cat_pop": 44.0}, {"name": "NA", "NA": 56.0}],
        [{"name": "long_97", "cat_pop": 0.0}, {"name": "long_139", "cat_pop": 0.0}, {"name": "long_12", "cat_pop": 0.0},
         {"name": "long_134", "cat_pop": 0.0}, {"name": "long_21", "cat_pop": 0.0}, {"name": "long_44", "cat_pop": 0.0},
         {"name": "long_58", "cat_pop": 0.0}, {"name": "longtail", "longtail": 77.0}, {"name": "NA", "NA": 20.0}],
        [{"name": "long_113", "cat_pop": 0.0}, {"name": "long_116", "cat_pop": 0.0},
         {"name": "long_33", "cat_pop": 0.0}, {"name": "long_72", "cat_pop": 0.0}, {"name": "long_122", "cat_pop": 0.0},
         {"name": "long_6", "cat_pop": 0.0}, {"name": "long_83", "cat_pop": 0.0},
         {"name": "longtail", "unique": 50.0, "longtail": 47.0}]]
    df = pd.DataFrame({"name": ["all_NA", "half_NA", "longtail", "longtail_unique"], "histogram_props": data})
    cfg = {"histogram_props": {"displayer_args": {"displayer": "histogram"}}}
    return df, cfg


def chart_fixture():
    data = [[{"lineRed": 33.0, "areaGray": 100, "barCustom3": 40, "barCustom1": 40,
        "name": "2000-01-01 00:00:00"}, {"lineRed": 33.0, "areaGray": 20, "name": "2001-01-01 00:00:00"}, {"lineRed": 66,
            "areaGray": 40, "barCustom2": 60, "name": "unique"}, {"lineRed": 100, "areaGray": 100, "barCustom1": 40,
                "name": "end"}], [{"barCustom3": 40, "barCustom1": 40, "name": "2000-01-01 00:00:00"},
                    {"name": "2001-01-01 00:00:00"}, {"barCustom2": 60, "name": "unique"},
                    {"barCustom1": 40, "name": "end"}], [{"areaRed": 100, "name": "2000-01-01 00:00:00"},
                        {"areaRed": 20, "name": "2001-01-01 00:00:00"}, {"areaRed": 40, "name": "unique"},
                        {"areaBlue": 100, "name": "end"}], [{"lineRed": 33.0, "name": "2000-01-01 00:00:00"},
                            {"lineBlue": 33.0, "name": "2001-01-01 00:00:00"}, {"lineGray": 66, "name": "unique"},
                            {"lineGray": 100, "name": "end"}]]
    df = pd.DataFrame({"name": ["everything", "bar custom only", "area", "line"], "chart": data,
        "chart_custom_colors": data})
    cfg = {
        "chart": {"displayer_args": {"displayer": "chart"}},
        "chart_custom_colors": {"displayer_args": {"displayer": "chart",
            "colors": {"custom1_color": "pink", "custom2_color": "brown",
                "custom3_color": "beige"}}},
    }
    return df, cfg


# 24x24 PNG smiley, PIL-generated (the Marimo-gallery copy turned out to
# have a corrupted IDAT chunk that Chrome silently rendered but Firefox
# rejected with "Image corrupt or truncated").
_PNG_SMILEY = (
    "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAAnElEQVR42sVVSRKAMAgrjI/y/yd/"
    "hSed2mEJHVq5QhMwEVpbHATWyex7QoDlMh6fMQ7NAGeINAJBgQ2iDyZXgXcTi0dQHlzVvTUFJwRM"
    "5UYCtfsHQAPycv0UWzWwOlH/By+XcpEHgJiCPQEREaO6bRqQ1cWMTfuVwcj39WwaaUHRLop0MOpf"
    "3AN10UgEr/LV6/qXg7PlZJYd/eVxAwbeP1vBDxyQAAAAAElFTkSuQmCC")


def image_fixture():
    # Two rows of the same smiley so both cells render (the previous
    # None-second-row produced a broken-image icon from
    # ``data:image/png;base64,null``). The PNG is 24x24 — ag-grid row
    # default is enough to show it without scaling.
    df = pd.DataFrame({"raw": [_PNG_SMILEY, _PNG_SMILEY],
        "image": [_PNG_SMILEY, _PNG_SMILEY]})
    cfg = {
        "raw": {"displayer_args": {"displayer": "string", "max_length": 40}},
        "image": {"displayer_args": {"displayer": "Base64PNGImageDisplayer"},
            "ag_grid_specs": {"width": 80}},
    }
    return df, cfg


def error_highlight_fixture():
    df = pd.DataFrame({
        "a": [10, 20, 30, 5, 3, 11, 12],
        "err_messages": [None, "a must be less than 19, it is 20",
            "a must be less than 19, it is 30", None, None, None, None],
    })
    cfg = {
        "a": {
            "color_map_config": {"color_rule": "color_not_null",
                "conditional_color": "red", "exist_column": "err_messages"},
            "tooltip_config": {"tooltip_type": "simple", "val_column": "err_messages"},
        },
        "err_messages": {"merge_rule": "hidden"},
    }
    return df, cfg


def color_from_column_fixture():
    df = pd.DataFrame({"a": [10, 20, 30], "a_colors": ["red", "#d3a", "green"]})
    cfg = {"a": {"color_map_config": {"color_rule": "color_from_column",
        "val_column": "a_colors"}}}
    return df, cfg


def color_map_continuous_fixture():
    rows = 200
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"int_col": rng.integers(1, 50, rows), "float_col": rng.integers(1, 30, rows) / 0.7,
        "str_col": ["foobar"] * rows})
    cfg = {"float_col": {"color_map_config": {"color_rule": "color_map",
        "map_name": "BLUE_TO_YELLOW", "val_column": "int_col"}}}
    return df, cfg


def color_categorical_fixture():
    # ``color_categorical`` indexes into the palette directly by the cell
    # value, no histogram_bins needed — the right tool when the value
    # itself is the category index (0..N).
    df = pd.DataFrame({"five_vals_5_colors":  [0, 1, 2, 3, 4, None, None, None, None, None],
        "five_vals_10_colors": [0, 1, 2, 3, 4, None, None, None, None, None],
        "ten_vals_5_colors":   [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], "ten_vals_10_colors":  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]})
    c10 = ["green", "blue", "red", "orange", "purple", "brown", "pink",
        "beige", "teal", "gray"]
    c5 = ["green", "blue", "red", "orange", "purple"]
    cfg = {
        "five_vals_5_colors": {"color_map_config": {"color_rule": "color_categorical",
            "map_name": c5}},
        "five_vals_10_colors": {"color_map_config": {"color_rule": "color_categorical",
            "map_name": c10}},
        "ten_vals_5_colors": {"color_map_config": {"color_rule": "color_categorical",
            "map_name": c5}},
        "ten_vals_10_colors": {"color_map_config": {"color_rule": "color_categorical",
            "map_name": c10}},
    }
    return df, cfg


def tooltip_fixture():
    rows = 30
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"int_col": rng.integers(1, 50, rows), "float_col": rng.integers(1, 30, rows) / 0.7,
        "str_col": ["foobar"] * rows})
    cfg = {"str_col": {"tooltip_config": {"tooltip_type": "simple",
        "val_column": "int_col"}}}
    return df, cfg


# ---------------------------------------------------------------------------
# Pinned-rows demo — the only example that overrides the default
# ``pinned_rows=[]`` used by every other entry. Documents the
# ``pinned_rows=`` argument by showing a non-default value alongside the
# stats it pins (dtype, histogram, mean, std, min, max).
# ---------------------------------------------------------------------------

PINNED_ROWS_DEMO = [obj_("dtype"), pinned_histogram(), float_("mean", 2), float_("std", 2), inherit_("min"),
    inherit_("max")]


def pinned_rows_fixture():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"int_col": rng.integers(0, 100, 200), "float_col": rng.normal(50, 15, 200),
        "str_col": rng.choice(["alpha", "beta", "gamma"], 200)})
    # No column_config_overrides — this example is only about pinned_rows.
    return df, {}


# (filename, title, fixture_callable, pinned_rows_override)
# pinned_rows_override defaults to [] so the rendered table has no
# summary band — the article's whole point is showing only what the
# column_config does, not the default dtype/histogram pair.
ENTRIES = [
    ("datetime", "Datetime Displayers", datetime_fixture, []),
    ("string", "String Displayer", string_fixture, []),
    ("float", "Float Displayer", float_fixture, []),
    ("link", "Link Displayer", link_fixture, []),
    ("histogram", "Histogram Displayer", histogram_fixture, []),
    ("chart", "Chart Displayer", chart_fixture, []),
    ("image", "Image Displayer", image_fixture, []),
    ("color-map-continuous", "Color Map (Continuous)", color_map_continuous_fixture, []),
    ("color-categorical", "Color Categorical (Explicit Palette)", color_categorical_fixture, []),
    ("color-from-column", "Color From Column", color_from_column_fixture, []),
    ("error-highlight", "Error Highlighting", error_highlight_fixture, []),
    ("tooltip", "Tooltip", tooltip_fixture, []),
    ("pinned-rows", "Pinned Summary Rows", pinned_rows_fixture, PINNED_ROWS_DEMO),
]


def styled_html(df, title, column_config_overrides, pinned_rows):
    artifact = prepare_buckaroo_artifact(
        df, column_config_overrides=column_config_overrides,
        pinned_rows=pinned_rows, embed_type="DFViewer")
    return _HTML_TEMPLATE.format(title=title, artifact_json=artifact_to_json(artifact))


def generate_embed(filename, title, df, column_config_overrides, pinned_rows):
    html = styled_html(df, title, column_config_overrides, pinned_rows)
    path = os.path.join(OUT_DIR, f"{filename}.html")
    with open(path, "w") as f:
        f.write(html)
    print(f"  Generated {path}")


def copy_static_assets():
    import shutil

    static_dir = os.path.join(os.path.dirname(__file__), "..", "buckaroo", "static")
    for fname in ("static-embed.js", "static-embed.css"):
        src = os.path.join(static_dir, fname)
        dst = os.path.join(OUT_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  Copied {fname}")
        else:
            print(f"  WARNING: {src} not found — run full_build.sh first")


if __name__ == "__main__":
    print("Generating column-config styling static embeds...")
    copy_static_assets()
    for filename, title, fixture, pinned_rows in ENTRIES:
        df, cfg = fixture()
        generate_embed(filename, title, df, cfg, pinned_rows)
    print(f"\nDone. Files in {OUT_DIR}")
