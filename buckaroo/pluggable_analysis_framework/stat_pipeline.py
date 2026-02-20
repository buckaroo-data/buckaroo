"""StatPipeline — top-level orchestrator for the pluggable analysis framework v2.

Replaces AnalysisPipeline with typed DAG execution and Ok/Err error propagation.
Accepts a mix of v2 @stat functions and v1 ColAnalysis classes (via adapter).
"""
from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import pandas as pd

from buckaroo.df_util import old_col_new_col

from .col_analysis import ColAnalysis, ColMeta, ErrDict, SDType
from .stat_func import (
    StatFunc, StatKey, RawSeries, SampledSeries, RawDataFrame,
    RAW_MARKER_TYPES, MISSING, collect_stat_funcs,
)
from .stat_result import Ok, Err, UpstreamError, StatError, StatResult, resolve_accumulator
from .typed_dag import build_typed_dag, build_column_dag, DAGConfigError
from .v1_adapter import col_analysis_to_stat_funcs
from .utils import PERVERSE_DF


def _normalize_inputs(inputs: list) -> List[StatFunc]:
    """Convert a mixed list of StatFunc, @stat functions, and ColAnalysis classes to StatFuncs."""
    all_funcs: List[StatFunc] = []

    for obj in inputs:
        # Already a StatFunc
        if isinstance(obj, StatFunc):
            all_funcs.append(obj)
            continue

        # A @stat-decorated function
        if callable(obj) and hasattr(obj, '_stat_func'):
            all_funcs.append(obj._stat_func)
            continue

        # A class with @stat-decorated methods (stat group)
        if isinstance(obj, type) and not issubclass(obj, ColAnalysis):
            collected = collect_stat_funcs(obj)
            if collected:
                all_funcs.extend(collected)
                continue

        # A v1 ColAnalysis subclass
        if isinstance(obj, type) and issubclass(obj, ColAnalysis):
            adapted = col_analysis_to_stat_funcs(obj)
            all_funcs.extend(adapted)
            continue

        raise TypeError(
            f"Cannot convert {obj!r} to StatFunc. Expected StatFunc, "
            f"@stat-decorated function, stat group class, or ColAnalysis subclass."
        )

    return all_funcs


def _execute_stat_func(
    sf: StatFunc,
    accumulator: Dict[str, StatResult],
    column_name: str,
    raw_series=None,
    sampled_series=None,
    raw_dataframe=None,
) -> None:
    """Execute a single StatFunc, updating the accumulator in place.

    Handles:
    - Raw data injection (RawSeries, SampledSeries, RawDataFrame)
    - Upstream error propagation
    - Multi-value return unpacking (for TypedDict and v1 adapter dict returns)
    - Default fallback on error
    """
    # Build kwargs from requires
    kwargs = {}
    has_upstream_err = False

    for req in sf.requires:
        if req.type is RawSeries:
            kwargs[req.name] = raw_series
            continue
        if req.type is SampledSeries:
            kwargs[req.name] = sampled_series if sampled_series is not None else raw_series
            continue
        if req.type is RawDataFrame:
            kwargs[req.name] = raw_dataframe
            continue

        # Look up in accumulator
        if req.name in accumulator:
            result = accumulator[req.name]
            if isinstance(result, Ok):
                kwargs[req.name] = result.value
            elif isinstance(result, Err):
                # Upstream error — propagate to all outputs
                upstream_err = UpstreamError(sf.name, req.name, result.error)
                for sk in sf.provides:
                    accumulator[sk.name] = Err(
                        error=upstream_err,
                        stat_func_name=sf.name,
                        column_name=column_name,
                        inputs={},
                    )
                has_upstream_err = True
                break
        else:
            # Required key not in accumulator — should not happen after DAG validation
            # but handle gracefully
            err = DAGConfigError(
                f"Required key '{req.name}' not found in accumulator for '{sf.name}'"
            )
            for sk in sf.provides:
                accumulator[sk.name] = Err(
                    error=err,
                    stat_func_name=sf.name,
                    column_name=column_name,
                    inputs={},
                )
            has_upstream_err = True
            break

    if has_upstream_err:
        return

    # Execute the function
    try:
        result = sf.func(**kwargs)

        # Unpack result — always try dict unpacking first
        # This handles both TypedDict returns (v2) and v1 adapter dict returns
        if isinstance(result, dict) and any(sk.name in result for sk in sf.provides):
            for sk in sf.provides:
                if sk.name in result:
                    accumulator[sk.name] = Ok(result[sk.name])
                else:
                    accumulator[sk.name] = Ok(None)
        elif len(sf.provides) == 1:
            accumulator[sf.provides[0].name] = Ok(result)
        else:
            # Non-dict multi-value — assign result to all (unusual)
            for sk in sf.provides:
                accumulator[sk.name] = Ok(result)

    except Exception as e:
        # Check for default fallback
        if sf.default is not MISSING:
            for sk in sf.provides:
                accumulator[sk.name] = Ok(sf.default)
        else:
            for sk in sf.provides:
                accumulator[sk.name] = Err(
                    error=e,
                    stat_func_name=sf.name,
                    column_name=column_name,
                    inputs=kwargs.copy(),
                )


class StatPipeline:
    """Top-level orchestrator for the pluggable analysis framework v2.

    Accepts a mix of:
    - StatFunc objects (v2)
    - @stat-decorated functions (v2)
    - Stat group classes with @stat methods (v2)
    - ColAnalysis subclasses (v1 via adapter)

    Builds a typed DAG, executes per-column with Ok/Err error propagation,
    and supports column-type filtering.

    Usage::

        pipeline = StatPipeline([TypingStats, DefaultSummaryStats, distinct_per])
        result, errors = pipeline.process_df(my_df)
    """

    def __init__(
        self,
        stat_funcs: list,
        unit_test: bool = True,
    ):
        self.all_stat_funcs = _normalize_inputs(stat_funcs)
        self._original_inputs = list(stat_funcs)

        # Validate the full DAG (raises DAGConfigError if invalid)
        self.ordered_stat_funcs = build_typed_dag(self.all_stat_funcs)

        # Build key -> StatFunc mapping for error reporting
        self._key_to_func: Dict[str, StatFunc] = {}
        for sf in self.ordered_stat_funcs:
            for sk in sf.provides:
                self._key_to_func[sk.name] = sf

        # Cache provided keys set (for compatibility)
        self.provided_summary_facts_set = set(self._key_to_func.keys())

        if unit_test:
            self._unit_test_result = self.unit_test()

    def process_column(
        self,
        column_name: str,
        column_dtype,
        raw_series=None,
        sampled_series=None,
        raw_dataframe=None,
    ) -> Tuple[Dict[str, Any], List[StatError]]:
        """Process a single column through the stat DAG.

        1. Filters stat functions by column dtype
        2. Executes in topological order with Ok/Err accumulator
        3. Returns (plain_dict, errors)
        """
        # Build column-specific DAG (filters by dtype)
        column_funcs = build_column_dag(self.all_stat_funcs, column_dtype)

        # Execute in order
        accumulator: Dict[str, StatResult] = {}
        for sf in column_funcs:
            _execute_stat_func(
                sf, accumulator, column_name,
                raw_series=raw_series,
                sampled_series=sampled_series,
                raw_dataframe=raw_dataframe,
            )

        # Build key_to_func for this column's funcs
        col_key_to_func: Dict[str, StatFunc] = {}
        for sf in column_funcs:
            for sk in sf.provides:
                col_key_to_func[sk.name] = sf

        return resolve_accumulator(accumulator, column_name, col_key_to_func)

    def process_df(
        self,
        df: pd.DataFrame,
        debug: bool = False,
    ) -> Tuple[SDType, List[StatError]]:
        """Process all columns of a DataFrame.

        Returns:
            (summary_dict, all_errors) where summary_dict is SDType-compatible
            (column_name -> {stat_name -> value}).
        """
        if len(df) == 0:
            return {}, []

        summary: SDType = {}
        all_errors: List[StatError] = []

        for orig_col_name, rewritten_col_name in old_col_new_col(df):
            ser = df[orig_col_name]
            col_dtype = ser.dtype

            col_result, col_errors = self.process_column(
                column_name=rewritten_col_name,
                column_dtype=col_dtype,
                raw_series=ser,
                sampled_series=ser,
                raw_dataframe=df,
            )

            # Add metadata (matches v1 behavior)
            col_result['orig_col_name'] = orig_col_name
            col_result['rewritten_col_name'] = rewritten_col_name

            summary[rewritten_col_name] = col_result
            all_errors.extend(col_errors)

        return summary, all_errors

    def process_df_v1_compat(
        self,
        df: pd.DataFrame,
        debug: bool = False,
    ) -> Tuple[SDType, ErrDict]:
        """Process DataFrame with v1-compatible error format.

        Returns (SDType, ErrDict) matching the v1 AnalysisPipeline interface.
        """
        summary, errors = self.process_df(df, debug=debug)

        # Convert StatError list to v1 ErrDict format
        errs: ErrDict = {}
        for se in errors:
            # Find the original ColAnalysis class if this came from v1 adapter
            kls = _find_v1_class(se.stat_func, self._original_inputs) if se.stat_func else None
            err_key = (se.column, se.stat_func.name if se.stat_func else "unknown")
            errs[err_key] = (se.error, kls)

        return summary, errs

    def unit_test(self) -> Tuple[bool, List[StatError]]:
        """Test the pipeline against PERVERSE_DF."""
        try:
            _, errors = self.process_df(PERVERSE_DF)
            if not errors:
                return True, []
            return False, errors
        except Exception:
            return False, []

    def add_stat(self, stat_func_or_class) -> Tuple[bool, List[StatError]]:
        """Add a stat function or ColAnalysis class interactively.

        Validates the DAG and runs unit test against PERVERSE_DF.
        """
        new_inputs = list(self._original_inputs)

        # Remove existing with same name if re-adding
        if isinstance(stat_func_or_class, type):
            new_inputs = [
                inp for inp in new_inputs
                if not (isinstance(inp, type) and inp.__name__ == stat_func_or_class.__name__)
            ]
        new_inputs.append(stat_func_or_class)

        try:
            new_funcs = _normalize_inputs(new_inputs)
            new_ordered = build_typed_dag(new_funcs)
        except DAGConfigError as e:
            return False, [StatError(
                column="<dag>", stat_key="<config>",
                error=e, stat_func=None,
            )]

        # Update internal state
        self.all_stat_funcs = new_funcs
        self.ordered_stat_funcs = new_ordered
        self._original_inputs = new_inputs
        self._key_to_func = {}
        for sf in self.ordered_stat_funcs:
            for sk in sf.provides:
                self._key_to_func[sk.name] = sf
        self.provided_summary_facts_set = set(self._key_to_func.keys())

        # Unit test
        passed, errors = self.unit_test()
        return passed, errors

    def test_stat(self, stat_name: str, inputs: Dict[str, Any]) -> Any:
        """Test a single stat function with given inputs.

        Returns Ok(value) or Err(exception).
        """
        # Find the stat func
        sf = self._key_to_func.get(stat_name)
        if sf is None:
            raise KeyError(f"No stat function provides '{stat_name}'")

        try:
            result = sf.func(**inputs)
            return Ok(result)
        except Exception as e:
            return Err(error=e, stat_func_name=sf.name, column_name="<test>")

    def explain(self, stat_name: str) -> str:
        """Return a human-readable description of a stat function."""
        sf = self._key_to_func.get(stat_name)
        if sf is None:
            raise KeyError(f"No stat function provides '{stat_name}'")

        lines = [f"StatFunc: {sf.name}"]
        req_strs = [f"{sk.name} ({sk.type.__name__ if hasattr(sk.type, '__name__') else sk.type})"
                     for sk in sf.requires]
        lines.append(f"  requires: {', '.join(req_strs) if req_strs else 'none'}")

        prov_strs = [f"{sk.name} ({sk.type.__name__ if hasattr(sk.type, '__name__') else sk.type})"
                      for sk in sf.provides]
        lines.append(f"  provides: {', '.join(prov_strs)}")

        if sf.column_filter is not None:
            filter_name = getattr(sf.column_filter, '__name__', repr(sf.column_filter))
            lines.append(f"  column_filter: {filter_name}")
        else:
            lines.append("  column_filter: None (all columns)")

        if sf.default is not MISSING:
            lines.append(f"  default: {sf.default!r}")

        return '\n'.join(lines)

    def print_errors(self, errors: List[StatError]) -> None:
        """Print reproduction code for all errors."""
        for err in errors:
            if err.stat_func is not None:
                print(err.reproduce_code())
                print()


def _find_v1_class(stat_func: Optional[StatFunc], original_inputs: list) -> Any:
    """Find the original v1 ColAnalysis class for a stat func name."""
    if stat_func is None:
        return None

    # The v1 adapter names funcs as "ClassName__series" or "ClassName__computed"
    name = stat_func.name
    for suffix in ('__series', '__computed'):
        if name.endswith(suffix):
            class_name = name[:-len(suffix)]
            for inp in original_inputs:
                if isinstance(inp, type) and inp.__name__ == class_name:
                    return inp
    return None
