"""Column type filter predicates for stat functions.

These predicates determine which columns a stat function applies to,
replacing ad-hoc isinstance/dtype checks inside function bodies.

Each predicate works for both pandas and polars dtypes.

Note: polars dtype equality (==) has surprising behavior with non-polars
types (e.g., `np.dtype('O') == pl.Int8` returns True). We guard against
this by checking isinstance(dtype, pl.DataType) before polars comparisons.
"""
from typing import Callable


def _is_polars_dtype(dtype) -> bool:
    """Check if dtype is a polars DataType instance or subclass."""
    try:
        import polars as pl
        return isinstance(dtype, (pl.DataType, type)) and (
            isinstance(dtype, pl.DataType) or
            (isinstance(dtype, type) and issubclass(dtype, pl.DataType))
        )
    except (ImportError, TypeError):
        return False


def is_numeric(dtype) -> bool:
    """Check if dtype is numeric (pandas or polars)."""
    if _is_polars_dtype(dtype):
        try:
            import polars as pl
            return dtype in (
                pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                pl.Float32, pl.Float64,
            )
        except ImportError:
            return False

    try:
        import pandas as pd
        return bool(pd.api.types.is_numeric_dtype(dtype))
    except (ImportError, TypeError):
        pass

    return False


def is_string(dtype) -> bool:
    """Check if dtype is string/object (pandas or polars)."""
    if _is_polars_dtype(dtype):
        try:
            import polars as pl
            return dtype in (pl.Utf8, pl.String)
        except (ImportError, AttributeError):
            return False

    try:
        import pandas as pd
        return bool(pd.api.types.is_string_dtype(dtype))
    except (ImportError, TypeError):
        pass

    return False


def is_temporal(dtype) -> bool:
    """Check if dtype is datetime/date/time/timedelta (pandas or polars)."""
    if _is_polars_dtype(dtype):
        try:
            import polars as pl
            return dtype in (pl.Date, pl.Datetime, pl.Time, pl.Duration)
        except (ImportError, AttributeError):
            return False

    try:
        import pandas as pd
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return True
        if pd.api.types.is_timedelta64_dtype(dtype):
            return True
    except (ImportError, TypeError):
        pass

    return False


def is_boolean(dtype) -> bool:
    """Check if dtype is boolean (pandas or polars)."""
    if _is_polars_dtype(dtype):
        try:
            import polars as pl
            return dtype is pl.Boolean or dtype == pl.Boolean
        except (ImportError, AttributeError):
            return False

    try:
        import pandas as pd
        return bool(pd.api.types.is_bool_dtype(dtype))
    except (ImportError, TypeError):
        pass

    return False


def is_numeric_not_bool(dtype) -> bool:
    """True for numeric types excluding boolean."""
    return is_numeric(dtype) and not is_boolean(dtype)


def any_of(*predicates: Callable) -> Callable:
    """Combinator: returns True if any predicate matches."""
    def combined(dtype) -> bool:
        return any(p(dtype) for p in predicates)
    combined.__name__ = f"any_of({', '.join(p.__name__ for p in predicates)})"
    return combined


def not_(predicate: Callable) -> Callable:
    """Combinator: negates a predicate."""
    def negated(dtype) -> bool:
        return not predicate(dtype)
    negated.__name__ = f"not_({predicate.__name__})"
    return negated
