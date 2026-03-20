"""A Hatchling plugin to build the buckaroo frontend."""
# based on quak

import pathlib
import shutil
import subprocess
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = pathlib.Path(__file__).parent / ".."
STATIC_DIR = ROOT / "buckaroo" / "static"

# Every JS/CSS file that the Python package expects to find at runtime.
# full_build.sh produces the real versions; this hook ensures empty stubs
# exist so that editable installs (uv sync) and Python-only CI jobs work
# without building JS first.
REQUIRED_STUBS = [
    "widget.js",
    "widget.css",
    "compiled.css",
    "standalone.js",
    "standalone.css",
    "static-embed.js",
    "static-embed.css",
]


class BuckarooBuildHook(BuildHookInterface):
    """Hatchling plugin to build the buckaroo frontend."""

    PLUGIN_NAME = "buckaroo_hatch"

    def initialize(self, version: str, build_data: dict) -> None:
        STATIC_DIR.mkdir(exist_ok=True)

        # If widget.js already exists with real content, the JS has been
        # built (by full_build.sh or a previous run) — nothing to do.
        widget_js = STATIC_DIR / "widget.js"
        if widget_js.exists() and widget_js.stat().st_size > 0:
            return

        # For standard (wheel) builds, try building the JS if pnpm is
        # available.  full_build.sh normally handles this before calling
        # uv build, but this is a safety net for bare `uv build`.
        if version == "standard" and shutil.which("pnpm"):
            bjs_core_root = ROOT / "packages" / "buckaroo-js-core"
            if not (bjs_core_root / "dist" / "index.esm.js").exists():
                subprocess.check_call(["pnpm", "install"], cwd=bjs_core_root)
                subprocess.check_call(["pnpm", "run", "build"], cwd=bjs_core_root)
            subprocess.check_call(["pnpm", "install"], cwd=ROOT / "packages")
            subprocess.check_call(
                ["pnpm", "--filter", "buckaroo-widget", "run", "build"],
                cwd=ROOT / "packages",
            )
            return

        # Otherwise (editable installs, or pnpm not available), create
        # empty stubs so the package is importable without JS.
        for name in REQUIRED_STUBS:
            path = STATIC_DIR / name
            if not path.exists():
                path.touch()
