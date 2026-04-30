"""paddy-format — lisp-style closing-bracket formatter for Python.

Two rules, applied in order to every bracket group (call args, function
parameters, list/set/dict/tuple literals, parenthesized imports):

  1. If the group has a trailing comma, collapse it to a single line and
     drop the trailing comma. Trailing comma is the "this fits" signal
     (the inverse of Black's magic trailing comma).
  2. Else, if the group is multiline, stack the closing bracket on the
     last token's line.

Skipped when a comment lives in the affected whitespace, so we never eat
a comment. Idempotent. Returns input unchanged on syntax errors.

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
    """ParenthesizedWhitespace with no comments anywhere."""
    if not isinstance(ws, cst.ParenthesizedWhitespace):
        return False
    if ws.first_line.comment is not None:
        return False
    for el in ws.empty_lines:
        if el.comment is not None:
            return False
    return True


def _is_clean_ws(ws) -> bool:
    """Any whitespace, clean (no comments). SimpleWhitespace is always clean."""
    if isinstance(ws, cst.SimpleWhitespace):
        return True
    return _is_clean_pw(ws)


def _empty():
    return cst.SimpleWhitespace("")


def _space():
    return cst.SimpleWhitespace(" ")


class _PaddyTransformer(cst.CSTTransformer):
    # ----- Call -----

    def leave_Call(self, original, updated):
        c = self._collapse_call(updated)
        if c is not None:
            return c
        return self._stack_call(updated)

    def _collapse_call(self, updated):
        if not updated.args:
            return None
        last = updated.args[-1]
        if not isinstance(last.comma, cst.Comma):
            return None
        if not _is_clean_ws(updated.whitespace_before_args):
            return None
        for a in updated.args:
            if isinstance(a.comma, cst.Comma) and not _is_clean_ws(
                a.comma.whitespace_after
            ):
                return None
            if not _is_clean_ws(a.whitespace_after_arg):
                return None
        new_args = []
        for i, a in enumerate(updated.args):
            if i == len(updated.args) - 1:
                new_args.append(
                    a.with_changes(
                        comma=cst.MaybeSentinel.DEFAULT,
                        whitespace_after_arg=_empty(),
                    )
                )
            else:
                new_comma = (
                    a.comma.with_changes(whitespace_after=_space())
                    if isinstance(a.comma, cst.Comma)
                    else a.comma
                )
                new_args.append(
                    a.with_changes(
                        comma=new_comma,
                        whitespace_after_arg=_empty(),
                    )
                )
        return updated.with_changes(
            args=new_args,
            whitespace_before_args=_empty(),
        )

    def _stack_call(self, updated):
        if not updated.args:
            return updated
        last = updated.args[-1]
        if isinstance(last.comma, cst.MaybeSentinel) and _is_clean_pw(
            last.whitespace_after_arg
        ):
            new_last = last.with_changes(whitespace_after_arg=_empty())
            return updated.with_changes(args=[*updated.args[:-1], new_last])
        return updated

    # ----- FunctionDef -----

    def leave_FunctionDef(self, original, updated):
        c = self._collapse_funcdef(updated)
        if c is not None:
            return c
        return self._stack_funcdef(updated)

    def _collapse_funcdef(self, updated):
        params = updated.params
        plist = list(params.params)
        if not plist:
            return None
        last = plist[-1]
        if not isinstance(last.comma, cst.Comma):
            return None
        if not _is_clean_ws(updated.whitespace_before_params):
            return None
        for p in plist:
            if isinstance(p.comma, cst.Comma) and not _is_clean_ws(
                p.comma.whitespace_after
            ):
                return None
            if not _is_clean_ws(p.whitespace_after_param):
                return None
        new_plist = []
        for i, p in enumerate(plist):
            if i == len(plist) - 1:
                new_plist.append(
                    p.with_changes(
                        comma=cst.MaybeSentinel.DEFAULT,
                        whitespace_after_param=_empty(),
                    )
                )
            else:
                new_comma = (
                    p.comma.with_changes(whitespace_after=_space())
                    if isinstance(p.comma, cst.Comma)
                    else p.comma
                )
                new_plist.append(
                    p.with_changes(
                        comma=new_comma,
                        whitespace_after_param=_empty(),
                    )
                )
        return updated.with_changes(
            params=params.with_changes(params=new_plist),
            whitespace_before_params=_empty(),
        )

    def _stack_funcdef(self, updated):
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

    # ----- ImportFrom -----

    def leave_ImportFrom(self, original, updated):
        names = updated.names
        if not isinstance(names, (list, tuple)) or not names:
            return updated
        has_parens = isinstance(updated.lpar, cst.LeftParen) and isinstance(
            updated.rpar, cst.RightParen
        )
        last = names[-1]
        if has_parens and isinstance(last.comma, cst.Comma):
            c = self._collapse_importfrom(updated)
            if c is not None:
                return c
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after
        ):
            new_last = last.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            return updated.with_changes(names=tuple([*names[:-1], new_last]))
        return updated

    def _collapse_importfrom(self, updated):
        names = list(updated.names)
        if not _is_clean_ws(updated.lpar.whitespace_after):
            return None
        if not _is_clean_ws(updated.rpar.whitespace_before):
            return None
        for n in names:
            if isinstance(n.comma, cst.Comma) and not _is_clean_ws(
                n.comma.whitespace_after
            ):
                return None
        new_names = []
        for i, n in enumerate(names):
            if i == len(names) - 1:
                new_names.append(n.with_changes(comma=cst.MaybeSentinel.DEFAULT))
            else:
                new_comma = (
                    n.comma.with_changes(whitespace_after=_space())
                    if isinstance(n.comma, cst.Comma)
                    else n.comma
                )
                new_names.append(n.with_changes(comma=new_comma))
        return updated.with_changes(
            names=tuple(new_names),
            lpar=updated.lpar.with_changes(whitespace_after=_empty()),
            rpar=updated.rpar.with_changes(whitespace_before=_empty()),
        )

    # ----- Collections (List, Set, Dict) -----

    def leave_List(self, original, updated):
        return self._handle_collection(updated, "lbracket", "rbracket")

    def leave_Set(self, original, updated):
        return self._handle_collection(updated, "lbrace", "rbrace")

    def leave_Dict(self, original, updated):
        return self._handle_collection(updated, "lbrace", "rbrace")

    def _handle_collection(self, updated, open_attr, close_attr):
        open_node = getattr(updated, open_attr)
        close_node = getattr(updated, close_attr)
        if updated.elements and isinstance(updated.elements[-1].comma, cst.Comma):
            c = self._collapse_collection(
                updated, open_attr, close_attr, open_node, close_node
            )
            if c is not None:
                return c
        if _is_clean_pw(close_node.whitespace_before):
            new_elements = list(updated.elements)
            if new_elements and isinstance(new_elements[-1].comma, cst.Comma):
                new_elements[-1] = new_elements[-1].with_changes(
                    comma=cst.MaybeSentinel.DEFAULT
                )
            new_close = close_node.with_changes(whitespace_before=_empty())
            return updated.with_changes(
                elements=new_elements, **{close_attr: new_close}
            )
        return updated

    def _collapse_collection(
        self, updated, open_attr, close_attr, open_node, close_node
    ):
        elements = list(updated.elements)
        if not _is_clean_ws(open_node.whitespace_after):
            return None
        if not _is_clean_ws(close_node.whitespace_before):
            return None
        for el in elements:
            if isinstance(el.comma, cst.Comma) and not _is_clean_ws(
                el.comma.whitespace_after
            ):
                return None
        new_elements = []
        for i, el in enumerate(elements):
            if i == len(elements) - 1:
                new_elements.append(el.with_changes(comma=cst.MaybeSentinel.DEFAULT))
            else:
                new_comma = (
                    el.comma.with_changes(whitespace_after=_space())
                    if isinstance(el.comma, cst.Comma)
                    else el.comma
                )
                new_elements.append(el.with_changes(comma=new_comma))
        return updated.with_changes(
            elements=new_elements,
            **{
                open_attr: open_node.with_changes(whitespace_after=_empty()),
                close_attr: close_node.with_changes(whitespace_before=_empty()),
            },
        )

    # ----- Tuple (parens are optional) -----

    def leave_Tuple(self, original, updated):
        if not updated.rpar or not updated.lpar:
            return updated
        lp = updated.lpar[0]
        rp = updated.rpar[0]
        if updated.elements and isinstance(updated.elements[-1].comma, cst.Comma):
            c = self._collapse_tuple(updated, lp, rp)
            if c is not None:
                return c
        if _is_clean_pw(rp.whitespace_before):
            new_elements = list(updated.elements)
            if new_elements and isinstance(new_elements[-1].comma, cst.Comma):
                new_elements[-1] = new_elements[-1].with_changes(
                    comma=cst.MaybeSentinel.DEFAULT
                )
            new_rp = rp.with_changes(whitespace_before=_empty())
            return updated.with_changes(elements=new_elements, rpar=[new_rp])
        return updated

    def _collapse_tuple(self, updated, lp, rp):
        elements = list(updated.elements)
        if not _is_clean_ws(lp.whitespace_after):
            return None
        if not _is_clean_ws(rp.whitespace_before):
            return None
        for el in elements:
            if isinstance(el.comma, cst.Comma) and not _is_clean_ws(
                el.comma.whitespace_after
            ):
                return None
        new_elements = []
        for i, el in enumerate(elements):
            if i == len(elements) - 1:
                # Single-element tuple: keep trailing comma (semantic).
                if len(elements) == 1:
                    new_elements.append(el)
                else:
                    new_elements.append(
                        el.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                    )
            else:
                new_comma = (
                    el.comma.with_changes(whitespace_after=_space())
                    if isinstance(el.comma, cst.Comma)
                    else el.comma
                )
                new_elements.append(el.with_changes(comma=new_comma))
        return updated.with_changes(
            elements=new_elements,
            lpar=[lp.with_changes(whitespace_after=_empty())],
            rpar=[rp.with_changes(whitespace_before=_empty())],
        )


def paddy_format(src: str) -> str:
    """Rewrite Python source to lisp-style brackets.

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
