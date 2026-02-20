"""Typed DAG construction for the pluggable analysis framework v2.

Replaces v1's order_analysis() and check_solvable() with type-aware
dependency resolution that supports column-type filtering.
"""
from __future__ import annotations

import graphlib
import warnings
from typing import Any, Dict, List, Set, Tuple

from .stat_func import StatFunc, StatKey, RAW_MARKER_TYPES


class DAGConfigError(Exception):
    """Raised when the stat DAG has unsatisfiable dependencies.

    This is a configuration-time error, not a runtime error.
    It means the set of stat functions cannot form a valid pipeline.
    """
    pass


def build_typed_dag(stat_funcs: List[StatFunc]) -> List[StatFunc]:
    """Build and topologically sort a typed stat DAG.

    1. Builds provides map: stat_name -> (StatKey, StatFunc)
    2. Validates all requirements have providers (raises DAGConfigError if not)
    3. Warns on type mismatches between provider and consumer
    4. Topologically sorts via graphlib
    5. Detects cycles

    Args:
        stat_funcs: list of StatFunc objects to order

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

            if req.name not in provides_map:
                raise DAGConfigError(
                    f"No function provides '{req.name}' (required by '{sf.name}')"
                )

            # Type compatibility check (warning, not error)
            provided_key, provider_func = provides_map[req.name]
            if (req.type is not Any and provided_key.type is not Any
                    and req.type != provided_key.type):
                if not (isinstance(req.type, type) and isinstance(provided_key.type, type)
                        and issubclass(provided_key.type, req.type)):
                    warnings.warn(
                        f"Type mismatch: '{sf.name}' expects '{req.name}' as "
                        f"{req.type.__name__}, but '{provider_func.name}' provides "
                        f"{provided_key.type.__name__}. beartype will enforce at runtime.",
                        stacklevel=2,
                    )

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


def build_column_dag(
    all_stat_funcs: List[StatFunc],
    column_dtype,
) -> List[StatFunc]:
    """Filter stat functions by column dtype and build DAG.

    Functions whose column_filter rejects this dtype are excluded.
    Functions whose requirements become unsatisfiable after filtering
    are also excluded (cascade removal). This is NOT an error — it
    means the stat doesn't apply to this column type.

    Args:
        all_stat_funcs: full set of stat functions
        column_dtype: the dtype of the column being processed

    Returns:
        Topologically sorted list of applicable StatFunc objects
    """
    # Step 1: filter by column_filter predicate
    candidates = [
        sf for sf in all_stat_funcs
        if sf.column_filter is None or sf.column_filter(column_dtype)
    ]

    # Step 2: iteratively remove funcs with unmet deps until stable
    prev_count = -1
    while len(candidates) != prev_count:
        prev_count = len(candidates)

        # Build current provides set
        provides: Set[str] = set()
        for sf in candidates:
            for sk in sf.provides:
                provides.add(sk.name)

        # Keep only funcs whose requirements are all met
        candidates = [
            sf for sf in candidates
            if all(
                req.type in RAW_MARKER_TYPES or req.name in provides
                for req in sf.requires
            )
        ]

    if not candidates:
        return []

    return build_typed_dag(candidates)
