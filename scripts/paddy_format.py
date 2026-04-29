"""paddy-format — lisp-style closing-bracket formatter for Python.

Rewrites Python source so that closing brackets ) ] } stack on the same
line as the last token, instead of dangling on their own line in Black/
ruff style. Idempotent.

Usage:
    uv run python scripts/paddy_format.py <files...>           # rewrite in place
    uv run python scripts/paddy_format.py --check <files...>   # exit 1 if changes needed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libcst as cst


def _is_clean_pw(ws) -> bool:
    """True iff `ws` is a ParenthesizedWhitespace (i.e. contains a newline)
    with no comments anywhere. Comments are a hard stop — we never want to
    eat a comment by stacking the close onto the previous line."""
    if not isinstance(ws, cst.ParenthesizedWhitespace):
        return False
    if ws.first_line.comment is not None:
        return False
    for el in ws.empty_lines:
        if el.comment is not None:
            return False
    return True


def _empty():
    return cst.SimpleWhitespace("")


class _PaddyTransformer(cst.CSTTransformer):
    # ----- Type A: newline lives in last_item.comma.whitespace_after -----

    def leave_Call(self, original, updated):
        if not updated.args:
            return updated
        last = updated.args[-1]
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after
        ):
            new_last = last.with_changes(
                comma=cst.MaybeSentinel.DEFAULT,
                whitespace_after_arg=_empty(),
            )
            return updated.with_changes(args=[*updated.args[:-1], new_last])
        if isinstance(last.comma, cst.MaybeSentinel) and _is_clean_pw(
            last.whitespace_after_arg
        ):
            new_last = last.with_changes(whitespace_after_arg=_empty())
            return updated.with_changes(args=[*updated.args[:-1], new_last])
        return updated

    def leave_FunctionDef(self, original, updated):
        params = updated.params
        if not params.params:
            return updated
        last = params.params[-1]
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after
        ):
            new_last = last.with_changes(
                comma=cst.MaybeSentinel.DEFAULT,
                whitespace_after_param=_empty(),
            )
            new_params = params.with_changes(params=[*params.params[:-1], new_last])
            return updated.with_changes(params=new_params)
        return updated

    def leave_ImportFrom(self, original, updated):
        names = updated.names
        if not isinstance(names, (list, tuple)) or not names:
            return updated
        last = names[-1]
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after
        ):
            new_last = last.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            return updated.with_changes(names=tuple([*names[:-1], new_last]))
        return updated

    # ----- Type B: newline lives in close-bracket node's whitespace_before -----

    def leave_List(self, original, updated):
        return self._collection(updated, "rbracket")

    def leave_Set(self, original, updated):
        return self._collection(updated, "rbrace")

    def leave_Dict(self, original, updated):
        return self._collection(updated, "rbrace")

    def leave_Tuple(self, original, updated):
        if not updated.rpar:
            return updated
        rp = updated.rpar[0]
        if not _is_clean_pw(rp.whitespace_before):
            return updated
        new_elements = list(updated.elements)
        if new_elements and isinstance(new_elements[-1].comma, cst.Comma):
            new_elements[-1] = new_elements[-1].with_changes(
                comma=cst.MaybeSentinel.DEFAULT
            )
        new_rp = rp.with_changes(whitespace_before=_empty())
        return updated.with_changes(elements=new_elements, rpar=[new_rp])

    def _collection(self, updated, close_attr):
        close = getattr(updated, close_attr)
        if not _is_clean_pw(close.whitespace_before):
            return updated
        new_elements = list(updated.elements)
        if new_elements and isinstance(new_elements[-1].comma, cst.Comma):
            new_elements[-1] = new_elements[-1].with_changes(
                comma=cst.MaybeSentinel.DEFAULT
            )
        new_close = close.with_changes(whitespace_before=_empty())
        return updated.with_changes(
            elements=new_elements,
            **{close_attr: new_close},
        )


def paddy_format(src: str) -> str:
    """Rewrite Python source to lisp-style stacked closing brackets.

    Idempotent. Returns input unchanged on syntax errors."""
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    return module.visit(_PaddyTransformer()).code


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Lisp-style Python formatter.")
    parser.add_argument("files", nargs="+", type=Path, help="files to format")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any file would be changed; do not write",
    )
    args = parser.parse_args(argv)

    needs_change: list[Path] = []
    for path in args.files:
        original = path.read_text()
        formatted = paddy_format(original)
        if formatted == original:
            continue
        needs_change.append(path)
        if not args.check:
            path.write_text(formatted)
            print(f"reformatted {path}")

    if args.check and needs_change:
        for p in needs_change:
            print(f"would reformat {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
