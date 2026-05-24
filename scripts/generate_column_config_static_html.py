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


# 24x24 PNG smiley — same fixture used by the Marimo gallery.
_PNG_SMILEY = (
    "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlz"
    "AAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURB"
    "VEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kov"
    "IHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00Y"
    "JsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvP"
    "FxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL"
    "0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQ"
    "bqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96Cu"
    "tRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFth"
    "atyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlith"
    "Jtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979"
    "jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9"
    "O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosX"
    "VTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCD"
    "V1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wb"
    "wLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjL"
    "YCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII=")


def image_fixture():
    df = pd.DataFrame({"raw": [_PNG_SMILEY, None], "image": [_PNG_SMILEY, None]})
    cfg = {
        "raw": {"displayer_args": {"displayer": "string", "max_length": 40}},
        "image": {"displayer_args": {"displayer": "Base64PNGImageDisplayer"},
            "ag_grid_specs": {"width": 150}},
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


def color_map_explicit_fixture():
    df = pd.DataFrame({"ten_vals_10_colors": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "ten_vals_5_colors": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "five_vals_10_colors": [0, 1, 2, 3, 4, None, None, None, None, None, None],
        "five_vals_5_colors": [0, 1, 2, 3, 4, None, None, None, None, None, None]})
    c10 = ["green", "blue", "red", "orange", "purple", "brown", "pink",
        "beige", "teal", "gray"]
    c5 = ["green", "blue", "red", "orange", "purple"]
    cfg = {
        "ten_vals_10_colors": {"color_map_config": {"color_rule": "color_map",
            "map_name": c10}},
        "ten_vals_5_colors": {"color_map_config": {"color_rule": "color_map",
            "map_name": c5}},
        "five_vals_10_colors": {"color_map_config": {"color_rule": "color_map",
            "map_name": c10}},
        "five_vals_5_colors": {"color_map_config": {"color_rule": "color_map",
            "map_name": c5}},
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


# (filename, title, fixture_callable)
ENTRIES = [
    ("datetime", "Datetime Displayers", datetime_fixture),
    ("string", "String Displayer", string_fixture),
    ("float", "Float Displayer", float_fixture),
    ("link", "Link Displayer", link_fixture),
    ("histogram", "Histogram Displayer", histogram_fixture),
    ("chart", "Chart Displayer", chart_fixture),
    ("image", "Image Displayer", image_fixture),
    ("color-map-continuous", "Color Map (Continuous)", color_map_continuous_fixture),
    ("color-map-explicit", "Color Map (Explicit Palette)", color_map_explicit_fixture),
    ("color-from-column", "Color From Column", color_from_column_fixture),
    ("error-highlight", "Error Highlighting", error_highlight_fixture),
    ("tooltip", "Tooltip", tooltip_fixture),
]


def styled_html(df, title, column_config_overrides):
    artifact = prepare_buckaroo_artifact(
        df, column_config_overrides=column_config_overrides, embed_type="DFViewer")
    return _HTML_TEMPLATE.format(title=title, artifact_json=artifact_to_json(artifact))


def generate_embed(filename, title, df, column_config_overrides):
    html = styled_html(df, title, column_config_overrides)
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
    for filename, title, fixture in ENTRIES:
        df, cfg = fixture()
        generate_embed(filename, title, df, cfg)
    print(f"\nDone. Files in {OUT_DIR}")
