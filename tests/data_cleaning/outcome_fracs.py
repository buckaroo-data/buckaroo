"""
Cleaning Outcome Fraction Functions

Given an original series and the result of applying a cleaning operation,
these functions measure what proportion of values were:

- **direct**: successfully converted via straightforward type cast, no content
  change. Example: "238" → int(238)
- **modified**: successfully cleaned but required interpretation — characters
  were added, removed, or rearranged. Example: "867-5309" → int(8675309)
- **discarded**: no valid conversion possible, mapped to null/NaN.
  Example: "N/A" → NaN

These three categories are mutually exclusive. For non-null original values:
    direct_frac + modified_frac + discarded_frac ≈ 1.0

Also provides:
    cleaned_frac = direct_frac + modified_frac (total success rate)
"""

import re

import numpy as np
import pandas as pd


# ============================================================================
# Core: element-wise classification
# ============================================================================

def classify_cleaning_outcomes(
    original: pd.Series,
    cleaned: pd.Series,
) -> pd.Series:
    """Classify each value's cleaning outcome.

    Returns a Series with values:
        'direct'         — converted with no content change
        'modified'       — converted but content was altered/interpreted
        'discarded'      — no valid conversion (cleaned is null)
        'null_original'  — original was already null (excluded from fracs)
    """
    result = pd.Series("null_original", index=original.index, dtype="object")

    orig_notna = original.notna()
    cleaned_notna = cleaned.notna()

    # Discarded: original present, cleaned absent
    result[orig_notna & ~cleaned_notna] = "discarded"

    # Both present: check if direct or modified
    both = orig_notna & cleaned_notna
    if both.any():
        is_direct = _compare_values(original, cleaned, both)
        result[both & is_direct] = "direct"
        result[both & ~is_direct] = "modified"

    return result


def _compare_values(
    original: pd.Series,
    cleaned: pd.Series,
    both_mask: pd.Series,
) -> pd.Series:
    """Determine which values are 'direct' conversions (no content change).

    Uses dtype-aware comparison:
    - Numeric cleaned: parse original as number, compare numerically.
      "238" → 238 is direct; "867-5309" can't parse → modified.
    - Datetime cleaned: parse original as datetime, compare.
      "2024-01-15" → same Timestamp is direct; "next Tuesday" can't → modified.
    - Bool cleaned: case-insensitive match of "True"/"False".
    - String cleaned: normalized string comparison.
    """
    orig_sub = original[both_mask]
    clean_sub = cleaned[both_mask]
    result = pd.Series(False, index=original.index)

    # Check bool BEFORE numeric — BooleanDtype is considered numeric by pandas
    if pd.api.types.is_bool_dtype(cleaned.dtype):
        orig_str = orig_sub.astype(str).str.strip().str.lower()
        clean_str = clean_sub.astype(str).str.strip().str.lower()
        result[both_mask] = (orig_str == clean_str).values
        return result

    if pd.api.types.is_numeric_dtype(cleaned.dtype):
        # Direct if the original string parses to the same number
        orig_numeric = pd.to_numeric(orig_sub, errors="coerce")
        clean_numeric = pd.to_numeric(clean_sub, errors="coerce")
        match = (orig_numeric == clean_numeric) & orig_numeric.notna()
        result[both_mask] = match.values
        return result

    if pd.api.types.is_datetime64_any_dtype(cleaned.dtype):
        orig_dt = pd.to_datetime(orig_sub, errors="coerce")
        match = (orig_dt == clean_sub) & orig_dt.notna()
        result[both_mask] = match.values
        return result

    # Default: string comparison with normalization
    orig_str = orig_sub.astype(str).str.strip()
    clean_str = clean_sub.astype(str).str.strip()
    # Normalize trailing .0 for float-like strings
    orig_norm = orig_str.str.replace(r"\.0$", "", regex=True)
    clean_norm = clean_str.str.replace(r"\.0$", "", regex=True)
    result[both_mask] = (orig_norm == clean_norm).values
    return result


# ============================================================================
# Core: fraction computation
# ============================================================================

_EMPTY = {
    "cleaned_frac": 0.0,
    "direct_frac": 0.0,
    "modified_frac": 0.0,
    "discarded_frac": 0.0,
}


def cleaning_outcome_fracs(
    original: pd.Series,
    cleaned: pd.Series,
) -> dict[str, float]:
    """Compute cleaning outcome fractions.

    Parameters
    ----------
    original : pd.Series — the raw/dirty values
    cleaned  : pd.Series — the result after cleaning

    Returns
    -------
    dict with:
        cleaned_frac   — total proportion successfully converted
        direct_frac    — proportion converted via direct type cast
        modified_frac  — proportion converted but content was altered
        discarded_frac — proportion that couldn't be converted
    """
    if len(original) == 0:
        return dict(_EMPTY)

    categories = classify_cleaning_outcomes(original, cleaned)

    n = int((categories != "null_original").sum())
    if n == 0:
        return dict(_EMPTY)

    direct = int((categories == "direct").sum())
    modified = int((categories == "modified").sum())
    discarded = int((categories == "discarded").sum())

    return {
        "cleaned_frac": (direct + modified) / n,
        "direct_frac": direct / n,
        "modified_frac": modified / n,
        "discarded_frac": discarded / n,
    }


# ============================================================================
# Pre-built: common type-parse outcome functions
# ============================================================================

def numeric_parse_outcomes(ser: pd.Series) -> dict[str, float]:
    """Try pd.to_numeric and compute outcome fracs.

    >>> s = pd.Series(["238", "867-5309", "N/A", "42"])
    >>> r = numeric_parse_outcomes(s)
    >>> r["direct_frac"]    # "238" and "42" parse directly
    0.5
    >>> r["discarded_frac"] # "867-5309" and "N/A" fail
    0.5
    """
    cleaned = pd.to_numeric(ser, errors="coerce")
    return cleaning_outcome_fracs(ser, cleaned)


def int_parse_outcomes(ser: pd.Series) -> dict[str, float]:
    """Try integer parsing (to_numeric, keep only whole numbers)."""
    numeric = pd.to_numeric(ser, errors="coerce")
    is_int = numeric.notna() & (numeric == numeric.round(0))
    cleaned = numeric.where(is_int)
    return cleaning_outcome_fracs(ser, cleaned)


def date_parse_outcomes(ser: pd.Series, format=None) -> dict[str, float]:
    """Try pd.to_datetime and compute outcome fracs.

    Date format standardization (e.g. "Jan 15, 2024" → 2024-01-15) is
    classified as 'direct' because the date VALUE is preserved — only
    the representation changed.
    """
    cleaned = pd.to_datetime(ser, errors="coerce", format=format)
    return cleaning_outcome_fracs(ser, cleaned)


def bool_parse_outcomes(ser: pd.Series) -> dict[str, float]:
    """Try boolean parsing and compute outcome fracs.

    Recognizes: true/false, yes/no, y/n, t/f, on/off, 1/0.
    "true" → True is direct; "yes" → True is modified (content changed).
    """
    _TRUTHY = {"true", "yes", "y", "t", "on", "1"}
    _FALSY = {"false", "no", "n", "f", "off", "0"}

    def _parse(val):
        if pd.isna(val):
            return pd.NA
        s = str(val).strip().lower()
        if s in _TRUTHY:
            return True
        if s in _FALSY:
            return False
        return pd.NA

    cleaned = ser.map(_parse).astype("boolean")
    return cleaning_outcome_fracs(ser, cleaned)


def formatted_number_outcomes(ser: pd.Series) -> dict[str, float]:
    """Strip currency symbols, thousands separators, accounting notation,
    then parse as numeric.

    "$1,234.56" → 1234.56 is modified (formatting stripped).
    "1234.56" → 1234.56 is direct (already plain numeric).
    """
    _CURRENCY_RE = re.compile(r"[$€£¥₹,\s']")
    _UNIT_SUFFIX_RE = re.compile(r"\s*(USD|EUR|GBP|JPY)\s*$", re.I)

    def _strip_format(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip()
        # Accounting negatives: (123.45) → -123.45
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        s = _CURRENCY_RE.sub("", s)
        s = _UNIT_SUFFIX_RE.sub("", s)
        try:
            return float(s)
        except (ValueError, TypeError):
            return np.nan

    cleaned = ser.map(_strip_format)
    return cleaning_outcome_fracs(ser, cleaned)


# ============================================================================
# Convenience: apply a cleaning function and measure all columns
# ============================================================================

def measure_cleaning_function(
    df: pd.DataFrame,
    clean_fn,
    column_pairs: list[tuple[str, str]] | None = None,
) -> dict[str, dict[str, float]]:
    """Apply a cleaning function and compute outcome fracs per column.

    Parameters
    ----------
    df : pd.DataFrame — the dirty input
    clean_fn : callable — takes df, returns cleaned df
    column_pairs : list of (orig_col, clean_col), optional
        If None, auto-detects columns ending in '_clean' and pairs them
        with the corresponding original column.

    Returns
    -------
    dict mapping original column name → outcome fracs dict
    """
    cleaned_df = clean_fn(df)

    if column_pairs is None:
        column_pairs = []
        for col in cleaned_df.columns:
            if col.endswith("_clean"):
                orig = col.removesuffix("_clean")
                if orig in df.columns:
                    column_pairs.append((orig, col))

    results = {}
    for orig_col, clean_col in column_pairs:
        results[orig_col] = cleaning_outcome_fracs(
            df[orig_col],
            cleaned_df[clean_col],
        )
    return results
