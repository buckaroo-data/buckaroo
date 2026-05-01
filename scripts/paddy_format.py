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


def _items_collapsible(items, open_ws, post_attr) -> bool:
    """Whether a comma-separated item list (Args, Params, Elements, or
    ImportAliases) can be collapsed to a single line: trailing comma
    present and no comments anywhere in the open-side whitespace, the
    per-item comma whitespace, or the per-item post whitespace (when the
    item type carries one — Arg.whitespace_after_arg /
    Param.whitespace_after_param)."""
    if not items:
        return False
    if not isinstance(items[-1].comma, cst.Comma):
        return False
    if not _is_clean_ws(open_ws):
        return False
    for it in items:
        if isinstance(it.comma, cst.Comma) and not _is_clean_ws(
            it.comma.whitespace_after):
            return False
        if post_attr is not None and not _is_clean_ws(getattr(it, post_attr)):
            return False
    return True


def _iter_param_slots(params: cst.Parameters):
    """Yield (kind, item) over every comma-bearing slot in a Parameters
    node, in source order: posonly_params, posonly_ind (`/`), params,
    star_arg (`*` or `*args`), kwonly_params, star_kwarg (`**kwargs`).
    Each slot has a `comma` field; only Param has `whitespace_after_param`.
    Empty / MaybeSentinel.DEFAULT slots are skipped."""
    for p in params.posonly_params:
        yield "posonly", p
    if isinstance(params.posonly_ind, cst.ParamSlash):
        yield "posslash", params.posonly_ind
    for p in params.params:
        yield "param", p
    if isinstance(params.star_arg, (cst.ParamStar, cst.Param)):
        yield "star", params.star_arg
    for p in params.kwonly_params:
        yield "kwonly", p
    if params.star_kwarg is not None:
        yield "starkwarg", params.star_kwarg


def _collapse_items(items, post_attr, preserve_singleton_comma: bool = False):
    """Rebuild items as a single-line sequence: every non-last comma
    becomes `, `, last comma drops to MaybeSentinel.DEFAULT.
    `post_attr`, when given, is cleared on every item.
    `preserve_singleton_comma` keeps the trailing comma on a length-1
    sequence — required for tuples (`(x,)` vs `(x)` differ in meaning)."""
    new_items = []
    for i, it in enumerate(items):
        is_last = i == len(items) - 1
        if is_last and preserve_singleton_comma and len(items) == 1:
            new_items.append(it)
            continue
        if is_last:
            changes = {"comma": cst.MaybeSentinel.DEFAULT}
        else:
            new_comma = (
                it.comma.with_changes(whitespace_after=_space())
                if isinstance(it.comma, cst.Comma)
                else it.comma
            )
            changes = {"comma": new_comma}
        if post_attr is not None:
            changes[post_attr] = _empty()
        new_items.append(it.with_changes(**changes))
    return new_items


class _PaddyTransformer(cst.CSTTransformer):
    def __init__(self, tabular_ids: set[int] | None = None):
        super().__init__()
        self.tabular_ids = tabular_ids or set()

    # ----- Call -----

    def leave_Call(self, original, updated):
        if id(original) in self.tabular_ids:
            return updated
        c = self._collapse_call(updated)
        if c is not None:
            return c
        return self._stack_call(updated)

    def _collapse_call(self, updated):
        if not updated.args:
            if _is_clean_pw(updated.whitespace_before_args):
                return updated.with_changes(whitespace_before_args=_empty())
            return None
        if not _items_collapsible(
            updated.args, updated.whitespace_before_args, "whitespace_after_arg"):
            return None
        return updated.with_changes(args=_collapse_items(updated.args, "whitespace_after_arg"),
            whitespace_before_args=_empty())

    def _stack_call(self, updated):
        if not updated.args:
            return updated
        last = updated.args[-1]
        if isinstance(last.comma, cst.MaybeSentinel) and _is_clean_pw(
            last.whitespace_after_arg):
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
        slots = list(_iter_param_slots(params))
        if not slots:
            if _is_clean_pw(updated.whitespace_before_params):
                return updated.with_changes(whitespace_before_params=_empty())
            return None
        # Need a trailing comma on the very last slot to trigger collapse.
        last_kind, last_item = slots[-1]
        if not isinstance(last_item.comma, cst.Comma):
            return None
        if not _is_clean_ws(updated.whitespace_before_params):
            return None
        for _, it in slots:
            if isinstance(it.comma, cst.Comma) and not _is_clean_ws(
                it.comma.whitespace_after):
                return None
            if isinstance(it, cst.Param) and not _is_clean_ws(
                it.whitespace_after_param):
                return None
        new_slots = []
        for i, (kind, it) in enumerate(slots):
            is_last = i == len(slots) - 1
            if is_last:
                changes = {"comma": cst.MaybeSentinel.DEFAULT}
            else:
                new_comma = (
                    it.comma.with_changes(whitespace_after=_space())
                    if isinstance(it.comma, cst.Comma)
                    else it.comma
                )
                changes = {"comma": new_comma}
            if isinstance(it, cst.Param):
                changes["whitespace_after_param"] = _empty()
            new_slots.append((kind, it.with_changes(**changes)))
        new_params = params.with_changes(posonly_params=tuple(it for k, it in new_slots if k == "posonly"),
            posonly_ind=next(
                (it for k, it in new_slots if k == "posslash"), params.posonly_ind),
            params=tuple(it for k, it in new_slots if k == "param"),
            star_arg=next((it for k, it in new_slots if k == "star"), params.star_arg),
            kwonly_params=tuple(it for k, it in new_slots if k == "kwonly"),
            star_kwarg=next(
                (it for k, it in new_slots if k == "starkwarg"), params.star_kwarg))
        return updated.with_changes(params=new_params, whitespace_before_params=_empty())

    def _stack_funcdef(self, updated):
        params = updated.params
        if not params.params:
            return updated
        last = params.params[-1]
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after):
            new_last = last.with_changes(comma=cst.MaybeSentinel.DEFAULT, whitespace_after_param=_empty())
            new_params = params.with_changes(params=[*params.params[:-1], new_last])
            return updated.with_changes(params=new_params)
        return updated

    # ----- ImportFrom -----

    def leave_ImportFrom(self, original, updated):
        names = updated.names
        if not isinstance(names, (list, tuple)) or not names:
            return updated
        has_parens = isinstance(updated.lpar, cst.LeftParen) and isinstance(
            updated.rpar, cst.RightParen)
        last = names[-1]
        if has_parens and isinstance(last.comma, cst.Comma):
            c = self._collapse_importfrom(updated)
            if c is not None:
                return c
        if isinstance(last.comma, cst.Comma) and _is_clean_pw(
            last.comma.whitespace_after):
            new_last = last.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            return updated.with_changes(names=tuple([*names[:-1], new_last]))
        return updated

    def _collapse_importfrom(self, updated):
        if not _is_clean_ws(updated.rpar.whitespace_before):
            return None
        if not _items_collapsible(updated.names, updated.lpar.whitespace_after, None):
            return None
        return updated.with_changes(
            names=tuple(_collapse_items(updated.names, None)),
            lpar=updated.lpar.with_changes(whitespace_after=_empty()),
            rpar=updated.rpar.with_changes(whitespace_before=_empty()),
        )

    # ----- Collections (List, Set, Dict) -----

    def leave_List(self, original, updated):
        if id(original) in self.tabular_ids:
            return updated
        return self._handle_collection(updated, "lbracket", "rbracket")

    def leave_Set(self, original, updated):
        if id(original) in self.tabular_ids:
            return updated
        return self._handle_collection(updated, "lbrace", "rbrace")

    def leave_Dict(self, original, updated):
        if id(original) in self.tabular_ids:
            return updated
        return self._handle_collection(updated, "lbrace", "rbrace")

    def _handle_collection(self, updated, open_attr, close_attr):
        open_node = getattr(updated, open_attr)
        close_node = getattr(updated, close_attr)
        if not updated.elements and _is_clean_pw(open_node.whitespace_after):
            return updated.with_changes(
                **{open_attr: open_node.with_changes(whitespace_after=_empty())})
        if updated.elements and isinstance(updated.elements[-1].comma, cst.Comma):
            c = self._collapse_collection(
                updated, open_attr, close_attr, open_node, close_node)
            if c is not None:
                return c
        if _is_clean_pw(close_node.whitespace_before):
            new_elements = list(updated.elements)
            if new_elements and isinstance(new_elements[-1].comma, cst.Comma):
                new_elements[-1] = new_elements[-1].with_changes(
                    comma=cst.MaybeSentinel.DEFAULT)
            new_close = close_node.with_changes(whitespace_before=_empty())
            return updated.with_changes(
                elements=new_elements, **{close_attr: new_close})
        return updated

    def _collapse_collection(
        self, updated, open_attr, close_attr, open_node, close_node
    ):
        if not _is_clean_ws(close_node.whitespace_before):
            return None
        if not _items_collapsible(updated.elements, open_node.whitespace_after, None):
            return None
        return updated.with_changes(elements=_collapse_items(updated.elements, None),
            **{open_attr: open_node.with_changes(whitespace_after=_empty()),
               close_attr: close_node.with_changes(whitespace_before=_empty())})

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
                    comma=cst.MaybeSentinel.DEFAULT)
            new_rp = rp.with_changes(whitespace_before=_empty())
            return updated.with_changes(elements=new_elements, rpar=[new_rp])
        return updated

    def _collapse_tuple(self, updated, lp, rp):
        if not _is_clean_ws(rp.whitespace_before):
            return None
        if not _items_collapsible(updated.elements, lp.whitespace_after, None):
            return None
        return updated.with_changes(elements=_collapse_items(
            updated.elements, None, preserve_singleton_comma=True), lpar=[lp.with_changes(whitespace_after=_empty())], rpar=[rp.with_changes(whitespace_before=_empty())])


_LINE_BUDGET = 120


def _newline_indent(col: int):
    return cst.ParenthesizedWhitespace(first_line=cst.TrailingWhitespace(whitespace=cst.SimpleWhitespace(""),
        comment=None, newline=cst.Newline()),
        empty_lines=[], indent=False, last_line=cst.SimpleWhitespace(" " * col))


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
    cleaned = arg.with_changes(comma=cst.MaybeSentinel.DEFAULT, whitespace_after_arg=cst.SimpleWhitespace(""))
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
                arg.with_changes(comma=comma, whitespace_after_arg=cst.SimpleWhitespace("")))
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
    """Wraps a single target node (matched by identity).

    `wrap_mode` selects the packing strategy:
      - "greedy": fit as many items per line as the budget allows
      - "one_per_line": every item on its own line at continuation_col
    """

    def __init__(self, target, first_col: int, continuation_col: int, module: cst.Module, budget: int,
            wrap_mode: str = "greedy"):
        super().__init__()
        self.target = target
        self.first_col = first_col
        self.continuation_col = continuation_col
        self.module = module
        self.budget = budget
        self.wrap_mode = wrap_mode
        self.applied = False

    def _pack(self, lens):
        if self.wrap_mode == "one_per_line":
            return [[i] for i in range(len(lens))]
        return _greedy_pack(lens, self.first_col, self.continuation_col, self.budget)

    def _open_ws(self):
        """Whitespace right after the open bracket. In one_per_line mode,
        even item 1 goes on its own line at continuation_col."""
        if self.wrap_mode == "one_per_line":
            return _newline_indent(self.continuation_col)
        return cst.SimpleWhitespace("")

    def _wrap_call(self, updated):
        args = list(updated.args)
        lens = [_arg_render_len(self.module, a) for a in args]
        groups = self._pack(lens)
        if len(groups) <= 1:
            return None
        new_args = _build_wrapped_args(args, groups, self.continuation_col)
        return updated.with_changes(args=new_args, whitespace_before_args=self._open_ws())

    def _wrap_collection(self, updated, open_attr, close_attr):
        elements = list(updated.elements)
        lens = [_element_render_len(self.module, e) for e in elements]
        groups = self._pack(lens)
        if len(groups) <= 1:
            return None
        new_elements = _build_wrapped_elements(elements, groups, self.continuation_col)
        open_node = getattr(updated, open_attr)
        close_node = getattr(updated, close_attr)
        return updated.with_changes(elements=new_elements,
            **{open_attr: open_node.with_changes(whitespace_after=self._open_ws()),
               close_attr: close_node.with_changes(whitespace_before=cst.SimpleWhitespace(""))})

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

    def _slot_render_len(self, kind, item) -> int:
        changes = {"comma": cst.MaybeSentinel.DEFAULT}
        if isinstance(item, cst.Param):
            changes["whitespace_after_param"] = cst.SimpleWhitespace("")
        cleaned = item.with_changes(**changes)
        return len(self.module.code_for_node(cleaned))

    def _wrap_funcdef(self, updated):
        params = updated.params
        slots = list(_iter_param_slots(params))
        if len(slots) < 2:
            return None
        lens = [self._slot_render_len(k, it) for k, it in slots]
        groups = self._pack(lens)
        if len(groups) <= 1:
            return None
        new_slots: list[tuple[str, object]] = []
        for line_idx, indices in enumerate(groups):
            for pos_in_line, i in enumerate(indices):
                kind, it = slots[i]
                is_last_overall = i == len(slots) - 1
                is_last_on_line = (
                    pos_in_line == len(indices) - 1 and line_idx < len(groups) - 1)
                if is_last_overall:
                    new_comma = cst.MaybeSentinel.DEFAULT
                elif is_last_on_line:
                    new_comma = cst.Comma(whitespace_after=_newline_indent(self.continuation_col))
                else:
                    new_comma = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                changes: dict = {"comma": new_comma}
                if isinstance(it, cst.Param):
                    changes["whitespace_after_param"] = cst.SimpleWhitespace("")
                new_slots.append((kind, it.with_changes(**changes)))
        new_params = params.with_changes(
            posonly_params=tuple(it for k, it in new_slots if k == "posonly"),
            posonly_ind=next((it for k, it in new_slots if k == "posslash"), params.posonly_ind),
            params=tuple(it for k, it in new_slots if k == "param"),
            star_arg=next((it for k, it in new_slots if k == "star"), params.star_arg),
            kwonly_params=tuple(it for k, it in new_slots if k == "kwonly"),
            star_kwarg=next((it for k, it in new_slots if k == "starkwarg"), params.star_kwarg))
        return updated.with_changes(params=new_params, whitespace_before_params=self._open_ws())

    def leave_FunctionDef(self, original, updated):
        if original is not self.target or self.applied:
            return updated
        wrapped = self._wrap_funcdef(updated)
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
    if isinstance(node, cst.FunctionDef):
        return positions[node.params].start.column
    return None


def _line_indent_plus_4(node, positions, lines) -> int | None:
    """Continuation indent: the leading whitespace count of the line where
    the bracket starts, plus 4."""
    line_idx = positions[node].start.line - 1
    if line_idx < 0 or line_idx >= len(lines):
        return None
    line = lines[line_idx]
    return (len(line) - len(line.lstrip())) + 4


def _continuation_col(node, positions, lines) -> int | None:
    """Where wrapped continuation lines start.

    - FunctionDef: line_indent + 8 (args distinct from body, which is at
      line_indent + 4 — PEP 8 hanging-indent guidance).
    - Call/List/Set/Dict: min(line_indent + 4, col_after_open_bracket).
      When the open bracket is "shallow" (close to line start), aligning
      with col_after_open avoids leaving item 1 (which sits at that col)
      visually offset from items 2..N. When the open bracket is deep
      (e.g. `result = some_function_name(`), line_indent + 4 wins."""
    base = _line_indent_plus_4(node, positions, lines)
    if base is None:
        return None
    if isinstance(node, cst.FunctionDef):
        return base + 4
    open_col = _open_bracket_first_col(node, positions)
    if open_col is None:
        return base
    return min(base, open_col)


def _is_tabular_layout(node, positions, lines) -> bool:
    """Detect "tabular hanging-indent" layout: the open bracket is at
    end of line, every child sits on its own line at the same column N,
    and N is none of the canonical column choices (line_indent + 4,
    col_after_open_bracket, or line_indent + 8 for FunctionDef). The
    user has deliberately chosen a non-canonical column to align the
    children (e.g. so multiple sibling dicts present as comparable
    tables). Skip collapse / wrap / re-indent on these — leave the
    layout alone."""
    if isinstance(node, cst.Call):
        children = node.args
    elif isinstance(node, (cst.List, cst.Set, cst.Dict)):
        children = node.elements
    else:
        return False
    if len(children) < 2:
        return False
    pos = positions[node]
    cols: list[int] = []
    prev_line = pos.start.line
    for c in children:
        target = c.key if isinstance(c, cst.DictElement) else c.value
        cpos = positions[target]
        if cpos.start.line == prev_line:
            return False
        cols.append(cpos.start.column)
        prev_line = cpos.start.line
    # Tolerate up to 1-col variance so a single off-by-one typo in an
    # otherwise tabular dict still gets recognised (real cases in the
    # codebase have minor misalignments).
    if max(cols) - min(cols) > 1:
        return False
    target_col = max(set(cols), key=cols.count)
    canonicals = set()
    plus_4 = _line_indent_plus_4(node, positions, lines)
    if plus_4 is not None:
        canonicals.add(plus_4)
        if isinstance(node, cst.FunctionDef):
            canonicals.add(plus_4 + 4)
    after_open = _open_bracket_first_col(node, positions)
    if after_open is not None:
        canonicals.add(after_open)
    if target_col in canonicals:
        return False
    return True


def _has_multiline_values(node, positions) -> bool:
    """Dict with 2+ items where any value spans multiple lines.
    Collapsing such a Dict would jam keys onto the previous value's
    close-brace line, making the keys hard to spot. Treat as user-
    formatted and skip collapse / wrap / re-indent."""
    if not isinstance(node, cst.Dict):
        return False
    if len(node.elements) < 2:
        return False
    for el in node.elements:
        if not isinstance(el, cst.DictElement):
            continue
        vpos = positions.get(el.value)
        if vpos is None:
            continue
        if vpos.start.line != vpos.end.line:
            return True
    return False


def _is_user_formatted(node, positions, lines) -> bool:
    """Combined predicate: tabular hanging-indent OR dict with
    multi-line values. Both cases are layouts the user has clearly
    chosen and the formatter should leave alone."""
    return (_is_tabular_layout(node, positions, lines)
        or _has_multiline_values(node, positions))


class _WrappableCollector(cst.CSTVisitor):
    """Collects every Call/List/Set/Dict node within a subtree."""

    def __init__(self):
        super().__init__()
        self.found: list = []

    def visit_Call(self, node):
        self.found.append(node)

    def visit_List(self, node):
        self.found.append(node)

    def visit_Set(self, node):
        self.found.append(node)

    def visit_Dict(self, node):
        self.found.append(node)


def _collect_wrappables(node) -> list:
    v = _WrappableCollector()
    node.visit(v)
    return v.found


class _FStringDescendantCollector(cst.CSTVisitor):
    """Collect every wrappable node (Call/List/Set/Dict) whose ancestor
    is a FormattedString. Wrapping inside an f-string would insert a
    newline inside the expression, which is a SyntaxError on Python 3.11
    (PEP 701 multi-line f-strings only landed in 3.12)."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.ids: set[int] = set()

    def visit_FormattedString(self, n):
        self.depth += 1

    def leave_FormattedString(self, n):
        self.depth -= 1

    def _maybe_add(self, n):
        if self.depth > 0:
            self.ids.add(id(n))

    def visit_Call(self, n):
        self._maybe_add(n)

    def visit_List(self, n):
        self._maybe_add(n)

    def visit_Set(self, n):
        self._maybe_add(n)

    def visit_Dict(self, n):
        self._maybe_add(n)


def _find_fstring_descendants(module) -> set[int]:
    v = _FStringDescendantCollector()
    module.visit(v)
    return v.ids


def _find_tabular_layouts(module, positions, lines) -> set[int]:
    ids: set[int] = set()
    for node in positions:
        if _is_user_formatted(node, positions, lines):
            ids.add(id(node))
    # Propagate: when a Dict has multi-line values, ALL nested wrappable
    # nodes within those values are part of the user-chosen layout.
    # Don't apply any transformation (collapse/stack/wrap/re-indent) to
    # them. Recursive walk handles cases like
    #   {'k': pd.to_timedelta(['a', 'b',\n                              'c'])}
    # where the multi-line continuation lives inside a Call's List arg.
    for node in list(positions):
        if not isinstance(node, cst.Dict):
            continue
        if not _has_multiline_values(node, positions):
            continue
        for el in node.elements:
            if not isinstance(el, cst.DictElement):
                continue
            for inner in _collect_wrappables(el.value):
                ids.add(id(inner))
    return ids


def _is_wrappable(node) -> bool:
    if isinstance(node, cst.Call):
        return len(node.args) >= 2
    if isinstance(node, (cst.List, cst.Set, cst.Dict)):
        return len(node.elements) >= 2
    if isinstance(node, cst.FunctionDef):
        return sum(1 for _ in _iter_param_slots(node.params)) >= 2
    return False


def _wrap_pass(src: str, budget: int, wrap_mode: str = "greedy") -> str:
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
        skip_ids = _find_tabular_layouts(module, positions, lines)
        skip_ids |= _find_fstring_descendants(module)

        candidates = []
        for node, pos in positions.items():
            if not _is_wrappable(node):
                continue
            line_idx = pos.start.line - 1
            if line_idx >= len(lines):
                continue
            if len(lines[line_idx]) <= budget:
                continue
            if id(node) in skip_ids:
                continue
            first_col = _open_bracket_first_col(node, positions)
            cont_col = _continuation_col(node, positions, lines)
            if first_col is None or cont_col is None:
                continue
            candidates.append((node, pos, first_col, cont_col))

        if not candidates:
            return src

        # Outermost first (leftmost start column, then earliest line)
        candidates.sort(key=lambda x: (x[1].start.line, x[1].start.column))
        progressed = False
        for target, pos, first_col, cont_col in candidates:
            wrapper_t = _NodeWrapper(target, first_col, cont_col, module, budget,
                wrap_mode=wrap_mode)
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
    return ws.with_changes(first_line=ws.first_line.with_changes(whitespace=cst.SimpleWhitespace("")), indent=False,
        last_line=cst.SimpleWhitespace(" " * indent))


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
        last_idx = len(updated.args) - 1
        for i, arg in enumerate(updated.args):
            new_arg = arg
            # Skip the last arg's comma: its whitespace_after sits before
            # the close bracket, not before another arg. When a comment
            # blocked collapse and left the close on its own line at the
            # user's chosen indent, reindenting here would relocate it.
            if isinstance(arg.comma, cst.Comma) and i != last_idx:
                new_arg = new_arg.with_changes(
                    comma=arg.comma.with_changes(
                        whitespace_after=_reindent_pw(
                            arg.comma.whitespace_after, indent)))
            if isinstance(arg.whitespace_after_arg, cst.ParenthesizedWhitespace):
                new_arg = new_arg.with_changes(
                    whitespace_after_arg=_reindent_pw(arg.whitespace_after_arg, indent))
            new_args.append(new_arg)
        return updated.with_changes(args=new_args,
            whitespace_before_args=_reindent_pw(updated.whitespace_before_args, indent))

    def _leave_collection(self, original, updated):
        indent = self.targets.get(id(original))
        if indent is None:
            return updated
        new_elements = []
        last_idx = len(updated.elements) - 1
        for i, el in enumerate(updated.elements):
            new_el = el
            if isinstance(el.comma, cst.Comma) and i != last_idx:
                new_el = el.with_changes(
                    comma=el.comma.with_changes(
                        whitespace_after=_reindent_pw(el.comma.whitespace_after, indent)))
            new_elements.append(new_el)
        return updated.with_changes(elements=new_elements)

    def leave_List(self, original, updated):
        return self._leave_collection(original, updated)

    def leave_Set(self, original, updated):
        return self._leave_collection(original, updated)

    def leave_Dict(self, original, updated):
        return self._leave_collection(original, updated)


def _has_aligned_hanging_indent(node, positions) -> bool:
    """True iff the bracket group has its first child inline with the
    opening bracket AND every subsequent child starts a new line at the
    same column as the first child. This is the "hanging indent aligned
    with item 1" pattern — re-indent should leave it alone instead of
    shifting items 2..N to line_indent + 4 (which would offset them from
    item 1)."""
    pos = positions[node]
    if isinstance(node, cst.Call):
        children = node.args
    else:
        children = node.elements
    if len(children) < 2:
        return False
    first_pos = positions[children[0].value]
    if first_pos.start.line != pos.start.line:
        return False
    target_col = first_pos.start.column
    prev_line = first_pos.start.line
    for c in children[1:]:
        cpos = positions[c.value]
        if cpos.start.line == prev_line:
            return False
        if cpos.start.column != target_col:
            return False
        prev_line = cpos.start.line
    return True


def _has_blank_line_subgroups(node) -> bool:
    """True iff any inter-element / inter-arg whitespace inside the bracket
    group carries empty_lines (= the user has used blank lines to structure
    the group). `_reindent_pw` already declines to touch such whitespace,
    which on its own causes the rest of the group to be re-indented while
    the blank-line-bordered elements stay put — half-formatting. When this
    pattern is present, leave the whole group's continuation alone."""
    if isinstance(node, cst.Call):
        children = node.args
    elif isinstance(node, (cst.List, cst.Set, cst.Dict)):
        children = node.elements
    else:
        return False
    for c in children:
        if isinstance(c.comma, cst.Comma):
            ws = c.comma.whitespace_after
            if isinstance(ws, cst.ParenthesizedWhitespace) and ws.empty_lines:
                return True
    return False


def _reindent_pass_once(src: str) -> str:
    """Single sweep: for each multi-line bracket group, re-indent
    continuation lines to line_indent + 4 based on the *current* source.
    Outer groups can shift the line a nested group sits on; that's why
    `_reindent_pass` wraps this in a fixed-point loop."""
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    wrapper = cst.metadata.MetadataWrapper(module)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    module = wrapper.module
    lines = src.splitlines()
    skip_ids = _find_tabular_layouts(module, positions, lines)

    targets: dict[int, int] = {}
    for node, pos in positions.items():
        if not isinstance(node, (cst.Call, cst.List, cst.Set, cst.Dict)):
            continue
        if pos.start.line == pos.end.line:
            continue
        if _has_aligned_hanging_indent(node, positions):
            continue
        if _has_blank_line_subgroups(node):
            continue
        if id(node) in skip_ids:
            continue
        indent = _continuation_col(node, positions, lines)
        if indent is None:
            continue
        targets[id(node)] = indent

    if not targets:
        return src
    new_module = module.visit(_Reindenter(targets))
    return new_module.code


def _reindent_pass(src: str) -> str:
    """Re-indent multi-line bracket groups to line_indent + 4. Iterates
    until the source stops changing — when an outer group's continuation
    is re-indented, an inner group's reference line shifts, so a single
    sweep can leave the inner group pointing at the old position."""
    last = None
    while src != last:
        last = src
        src = _reindent_pass_once(src)
    return src


# ---------------------------------------------------------------------------
# `# table-format` directive
# ---------------------------------------------------------------------------


def _atom_text(node) -> str | None:
    """Render a value node (Integer / Float / negated number / Tuple / Dict /
    SimpleString / Name) to its source-text form. Returns None if the node
    is not a recognised atom we can table-format."""
    if isinstance(node, (cst.Integer, cst.Float)):
        return node.value
    if isinstance(node, cst.UnaryOperation) and isinstance(
        node.operator, (cst.Plus, cst.Minus)):
        inner = _atom_text(node.expression)
        if inner is None:
            return None
        sign = "-" if isinstance(node.operator, cst.Minus) else "+"
        return sign + inner
    if isinstance(node, cst.Tuple):
        items = [_atom_text(e.value) for e in node.elements]
        if any(x is None for x in items):
            return None
        return "(" + ", ".join(items) + ")"
    if isinstance(node, cst.SimpleString):
        return node.value
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Dict):
        items = []
        for de in node.elements:
            if not isinstance(de, cst.DictElement):
                return None
            k = _atom_text(de.key)
            v = _atom_text(de.value)
            if k is None or v is None:
                return None
            items.append(f"{k}: {v}")
        return "{" + ", ".join(items) + "}"
    return None


def _list_compact_length(node: "cst.List") -> int | None:
    """Length of `[a, b, c]` as a single line. None if any element is not
    a recognised atom."""
    items = [_atom_text(e.value) for e in node.elements]
    if not items or any(x is None for x in items):
        return None
    return 1 + len(", ".join(items)) + 1


def _is_directive_comment(comment) -> bool:
    if comment is None:
        return False
    text = comment.value.strip()
    return text in ("# table-format", "#table-format")


def _has_directive_in(lines) -> bool:
    return any(_is_directive_comment(line.comment) for line in lines)


def _list_in_stmt(stmt) -> "cst.List | None":
    """Find a `cst.List` value inside an Assign / AnnAssign in a
    SimpleStatementLine. Returns None otherwise."""
    if not isinstance(stmt, cst.SimpleStatementLine):
        return None
    for s in stmt.body:
        if isinstance(s, cst.Assign) and isinstance(s.value, cst.List):
            return s.value
        if isinstance(s, cst.AnnAssign) and isinstance(s.value, cst.List):
            return s.value
    return None


def _find_directive_lists(module: cst.Module) -> list[cst.List]:
    """Walk module body (and nested IndentedBlocks) and return List nodes
    whose immediately preceding line carries a `# table-format` comment."""
    targets: list[cst.List] = []

    def visit_block(stmts, header_lines):
        prev_marked = _has_directive_in(header_lines)
        for stmt in stmts:
            marked = prev_marked
            if hasattr(stmt, "leading_lines"):
                marked = marked or _has_directive_in(stmt.leading_lines)
            if marked:
                lst = _list_in_stmt(stmt)
                if lst is not None:
                    targets.append(lst)
            prev_marked = False
            inner = getattr(stmt, "body", None)
            if isinstance(inner, cst.IndentedBlock):
                visit_block(inner.body, ())

    visit_block(module.body, module.header)
    return targets


def _column_padding(values: list[str]) -> list[tuple[int, int]]:
    """For a column of value strings, return (leading_pad, trailing_pad) per
    value so that decimals (or least-significant digits) line up."""
    parts: list[tuple[str, str, bool]] = []
    for v in values:
        if "." in v:
            i, f = v.split(".", 1)
            parts.append((i, f, True))
        else:
            parts.append((v, "", False))
    max_int = max(len(p[0]) for p in parts)
    max_frac = max(len(p[1]) for p in parts)
    has_any_dec = any(p[2] for p in parts)
    pads: list[tuple[int, int]] = []
    for i_part, f_part, this_has_dec in parts:
        leading = max_int - len(i_part)
        if this_has_dec:
            trailing = max_frac - len(f_part)
        elif has_any_dec:
            # Int sitting in a column with floats — pad to fill the cell.
            trailing = 1 + max_frac
        else:
            trailing = 0
        pads.append((leading, trailing))
    return pads


def _row_break_ws(indent_col: int) -> cst.ParenthesizedWhitespace:
    return cst.ParenthesizedWhitespace(first_line=cst.TrailingWhitespace(whitespace=cst.SimpleWhitespace(""),
        comment=None, newline=cst.Newline()),
        empty_lines=[], indent=False, last_line=cst.SimpleWhitespace(" " * indent_col))


def _table_format_single_col(
    node: cst.List, values: list[str], cont_col: int, budget: int
) -> cst.List:
    """Build a new List with strict uniform cells, greedily packed into rows.
    cont_col is the column where the first item starts (right after `[`)
    AND where each continuation row begins, so decimals line up across rows."""
    pads = _column_padding(values)
    parts = [v.split(".", 1) if "." in v else (v, "") for v in values]
    max_int = max(len(p[0]) for p in parts)
    max_frac = max(len(p[1]) for p in parts)
    cell_w = max_int + (1 if max_frac else 0) + max_frac

    # Greedy pack into rows of indices.
    rows: list[list[int]] = [[]]
    col = cont_col
    for i in range(len(values)):
        is_last = i == len(values) - 1
        sep = 0 if not rows[-1] else 2
        proposed = col + sep + cell_w + 1
        if rows[-1] and proposed > budget:
            rows.append([i])
            col = cont_col + cell_w + (1 if is_last else 0)
        else:
            rows[-1].append(i)
            col += sep + cell_w + (1 if is_last else 0)

    # Rebuild element comma whitespace to encode pads + sep + breaks.
    new_elements = []
    n = len(values)
    for r_idx, row in enumerate(rows):
        for in_row, i in enumerate(row):
            el = node.elements[i]
            leading_i, trailing_i = pads[i]
            is_last_overall = i == n - 1
            is_last_in_row = in_row == len(row) - 1
            if is_last_overall:
                new_el = el.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            elif is_last_in_row:
                # End-of-row comma: newline + (cont_col + leading-of-next)
                next_leading = pads[i + 1][0]
                comma = cst.Comma(
                    whitespace_before=cst.SimpleWhitespace(" " * trailing_i),
                    whitespace_after=_row_break_ws(cont_col + next_leading),
                )
                new_el = el.with_changes(comma=comma)
            else:
                # Mid-row comma: ", " + leading-of-next
                next_leading = pads[i + 1][0]
                comma = cst.Comma(
                    whitespace_before=cst.SimpleWhitespace(" " * trailing_i),
                    whitespace_after=cst.SimpleWhitespace(" " + " " * next_leading),
                )
                new_el = el.with_changes(comma=comma)
            new_elements.append(new_el)

    return node.with_changes(
        elements=new_elements,
        lbracket=node.lbracket.with_changes(
            whitespace_after=cst.SimpleWhitespace(" " * pads[0][0])),
        rbracket=node.rbracket.with_changes(
            whitespace_before=cst.SimpleWhitespace(" " * pads[-1][1])),
    )


def _table_format_multi_col(node: cst.List, line_indent: int) -> "cst.List | None":
    """Build a new List where each Tuple element occupies its own line,
    columns aligned across rows. Returns None if any element isn't a Tuple
    or the tuples have mismatched arity."""
    elements = list(node.elements)
    tuples = [e.value for e in elements]
    if not all(isinstance(t, cst.Tuple) for t in tuples):
        return None
    n_cols = len(tuples[0].elements)
    if any(len(t.elements) != n_cols for t in tuples):
        return None
    col_values: list[list[str]] = [[] for _ in range(n_cols)]
    for t in tuples:
        for c, te in enumerate(t.elements):
            atom = _atom_text(te.value)
            if atom is None:
                return None
            col_values[c].append(atom)
    col_pads = [_column_padding(vs) for vs in col_values]

    cont_col = line_indent + 4
    new_elements = []
    for r_idx, (el, t) in enumerate(zip(elements, tuples)):
        is_last = r_idx == len(elements) - 1
        # Rebuild tuple's inner elements with cell padding.
        new_t_elems = []
        for c, te in enumerate(t.elements):
            leading, trailing = col_pads[c][r_idx]
            is_last_col = c == n_cols - 1
            if is_last_col:
                inner_comma = cst.MaybeSentinel.DEFAULT
            else:
                next_leading = col_pads[c + 1][r_idx][0]
                inner_comma = cst.Comma(
                    whitespace_before=cst.SimpleWhitespace(" " * trailing),
                    whitespace_after=cst.SimpleWhitespace(" " + " " * next_leading),
                )
            new_t_elems.append(te.with_changes(comma=inner_comma))
        first_leading = col_pads[0][r_idx][0]
        last_trailing = col_pads[-1][r_idx][1]
        new_lpar = (
            [
                t.lpar[0].with_changes(
                    whitespace_after=cst.SimpleWhitespace(" " * first_leading))]
            if t.lpar
            else t.lpar
        )
        new_rpar = (
            [
                t.rpar[0].with_changes(
                    whitespace_before=cst.SimpleWhitespace(" " * last_trailing))]
            if t.rpar
            else t.rpar
        )
        new_t = t.with_changes(elements=new_t_elems, lpar=new_lpar, rpar=new_rpar)
        # Data-block style: trailing comma after every tuple, including the
        # last; close bracket sits on its own line at the original indent.
        outer_comma = cst.Comma(
            whitespace_before=cst.SimpleWhitespace(""),
            whitespace_after=_row_break_ws(line_indent if is_last else cont_col),
        )
        new_elements.append(el.with_changes(value=new_t, comma=outer_comma))

    return node.with_changes(
        elements=new_elements,
        lbracket=node.lbracket.with_changes(whitespace_after=_row_break_ws(cont_col)),
        rbracket=node.rbracket.with_changes(whitespace_before=cst.SimpleWhitespace("")),
    )


def _table_format_dict_rows(node: cst.List, line_indent: int) -> "cst.List | None":
    """Build a new List where each Dict element occupies its own line, with
    value columns aligned across rows. All dicts must share the same keys
    in the same order; values must be atom-rendered. Returns None otherwise."""
    elements = list(node.elements)
    dicts = [e.value for e in elements]
    if not all(isinstance(d, cst.Dict) for d in dicts):
        return None

    keys_per_dict: list[tuple[str, ...]] = []
    for d in dicts:
        keys: list[str] = []
        for de in d.elements:
            if not isinstance(de, cst.DictElement):
                return None
            k = _atom_text(de.key)
            if k is None:
                return None
            keys.append(k)
        keys_per_dict.append(tuple(keys))
    if len(set(keys_per_dict)) != 1:
        return None  # mismatched keys
    n_cols = len(keys_per_dict[0])
    if n_cols == 0:
        return None

    col_values: list[list[str]] = [[] for _ in range(n_cols)]
    for d in dicts:
        for c, de in enumerate(d.elements):
            atom = _atom_text(de.value)
            if atom is None:
                return None
            col_values[c].append(atom)
    col_pads = [_column_padding(vs) for vs in col_values]

    cont_col = line_indent + 4
    new_elements = []
    for r_idx, (el, d) in enumerate(zip(elements, dicts)):
        is_last = r_idx == len(elements) - 1
        new_d_elems = []
        for c, de in enumerate(d.elements):
            leading, trailing = col_pads[c][r_idx]
            is_last_col = c == n_cols - 1
            # Value's leading pad lives in whitespace_after_colon (after
            # the standard one space).
            new_ws_after_colon = cst.SimpleWhitespace(" " + " " * leading)
            if is_last_col:
                inner_comma = cst.MaybeSentinel.DEFAULT
            else:
                inner_comma = cst.Comma(
                    whitespace_before=cst.SimpleWhitespace(" " * trailing),
                    whitespace_after=cst.SimpleWhitespace(" "),
                )
            new_d_elems.append(
                de.with_changes(whitespace_before_colon=cst.SimpleWhitespace(""),
                    whitespace_after_colon=new_ws_after_colon, comma=inner_comma))
        last_trailing = col_pads[-1][r_idx][1]
        new_d = d.with_changes(elements=new_d_elems,
            lbrace=d.lbrace.with_changes(whitespace_after=cst.SimpleWhitespace("")),
            rbrace=d.rbrace.with_changes(
                whitespace_before=cst.SimpleWhitespace(" " * last_trailing)))
        outer_comma = cst.Comma(
            whitespace_before=cst.SimpleWhitespace(""),
            whitespace_after=_row_break_ws(line_indent if is_last else cont_col),
        )
        new_elements.append(el.with_changes(value=new_d, comma=outer_comma))

    return node.with_changes(
        elements=new_elements,
        lbracket=node.lbracket.with_changes(whitespace_after=_row_break_ws(cont_col)),
        rbracket=node.rbracket.with_changes(whitespace_before=cst.SimpleWhitespace("")),
    )


class _TableFormatter(cst.CSTTransformer):
    def __init__(self, targets, positions, lines, budget):
        super().__init__()
        self.targets = targets  # set of id(node)
        self.positions = positions
        self.lines = lines
        self.budget = budget

    def leave_List(self, original, updated):
        if id(original) not in self.targets:
            return updated
        pos = self.positions.get(original)
        if pos is None:
            return updated
        compact_len = _list_compact_length(updated)
        if compact_len is None:
            return updated
        # Total length on the original line if list were rendered single-line.
        if pos.start.column + compact_len <= self.budget:
            return updated  # fits — directive is a no-op

        line_idx = pos.start.line - 1
        if line_idx < 0 or line_idx >= len(self.lines):
            return updated
        line = self.lines[line_idx]
        line_indent = len(line) - len(line.lstrip())

        elements = updated.elements
        if all(_atom_text(e.value) is not None for e in elements):
            if all(isinstance(e.value, cst.Dict) for e in elements):
                rows = _table_format_dict_rows(updated, line_indent)
                if rows is not None:
                    return rows
            elif all(isinstance(e.value, cst.Tuple) for e in elements):
                multi = _table_format_multi_col(updated, line_indent)
                if multi is not None:
                    return multi
            elif all(
                isinstance(e.value, (cst.Integer, cst.Float, cst.UnaryOperation))
                for e in elements):
                values = [_atom_text(e.value) for e in elements]
                cont_col = pos.start.column + 1
                return _table_format_single_col(updated, values, cont_col, self.budget)
        return updated


def _table_format_pass(src: str, budget: int) -> str:
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    targets_pre = _find_directive_lists(module)
    if not targets_pre:
        return src
    wrapper = cst.metadata.MetadataWrapper(module)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    module = wrapper.module
    target_ids = {id(t) for t in _find_directive_lists(module)}
    if not target_ids:
        return src
    lines = src.splitlines()
    new_module = module.visit(_TableFormatter(target_ids, positions, lines, budget))
    return new_module.code


def paddy_format(src: str, wrap_mode: str = "greedy") -> str:
    """Rewrite Python source to lisp-style brackets.

    `wrap_mode` controls how over-budget bracket groups are wrapped:
      - "greedy" (default): pack as many items per line as fit in the budget
      - "one_per_line": every item on its own line at line_indent + 4

    Idempotent. Returns input unchanged on syntax errors."""
    if wrap_mode not in ("greedy", "one_per_line"):
        raise ValueError(f"unknown wrap_mode: {wrap_mode!r}")
    try:
        module = cst.parse_module(src)
    except cst.ParserSyntaxError:
        return src
    wrapper = cst.metadata.MetadataWrapper(module)
    positions = wrapper.resolve(cst.metadata.PositionProvider)
    module = wrapper.module
    lines = src.splitlines()
    tabular_ids = _find_tabular_layouts(module, positions, lines)
    src = module.visit(_PaddyTransformer(tabular_ids)).code
    # Re-indent and wrap interact: when wrap moves an outer bracket to a
    # multi-line form, an inner group's reference line shifts and its
    # continuation indent (line_indent + 4) needs to be re-derived.
    # Loop until the source stops changing. Table-format is applied last
    # inside the loop so a directive-marked list always gets the final word.
    last = None
    while src != last:
        last = src
        src = _reindent_pass(src)
        src = _wrap_pass(src, _LINE_BUDGET, wrap_mode=wrap_mode)
        src = _table_format_pass(src, _LINE_BUDGET)
    return src


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Lisp-style Python formatter.")
    parser.add_argument("files", nargs="+", type=Path, help="files to format")
    parser.add_argument("--check", action="store_true", help="exit 1 if any file would be changed; do not write")
    parser.add_argument("--wrap-mode", choices=("greedy", "one-per-line"), default="greedy",
        help="how to wrap over-budget bracket groups (default: greedy)")
    args = parser.parse_args(argv)
    wrap_mode = args.wrap_mode.replace("-", "_")

    needs_change: list[Path] = []
    for path in args.files:
        original = path.read_text()
        formatted = paddy_format(original, wrap_mode=wrap_mode)
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
