"""Server-side xorq loading — mirrors ``buckaroo.server.data_loading``
for the xorq backend.

Isolated module so the xorq import surface stays out of the rest of
the server. The handler in ``handlers.py`` lazy-imports this module
inside ``LoadExprHandler.post`` so a server without ``buckaroo[xorq]``
installed still imports cleanly.
"""
from __future__ import annotations

import builtins
import inspect
import logging
import traceback
from pathlib import Path

from buckaroo.xorq_buckaroo import (
    NoCleaningConfXorq, XorqAutocleaning, XorqDataflow, XorqDfStatsV2,
    XorqInfiniteSampling, _XORQ_ANALYSIS_KLASSES, _expr_count,
    window_to_parquet)

log = logging.getLogger(__name__)


class XorqServerDataflow(XorqDataflow):
    """Headless XorqDataflow with infinite sampling.

    Mirrors the class-attribute set ``XorqBuckarooWidget`` injects into
    its ``InnerDataFlow`` (xorq_buckaroo.py:181-186) — without
    ``InnerDataFlow``'s widget-side ``_df_to_obj`` override, since the
    server never serialises a main-frame sample (``skip_main_serial=True``).

    ``extra_klasses`` is an optional list of additional ``@stat()``-decorated
    functions (or ``ColAnalysis`` subclasses) to fold into ``analysis_klasses``
    at the per-instance level. ``LoadExprHandler.post`` uses it to inject
    project-authored stats discovered under ``<project_root>/stats/*.py``;
    the built-in xorq stats are kept first so collisions resolve to the
    built-in.
    """

    sampling_klass = XorqInfiniteSampling
    autocleaning_klass = XorqAutocleaning
    autoclean_conf = (NoCleaningConfXorq,)
    DFStatsClass = XorqDfStatsV2
    analysis_klasses = _XORQ_ANALYSIS_KLASSES

    def __init__(self, expr, *args, extra_klasses=None, **kwargs):
        if extra_klasses:
            # Per-instance override — class-level _XORQ_ANALYSIS_KLASSES is
            # left untouched so other sessions / direct widget usage don't
            # inherit one project's stats.
            self.analysis_klasses = list(_XORQ_ANALYSIS_KLASSES) + list(extra_klasses)
        super().__init__(expr, *args, **kwargs)


def load_expr_build_dir(build_dir: str):
    """Rehydrate an ibis expression from a xorq build directory.

    Wrapper around ``xorq.api.load_expr``. Build dirs that contain
    in-memory memtables (the small reference tables joined against a
    remote source) need a backend to re-read their parquet snapshot
    during rehydration. xorq's own datafusion backend is the natural
    default — it's what ``xo.connect()`` returns and what ships with
    every ``buckaroo[xorq]`` install. If the caller has already set
    a default (e.g. DuckDB), respect that."""
    from xorq.api import connect, load_expr  # noqa: PLC0415  (lazy, see module docstring)
    from xorq.vendor import ibis  # noqa: PLC0415
    # Direct option assignment — `ibis.set_backend(...)` was removed in
    # xorq 0.3.25; the option is the stable cross-version contract.
    if ibis.options.default_backend is None:
        ibis.options.default_backend = connect()
    return load_expr(build_dir)


def get_xorq_metadata(xorq_dataflow: XorqServerDataflow, build_dir: str) -> dict:
    """Metadata payload matching ``data_loading.get_metadata``'s shape."""
    expr = xorq_dataflow.processed_df
    columns = [{"name": str(name), "dtype": str(dtype)}
        for name, dtype in expr.schema().items()]
    return {"path": build_dir, "rows": _expr_count(expr), "columns": columns}


# ---------------------------------------------------------------------------
# project-authored summary stats (loaded from <project_root>/stats/*.py)
# ---------------------------------------------------------------------------

# Names from ``builtins`` that the exec'd stat source is allowed to see.
# Notable absences: ``__import__``, ``open``, ``exec``, ``eval``, ``compile``,
# ``input``, ``getattr``/``setattr``/``delattr`` — without those the function
# body cannot reach the filesystem, the import system, or the live process
# graph through name lookup. Not a real sandbox (a determined caller can
# walk ``col.__class__.__mro__``); acceptable because the project owner is
# trusted (the buckaroo subprocess only reads project paths a host like
# pydata-app explicitly passed in).
_SAFE_BUILTIN_NAMES = ("True", "False", "None", "abs", "min", "max", "round", "sum", "len", "int", "float", "str", "bool", "list", "tuple", "dict", "set", "range", "enumerate", "zip", "map", "filter", "isinstance", "issubclass", "type")


def _safe_builtins() -> dict:
    return {n: getattr(builtins, n) for n in _SAFE_BUILTIN_NAMES}


def load_project_stat_klasses(project_root) -> list:
    """Scan ``<project_root>/stats/*.py`` and return wrapped ``@stat()`` funcs.

    Each file must define a callable ``compute(col)`` returning an ibis
    expression. The function is renamed to the filename stem and decorated
    with ``@stat()`` from ``pluggable_analysis_framework.stat_func`` so it
    slots into the same ``XORQ_STATS_V2`` list as the built-in xorq stats —
    the ``XorqStatPipeline`` doesn't distinguish.

    Files whose name starts with ``_`` (e.g. ``_disabled.py``, ``_helpers.py``)
    are skipped, as a convention for parking work-in-progress without
    removing it from the project directory.

    Errors in any one file are logged and the file is skipped — one bad
    stat shouldn't keep the rest from loading.
    """
    stats_dir = Path(project_root) / "stats"
    if not stats_dir.is_dir():
        return []

    # Local imports — keep the noisy stat_func module surface off this
    # file's import path. The @stat decorator + XorqColumn marker live
    # in the pluggable framework rather than xorq itself.
    from buckaroo.pluggable_analysis_framework.stat_func import (
        XorqColumn, stat)

    klasses: list = []
    for path in sorted(stats_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        if not name.isidentifier():
            log.warning(
                "project stat %s: filename stem is not a valid python identifier; skipping",
                path)
            continue
        try:
            wrapped = _compile_project_stat(name, path, stat, XorqColumn)
        except Exception as e:
            log.warning("project stat %s skipped: %s", path, e)
            continue
        klasses.append(wrapped)
    return klasses


def _compile_project_stat(name: str, path: Path, stat_decorator, XorqColumn):
    """Read, exec, validate, and wrap one stat file. Raises on any failure;
    the caller logs + skips. Kept separate so the per-file try/except in
    the loader doesn't accidentally hide bugs in the loop bookkeeping."""
    source = path.read_text()
    globs: dict = {"__builtins__": _safe_builtins()}
    # Expose ibis / xorq inside the function body for stats that need
    # references beyond bare column methods (literal, case().when(), etc.).
    try:
        from xorq.vendor import ibis as _ibis  # noqa: PLC0415
        globs["ibis"] = _ibis
    except ImportError:
        pass
    try:
        import xorq.api as _xo  # noqa: PLC0415
        globs["xorq"] = _xo
    except ImportError:
        pass

    # Single shared namespace for globals + locals so top-level
    # constants and helper functions in the stat file are visible to
    # ``compute`` when it runs. With separate dicts, ``compute`` captures
    # ``globs`` as its ``__globals__`` while module-level names land in
    # ``locals`` — every call would NameError.
    exec(compile(source, str(path), "exec"), globs)

    compute = globs.get("compute")
    if not callable(compute):
        raise ValueError("no callable 'compute' defined")

    sig = inspect.signature(compute)
    params = list(sig.parameters.values())
    if len(params) != 1:
        raise ValueError(
            f"compute() must take exactly one parameter, got {len(params)}")

    # Inject the XorqColumn annotation on the single param so the @stat
    # decorator marks the function as needing raw column data (the
    # pipeline then passes the actual ibis column expression in rather
    # than looking up a stat keyed by the parameter name).
    compute.__annotations__ = {params[0].name: XorqColumn}
    compute.__name__ = name
    compute.__qualname__ = name
    return stat_decorator()(compute)


def handle_infinite_request_xorq(xorq_dataflow: XorqServerDataflow,
        payload_args: dict) -> tuple[dict, bytes]:
    """Drive one infinite_request window against a xorq expression.

    Reads the current ``processed_df`` (the expression, post-filter)
    from ``widget_args_tuple``, calls the shared
    ``window_to_parquet`` helper, and returns the
    ``(json_msg, parquet_bytes)`` pair the WebSocket handler ships as
    a text + binary frame pair (matching the pandas/polars paths)."""
    start = int(payload_args["start"])
    end = int(payload_args["end"])
    _unused, processed_df, merged_sd = xorq_dataflow.widget_args_tuple
    if processed_df is None:
        return ({"type": "infinite_resp", "key": payload_args, "data": [], "length": 0}, b"")

    try:
        sort = payload_args.get("sort")
        sort_col = None
        ascending = True
        if sort:
            sort_col = merged_sd[sort]["orig_col_name"]
            ascending = payload_args.get("sort_direction") == "asc"

        total_length = _expr_count(processed_df)
        parquet_bytes = window_to_parquet(processed_df, start, end, sort_col, ascending)
        return ({"type": "infinite_resp", "key": payload_args, "data": [],
            "length": total_length}, parquet_bytes)
    except Exception:
        return ({"type": "infinite_resp", "key": payload_args, "data": [],
            "length": 0, "error_info": traceback.format_exc()}, b"")
