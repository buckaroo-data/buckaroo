"""A Hatchling plugin to build the buckaroo frontend."""
# based on quak

import pathlib
import subprocess
import os
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ROOT = pathlib.Path(__file__).parent / ".."

def list_dir(d):
    files = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
    print(files)

class BuckarooBuildHook(BuildHookInterface):
    """Hatchling plugin to build the buckaroo frontend."""

    PLUGIN_NAME = "buckaroo_hatch"

    def initialize2(self, version: str, build_data: dict) -> None:
        """Initialize the plugin."""
        # if os.getenv("SKIP_DENO_BUILD", "0") == "1":
        #     # Skip the build if the environment variable is set
        #     # Useful in CI/CD pipelines
        #     return


        bjs_core_root = ROOT / "packages/buckaroo-js-core"
        print("ROOT LISTING")
        list_dir(ROOT)

        print("packages listing")
        list_dir(ROOT / "packages")

        print("buckaroo-js-core listing")
        list_dir(ROOT / "packages/buckaroo-js-core")
        
        if not (bjs_core_root / "dist/index.esm.js").exists():
            subprocess.check_call(["pnpm", "install"], cwd=bjs_core_root)
            subprocess.check_call(["pnpm", "run", "build"], cwd=bjs_core_root)
        subprocess.check_call(["pnpm", "install"], cwd=ROOT)
        subprocess.check_call(["pnpm", "run", "build"], cwd=ROOT)
