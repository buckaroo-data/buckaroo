"""Project-authored klasses for server sessions: the loaders that don't
need xorq, and the helpers the xorq loaders in ``xorq_loading`` share.

A project root holds klasses the server picks up at ``/load`` and
``/load_expr`` time and again on ``/reload_expr``. The engine a stat or
post-processing file is written for is chosen by its directory (#994), so
the loaders never guess it from a file's contents:

* ``stats/*.py`` and ``post_processing/*.py`` are the xorq contracts
  (``compute(col)`` returning an ibis expression, ``process(expr)``), loaded
  by ``xorq_loading``.
* ``stats/polars/*.py`` is ``compute(ser)`` taking a ``pl.Series`` and
  returning a value; ``post_processing/polars/*.py`` is ``process(df)``
  taking and returning a ``pl.DataFrame``. Loaded here.
* ``display/*.py`` holds ``ColAnalysis`` styling subclasses, which don't
  depend on the engine. Loaded here, for both.

This module imports neither xorq nor polars at import time, so a polars
session loads its project klasses on a server without ``buckaroo[xorq]``.
"""
from __future__ import annotations

import builtins
import inspect
import logging
from pathlib import Path
from typing import Callable, Iterator

from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.pluggable_analysis_framework.stat_func import RawSeries, stat

log = logging.getLogger(__name__)

# Names from ``builtins`` that the exec'd project source is allowed to see.
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


def iter_project_files(directory: Path, kind: str) -> Iterator[tuple[str, Path]]:
    """Yield ``(stem, path)`` for each loadable ``*.py`` under ``directory``.

    Files whose name starts with ``_`` (e.g. ``_disabled.py``, ``_helpers.py``)
    are skipped, as a convention for parking work-in-progress without
    removing it from the project directory. A stem that is not a python
    identifier can't name a stat or a method, so it is logged and skipped.
    Yields nothing when the directory doesn't exist. ``kind`` labels the log
    line (``"stat"``, ``"post_processing"``, ...)."""
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        if not path.stem.isidentifier():
            log.warning(
                "project %s %s: filename stem is not a valid python identifier; skipping",
                kind, path)
            continue
        yield path.stem, path


def exec_project_file(path: Path, globs: dict) -> dict:
    """Exec one project file with the restricted builtins and return its
    namespace. ``globs`` carries whatever the file may reference beyond
    the builtins (``pl``, ``ibis``, base classes).

    Single shared namespace for globals + locals so top-level constants
    and helper functions in the file are visible to ``compute`` /
    ``process`` when they run. With separate dicts, the function captures
    ``globs`` as its ``__globals__`` while module-level names land in
    ``locals`` — every call would NameError."""
    globs = {"__builtins__": _safe_builtins(), **globs}
    exec(compile(path.read_text(), str(path), "exec"), globs)
    return globs


def single_param_callable(namespace: dict, name: str) -> Callable:
    """The project file's entry point: ``namespace[name]`` must be callable
    and take exactly one parameter. Raises ``ValueError`` otherwise; the
    loaders log and skip the file."""
    func = namespace.get(name)
    if not callable(func):
        raise ValueError(f"no callable '{name}' defined")
    params = list(inspect.signature(func).parameters.values())
    if len(params) != 1:
        raise ValueError(
            f"{name}() must take exactly one parameter, got {len(params)}")
    return func


def wrap_project_stat(name: str, compute: Callable, marker: type):
    """Rename ``compute`` to the filename stem and decorate it with
    ``@stat()``. The single parameter is annotated with ``marker`` (the
    pipeline's raw-data marker: ``RawSeries`` for polars, ``XorqColumn``
    for xorq) so the pipeline passes the column itself in rather than
    looking up a stat keyed by the parameter name; the return value lands
    under ``name``."""
    param = next(iter(inspect.signature(compute).parameters))
    compute.__annotations__ = {param: marker}
    compute.__name__ = name
    compute.__qualname__ = name
    return stat()(compute)


def make_post_processing_klass(name: str, process: Callable) -> type:
    """Wrap ``process`` in a ``ColAnalysis`` subclass shaped like the
    ``DecoratedXorqProcessing`` that ``XorqDataflow.add_processing`` builds
    at runtime: ``post_processing_method = <stem>`` and a ``post_process_df``
    classmethod returning ``[process(df), {}]``. ``filter_analysis(
    analysis_klasses, "post_processing_method")`` in ``CustomizableDataflow``
    then surfaces it through ``post_processing_klasses`` and the
    ``buckaroo_options`` dropdown.

    Default-arg capture (``_f=process``) on the lambda binds the loaded
    function at class-construction time so a later iteration of a loader
    loop can't shadow it via the outer name."""
    return type(f"ProjectPostProcessing_{name}", (ColAnalysis,), {
        "provides_defaults": {},
        "post_processing_method": name,
        "post_process_df": classmethod(
            lambda kls, df, _f=process: [_f(df), {}]),
    })


# ---------------------------------------------------------------------------
# polars stats (loaded from <project_root>/stats/polars/*.py)
# ---------------------------------------------------------------------------


def _polars_globals() -> dict:
    """``pl`` in scope for stats and post-processors that need dtypes or
    expressions beyond bare series / frame methods, as ``ibis`` and
    ``xorq`` are for the xorq files."""
    import polars as pl  # noqa: PLC0415  (polars is an optional dependency)
    return {"pl": pl}


def load_project_polars_stat_klasses(project_root) -> list:
    """Scan ``<project_root>/stats/polars/*.py`` and return wrapped
    ``@stat()`` funcs.

    Each file must define a callable ``compute(ser)`` taking a ``pl.Series``
    and returning the stat's value. The function is renamed to the filename
    stem, its parameter marked ``RawSeries``, and decorated with ``@stat()``
    so it slots into the same ``PL_ANALYSIS_V2`` list as the built-in polars
    stats — ``StatPipeline`` doesn't distinguish.

    Errors in any one file are logged and the file is skipped — one bad
    stat shouldn't keep the rest from loading.
    """
    klasses: list = []
    for name, path in iter_project_files(Path(project_root) / "stats" / "polars", "polars stat"):
        try:
            namespace = exec_project_file(path, _polars_globals())
            wrapped = wrap_project_stat(name, single_param_callable(namespace, "compute"), RawSeries)
        except Exception as e:
            log.warning("project polars stat %s skipped: %s", path, e)
            continue
        klasses.append(wrapped)
    return klasses


# ---------------------------------------------------------------------------
# polars post-processing (loaded from <project_root>/post_processing/polars/*.py)
# ---------------------------------------------------------------------------


def load_project_polars_post_processing_klasses(project_root) -> list:
    """Scan ``<project_root>/post_processing/polars/*.py`` and return
    wrapped ``ColAnalysis`` subclasses for use as post-processing methods.

    Each file must define a callable ``process(df)`` taking and returning
    a ``pl.DataFrame``; ``PolarsServerDataflow`` runs its stats and serves
    rows from the returned frame. Wrapped by ``make_post_processing_klass``
    under the filename stem.

    Errors in any one file are logged and the file is skipped.
    """
    klasses: list = []
    for name, path in iter_project_files(
        Path(project_root) / "post_processing" / "polars", "polars post_processing"):
        try:
            namespace = exec_project_file(path, _polars_globals())
            wrapped = make_post_processing_klass(name, single_param_callable(namespace, "process"))
        except Exception as e:
            log.warning("project polars post_processing %s skipped: %s", path, e)
            continue
        klasses.append(wrapped)
    return klasses


def load_project_polars_klasses(project_root) -> list:
    """Everything a polars session loads from ``project_root``: the polars
    stats and post-processors plus the engine-neutral display klasses.
    The /load and /reload_expr handlers call this."""
    return (load_project_polars_stat_klasses(project_root)
        + load_project_polars_post_processing_klasses(project_root)
        + load_project_display_klasses(project_root))


# ---------------------------------------------------------------------------
# project-authored display klasses (loaded from <project_root>/display/*.py)
# ---------------------------------------------------------------------------


def load_project_display_klasses(project_root) -> list:
    """Scan ``<project_root>/display/*.py`` for ``ColAnalysis`` subclasses
    with a ``df_display_name`` attribute and return them as ``extra_klasses``.

    Unlike the stat and post-processing loaders, display files define full
    class bodies rather than a single function. Each file is exec'd with
    ``ColAnalysis`` and the standard styling base classes in scope; any
    class found in the resulting namespace that (a) subclasses ``ColAnalysis``
    and (b) carries a ``df_display_name`` string is collected.

    Because ``filter_analysis(klasses, "df_display_name")`` maps display-name
    → last-klass-wins, a display klass loaded here overrides the built-in
    ``DefaultMainStyling`` (``df_display_name = "main"``) for this session
    only — the dataflow's class-level klass list is not mutated.

    Errors in any one file are logged and the file is skipped.
    """
    from buckaroo.customizations.styling import (  # noqa: PLC0415
        DefaultMainStyling, DefaultSummaryStatsStyling, StylingAnalysis)

    klasses: list = []
    for _name, path in iter_project_files(Path(project_root) / "display", "display"):
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
