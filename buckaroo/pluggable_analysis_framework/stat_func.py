"""Core types for the pluggable analysis framework v2.

StatKey, StatFunc, @stat decorator, and marker types.

The function signature IS the contract:
  - Parameter names/types become `requires`
  - Return type becomes `provides`
  - RawSeries/SampledSeries params indicate raw data needs
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, TypedDict, get_type_hints


class MultipleProvides(TypedDict):
    """Marker base class for stat funcs that return more than one accumulator key.

    Subclass this (instead of ``TypedDict`` directly) when a single ``@stat``
    function should write several keys into the per-column accumulator. The
    pipeline expands every field of the subclass into its own ``StatKey``::

        class TypingResult(MultipleProvides):
            is_numeric: bool
            is_integer: bool

        @stat()
        def typing_stats(dtype: str) -> TypingResult:
            return {'is_numeric': ..., 'is_integer': ...}

    On Python 3.11, TypedDict's metaclass collapses subclass inheritance to
    ``(dict,)`` at class-creation time and discards ``__orig_bases__`` —
    runtime detection of "this TypedDict subclassed MultipleProvides" is
    impossible. The class still serves as a named, importable marker that
    documents intent in source code, and the pipeline handles its expansion
    via the same TypedDict-field walk used for any TypedDict return.
    """


# Sentinel for "no default provided"
class _MissingSentinel:
    """Sentinel object indicating no default was provided."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return '<MISSING>'

    def __bool__(self):
        return False


MISSING = _MissingSentinel()


# ---------------------------------------------------------------------------
# Marker types for raw data access
# ---------------------------------------------------------------------------

class RawSeries:
    """Marker type: 'give me the raw column series'."""
    pass


class SampledSeries:
    """Marker type: 'give me the downsampled series'."""
    pass


class RawDataFrame:
    """Marker type: 'give me the full dataframe'."""
    pass


class XorqColumn:
    """Marker type: 'give me table[col] as a xorq column expression'.

    Used by XorqStatPipeline's batch-aggregate phase. Functions taking an
    XorqColumn are expected to return a xorq expression (xorq.vendor.ibis)
    that the pipeline folds into a single ``table.aggregate(...)`` query.
    """
    pass


class XorqExpr:
    """Marker type: 'give me the full xorq table expression'.

    Used by XorqStatPipeline for stats that need to run their own per-column
    query (e.g. histograms — group_by + aggregate cannot be folded into the
    main batch).
    """
    pass


class XorqExecute:
    """Marker type: 'give me a callable that executes xorq expressions via the
    pipeline's backend'.

    The injected value is ``pipeline._execute``: a 1-arg callable that runs
    ``backend.execute(query)`` if a backend was passed to the pipeline, or
    falls back to ``query.execute()`` otherwise. Stats that issue their own
    queries (histograms, etc.) must use this instead of calling
    ``query.execute()`` directly so a user-supplied backend isn't bypassed.
    """
    pass


RAW_MARKER_TYPES = (RawSeries, SampledSeries, RawDataFrame, XorqColumn, XorqExpr, XorqExecute)


# ---------------------------------------------------------------------------
# StatKey — a named, typed slot in the DAG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StatKey:
    """A named, typed slot in the stat DAG."""
    name: str
    type: type  # Python type (int, float, Any, pd.Series, etc.)

    def __repr__(self):
        type_name = getattr(self.type, '__name__', str(self.type))
        return f"StatKey({self.name!r}, {type_name})"


# ---------------------------------------------------------------------------
# StatFunc — a registered stat computation
# ---------------------------------------------------------------------------

@dataclass
class StatFunc:
    """A registered stat computation.

    Attributes:
        name: identifier for this stat function
        func: the actual callable
        requires: list of StatKeys this function needs as input
        provides: list of StatKeys this function produces
        needs_raw: True if any parameter is RawSeries/SampledSeries/RawDataFrame
        column_filter: optional predicate on column dtype
        quiet: suppress error reporting
        default: fallback value on failure (MISSING = no fallback)
    """
    name: str
    func: Callable
    requires: List[StatKey]
    provides: List[StatKey]
    needs_raw: bool
    column_filter: Optional[Callable] = None
    quiet: bool = False
    default: Any = field(default_factory=lambda: MISSING)
    spread_dict_result: bool = False  # v1 compat: spread all dict keys into accumulator
    v1_computed: bool = False  # v1 compat: pass full accumulator as single dict arg


# ---------------------------------------------------------------------------
# Helpers for @stat decorator
# ---------------------------------------------------------------------------

def _is_typed_dict(tp) -> bool:
    """Check if a type is a TypedDict subclass."""
    if tp is None or not isinstance(tp, type):
        return False
    # TypedDict classes have __required_keys__ or __optional_keys__
    return hasattr(tp, '__required_keys__') or hasattr(tp, '__optional_keys__')


def _is_multiple_provides(tp) -> bool:
    """Check if a return type explicitly opts into MultipleProvides.

    Walks ``__orig_bases__`` because TypedDict's metaclass collapses
    ``__bases__`` to ``(dict,)`` and ``issubclass`` is unsupported on
    TypedDict types.

    Detection is best-effort: Python 3.11's TypedDict implementation
    discards ``__orig_bases__`` for subclasses, so on 3.11 this returns
    False even for genuine ``class Foo(MultipleProvides):`` declarations.
    Callers must fall through to ``_is_typed_dict`` for back-compat.
    """
    if not _is_typed_dict(tp):
        return False
    seen = set()
    stack = list(getattr(tp, '__orig_bases__', ()))
    while stack:
        base = stack.pop()
        if id(base) in seen:
            continue
        seen.add(id(base))
        if base is MultipleProvides:
            return True
        stack.extend(getattr(base, '__orig_bases__', ()))
    return False


def _expand_typed_dict_fields(tp) -> List[StatKey]:
    """One StatKey per declared field, type from the field's annotation."""
    return [StatKey(k, v) for k, v in get_type_hints(tp).items()]


def _get_provides_from_return_type(func_name: str, return_type) -> List[StatKey]:
    """Derive provided StatKeys from a stat func's return annotation.

    Three branches, in order:
      1. No annotation → single StatKey under the function name, type Any.
      2. ``MultipleProvides`` subclass (the documented multi-key idiom) →
         one StatKey per field. Detected on Python 3.12+ via
         ``__orig_bases__``; on 3.11 falls through to (3) since the
         TypedDict metaclass loses inheritance info.
      3. Bare TypedDict subclass (back-compat — pd_stats_v2 still has
         many of these) → one StatKey per field, identical to (2).
      4. Any other type → single StatKey under the function name.
    """
    if return_type is inspect.Parameter.empty or return_type is None:
        return [StatKey(func_name, Any)]

    if _is_multiple_provides(return_type):
        return _expand_typed_dict_fields(return_type)

    if _is_typed_dict(return_type):
        return _expand_typed_dict_fields(return_type)

    return [StatKey(func_name, return_type)]


def _get_requires_from_params(sig: inspect.Signature, hints: dict) -> tuple:
    """Derive required StatKeys and needs_raw flag from parameter annotations."""
    requires = []
    needs_raw = False

    for param_name, param in sig.parameters.items():
        if param_name in ('self', 'cls'):
            continue

        param_type = hints.get(param_name, Any)

        if param_type in RAW_MARKER_TYPES:
            needs_raw = True

        requires.append(StatKey(param_name, param_type))

    return requires, needs_raw


# ---------------------------------------------------------------------------
# @stat decorator
# ---------------------------------------------------------------------------

def stat(column_filter=None, quiet=False, default=MISSING):
    """Decorator that converts a function into a StatFunc.

    The function signature IS the contract:
      - Parameter names/types become `requires`
      - Function name (or each TypedDict / MultipleProvides field) becomes
        `provides`
      - RawSeries/SampledSeries/Xorq* params indicate raw data needs

    Single-provider stats: name the function the same as the accumulator
    key the rest of the DAG expects. Use ``MultipleProvides`` (a TypedDict
    alias) when one function should write several keys.

    Usage::

        @stat()
        def distinct_per(length: int, distinct_count: int) -> float:
            return distinct_count / length

        @stat(column_filter=is_numeric)
        def mean(ser: RawSeries) -> float:
            return ser.mean()

        @stat(default=0)
        def safe_ratio(a: int, b: int) -> float:
            return a / b

        class TypingResult(MultipleProvides):
            is_numeric: bool
            is_integer: bool

        @stat()
        def typing_stats(dtype: str) -> TypingResult:
            ...
    """
    def decorator(func):
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        return_type = hints.get('return', inspect.Parameter.empty)

        requires, needs_raw = _get_requires_from_params(sig, hints)
        provides_keys = _get_provides_from_return_type(func.__name__, return_type)

        stat_func = StatFunc(name=func.__name__, func=func, requires=requires, provides=provides_keys,
            needs_raw=needs_raw, column_filter=column_filter, quiet=quiet, default=default)

        # Attach metadata to the function so pipeline can find it
        func._stat_func = stat_func
        return func

    return decorator


# ---------------------------------------------------------------------------
# collect_stat_funcs — extract StatFunc objects from various sources
# ---------------------------------------------------------------------------

def collect_stat_funcs(obj) -> List[StatFunc]:
    """Collect StatFunc objects from a class, function, or StatFunc instance.

    - StatFunc instance: returned as-is in a list
    - Function with @stat: returns its ._stat_func
    - Class with @stat-decorated methods: collects all of them
    - Anything else: returns empty list
    """
    if isinstance(obj, StatFunc):
        return [obj]

    if callable(obj) and hasattr(obj, '_stat_func'):
        return [obj._stat_func]

    if isinstance(obj, type):
        # It's a class — collect all @stat-decorated methods
        funcs = []
        for name in sorted(dir(obj)):
            attr = getattr(obj, name, None)
            if callable(attr) and hasattr(attr, '_stat_func'):
                funcs.append(attr._stat_func)
        return funcs

    return []
