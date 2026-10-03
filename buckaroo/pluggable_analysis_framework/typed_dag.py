"""Typed DAG construction for the pluggable analysis framework.

Type-aware dependency resolution and cycle/solvability checking for stat
functions, with support for column-type filtering.
"""
from __future__ import annotations

import graphlib
import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

from .stat_func import StatFunc, StatKey, RAW_MARKER_TYPES


class DAGConfigError(Exception):
    """Raised when the stat DAG has unsatisfiable dependencies.

    This is a configuration-time error, not a runtime error.
    It means the set of stat functions cannot form a valid pipeline.
    """
    pass


def build_typed_dag(stat_funcs: List[StatFunc], external_keys: Set[str] = frozenset()) -> List[StatFunc]:
    """Build and topologically sort a typed stat DAG.

    1. Builds provides map: stat_name -> (StatKey, StatFunc)
    2. Validates all requirements have providers (raises DAGConfigError if not)
    3. Warns on type mismatches between provider and consumer
    4. Topologically sorts via graphlib
    5. Detects cycles

    Args:
        stat_funcs: list of StatFunc objects to order
        external_keys: keys provided externally (e.g. orig_col_name), skip validation

    Returns:
        Topologically sorted list of StatFunc objects

    Raises:
        DAGConfigError: if a required stat has no provider, or if a cycle exists
    """
    if not stat_funcs:
        return []

    # Build provides map: stat_name -> (StatKey, StatFunc)
    provides_map: Dict[str, Tuple[StatKey, StatFunc]] = {}
    for sf in stat_funcs:
        for sk in sf.provides:
            provides_map[sk.name] = (sk, sf)

    # Validate all requirements are satisfiable
    for sf in stat_funcs:
        for req in sf.requires:
            if req.type in RAW_MARKER_TYPES:
                continue  # Raw types are provided by the executor, not the DAG

            if req.name in external_keys:
                continue  # Provided externally

            if req.name not in provides_map:
                raise DAGConfigError(
                    f"No function provides '{req.name}' (required by '{sf.name}')")

            # Type compatibility check (warning, not error)
            provided_key, provider_func = provides_map[req.name]
            if (req.type is not Any and provided_key.type is not Any
                    and req.type != provided_key.type):
                if not (isinstance(req.type, type) and isinstance(provided_key.type, type)
                        and issubclass(provided_key.type, req.type)):
                    warnings.warn(f"Type mismatch: '{sf.name}' expects '{req.name}' as "
                        f"{req.type.__name__}, but '{provider_func.name}' provides "
                        f"{provided_key.type.__name__}. beartype will enforce at runtime.", stacklevel=2)

    # Build dependency graph for topological sort
    # Each StatFunc is identified by its name
    graph: Dict[str, Set[str]] = {}
    func_map: Dict[str, StatFunc] = {}

    for sf in stat_funcs:
        func_map[sf.name] = sf
        deps: Set[str] = set()
        for req in sf.requires:
            if req.type in RAW_MARKER_TYPES:
                continue
            if req.name in provides_map:
                provider = provides_map[req.name][1]
                if provider.name != sf.name:
                    deps.add(provider.name)
        graph[sf.name] = deps

    # Topological sort
    ts = graphlib.TopologicalSorter(graph)
    try:
        order = list(ts.static_order())
    except graphlib.CycleError as e:
        raise DAGConfigError(f"Cycle detected in stat DAG: {e}") from e

    # Map back to StatFunc objects (only those in our input set)
    return [func_map[name] for name in order if name in func_map]


def row_gated(sf: StatFunc, row_count: Optional[int]) -> bool:
    """True when ``sf.max_rows`` is set and the frame has more rows than that."""
    return row_count is not None and sf.max_rows is not None and row_count > sf.max_rows


def build_column_dag(all_stat_funcs: List[StatFunc], column_dtype, external_keys: Set[str] = frozenset(),
        row_count: Optional[int] = None) -> List[StatFunc]:
    """Filter stat functions by column dtype and build DAG.

    Functions whose column_filter rejects this dtype are excluded, as are
    functions whose ``max_rows`` is below ``row_count`` (the row gate; a
    ``row_count`` of None applies no gate). Functions whose requirements
    become unsatisfiable after filtering are also excluded (cascade
    removal). This is NOT an error — it means the stat doesn't apply to
    this column type, or doesn't run on a frame this size.

    Args:
        all_stat_funcs: full set of stat functions
        column_dtype: the dtype of the column being processed
        row_count: the frame's row count, for ``max_rows`` gating

    Returns:
        Topologically sorted list of applicable StatFunc objects
    """
    # Step 1: filter by column_filter predicate and the row gate
    candidates = [
        sf for sf in all_stat_funcs
        if (sf.column_filter is None or sf.column_filter(column_dtype)) and not row_gated(sf, row_count)
    ]

    # Step 2: iteratively remove funcs with unmet deps until stable
    prev_count = -1
    while len(candidates) != prev_count:
        prev_count = len(candidates)

        # Build current provides set
        provides: Set[str] = set(external_keys)
        for sf in candidates:
            for sk in sf.provides:
                provides.add(sk.name)

        # Keep only funcs whose requirements are all met
        candidates = [
            sf for sf in candidates
            if all(
                req.type in RAW_MARKER_TYPES or req.name in provides
                for req in sf.requires)
        ]

    if not candidates:
        return []

    return build_typed_dag(candidates, external_keys=external_keys)


def gated_stat_keys(all_stat_funcs: List[StatFunc], column_dtype, external_keys: Set[str],
        gated_funcs: List[StatFunc]) -> List[str]:
    """Keys the row gate removed from one column's DAG.

    ``gated_funcs`` is the DAG ``build_column_dag`` built with a row_count;
    any key the ungated DAG provides that it doesn't is gated, directly or
    through the cascade. Sorted, so callers can compare lists.
    """
    kept = {sf.name for sf in gated_funcs}
    keys: Set[str] = set()
    for sf in build_column_dag(all_stat_funcs, column_dtype, external_keys=external_keys):
        if sf.name not in kept:
            keys.update(sk.name for sk in sf.provides)
    return sorted(keys)
