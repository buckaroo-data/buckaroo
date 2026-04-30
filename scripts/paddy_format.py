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
            if _is_clean_pw(updated.whitespace_before_args):
                return updated.with_changes(whitespace_before_args=_empty())
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
            if _is_clean_pw(updated.whitespace_before_params):
                return updated.with_changes(whitespace_before_params=_empty())
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
        if not updated.elements and _is_clean_pw(open_node.whitespace_after):
            return updated.with_changes(
                **{open_attr: open_node.with_changes(whitespace_after=_empty())}
            )
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


_LINE_BUDGET = 120


def _newline_indent(col: int):
    return cst.ParenthesizedWhitespace(
        first_line=cst.TrailingWhitespace(
            whitespace=cst.SimpleWhitespace(""),
            comment=None,
            newline=cst.Newline(),
        ),
        empty_lines=[],
        indent=False,
        last_line=cst.SimpleWhitespace(" " * col),
    )


def _greedy_pack(
    lens: list[int], first_col: int, continuation_col: int, budget: int
) -> list[list[int]]:
    """Pack item indices into lines. Each non-final line ends with a comma,
    the final line ends with the close bracket.

    first_col: column where the first item starts on the first line (right
    after the open bracket).
    continuation_col: column where items start on continuation lines.

    Returns list of lists of item indices."""
    if not lens:
        return []
    lines: list[list[int]] = []
    cur: list[int] = []
    col = first_col
    for i, alen in enumerate(lens):
        is_last = i == len(lens) - 1
        sep = 0 if not cur else 2  # ", " between items
        # Cost includes the trailing comma (break) or close bracket (last):
        # both are 1 char.
        proposed = col + sep + alen + 1
        if cur and proposed > budget:
            lines.append(cur)
            cur = [i]
            col = continuation_col + alen + (1 if is_last else 0)
        else:
            cur.append(i)
            col += sep + alen + (1 if is_last else 0)
    if cur:
        lines.append(cur)
    return lines


def _arg_render_len(module: cst.Module, arg: cst.Arg) -> int:
    cleaned = arg.with_changes(
        comma=cst.MaybeSentinel.DEFAULT,
        whitespace_after_arg=cst.SimpleWhitespace(""),
    )
    return len(module.code_for_node(cleaned))


def _element_render_len(module: cst.Module, el) -> int:
    cleaned = el.with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return len(module.code_for_node(cleaned))


def _build_wrapped_args(args, groups, indent_col):
    """Apply greedy-pack groups to a sequence of Arg nodes."""
    new_args = []
    for line_idx, indices in enumerate(groups):
        for pos_in_line, i in enumerate(indices):
            arg = args[i]
            is_last_overall = i == len(args) - 1
            is_last_on_line = (
                pos_in_line == len(indices) - 1 and line_idx < len(groups) - 1
            )
            if is_last_overall:
                comma = cst.MaybeSentinel.DEFAULT
            elif is_last_on_line:
                comma = cst.Comma(whitespace_after=_newline_indent(indent_col))
            else:
                comma = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
            new_args.append(
                arg.with_changes(
                    comma=comma,
                    whitespace_after_arg=cst.SimpleWhitespace(""),
                )
            )
    return new_args


def _build_wrapped_elements(elements, groups, indent_col):
    """Apply greedy-pack groups to a sequence of element nodes (List/Dict/etc)."""
    new_elements = []
    for line_idx, indices in enumerate(groups):
        for pos_in_line, i in enumerate(indices):
            el = elements[i]
            is_last_overall = i == len(elements) - 1
            is_last_on_line = (
                pos_in_line == len(indices) - 1 and line_idx < len(groups) - 1
            )
            if is_last_overall:
                comma = cst.MaybeSentinel.DEFAULT
            elif is_last_on_line:
                comma = cst.Comma(whitespace_after=_newline_indent(indent_col))
            else:
                comma = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
            new_elements.append(el.with_changes(comma=comma))
    return new_elements


class _NodeWrapper(cst.CSTTransformer):
    """Wraps a single target node (matched by identity) using greedy pack."""

    def __init__(
        self,
        target,
        first_col: int,
        continuation_col: int,
        module: cst.Module,
        budget: int,
    ):
        super().__init__()
        self.target = target
        self.first_col = first_col
        self.continuation_col = continuation_col
        self.module = module
        self.budget = budget
        self.applied = False

    def _wrap_call(self, updated):
        args = list(updated.args)
        lens = [_arg_render_len(self.module, a) for a in args]
        groups = _greedy_pack(lens, self.first_col, self.continuation_col, self.budget)
        if len(groups) <= 1:
            return None
        new_args = _build_wrapped_args(args, groups, self.continuation_col)
        return updated.with_changes(
            args=new_args,
            whitespace_before_args=cst.SimpleWhitespace(""),
        )

    def _wrap_collection(self, updated, open_attr, close_attr):
        elements = list(updated.elements)
        lens = [_element_render_len(self.module, e) for e in elements]
        groups = _greedy_pack(lens, self.first_col, self.continuation_col, self.budget)
        if len(groups) <= 1:
            return None
        new_elements = _build_wrapped_elements(elements, groups, self.continuation_col)
        open_node = getattr(updated, open_attr)
        close_node = getattr(updated, close_attr)
        return updated.with_changes(
            elements=new_elements,
            **{
                open_attr: open_node.with_changes(
                    whitespace_after=cst.SimpleWhitespace("")
                ),
                close_attr: close_node.with_changes(
                    whitespace_before=cst.SimpleWhitespace("")
                ),
            },
        )

    def leave_Call(self, original, updated):
        if original is not self.target or self.applied:
            return updated
        wrapped = self._wrap_call(updated)
        if wrapped is None:
            return updated
        self.applied = True
        return wrapped

    def leave_List(self, original, updated):
        if original is not self.target or self.applied:
            return updated
        wrapped = self._wrap_collection(updated, "lbracket", "rbracket")
        if wrapped is None:
            return updated
        self.applied = True
        return wrapped

    def leave_Set(self, original, updated):
        if original is not self.target or self.applied:
            return updated
        wrapped = self._wrap_collection(updated, "lbrace", "rbrace")
        if wrapped is None:
            return updated
        self.applied = True
        return wrapped

    def leave_Dict(self, original, updated):
        if original is not self.target or self.applied:
            return updated
        wrapped = self._wrap_collection(updated, "lbrace", "rbrace")
        if wrapped is None:
            return updated
        self.applied = True
        return wrapped


def _open_bracket_first_col(node, positions) -> int | None:
    """Column where first item starts on the first line (right after `(`)."""
    if isinstance(node, cst.Call):
        return positions[node.func].end.column + 1
    if isinstance(node, (cst.List, cst.Set, cst.Dict)):
        return positions[node].start.column + 1
    return None


def _line_indent_plus_4(node, positions, lines) -> int | None:
    """Continuation indent: the leading whitespace count of the line where
    the bracket starts, plus 4."""
    line_idx = positions[node].start.line - 1
    if line_idx < 0 or line_idx >= len(lines):
        return None
    line = lines[line_idx]
    return (len(line) - len(line.lstrip())) + 4


def _is_wrappable(node) -> bool:
    if isinstance(node, cst.Call):
        return len(node.args) >= 2
    if isinstance(node, (cst.List, cst.Set, cst.Dict)):
        return len(node.elements) >= 2
    return False


def _wrap_pass(src: str, budget: int) -> str:
    """Iteratively find an over-budget line and wrap the outermost wrappable
    bracket group whose start sits on that line."""
    while True:
        try:
            module = cst.parse_module(src)
        except cst.ParserSyntaxError:
            return src
        wrapper = cst.metadata.MetadataWrapper(module)
        positions = wrapper.resolve(cst.metadata.PositionProvider)
        module = wrapper.module
        lines = src.splitlines()

        candidates = []
        for node, pos in positions.items():
            if not _is_wrappable(node):
                continue
            line_idx = pos.start.line - 1
            if line_idx >= len(lines):
                continue
            if len(lines[line_idx]) <= budget:
                continue
            first_col = _open_bracket_first_col(node, positions)
            cont_col = _line_indent_plus_4(node, positions, lines)
            if first_col is None or cont_col is None:
                continue
            candidates.append((node, pos, first_col, cont_col))

        if not candidates:
            return src

        # Outermost first (leftmost start column, then earliest line)
        candidates.sort(key=lambda x: (x[1].start.line, x[1].start.column))
        progressed = False
        for target, pos, first_col, cont_col in candidates:
            wrapper_t = _NodeWrapper(target, first_col, cont_col, module, budget)
            new_module = module.visit(wrapper_t)
            if not wrapper_t.applied:
                continue
            new_src = new_module.code
            if new_src != src:
                src = new_src
                progressed = True
                break
        if not progressed:
            return src


def _reindent_pw(ws, indent: int):
    """Replace the last_line of a clean ParenthesizedWhitespace with `indent`
    spaces. Skips PWs with comments or empty_lines (don't touch annotated
    blank-space). Returns ws unchanged if not a clean PW."""
    if not _is_clean_pw(ws):
        return ws
    if ws.empty_lines:
        return ws
    return ws.with_changes(
        first_line=ws.first_line.with_changes(whitespace=cst.SimpleWhitespace("")),
        indent=False,
        last_line=cst.SimpleWhitespace(" " * indent),
    )


class _Reindenter(cst.CSTTransformer):
    """Re-indents continuation lines of pre-marked multi-line bracket groups
    to a fixed `indent` column. Targets are matched by id() of original nodes."""

    def __init__(self, targets: dict[int, int]):
        super().__init__()
        self.targets = targets

    def leave_Call(self, original, updated):
        indent = self.targets.get(id(original))
        if indent is None:
            return updated
        new_args = []
        for arg in updated.args:
            new_arg = arg
            if isinstance(arg.comma, cst.Comma):
                new_arg = new_arg.with_changes(
                    comma=arg.comma.with_changes(
                        whitespace_after=_reindent_pw(
                            arg.comma.whitespace_after, indent
                        )
                    )
                )
            if isinstance(arg.whitespace_after_arg, cst.ParenthesizedWhitespace):
                new_arg = new_arg.with_changes(
                    whitespace_after_arg=_reindent_pw(arg.whitespace_after_arg, indent)
                )
            new_args.append(new_arg)
        return updated.with_changes(
            args=new_args,
            whitespace_before_args=_reindent_pw(updated.whitespace_before_args, indent),
        )

    def _leave_collection(self, original, updated):
        indent = self.targets.get(id(original))
        if indent is None:
            return updated
        new_elements = []
        for el in updated.elements:
            new_el = el
            if isinstance(el.comma, cst.Comma):
                new_el = el.with_changes(
                    comma=el.comma.with_changes(
                        whitespace_after=_reindent_pw(el.comma.whitespace_after, indent)
                    )
                )
            new_elements.append(new_el)
        return updated.with_changes(elements=new_elements)

    def leave_List(self, original, updated):
        return self._leave_collection(original, updated)

    def leave_Set(self, original, updated):
        return self._leave_collection(original, updated)

    def leave_Dict(self, original, updated):
        return self._leave_collection(original, updated)


def _reindent_pass(src: str) -> str:
    """For each multi-line bracket group, re-indent continuation lines to
    line_indent + 4. Skips groups containing comments in their inner
    whitespace (handled in _reindent_pw)."""
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    wrapper = cst.metadata.MetadataWrapper(module)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    module = wrapper.module
    lines = src.splitlines()

    targets: dict[int, int] = {}
    for node, pos in positions.items():
        if not isinstance(node, (cst.Call, cst.List, cst.Set, cst.Dict)):
            continue
        if pos.start.line == pos.end.line:
            continue
        indent = _line_indent_plus_4(node, positions, lines)
        if indent is None:
            continue
        targets[id(node)] = indent

    if not targets:
        return src
    new_module = module.visit(_Reindenter(targets))
    return new_module.code


def paddy_format(src: str) -> str:
    """Rewrite Python source to lisp-style brackets.

    Idempotent. Returns input unchanged on syntax errors."""
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    src = module.visit(_PaddyTransformer()).code
    src = _reindent_pass(src)
    src = _wrap_pass(src, _LINE_BUDGET)
    return src


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
