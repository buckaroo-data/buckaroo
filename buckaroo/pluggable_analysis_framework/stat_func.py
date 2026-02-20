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
from typing import Any, Callable, List, Optional, get_type_hints


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


RAW_MARKER_TYPES = (RawSeries, SampledSeries, RawDataFrame)


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


def _get_provides_from_return_type(func_name: str, return_type) -> List[StatKey]:
    """Derive provided StatKeys from return annotation."""
    if return_type is inspect.Parameter.empty or return_type is None:
        return [StatKey(func_name, Any)]

    if _is_typed_dict(return_type):
        provides = []
        for key, val_type in get_type_hints(return_type).items():
            provides.append(StatKey(key, val_type))
        return provides

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
      - Return type becomes `provides`
      - RawSeries/SampledSeries params indicate raw data needs

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
    """
    def decorator(func):
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        return_type = hints.get('return', inspect.Parameter.empty)

        requires, needs_raw = _get_requires_from_params(sig, hints)
        provides = _get_provides_from_return_type(func.__name__, return_type)

        stat_func = StatFunc(
            name=func.__name__,
            func=func,
            requires=requires,
            provides=provides,
            needs_raw=needs_raw,
            column_filter=column_filter,
            quiet=quiet,
            default=default,
        )

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
