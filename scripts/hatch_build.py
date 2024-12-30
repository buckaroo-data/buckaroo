"""A Hatchling plugin to build the buckaroo frontend."""
# based on quak

import pathlib
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = pathlib.Path(__file__).parent / ".."


class BuckarooBuildHook(BuildHookInterface):
    """Hatchling plugin to build the buckaroo frontend."""

    PLUGIN_NAME = "buckaroo_hatch"

    def initialize(self, version: str, build_data: dict) -> None:
        """Initialize the plugin."""
        # if os.getenv("SKIP_DENO_BUILD", "0") == "1":
        #     # Skip the build if the environment variable is set
        #     # Useful in CI/CD pipelines
        #     return


        bjs_core_root = ROOT / "packages/buckaroo-js-core"
        if not (bjs_core_root / "dist/index.esm.js").exists():
            subprocess.check_call(["npm", "install"], cwd=bjs_core_root)
            subprocess.check_call(["npm", "run", "build"], cwd=bjs_core_root)
        subprocess.check_call(["npm", "install"], cwd=ROOT)
        subprocess.check_call(["npm", "run", "build"], cwd=ROOT)
