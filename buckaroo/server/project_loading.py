"""Project-authored klasses: summary stats, post-processing and display
klasses loaded from ``<project_root>/stats``, ``post_processing`` and
``display``.

Shared by ``/load_expr`` (xorq) and ``/load`` with ``backend="polars"``,
so nothing here imports xorq or polars at module import; each engine's
namespace extras are imported when a file for that engine is compiled.
``buckaroo.server.xorq_loading`` re-exports the loaders for callers that
predate this module.

Which engine a stat or post-processing file is written for is declared
in the file itself, with a module-level ``ENGINE = "polars"``. A file
without the marker is a xorq file, so projects written before the
marker existed load as they did. The marker is read from the file's AST
before it is exec'd, so a file is only ever run under the namespace of
its own engine. Display klasses are engine-independent ``ColAnalysis``
subclasses and carry no marker.
"""
from __future__ import annotations

import ast
import builtins
import inspect
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ENGINES = ("xorq", "polars")
_DEFAULT_ENGINE = "xorq"
_ENGINE_MARKER = "ENGINE"

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


def _check_engine(engine: str) -> None:
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, got {engine!r}")


def read_engine_marker(source: str, path: Path) -> str:
    """The engine a stat or post-processing file is written for.

    The last module-level ``ENGINE = "<engine>"`` assignment wins, as it
    would after exec; absent, the file is a xorq file. Read from the AST
    so a file can be routed before it is exec'd under either engine's
    namespace. Raises ``SyntaxError`` on a file that doesn't parse, which
    the loaders log and skip like any other per-file failure."""
    engine = _DEFAULT_ENGINE
    for node in ast.parse(source, filename=str(path)).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        if (len(targets) == 1 and isinstance(targets[0], ast.Name)
                and targets[0].id == _ENGINE_MARKER):
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                raise ValueError(f"{_ENGINE_MARKER} must be a string literal")
            engine = node.value.value
    return engine


def _engine_globals(engine: str) -> dict:
    """What a stat or post-processing file sees besides the safe builtins.

    xorq files get ``ibis`` and ``xorq`` for references beyond bare column
    methods (literal, case().when(), deferred_read_parquet); either may be
    absent, since the xorq loader also runs where only polars is installed.
    polars files get ``pl``; polars is present whenever a polars session
    asks for its klasses."""
    globs: dict = {"__builtins__": _safe_builtins()}
    if engine == "xorq":
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
    else:
        import polars as _pl  # noqa: PLC0415
        globs["pl"] = _pl
    return globs


def _iter_engine_files(directory: Path, kind: str, engine: str):
    """Yield ``(name, path, source)`` for the files in ``directory`` written
    for ``engine``. Shared bookkeeping of the stat and post-processing
    loaders: the ``_`` parking convention, the identifier check on the stem
    (it becomes the stat key / post-processing method name), the marker
    read, and log-and-skip on a file that doesn't parse."""
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        if not name.isidentifier():
            log.warning("project %s %s: filename stem is not a valid python identifier; skipping", kind, path)
            continue
        try:
            source = path.read_text()
            file_engine = read_engine_marker(source, path)
        except Exception as e:
            log.warning("project %s %s skipped: %s", kind, path, e)
            continue
        if file_engine not in ENGINES:
            log.warning("project %s %s: unknown %s %r; skipping", kind, path, _ENGINE_MARKER, file_engine)
            continue
        if file_engine != engine:
            log.debug("project %s %s is a %s file; skipping for %s", kind, path, file_engine, engine)
            continue
        yield name, path, source


# ---------------------------------------------------------------------------
# project-authored summary stats (loaded from <project_root>/stats/*.py)
# ---------------------------------------------------------------------------


def load_project_stat_klasses(project_root, engine: str = _DEFAULT_ENGINE) -> list:
    """Scan ``<project_root>/stats/*.py`` and return the ``@stat()``-wrapped
    functions written for ``engine``.

    Each file must define a callable ``compute`` taking one parameter. For
    xorq that parameter is the ibis column and the return an ibis
    expression, which the ``XorqColumn`` marker tells ``XorqStatPipeline``
    to fold into its batch aggregate. For polars it is the column's
    ``pl.Series`` and the return a value, which the ``RawSeries`` marker
    tells ``StatPipeline`` to pass in directly, as it does for the built-in
    stats in ``customizations/pl_stats_v2.py``. Either way the function is
    renamed to the filename stem, which becomes the stat key.

    Files whose name starts with ``_`` (e.g. ``_disabled.py``, ``_helpers.py``)
    are skipped, as a convention for parking work-in-progress without
    removing it from the project directory. Files for another engine are
    skipped, as are files with an ``ENGINE`` neither engine recognises.

    Errors in any one file are logged and the file is skipped — one bad
    stat shouldn't keep the rest from loading.
    """
    _check_engine(engine)
    stats_dir = Path(project_root) / "stats"
    if not stats_dir.is_dir():
        return []

    # Local imports — keep the noisy stat_func module surface off this
    # file's import path.
    from buckaroo.pluggable_analysis_framework.stat_func import (  # noqa: PLC0415
        RawSeries, XorqColumn, stat)
    marker = XorqColumn if engine == "xorq" else RawSeries

    klasses: list = []
    for name, path, source in _iter_engine_files(stats_dir, "stat", engine):
        try:
            wrapped = _compile_project_stat(name, path, source, engine, stat, marker)
        except Exception as e:
            log.warning("project stat %s skipped: %s", path, e)
            continue
        klasses.append(wrapped)
    return klasses


def _compile_project_stat(name: str, path: Path, source: str, engine: str, stat_decorator, marker):
    """Exec, validate, and wrap one stat file. Raises on any failure;
    the caller logs + skips. Kept separate so the per-file try/except in
    the loader doesn't accidentally hide bugs in the loop bookkeeping."""
    globs = _engine_globals(engine)

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

    # Inject the engine's raw-data marker as the single param's annotation
    # so the @stat decorator marks the function as needing raw column data
    # (the pipeline then passes the column in rather than looking up a stat
    # keyed by the parameter name).
    compute.__annotations__ = {params[0].name: marker}
    compute.__name__ = name
    compute.__qualname__ = name
    return stat_decorator()(compute)


# ---------------------------------------------------------------------------
# project-authored post-processing (loaded from <project_root>/post_processing/*.py)
# ---------------------------------------------------------------------------


def load_project_post_processing_klasses(project_root, engine: str = _DEFAULT_ENGINE) -> list:
    """Scan ``<project_root>/post_processing/*.py`` and return wrapped
    ``ColAnalysis`` subclasses, written for ``engine``, for use as
    post-processing methods.

    Each file must define a callable ``process`` taking one parameter. For
    xorq it takes the ibis expression and returns either a new expression
    or a pandas DataFrame — the same shape ``XorqDataflow.add_processing``
    accepts at the widget API. For polars it takes and returns a
    ``pl.DataFrame``. The function is wrapped in a ``ColAnalysis`` subclass
    with ``post_processing_method = <filename_stem>`` and a
    ``post_process_df`` classmethod that delegates to ``process``;
    ``filter_analysis(analysis_klasses, "post_processing_method")``
    in ``CustomizableDataflow`` then surfaces it through
    ``post_processing_klasses`` and the ``buckaroo_options`` dropdown.

    Files whose name starts with ``_`` are skipped (parking convention),
    as are files for another engine. Errors in any one file are logged
    and the file is skipped — one bad post-processor shouldn't keep the
    rest from loading.
    """
    _check_engine(engine)
    pp_dir = Path(project_root) / "post_processing"
    if not pp_dir.is_dir():
        return []

    klasses: list = []
    for name, path, source in _iter_engine_files(pp_dir, "post_processing", engine):
        try:
            wrapped = _compile_project_post_processing(name, path, source, engine)
        except Exception as e:
            log.warning("project post_processing %s skipped: %s", path, e)
            continue
        klasses.append(wrapped)
    return klasses


def _compile_project_post_processing(name: str, path: Path, source: str, engine: str):
    """Exec, validate, and wrap one post-processing file into a
    ``ColAnalysis`` subclass. Mirror of ``_compile_project_stat`` for
    the post-processing channel: instead of an ``@stat()``-decorated
    function, returns a class shaped like the ``DecoratedXorqProcessing``
    that ``XorqDataflow.add_processing`` builds at runtime —
    ``post_processing_method = <stem>`` and a ``post_process_df``
    classmethod returning ``[process(df), {}]``.
    """
    # Local import — ColAnalysis lives in the pluggable framework and
    # only the post-processing path needs it from this module.
    from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis  # noqa: PLC0415

    globs = _engine_globals(engine)

    # Single shared namespace so top-level constants and helper
    # functions are visible at call time — same Codex P1 hazard the
    # stat loader documents.
    exec(compile(source, str(path), "exec"), globs)

    process = globs.get("process")
    if not callable(process):
        raise ValueError("no callable 'process' defined")

    sig = inspect.signature(process)
    params = list(sig.parameters.values())
    if len(params) != 1:
        raise ValueError(
            f"process() must take exactly one parameter, got {len(params)}")

    # Default-arg capture (`_f=process`) on the lambda binds the loaded
    # process function at class-construction time so a later iteration
    # of the loader loop can't shadow it via the outer ``process`` name.
    return type(f"ProjectPostProcessing_{name}", (ColAnalysis,), {
        "provides_defaults": {},
        "post_processing_method": name,
        "post_process_df": classmethod(
            lambda cls, df, _f=process: [_f(df), {}]),
    })


# ---------------------------------------------------------------------------
# project-authored display klasses (loaded from <project_root>/display/*.py)
# ---------------------------------------------------------------------------


def load_project_display_klasses(project_root) -> list:
    """Scan ``<project_root>/display/*.py`` for ``ColAnalysis`` subclasses
    with a ``df_display_name`` attribute and return them as ``extra_klasses``.

    Unlike the stat and post-processing loaders, display files define full
    class bodies rather than a single function, and carry no engine
    marker: a display klass styles the summary dict, whichever engine
    computed it. Each file is exec'd with ``ColAnalysis`` and the standard
    styling base classes in scope; any class found in the resulting
    namespace that (a) subclasses ``ColAnalysis`` and (b) carries a
    ``df_display_name`` string is collected.

    Because ``filter_analysis(klasses, "df_display_name")`` maps display-name
    → last-klass-wins, a display klass loaded here overrides the built-in
    ``DefaultMainStyling`` (``df_display_name = "main"``) for this session
    only — the dataflow's class-level klass list is not mutated.

    Files whose name starts with ``_`` are skipped (parking convention).
    Errors in any one file are logged and the file is skipped.
    """
    display_dir = Path(project_root) / "display"
    if not display_dir.is_dir():
        return []

    from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis  # noqa: PLC0415
    from buckaroo.customizations.styling import (  # noqa: PLC0415
        DefaultMainStyling, DefaultSummaryStatsStyling, StylingAnalysis)

    klasses: list = []
    for path in sorted(display_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        if not path.stem.isidentifier():
            log.warning(
                "project display %s: filename stem is not a valid python identifier; skipping",
                path)
            continue
        try:
            found = _compile_project_display(path, ColAnalysis,
                DefaultMainStyling, DefaultSummaryStatsStyling, StylingAnalysis)
            klasses.extend(found)
        except Exception as e:
            log.warning("project display %s skipped: %s", path, e)
    return klasses


def _compile_project_display(path: Path, ColAnalysis, *extra_bases):
    """Exec one display file and return all ColAnalysis subclasses with
    ``df_display_name`` found in its namespace. Raises on syntax errors
    so the loader can log-and-skip. Returns an empty list when a valid
    file defines no qualifying classes (not an error)."""
    source = path.read_text()
    safe = _safe_builtins()
    # __build_class__ is the CPython hook that executes class bodies; without
    # it, any ``class Foo:`` statement raises NameError. Adding it opens more
    # exec surface than the function-only stat/post-processing loaders — class
    # bodies run arbitrary code at definition time (descriptors,
    # __init_subclass__, metaclasses). Display files are project-developer-
    # authored, not end-user input, so this is acceptable; keep that scope in
    # mind if the sandbox model is ever revisited.
    safe["__build_class__"] = __build_class__
    safe["classmethod"] = classmethod
    safe["staticmethod"] = staticmethod
    # super() is a builtin but not in _SAFE_BUILTIN_NAMES; without it,
    # calling super() inside any method succeeds at class-definition time
    # but raises NameError at render time — the common override pattern
    # (subclass DefaultMainStyling, call super().style_column(...)) would
    # silently break.
    safe["super"] = super
    globs: dict = {"__builtins__": safe, "__name__": str(path.stem), "ColAnalysis": ColAnalysis}
    for base in extra_bases:
        globs[base.__name__] = base

    # Track identities of pre-injected classes so we don't return them as
    # user-defined klasses — they're context for the file, not the output.
    injected_ids = {id(ColAnalysis)} | {id(b) for b in extra_bases}

    exec(compile(source, str(path), "exec"), globs)

    found = []
    for obj in globs.values():
        if (isinstance(obj, type)
                and id(obj) not in injected_ids
                and issubclass(obj, ColAnalysis)
                and isinstance(getattr(obj, "df_display_name", None), str)):
            found.append(obj)
    return found


def load_project_klasses(project_root, engine: str) -> list:
    """Every klass a session for ``engine`` gets from ``project_root``:
    its stats and post-processors, then the display klasses."""
    return (load_project_stat_klasses(project_root, engine=engine)
        + load_project_post_processing_klasses(project_root, engine=engine)
        + load_project_display_klasses(project_root))
