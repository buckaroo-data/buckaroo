"""Lockfile hash comparison — port of lockcheck.sh.

Determines whether CI deps need rebuilding. On 95% of pushes lockfiles
don't change; skip expensive dep install entirely.
"""
import hashlib
import subprocess
from pathlib import Path

HASH_DIR = Path("/opt/ci/logs/.lockcheck-hashes")
LOCKFILES = ["uv.lock", "packages/pnpm-lock.yaml", "pyproject.toml"]


def _hash_path(lockfile: str) -> Path:
    safe_name = lockfile.replace("/", "_") + ".sha256"
    return HASH_DIR / safe_name


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except FileNotFoundError:
        return "missing"
    return h.hexdigest()


def lockcheck_valid() -> bool:
    """Return True if all lockfile hashes match stored values."""
    HASH_DIR.mkdir(parents=True, exist_ok=True)
    for lockfile in LOCKFILES:
        hp = _hash_path(lockfile)
        if not hp.exists():
            return False
        stored = hp.read_text().strip()
        current = _file_hash(lockfile)
        if stored != current:
            return False
    return True


def lockcheck_update() -> None:
    """Store current lockfile hashes."""
    HASH_DIR.mkdir(parents=True, exist_ok=True)
    for lockfile in LOCKFILES:
        hp = _hash_path(lockfile)
        hp.write_text(_file_hash(lockfile) + "\n")


def rebuild_deps() -> None:
    """Rebuild Python venvs and JS node_modules."""
    print("[lockcheck] Rebuilding Python deps...")
    for v in ["3.11", "3.12", "3.13", "3.14"]:
        subprocess.run(
            ["uv", "sync", "--locked", "--dev", "--all-extras", "--no-install-project"],
            env={**__import__("os").environ, "UV_PROJECT_ENVIRONMENT": f"/opt/venvs/{v}"},
            cwd="/repo",
        )

    print("[lockcheck] Rebuilding JS deps...")
    for d in ["packages/node_modules", "packages/js/node_modules",
              "packages/buckaroo-js-core/node_modules"]:
        p = Path("/repo") / d
        if p.exists():
            subprocess.run(["rm", "-rf", str(p)])
    subprocess.run(
        ["pnpm", "install", "--frozen-lockfile", "--store-dir", "/opt/pnpm-store"],
        cwd="/repo/packages",
    )

    print("[lockcheck] Reinstalling Playwright browsers...")
    subprocess.run(["/opt/venvs/3.13/bin/playwright", "install", "chromium"])
    subprocess.run(
        ["pnpm", "exec", "playwright", "install", "chromium"],
        cwd="/repo/packages/buckaroo-js-core",
    )
    print("[lockcheck] Rebuild complete.")
