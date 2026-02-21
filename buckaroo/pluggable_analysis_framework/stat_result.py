"""Result types for the pluggable analysis framework v2.

Ok/Err result type with typed error propagation through the stat DAG.
Two failure modes clearly distinguished:
  - Config error (DAGConfigError) raised at pipeline construction
  - Runtime error (Err) propagated downstream per-column
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union

T = TypeVar('T')


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Successful stat computation result."""
    value: T


class UpstreamError(Exception):
    """A required input failed, so this stat cannot be computed."""

    def __init__(self, stat_func_name: str, failed_input: str, original_error: Exception):
        self.stat_func_name = stat_func_name
        self.failed_input = failed_input
        self.original_error = original_error
        super().__init__(
            f"Cannot compute '{stat_func_name}': input '{failed_input}' failed"
        )


@dataclass(frozen=True)
class Err:
    """Failed stat computation result."""
    error: Exception
    stat_func_name: str
    column_name: str
    inputs: Dict[str, Any] = field(default_factory=dict)


# Union type for stat results
StatResult = Union[Ok, Err]


@dataclass
class StatError:
    """Error report from stat pipeline execution, with reproduction support."""
    column: str
    stat_key: str
    error: Exception
    stat_func: Any  # StatFunc reference (Any to avoid circular import)
    inputs: Dict[str, Any] = field(default_factory=dict)

    def reproduce_code(self) -> str:
        """Generate standalone Python code to reproduce this error."""
        lines = []
        lines.append(f"# Error in {self.stat_func.name} for column '{self.column}':")

        # Determine if we need pandas import for series inputs
        has_series = False
        series_inputs = {}
        scalar_inputs = {}

        for k, v in self.inputs.items():
            try:
                import pandas as pd
                if isinstance(v, pd.Series):
                    has_series = True
                    series_inputs[k] = v
                    continue
            except ImportError:
                pass
            scalar_inputs[k] = v

        # Import the function's module
        if self.stat_func.func is not None:
            mod = getattr(self.stat_func.func, '__module__', None)
            qualname = getattr(self.stat_func.func, '__qualname__', self.stat_func.name)
            top_name = qualname.split('.')[0]
            if mod:
                lines.append(f"from {mod} import {top_name}")

        if has_series:
            lines.append("import pandas as pd")

        # Serialize series inputs
        for k, v in series_inputs.items():
            try:
                import pandas as pd
                lines.append(f"{k} = pd.Series({v.tolist()!r}, dtype='{v.dtype}')")
            except Exception:
                lines.append(f"{k} = ...  # could not serialize")

        # Build the function call
        args = []
        for k in self.inputs:
            if k in series_inputs:
                args.append(f"{k}={k}")
            else:
                args.append(f"{k}={scalar_inputs[k]!r}")

        func_name = self.stat_func.name
        err_type = type(self.error).__name__
        err_msg = str(self.error)
        lines.append(f"{func_name}({', '.join(args)})  # {err_type}: {err_msg}")

        return '\n'.join(lines)


def resolve_accumulator(
    accumulator: Dict[str, StatResult],
    column_name: str,
    key_to_func: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[StatError]]:
    """Convert Ok/Err accumulator to plain dict + error list.

    Args:
        accumulator: mapping of stat_name -> StatResult
        column_name: the column being processed
        key_to_func: mapping of stat_name -> StatFunc (for error reporting)

    Returns:
        (plain_dict, errors) where plain_dict has raw values for Ok results
        and None for Err results.
    """
    if key_to_func is None:
        key_to_func = {}

    plain: Dict[str, Any] = {}
    errors: List[StatError] = []

    for key, result in accumulator.items():
        if isinstance(result, Ok):
            plain[key] = result.value
        elif isinstance(result, Err):
            plain[key] = None
            stat_func = key_to_func.get(key)
            errors.append(StatError(
                column=column_name,
                stat_key=key,
                error=result.error,
                stat_func=stat_func,
                inputs=result.inputs,
            ))
        else:
            # Should not happen, but be defensive
            plain[key] = result

    return plain, errors
