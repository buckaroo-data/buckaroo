"""buckaroo Commands targeting xorq/ibis expressions.

Each command mirrors the shape of pandas_commands.py / polars_commands.py:
a ``command_default`` / ``command_pattern`` pair that the frontend reads,
plus ``transform`` (expr -> expr) and ``transform_to_py`` (str). Unlike
the pandas commands, transforms never mutate — ibis expressions are
immutable, so each transform builds and returns a new expression that
the dataflow continues to push down.

xorq is an optional dependency; this module is import-safe without it,
because nothing here imports xorq at module load. Transforms call methods
on the passed-in expression (duck typing), so the module only matters
when an ibis/xorq expression actually flows through.

Code-gen quoting: ``transform_to_py`` uses ``{val!r}`` / ``{col!r}`` so
that values containing quotes, backslashes, etc. round-trip safely into
the generated snippet.
"""

from ..jlisp.configure_utils import SDResult  # noqa: F401 (re-export for command authors)
from ..jlisp.lisp_utils import s


class NoOp:
    command_default = [s('noop'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod
    def transform(expr, col):
        return expr

    @staticmethod
    def transform_to_py(expr, col):
        return "    # no op"


class DropCol:
    command_default = [s('dropcol'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod
    def transform(expr, col):
        return expr.drop(col)

    @staticmethod
    def transform_to_py(expr, col):
        return f"    df = df.drop({col!r})"


class FillNA:
    command_default = [s('fillna'), s('df'), "col", 0]
    command_pattern = [[3, 'fillVal', 'type', 'integer']]

    @staticmethod
    def transform(expr, col, val):
        return expr.mutate(**{col: expr[col].fill_null(val)})

    @staticmethod
    def transform_to_py(expr, col, val):
        return f"    df = df.mutate({col}=df[{col!r}].fill_null({val!r}))"


class DropDuplicates:
    command_default = [s('drop_duplicates'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod
    def transform(expr, col):
        return expr.distinct(on=[col])

    @staticmethod
    def transform_to_py(expr, col):
        return f"    df = df.distinct(on=[{col!r}])"


def search_expr(expr, val):
    """Filter rows where any string column contains ``val``.

    Empty / None val short-circuits — the frontend sends "" to clear the
    quick-search box, and pl.col-style ``contains(None)`` would drop every
    row on the polars side; mirror that contract here.

    Public because ``Search.transform_to_py`` emits an import of this
    function into the generated user-facing code.
    """
    if val is None or val == "":
        return expr
    schema = expr.schema()
    string_cols = [name for name in expr.columns if schema[name].is_string()]
    if not string_cols:
        return expr
    cond = None
    for c in string_cols:
        c_cond = expr[c].contains(val)
        cond = c_cond if cond is None else cond | c_cond
    return expr.filter(cond)


class Search:
    command_default = [s('search'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]
    quick_args_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod
    def transform(expr, col, val):
        filtered = search_expr(expr, val)
        if val is None or val == "":
            return filtered
        # ibis ``StringValue.contains`` is a literal substring match (not
        # regex), so expose the term as highlight_phrase (list) — matching
        # pandas Search (#764). Polars uses highlight_regex (#758) because
        # its ``str.contains`` is a regex match.
        schema = expr.schema()
        string_cols = [name for name in expr.columns if schema[name].is_string()]
        sd_updates = {c: {'highlight_phrase': [val]} for c in string_cols}
        return SDResult(filtered, sd_updates)

    @staticmethod
    def transform_to_py(expr, col, val):
        return (
            "    from buckaroo.customizations.xorq_commands import search_expr\n"
            f"    df = search_expr(df, {val!r})")
