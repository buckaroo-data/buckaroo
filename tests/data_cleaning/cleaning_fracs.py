"""
Data Cleaning Fraction / Measure Functions

Each function takes a pd.Series and returns a float (0.0 to 1.0)
representing what proportion of the series is a candidate for a
given cleaning method. These are diagnostic heuristics — they tell
you whether a cleaning operation is worth applying to a column.

Convention: function names end in _frac, return float.
All operations are vectorized (str accessors, numpy) — no .apply(lambda).
"""

import re

import numpy as np
import pandas as pd


# ============================================================================
# Helpers
# ============================================================================

def _sample(ser: pd.Series, n: int = 500) -> pd.Series:
    """Sample for performance on large series."""
    if len(ser) <= n:
        return ser
    return ser.sample(n, random_state=42)


def _as_str(ser: pd.Series) -> pd.Series:
    """Coerce series to string, filling NaN with empty string for str ops."""
    return ser.astype(str).fillna("")


def _is_stringlike(ser: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(ser) or pd.api.types.is_object_dtype(ser)


# ============================================================================
# 1. Phone number detection
# ============================================================================

_PHONE_PAT = (
    r"(?:\+?1[\s.-]?)?"
    r"\(?\d{3}\)?[\s.-]?"
    r"\d{3}[\s.-]?\d{4}"
)


def phone_number_frac(ser: pd.Series) -> float:
    """Fraction of values that contain a phone number pattern."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_PHONE_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 2. Mixed date format detection
# ============================================================================

# Combined OR pattern for all date-like formats
_DATE_COMBINED_PAT = (
    r"^\d{4}-\d{2}-\d{2}"          # ISO
    r"|^\d{1,2}/\d{1,2}/\d{2,4}$"  # US or Euro slash
    r"|^\d{1,2}-\w{3}-\d{4}$"      # 15-Jan-2024
    r"|^\w{3,9}\s+\d{1,2},?\s+\d{4}$"  # Jan 15, 2024
    r"|^\d{8}$"                      # compact YYYYMMDD
    r"|^\d{10}$"                     # Unix timestamp
    r"|^\d{5}$"                      # Excel serial
)

# Individual patterns for format-counting (used only in mixed_date_format_frac)
_DATE_INDIVIDUAL_PATS = [
    r"^\d{4}-\d{2}-\d{2}",
    r"^\d{1,2}/\d{1,2}/\d{2,4}$",
    r"^\d{1,2}-\w{3}-\d{4}$",
    r"^\w{3,9}\s+\d{1,2},?\s+\d{4}$",
    r"^\d{8}$",
    r"^\d{10}$",
    r"^\d{5}$",
]


def date_parseable_frac(ser: pd.Series) -> float:
    """Fraction of values that look like a date in any format."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    return s.str.contains(_DATE_COMBINED_PAT, regex=True, na=False).sum() / len(ser)


def mixed_date_format_frac(ser: pd.Series) -> float:
    """Fraction of values parseable as dates, measured by how many different
    formats are present. Returns > 0 only if multiple formats detected."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()

    # Check each pattern vectorially, count how many distinct patterns match anything
    formats_with_hits = 0
    total_matched = np.zeros(len(s), dtype=bool)
    for pat in _DATE_INDIVIDUAL_PATS:
        hits = s.str.contains(pat, regex=True, na=False)
        if hits.any():
            formats_with_hits += 1
        total_matched |= hits.values

    if formats_with_hits <= 1:
        return 0.0
    return total_matched.sum() / len(ser)


# ============================================================================
# 3. Impossible / suspicious date detection
# ============================================================================

def impossible_date_frac(ser: pd.Series) -> float:
    """Fraction of values that parse as dates but are logically suspicious
    (future, pre-1900, month-13, Feb 30, null sentinels, etc.)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()

    # Null sentinels
    is_null_sentinel = s.isin({"", "0000-00-00", "9999-12-31"})

    # Try parsing
    parsed = pd.to_datetime(s, errors="coerce")
    now = pd.Timestamp.now()
    is_future = parsed > now
    is_ancient = parsed < pd.Timestamp("1900-01-01")
    is_max = parsed.dt.year == 9999

    # Values that look date-ish but failed to parse
    looks_dateish = s.str.contains(r"^\d{4}-\d{2}-\d{2}", regex=True, na=False)
    failed_parse = parsed.isna() & looks_dateish & ~is_null_sentinel

    suspicious = is_null_sentinel | is_future | is_ancient | is_max | failed_parse
    return suspicious.sum() / len(ser)


# ============================================================================
# 4. Mostly-numeric with string outliers
# ============================================================================

def numeric_parseable_frac(ser: pd.Series) -> float:
    """Fraction of non-null values that parse as numeric."""
    if len(ser) == 0:
        return 0.0
    non_null = ser.dropna()
    if len(non_null) == 0:
        return 0.0
    parsed = pd.to_numeric(non_null, errors="coerce")
    return (~parsed.isna()).sum() / len(non_null)


def string_in_numeric_col_frac(ser: pd.Series) -> float:
    """Fraction of values that are non-null, non-numeric strings in a column
    that is mostly numeric. Returns 0 if column is < 50% numeric."""
    if len(ser) == 0:
        return 0.0
    non_null = ser.dropna()
    if len(non_null) == 0:
        return 0.0
    parsed = pd.to_numeric(non_null, errors="coerce")
    num_frac = (~parsed.isna()).sum() / len(non_null)
    if num_frac < 0.5:
        return 0.0
    return parsed.isna().sum() / len(non_null)


# ============================================================================
# 5. Missing value sentinel detection
# ============================================================================

_MISSING_SENTINELS = {
    "", " ", "  ", "n/a", "na", "null", "none", "nil",
    "-", "--", "---", ".", "..", "...",
    "?", "??", "???", "tbd", "tba",
    "#n/a", "#null!", "#value!", "nan",
    "missing", "unknown", "not available",
}


def missing_sentinel_frac(ser: pd.Series) -> float:
    """Fraction of values that are a known missing-value sentinel string."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    lowered = _as_str(ser).str.strip().str.lower()
    return lowered.isin(_MISSING_SENTINELS).sum() / len(ser)


# ============================================================================
# 6. Formatted number detection (currency, locale, etc.)
# ============================================================================

_CURRENCY_PAT = r"^[($€£¥₹\s]*[-]?[\d,.\s']+[)%]?\s*(?:USD|EUR|GBP|JPY)?$"


def formatted_number_frac(ser: pd.Series) -> float:
    """Fraction of values that look like locale-formatted numbers
    (currency symbols, thousands separators, accounting negatives)
    but are NOT plain parseable floats."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()

    # Match the formatted-number pattern
    matches_formatted = s.str.contains(_CURRENCY_PAT, regex=True, na=False, flags=re.I)
    # Exclude plain parseable numbers (those aren't "formatted")
    is_plain_numeric = pd.to_numeric(s, errors="coerce").notna()
    # Formatted = matches pattern but NOT plain numeric
    is_formatted = matches_formatted & ~is_plain_numeric
    return is_formatted.sum() / len(ser)


# ============================================================================
# 7. Whitespace / invisible character contamination
# ============================================================================

_INVISIBLE_PAT = r"[\u200b\u200c\u200d\ufeff\u00ad\u200e\u200f]"
_INTERNAL_WS_PAT = r"[\t\n\r\x0b\xa0]|  +"


def whitespace_contaminated_frac(ser: pd.Series) -> float:
    """Fraction of values with leading/trailing whitespace, invisible
    Unicode characters, or internal multi-spaces/tabs/newlines."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser)
    stripped = s.str.strip()

    has_outer_ws = (s != stripped)
    has_invisible = s.str.contains(_INVISIBLE_PAT, regex=True, na=False)
    has_internal_ws = s.str.contains(_INTERNAL_WS_PAT, regex=True, na=False)

    dirty = has_outer_ws | has_invisible | has_internal_ws
    return dirty.sum() / len(ser)


# ============================================================================
# 8. Mojibake / encoding error detection
# ============================================================================

_MOJIBAKE_PAT = (
    r"Ã[\x80-\xbf]"
    r"|Ã©|Ã¨|Ã¼|Ã¶|Ã¤|Ã±|Ã§"
    r"|â€[™\x9c\x9d\x93\x94\x98\x99]"
)


def mojibake_frac(ser: pd.Series) -> float:
    """Fraction of values showing mojibake (UTF-8 read as Latin-1) patterns."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_MOJIBAKE_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 9. Email-in-wrong-field detection
# ============================================================================

_EMAIL_PAT = r"[\w.+-]+@[\w.-]+\.\w{2,}"


def email_in_field_frac(ser: pd.Series) -> float:
    """Fraction of values that contain an email address."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_EMAIL_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 10. SSN / sensitive PII pattern detection
# ============================================================================

_SSN_PAT = r"\b\d{3}-\d{2}-\d{4}\b"


def ssn_pattern_frac(ser: pd.Series) -> float:
    """Fraction of values that contain an SSN-like pattern (NNN-NN-NNNN)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_SSN_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 11. Boolean synonym detection (extends existing str_bool_frac)
# ============================================================================

_BOOL_EXTENDED = {
    "true", "false", "yes", "no", "y", "n", "t", "f",
    "on", "off", "1", "0",
}


def extended_bool_frac(ser: pd.Series) -> float:
    """Fraction of values that are boolean synonyms (including Y/N, T/F, on/off)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip().str.lower()
    return s.isin(_BOOL_EXTENDED).sum() / len(ser)


# ============================================================================
# 12. Categorical inconsistency (same value, many spellings)
# ============================================================================

def categorical_entropy_frac(ser: pd.Series) -> float:
    """Fraction of unique values that would collapse under case-normalization
    and whitespace stripping. High value = many duplicates hiding behind
    formatting differences."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser).dropna()
    if len(ser) == 0:
        return 0.0
    raw_uniques = ser.astype(str).nunique()
    normalized = ser.astype(str).str.strip().str.lower().str.replace(r"[.\s]+", "", regex=True)
    norm_uniques = normalized.nunique()
    if raw_uniques <= 1:
        return 0.0
    return (raw_uniques - norm_uniques) / raw_uniques


# ============================================================================
# 13. Excel error / artifact detection
# ============================================================================

_EXCEL_ERRORS = {"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "###"}


def excel_error_frac(ser: pd.Series) -> float:
    """Fraction of values that are Excel error codes or display artifacts."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    is_error = s.isin(_EXCEL_ERRORS)
    is_formula = s.str.startswith("=")
    return (is_error | is_formula).sum() / len(ser)


# ============================================================================
# 14. Unit-embedded-in-value detection
# ============================================================================

_UNIT_SUFFIX_PAT = r"\d\s*(?:kg|lbs?|g|oz|cm|mm|m|in|ft|°[CF]|mph|km/?h|mg|ml|L)\b"


def unit_in_value_frac(ser: pd.Series) -> float:
    """Fraction of values that have a measurement unit embedded in the string."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_UNIT_SUFFIX_PAT, regex=True, na=False, flags=re.I).sum() / len(ser)


# ============================================================================
# 15. HTML / markup contamination
# ============================================================================

_HTML_PAT = r"<[a-zA-Z/][^>]*>|&[a-zA-Z]+;|&#\d+;"


def html_markup_frac(ser: pd.Series) -> float:
    """Fraction of values containing HTML tags or entities."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_HTML_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 16. CSV injection / formula injection detection
# ============================================================================

def csv_injection_frac(ser: pd.Series) -> float:
    """Fraction of values that start with =, +, @, or tab (CSV injection risk)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    return s.str.contains(r"^[=+@\t]", regex=True, na=False).sum() / len(ser)


# ============================================================================
# 17. Near-duplicate name detection (fuzzy)
# ============================================================================

def duplicate_after_normalization_frac(ser: pd.Series) -> float:
    """Fraction of values that become duplicates after case + whitespace
    normalization. Measures deduplication opportunity."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser).dropna()
    if len(ser) == 0:
        return 0.0
    raw_dupes = ser.duplicated().sum()
    normalized = ser.astype(str).str.strip().str.lower()
    norm_dupes = normalized.duplicated().sum()
    new_dupes = norm_dupes - raw_dupes
    return new_dupes / len(ser) if new_dupes > 0 else 0.0


# ============================================================================
# 18. Floating point special value detection
# ============================================================================

def float_special_value_frac(ser: pd.Series) -> float:
    """Fraction of values that are inf, -inf, or NaN."""
    if not pd.api.types.is_float_dtype(ser) or len(ser) == 0:
        return 0.0
    return (np.isinf(ser) | ser.isna()).sum() / len(ser)


# ============================================================================
# 19. Schema artifact column detection (Unnamed, empty-name)
# ============================================================================

def all_null_frac(ser: pd.Series) -> float:
    """Fraction of values that are null. Returns 1.0 for artifact columns."""
    if len(ser) == 0:
        return 0.0
    return ser.isna().sum() / len(ser)


# ============================================================================
# 20. Suspicious age detection
# ============================================================================

def suspicious_age_frac(ser: pd.Series) -> float:
    """Fraction of numeric values that are suspicious as ages
    (negative, > 120, or exactly 0)."""
    if len(ser) == 0:
        return 0.0
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) == 0:
        return 0.0
    suspicious = (numeric < 0) | (numeric > 120) | (numeric == 0)
    return suspicious.sum() / len(numeric)


# ============================================================================
# 21. Numeric scale inconsistency (order-of-magnitude spread)
# ============================================================================

def magnitude_spread_frac(ser: pd.Series) -> float:
    """Measures whether values span many orders of magnitude, suggesting
    mixed scales (units vs thousands vs millions). Returns fraction of
    values that are > 2 orders of magnitude from the median."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) < 3:
        return 0.0
    positive = numeric[numeric > 0]
    if len(positive) < 3:
        return 0.0
    log_vals = np.log10(positive.values)
    median_log = np.median(log_vals)
    far = (np.abs(log_vals - median_log) > 2).sum()
    return far / len(positive)


# ============================================================================
# 22. Timezone / offset detection in timestamps
# ============================================================================

_TZ_PAT = (
    r"[+-]\d{2}:\d{2}$"
    r"|\b(?:UTC|GMT|EST|CST|PST|MST|IST|CET|EET|JST|ET|PT)\b"
    r"|Z$"
)


def timezone_present_frac(ser: pd.Series) -> float:
    """Fraction of values that contain timezone information."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_TZ_PAT, regex=True, na=False).sum() / len(ser)


def timezone_mixed_frac(ser: pd.Series) -> float:
    """Returns > 0 if the series has a mix of timezone-aware and
    timezone-naive timestamps."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    has_tz = _as_str(ser).str.contains(_TZ_PAT, regex=True, na=False)
    frac_with = has_tz.sum() / len(ser)
    if frac_with == 0 or frac_with == 1:
        return 0.0
    return min(frac_with, 1 - frac_with) * 2


# ============================================================================
# 23. Column name quality (operates on column name string, not series values)
# ============================================================================

def column_name_needs_cleaning(col_name: str) -> float:
    """Score 0.0-1.0 for how much a column name needs cleaning.
    Not a series function — takes a column name string."""
    score = 0.0
    if col_name != col_name.strip():
        score += 0.3
    if col_name == "" or col_name.startswith("Unnamed:"):
        score += 0.5
    if re.search(r"[\n\r\t]", col_name):
        score += 0.3
    if re.search(r"[($)#@!]", col_name):
        score += 0.1
    return min(score, 1.0)


# ============================================================================
# 24. Freetext in structured field
# ============================================================================

_NUMERIC_LOOSE_PAT = r"^-?[\d,.]+%?$"


def freetext_in_numeric_frac(ser: pd.Series) -> float:
    """Fraction of values that are non-numeric freetext in a column where
    some values are numeric. Catches survey responses like 'thirty-two'
    in an age column."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser).dropna()
    if len(ser) == 0:
        return 0.0
    s = _as_str(ser).str.strip()
    is_numeric = s.str.contains(_NUMERIC_LOOSE_PAT, regex=True, na=False)
    numeric_frac = is_numeric.sum() / len(s)
    if numeric_frac < 0.2 or numeric_frac > 0.95:
        return 0.0
    return (~is_numeric).sum() / len(s)


# ============================================================================
# 25. Log/operational artifact detection
# ============================================================================

_LOG_NOISE_PAT = r"^---.*---$|^\*\*\*|^#+\s|^NULL$|^\[.*\]\s"


def log_artifact_frac(ser: pd.Series) -> float:
    """Fraction of values that look like log/operational artifacts
    (--- markers ---, NULL strings, [LEVEL] prefixes)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    return s.str.contains(_LOG_NOISE_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 26. Sub-cent / excess precision detection (financial)
# ============================================================================

def excess_decimal_precision_frac(ser: pd.Series) -> float:
    """Fraction of float values with more than 2 decimal places."""
    if not pd.api.types.is_float_dtype(ser) or len(ser) == 0:
        return 0.0
    ser = ser.dropna()
    if len(ser) == 0:
        return 0.0
    rounded = ser.round(2)
    differs = (ser != rounded) & (~np.isinf(ser))
    return differs.sum() / len(ser)


# ============================================================================
# 27. Structured data in cell detection (JSON, XML, key=value)
# ============================================================================

_STRUCTURED_PAT = r"^[\[{].*[\]}]$|^<\w+[ >]|^\w+\s*[=:]\s*\S"


def structured_in_cell_frac(ser: pd.Series) -> float:
    """Fraction of values that contain embedded structured data
    (JSON objects/arrays, XML, key=value pairs)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    # Filter out very short strings (< 3 chars can't be structured)
    long_enough = s.str.len() >= 3
    matches = s.str.contains(_STRUCTURED_PAT, regex=True, na=False)
    return (matches & long_enough).sum() / len(ser)


# ============================================================================
# 28. Truncation detection
# ============================================================================

_SUSPICIOUS_LENGTHS = {40, 50, 100, 128, 140, 200, 255, 256, 500, 512, 1000, 1024}


def truncated_frac(ser: pd.Series) -> float:
    """Fraction of values that appear truncated (end with '...',
    or cluster at a suspicious fixed length like 40, 255)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()

    ends_ellipsis = s.str.endswith("...")
    lengths = s.str.len()
    at_limit = lengths.isin(_SUSPICIOUS_LENGTHS)

    return (ends_ellipsis | at_limit).sum() / len(ser)


# ============================================================================
# 29. Mixed ID format detection
# ============================================================================

_UUID_PAT = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_PREFIXED_ID_PAT = r"^[A-Za-z]+-\d+"
_NUMERIC_ID_PAT = r"^[\d.\-]+$"


def mixed_id_format_frac(ser: pd.Series) -> float:
    """Fraction of values suggesting mixed identifier formats
    (some numeric, some prefixed, some UUIDs, some emails)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser).dropna()
    if len(ser) == 0:
        return 0.0
    s = _as_str(ser).str.strip()

    has_uuid = s.str.contains(_UUID_PAT, regex=True, na=False, flags=re.I).any()
    has_email = s.str.contains(_EMAIL_PAT, regex=True, na=False).any()
    has_numeric = s.str.contains(_NUMERIC_ID_PAT, regex=True, na=False).any()
    has_prefixed = s.str.contains(_PREFIXED_ID_PAT, regex=True, na=False).any()

    categories = sum([has_uuid, has_email, has_numeric, has_prefixed])
    if categories <= 1:
        return 0.0
    return min((categories - 1) / 3, 1.0)


# ============================================================================
# 30. Time series anomaly indicators
# ============================================================================

_SYSTEM_CAPS = {999, 9999, 99999, 999999, 9999999, 99999999, 999999999}


def system_cap_frac(ser: pd.Series) -> float:
    """Fraction of values at common system maximums
    (999, 9999, 99999, 999999, etc.)."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) == 0:
        return 0.0
    return numeric.isin(_SYSTEM_CAPS).sum() / len(numeric)


def flatline_frac(ser: pd.Series) -> float:
    """Fraction of values that are part of a run of 3+ identical consecutive values."""
    numeric = pd.to_numeric(ser, errors="coerce")
    if len(numeric) < 3:
        return 0.0
    vals = numeric.values
    notna = ~np.isnan(vals.astype(float))

    # Vectorized: compare each value to its 1-back and 2-back neighbors
    same_as_prev = np.zeros(len(vals), dtype=bool)
    same_as_prev[1:] = (vals[1:] == vals[:-1]) & notna[1:] & notna[:-1]
    same_as_prev2 = np.zeros(len(vals), dtype=bool)
    same_as_prev2[2:] = same_as_prev[2:] & same_as_prev[1:-1]

    # A flatline point is any point in a run of 3+
    # Mark the triplet: i, i-1, i-2 when same_as_prev2[i] is True
    in_flatline = np.zeros(len(vals), dtype=bool)
    in_flatline |= same_as_prev2
    in_flatline[:-1] |= same_as_prev2[1:]
    in_flatline[:-2] |= same_as_prev2[2:]

    return in_flatline.sum() / len(numeric)


# ============================================================================
# 31. Medical: blood pressure format detection
# ============================================================================

_BP_PAT = r"^\d{2,3}\s*[/\\-]\s*\d{2,3}"


def blood_pressure_format_frac(ser: pd.Series) -> float:
    """Fraction of values that look like blood pressure readings (NNN/NN)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    return s.str.contains(_BP_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 32. Geocoordinate detection
# ============================================================================

def coordinate_out_of_range_frac(ser: pd.Series) -> float:
    """Fraction of numeric values outside valid lat (-90,90) or lon (-180,180) range.
    Applies the wider lon range to be conservative."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) == 0:
        return 0.0
    return (numeric.abs() > 180).sum() / len(numeric)


def null_island_frac(ser: pd.Series) -> float:
    """Fraction of values that are exactly 0.0 (suspicious for coordinates)."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) == 0:
        return 0.0
    return (numeric == 0.0).sum() / len(numeric)


# ============================================================================
# 33. Homoglyph / confusable character detection
# ============================================================================

_CONFUSABLE_PAT = (
    r"[\u0400-\u04ff"     # Cyrillic
    r"\u13a0-\u13ff"      # Cherokee
    r"\uff01-\uff5e"      # Fullwidth ASCII
    r"\u2000-\u200f"      # Various spaces and format chars
    r"\u0300-\u036f]"     # Combining diacriticals
)


def homoglyph_frac(ser: pd.Series) -> float:
    """Fraction of values containing characters from confusable Unicode ranges
    (Cyrillic, Cherokee, fullwidth) that could be homoglyph substitutions."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_CONFUSABLE_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 34. OCR character confusion detection
# ============================================================================

def ocr_confusion_frac(ser: pd.Series) -> float:
    """Fraction of values where O, l, Z, B appear in positions that should
    be digits (adjacent to digits), suggesting OCR character confusion."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    s = _as_str(ser).str.strip()
    # Heuristic: letter O/l/Z/B adjacent to a digit is suspicious
    # e.g., "2O24" "l234" "Z024" "5,67B"
    has_confusion = (
        s.str.contains(r"\d[OlZB]", regex=True, na=False)
        | s.str.contains(r"[OlZB]\d", regex=True, na=False)
    )
    return has_confusion.sum() / len(ser)


# ============================================================================
# 35. ISO date detection
# ============================================================================

def iso_date_frac(ser: pd.Series) -> float:
    """Fraction of values parseable as ISO dates (YYYY-MM-DD)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    parsed = pd.to_datetime(ser, errors="coerce", format="%Y-%m-%d")
    return (~parsed.isna()).sum() / len(ser)


# ============================================================================
# 36. Large integer precision risk
# ============================================================================

_MAX_SAFE_INT = 2**53


def large_int_precision_risk_frac(ser: pd.Series) -> float:
    """Fraction of values that are integers beyond 2^53 (unsafe for float64/JSON)."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) == 0:
        return 0.0
    return (numeric.abs() > _MAX_SAFE_INT).sum() / len(numeric)


# ============================================================================
# 37. em-dash / smart punctuation detection
# ============================================================================

_SMART_PUNCT_PAT = r"[\u2013\u2014\u2018\u2019\u201c\u201d\u2026]"


def smart_punctuation_frac(ser: pd.Series) -> float:
    """Fraction of values containing smart quotes, em-dashes, or ellipsis
    characters (common from Word/PDF copy-paste)."""
    if not _is_stringlike(ser) or len(ser) == 0:
        return 0.0
    ser = _sample(ser)
    return _as_str(ser).str.contains(_SMART_PUNCT_PAT, regex=True, na=False).sum() / len(ser)


# ============================================================================
# 38. Negative value in likely-unsigned column
# ============================================================================

def negative_in_unsigned_frac(ser: pd.Series) -> float:
    """Fraction of values that are negative in a column that is >90% positive.
    Suggests sign-flip errors or data entry mistakes."""
    numeric = pd.to_numeric(ser, errors="coerce").dropna()
    if len(numeric) < 5:
        return 0.0
    positive_frac = (numeric > 0).sum() / len(numeric)
    if positive_frac < 0.9:
        return 0.0
    return (numeric < 0).sum() / len(numeric)


# ============================================================================
# REGISTRY: all fraction functions with typical thresholds
# ============================================================================

FRAC_REGISTRY = {
    "phone_number":                  (phone_number_frac,              0.1),
    "date_parseable":                (date_parseable_frac,            0.5),
    "mixed_date_format":             (mixed_date_format_frac,         0.3),
    "impossible_date":               (impossible_date_frac,           0.05),
    "numeric_parseable":             (numeric_parseable_frac,         0.5),
    "string_in_numeric_col":         (string_in_numeric_col_frac,     0.01),
    "missing_sentinel":              (missing_sentinel_frac,          0.01),
    "formatted_number":              (formatted_number_frac,          0.1),
    "whitespace_contaminated":       (whitespace_contaminated_frac,   0.01),
    "mojibake":                      (mojibake_frac,                  0.01),
    "email_in_field":                (email_in_field_frac,            0.01),
    "ssn_pattern":                   (ssn_pattern_frac,               0.001),
    "extended_bool":                 (extended_bool_frac,             0.8),
    "categorical_entropy":           (categorical_entropy_frac,       0.1),
    "excel_error":                   (excel_error_frac,               0.01),
    "unit_in_value":                 (unit_in_value_frac,             0.1),
    "html_markup":                   (html_markup_frac,               0.01),
    "csv_injection":                 (csv_injection_frac,             0.001),
    "duplicate_after_normalization": (duplicate_after_normalization_frac, 0.05),
    "float_special_value":           (float_special_value_frac,       0.01),
    "all_null":                      (all_null_frac,                  0.95),
    "suspicious_age":                (suspicious_age_frac,            0.01),
    "magnitude_spread":              (magnitude_spread_frac,          0.1),
    "timezone_present":              (timezone_present_frac,          0.1),
    "timezone_mixed":                (timezone_mixed_frac,            0.1),
    "freetext_in_numeric":           (freetext_in_numeric_frac,       0.1),
    "log_artifact":                  (log_artifact_frac,              0.01),
    "excess_decimal_precision":      (excess_decimal_precision_frac,  0.01),
    "structured_in_cell":            (structured_in_cell_frac,        0.1),
    "truncated":                     (truncated_frac,                 0.05),
    "mixed_id_format":               (mixed_id_format_frac,           0.3),
    "system_cap":                    (system_cap_frac,                0.01),
    "flatline":                      (flatline_frac,                  0.01),
    "blood_pressure_format":         (blood_pressure_format_frac,     0.3),
    "coordinate_out_of_range":       (coordinate_out_of_range_frac,   0.01),
    "null_island":                   (null_island_frac,               0.1),
    "homoglyph":                     (homoglyph_frac,                 0.01),
    "ocr_confusion":                 (ocr_confusion_frac,             0.05),
    "iso_date":                      (iso_date_frac,                  0.5),
    "large_int_precision_risk":      (large_int_precision_risk_frac,  0.01),
    "smart_punctuation":             (smart_punctuation_frac,         0.01),
    "negative_in_unsigned":          (negative_in_unsigned_frac,      0.01),
}


def profile_series(ser: pd.Series) -> dict[str, float]:
    """Run all fraction functions against a series and return those that
    exceed their typical threshold."""
    results = {}
    for name, (func, threshold) in FRAC_REGISTRY.items():
        try:
            val = func(ser)
            if val > threshold:
                results[name] = val
        except Exception:
            pass
    return results


def profile_dataframe(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Run all fraction functions against every column in a DataFrame.
    Returns {column_name: {issue_name: fraction}} for triggered issues."""
    report = {}
    for col in df.columns:
        col_results = profile_series(df[col])
        if col_results:
            report[col] = col_results
    return report
