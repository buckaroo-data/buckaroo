"""paddy-format — lisp-style closing-bracket formatter for Python.

Rewrites Python source so that closing brackets ) ] } stack on the same
line as the last token, instead of dangling on their own line in Black/
ruff style. Idempotent.

Usage:
    uv run python scripts/paddy_format.py <files...>           # rewrite in place
    uv run python scripts/paddy_format.py --check <files...>   # exit 1 if changes needed
"""
from __future__ import annotations

import sys


def paddy_format(src: str) -> str:
    """Stub — returns input unchanged. Real implementation lands next commit."""
    return src


def main(argv: list[str]) -> int:
    raise NotImplementedError("paddy-format CLI not implemented yet")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
