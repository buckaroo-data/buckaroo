#!/usr/bin/env python3
"""Generate static embed HTML pages for the theme customization article.

Produces one HTML file per theme variant in docs/extra-html/themes/,
demonstrating the full range of buckaroo theming options.
"""

import sys
import os

# Ensure the repo root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np

from buckaroo.artifact import (prepare_buckaroo_artifact, artifact_to_json, _HTML_TEMPLATE)


OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "extra-html", "themes")
os.makedirs(OUT_DIR, exist_ok=True)


def sample_df():
    """A small but varied DataFrame for theme demos."""
    np.random.seed(42)
    return pd.DataFrame(
        {
            "city": ["Tokyo", "London", "New York", "Paris", "Sydney", "Berlin", "Toronto", "Mumbai", "Seoul", "Lagos"],
            "population_m": [13.96, 8.98, 8.34, 2.16, 5.31, 3.64, 2.93, 20.67, 9.78, 15.39],
            "area_km2": [2194, 1572, 783, 105, 12368, 892, 630, 603, 605, 1171],
            "founded": [1457, 47, 1624, 250, 1788, 1237, 1793, 1507, 18, 1472],
            "continent": [
                "Asia",
                "Europe",
                "N. America",
                "Europe",
                "Oceania",
                "Europe",
                "N. America",
                "Asia",
                "Asia",
                "Africa"]})


def multiindex_df():
    """A DataFrame with MultiIndex columns — the kind pivot_table produces."""
    cols = pd.MultiIndex.from_tuples(
        [
            ("Revenue", "Q1"),
            ("Revenue", "Q2"),
            ("Revenue", "Q3"),
            ("Headcount", "Engineering"),
            ("Headcount", "Sales"),
            ("Headcount", "Support")],
        names=["Category", "Detail"])
    return pd.DataFrame(
        [
            [1.2, 1.4, 1.8, 45, 12, 8],
            [0.9, 1.1, 1.3, 30, 8, 5],
            [2.1, 2.5, 3.0, 80, 20, 15],
            [0.5, 0.6, 0.7, 15, 5, 3],
            [3.4, 3.8, 4.2, 120, 35, 22]],
        index=pd.Index(
            ["ACME Corp", "Widgets Inc", "MegaTech", "StartupCo", "BigData Ltd"]),
        columns=cols)


def vc_pricing_df():
    """The kind of table you see on a VC-backed SaaS pricing page."""
    return pd.DataFrame(
        {
            "Feature": ["Seats", "Storage", "API calls/mo", "SSO", "Audit log", "Support"],
            "Starter": ["5", "10 GB", "1,000", "No", "No", "Email"],
            "Enterprise": ["Unlimited", "Unlimited", "Unlimited", "Yes", "Yes", "Call us for pricing"]})


def themed_html(df, title, theme_config):
    """Generate a static embed HTML with a theme applied to the artifact."""
    artifact = prepare_buckaroo_artifact(df, embed_type="Buckaroo")

    # Inject theme into the top-level df_viewer_config
    cc = artifact["df_viewer_config"].setdefault("component_config", {})
    cc["theme"] = theme_config

    # Also inject into each display's df_viewer_config so Buckaroo mode picks it up
    for display_args in artifact.get("df_display_args", {}).values():
        dvc = display_args.get("df_viewer_config")
        if dvc is not None:
            dvc.setdefault("component_config", {})["theme"] = theme_config

    return _HTML_TEMPLATE.format(title=title, artifact_json=artifact_to_json(artifact))


# Each entry: (filename, title, theme_config, description[, df_override])
THEME_ENTRIES = [
    ("default-light", "Default (Light)", {}, "No theme overrides — uses the OS-detected light scheme with default colors."),
    ("default-dark", "Default (Dark)", {"colorScheme": "dark"}, "Force dark mode with colorScheme. No explicit colors — uses built-in dark defaults."),
    ("accent-color", "Custom Accent Color", {
        "accentColor": "#ff6600",
        "accentHoverColor": "#cc5200"}, "Override the accent color used for column selection highlights and interactive elements."),
    ("ocean-dark", "Ocean Dark", {
        "colorScheme": "dark",
        "accentColor": "#00bcd4",
        "accentHoverColor": "#0097a7",
        "backgroundColor": "#0a1628",
        "foregroundColor": "#b0bec5",
        "oddRowBackgroundColor": "#0d2137",
        "borderColor": "#1a3a5c"}, "A deep ocean-inspired dark theme with cyan accents."),
    ("warm-light", "Warm Light", {
        "colorScheme": "light",
        "accentColor": "#e65100",
        "accentHoverColor": "#bf360c",
        "backgroundColor": "#fff8f0",
        "foregroundColor": "#3e2723",
        "oddRowBackgroundColor": "#fff3e0",
        "borderColor": "#ffe0b2"}, "A warm, earthy light theme with orange accents."),
    ("neon-dark", "Neon Dark", {
        "colorScheme": "dark",
        "accentColor": "#e91e63",
        "accentHoverColor": "#c2185b",
        "backgroundColor": "#1a1a2e",
        "foregroundColor": "#e0e0e0",
        "oddRowBackgroundColor": "#16213e",
        "borderColor": "#0f3460"}, "A cyberpunk-inspired dark theme with hot pink accents."),
    ("forest-dark", "Forest Dark", {
        "colorScheme": "dark",
        "accentColor": "#66bb6a",
        "accentHoverColor": "#43a047",
        "backgroundColor": "#1b2a1b",
        "foregroundColor": "#c8e6c9",
        "oddRowBackgroundColor": "#223322",
        "borderColor": "#2e7d32"}, "A dark theme with forest green accents — easy on the eyes for long sessions."),
    ("minimal-light", "Minimal Light", {
        "colorScheme": "light",
        "accentColor": "#9e9e9e",
        "accentHoverColor": "#757575",
        "backgroundColor": "#ffffff",
        "foregroundColor": "#212121",
        "oddRowBackgroundColor": "#fafafa",
        "borderColor": "#e0e0e0"}, "A neutral, low-contrast light theme that keeps data front and center."),
    ("high-contrast", "High Contrast", {
        "colorScheme": "dark",
        "accentColor": "#ffff00",
        "accentHoverColor": "#ffd600",
        "backgroundColor": "#000000",
        "foregroundColor": "#ffffff",
        "oddRowBackgroundColor": "#1a1a1a",
        "borderColor": "#ffffff"}, "Maximum contrast for accessibility — bright yellow accents on pure black."),
    ("auto-branded", "Auto Light/Dark (Branded)", {
        "colorScheme": "auto",
        "light": {
            "accentColor": "#e65100",
            "accentHoverColor": "#bf360c",
            "backgroundColor": "#fff8f0",
            "foregroundColor": "#3e2723",
            "oddRowBackgroundColor": "#fff3e0",
            "borderColor": "#ffe0b2"},
        "dark": {
            "accentColor": "#ffab40",
            "accentHoverColor": "#ff9100",
            "backgroundColor": "#1a1209",
            "foregroundColor": "#ffe0b2",
            "oddRowBackgroundColor": "#2a1e0f",
            "borderColor": "#4e342e"}}, "Auto light/dark with separate branded palettes for each scheme."),
    ("spacious", "Spacious Layout", {
        "colorScheme": "dark",
        "accentColor": "#7c4dff",
        "accentHoverColor": "#651fff",
        "spacing": 10,
        "rowVerticalPaddingScale": 1.2,
        "cellHorizontalPaddingScale": 0.8,
        "headerBorderColor": "#7c4dff"}, "Increased spacing, padding, and a purple header border for a more airy layout."),
    ("compact", "Compact Layout", {
        "colorScheme": "light",
        "spacing": 2,
        "rowVerticalPaddingScale": 0.2,
        "cellHorizontalPaddingScale": 0.15,
        "headerBorderColor": "#bdbdbd"}, "Minimal spacing for maximum data density — fits more rows on screen."),
    ("vc-pricing", "VC Pricing Page", {
        "colorScheme": "light",
        "accentColor": "#6c5ce7",
        "accentHoverColor": "#5a4bd1",
        "backgroundColor": "#ffffff",
        "foregroundColor": "#2d3436",
        "oddRowBackgroundColor": "#f8f9ff",
        "borderColor": "#e8e8f0",
        "headerBorderColor": "#6c5ce7",
        "spacing": 16,
        "rowVerticalPaddingScale": 2.0,
        "cellHorizontalPaddingScale": 1.5}, 'The opposite of trader styling. Maximum whitespace, three columns, last column ends with "Call us for pricing".', "vc"),
    ("multiindex-headers", "MultiIndex Headers", {
        "colorScheme": "dark",
        "accentColor": "purple",
        "accentHoverColor": "orange",
        "backgroundColor": "blue",
        "foregroundColor": "teal",
        "oddRowBackgroundColor": "red",
        "borderColor": "pink",
        "headerBorderColor": "green",
        "headerBackgroundColor": "brown"}, "Garish colors so you can see exactly which property targets which piece.", "multiindex")]


def generate_embed(filename, title, df, theme_config):
    """Generate a single themed static embed HTML file."""
    html = themed_html(df, title, theme_config)
    path = os.path.join(OUT_DIR, f"{filename}.html")
    with open(path, "w") as f:
        f.write(html)
    print(f"  Generated {path}")


def copy_static_assets():
    """Copy static-embed.js and static-embed.css into the output directory."""
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


DF_OVERRIDES = {"vc": vc_pricing_df, "multiindex": multiindex_df}


if __name__ == "__main__":
    print("Generating theme customization static embeds...")
    copy_static_assets()
    df = sample_df()
    for entry in THEME_ENTRIES:
        filename, title, theme_config, description = entry[:4]
        df_key = entry[4] if len(entry) > 4 else None
        entry_df = DF_OVERRIDES[df_key]() if df_key else df
        generate_embed(filename, title, entry_df, theme_config)
    print(f"\nDone. Files in {OUT_DIR}")
