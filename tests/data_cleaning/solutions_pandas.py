"""
Data Cleaning Solutions — pandas

Each function takes a dirty DataFrame (as loaded from the test case parquet)
and returns a cleaned DataFrame. Where cleaning is lossy or ambiguous, a
secondary DataFrame of flags/issues is also returned.
"""

import re
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd


# ============================================================================
# Helpers
# ============================================================================

PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?"
    r"(?:\(?\d{3}\)?[\s.-]?)"
    r"\d{3}[\s.-]?\d{4}"
    r"|1-\d{3}-[A-Z]{7}"   # vanity: 1-800-FLOWERS
)

MISSING_STRINGS = {
    "", " ", "  ", "N/A", "n/a", "NA", "na", "NULL", "null", "Null",
    "None", "none", "NONE", "-", "--", "---", ".", "..", "...",
    "?", "??", "???", "TBD", "TBA", "#N/A", "#NULL!", "#VALUE!",
    "NaN", "nan",
}

TRUTHY = {"true", "yes", "y", "t", "on", "1"}
FALSY = {"false", "no", "n", "f", "off", "0"}


def _to_bool(val) -> object:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and not np.isnan(val):
        return bool(val)
    s = str(val).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    return pd.NA


def _normalize_whitespace(s: str) -> str:
    """Strip all Unicode whitespace and zero-width chars, normalize to NFC."""
    if not isinstance(s, str):
        return s
    # Remove zero-width characters
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", s)
    # Normalize unicode
    s = unicodedata.normalize("NFC", s)
    # Replace all unicode whitespace with regular space
    s = re.sub(r"[\s\xa0]+", " ", s)
    return s.strip()


def _coerce_missing(val) -> object:
    """Convert known missing-value strings to None."""
    if pd.isna(val):
        return None
    if isinstance(val, str) and val.strip() in MISSING_STRINGS:
        return None
    return val


# ============================================================================
# 1. Phone in Address
# ============================================================================

def clean_phone_in_address(df: pd.DataFrame) -> pd.DataFrame:
    """Detect phone numbers in address field, move to phone column or flag."""
    df = df.copy()
    df["address_is_phone"] = False
    df["address_contains_phone"] = False
    df["extracted_phone_from_address"] = pd.NA

    for i, addr in df["address"].items():
        if pd.isna(addr):
            continue
        match = PHONE_RE.search(addr)
        if match:
            cleaned_addr = addr[:match.start()] + addr[match.end():]
            cleaned_addr = cleaned_addr.strip().strip(",").strip()
            if not cleaned_addr or len(cleaned_addr) < 5:
                # The whole address was basically just a phone number
                df.at[i, "address_is_phone"] = True
                df.at[i, "address"] = pd.NA
            else:
                df.at[i, "address_contains_phone"] = True
                df.at[i, "address"] = cleaned_addr
            df.at[i, "extracted_phone_from_address"] = match.group()
    return df


# ============================================================================
# 2. Mixed Date Formats
# ============================================================================

def clean_mixed_date_formats(df: pd.DataFrame) -> pd.DataFrame:
    """Parse dates in multiple formats, flag unparseable ones."""
    df = df.copy()
    df["parsed_date"] = pd.NaT
    df["date_parse_method"] = ""

    for i, raw in df["date"].items():
        if pd.isna(raw) or str(raw).strip() == "":
            df.at[i, "date_parse_method"] = "empty"
            continue

        raw = str(raw).strip()

        # Unix timestamp (all digits, 10 or 13 digits)
        if re.match(r"^\d{10}$", raw):
            df.at[i, "parsed_date"] = pd.Timestamp(int(raw), unit="s")
            df.at[i, "date_parse_method"] = "unix_seconds"
            continue
        if re.match(r"^\d{13}$", raw):
            df.at[i, "parsed_date"] = pd.Timestamp(int(raw), unit="ms")
            df.at[i, "date_parse_method"] = "unix_ms"
            continue

        # Excel serial date (5-digit number)
        if re.match(r"^\d{5}$", raw):
            try:
                dt = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(raw))
                df.at[i, "parsed_date"] = dt
                df.at[i, "date_parse_method"] = "excel_serial"
                continue
            except Exception:
                pass

        # Compact YYYYMMDD
        if re.match(r"^\d{8}$", raw):
            try:
                df.at[i, "parsed_date"] = pd.to_datetime(raw, format="%Y%m%d")
                df.at[i, "date_parse_method"] = "compact_YYYYMMDD"
                continue
            except Exception:
                pass

        # Quarter / Week — can't parse to exact date, flag it
        if re.match(r"^Q\d\s+\d{4}$", raw) or re.match(r"^Week\s+\d", raw):
            df.at[i, "date_parse_method"] = "period_not_date"
            continue

        # Remove ordinal suffixes (1st, 2nd, 3rd, 15th)
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw)

        # Try general parsing
        try:
            df.at[i, "parsed_date"] = pd.to_datetime(cleaned, dayfirst=False)
            df.at[i, "date_parse_method"] = "auto_parsed"
        except Exception:
            df.at[i, "date_parse_method"] = "unparseable"

    return df


# ============================================================================
# 3. Impossible Dates
# ============================================================================

def clean_impossible_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Validate dates for logical possibility, flag suspicious ones."""
    df = df.copy()
    df["birth_date_valid"] = True
    df["birth_date_issue"] = ""

    for i, raw in df["birth_date"].items():
        if pd.isna(raw) or str(raw).strip() == "":
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "missing"
            continue

        raw = str(raw).strip()

        # Null sentinel
        if raw == "0000-00-00":
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "null_sentinel"
            continue

        try:
            dt = pd.to_datetime(raw, errors="raise")
        except Exception:
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "unparseable"
            continue

        # Future date
        if dt > pd.Timestamp.now():
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "future_date"
        # Very old
        elif dt < pd.Timestamp("1900-01-01"):
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "before_1900"
        # Epoch boundary
        elif dt == pd.Timestamp("1970-01-01"):
            df.at[i, "birth_date_issue"] = "suspicious_epoch"
        # Max date
        elif dt.year == 9999:
            df.at[i, "birth_date_valid"] = False
            df.at[i, "birth_date_issue"] = "max_date_sentinel"

    return df


# ============================================================================
# 4. Mostly Int with Strings
# ============================================================================

def clean_mostly_int_with_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Separate numeric values from string outliers in quantity column."""
    df = df.copy()
    df["quantity_clean"] = pd.NA
    df["quantity_flag"] = ""

    for i, val in df["quantity"].items():
        if pd.isna(val):
            df.at[i, "quantity_flag"] = "missing"
            continue

        s = str(val).strip()

        # Known missing values
        if s.lower() in {"n/a", "null", "unknown", "-", "tbd", "none"}:
            df.at[i, "quantity_flag"] = f"missing:{s}"
            continue

        # Excel error
        if s.startswith("#"):
            df.at[i, "quantity_flag"] = f"excel_error:{s}"
            continue

        # Free text
        if re.search(r"[a-df-zA-DF-Z]", s):  # letters other than 'e/E' (scientific)
            df.at[i, "quantity_flag"] = f"freetext:{s}"
            continue

        # Try parsing as number (handle commas, whitespace)
        try:
            cleaned = s.replace(",", "").strip()
            num = float(cleaned)
            if num == int(num):
                df.at[i, "quantity_clean"] = int(num)
            else:
                df.at[i, "quantity_clean"] = num
                df.at[i, "quantity_flag"] = "float_in_int_col"
        except ValueError:
            df.at[i, "quantity_flag"] = f"unparseable:{s}"

    return df


# ============================================================================
# 5. Missing Value Zoo
# ============================================================================

def clean_missing_value_zoo(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all missing value representations to None/NaN."""
    df = df.copy()
    df["value_was"] = df["value"].copy()
    df["value"] = df["value"].apply(_coerce_missing)
    return df


# ============================================================================
# 6. Formatted Numbers
# ============================================================================

def clean_formatted_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Parse locale-formatted numbers to float."""
    df = df.copy()
    df["price_clean"] = np.nan
    df["price_flag"] = ""

    for i, raw in df["price"].items():
        if pd.isna(raw):
            continue
        s = str(raw).strip()

        # Approximate / comparison / plus suffix — flag but extract number
        if s.startswith(("~", "<", ">", "≈")):
            df.at[i, "price_flag"] = "approximate"
            s = re.sub(r"^[~<>≈]\s*", "", s)
        if s.endswith("+"):
            df.at[i, "price_flag"] = "lower_bound"
            s = s[:-1].strip()

        # Fraction
        frac_match = re.match(r"^(\d+)/(\d+)$", s)
        if frac_match:
            df.at[i, "price_clean"] = int(frac_match[1]) / int(frac_match[2])
            df.at[i, "price_flag"] = "fraction"
            continue

        # Percentage
        if s.endswith("%"):
            try:
                df.at[i, "price_clean"] = float(s[:-1])
                df.at[i, "price_flag"] = "percentage"
                continue
            except ValueError:
                pass

        # Strip currency symbols and whitespace
        s = re.sub(r"[$ €£¥₹]", "", s).strip()
        s = re.sub(r"\s*(USD|EUR|GBP|JPY)\s*$", "", s, flags=re.I).strip()

        # Detect European format: if pattern is N.NNN,NN -> European
        if re.match(r"^[\d.]+,\d{2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            # US/standard: remove commas, apostrophes, spaces as thousands separators
            s = s.replace(",", "").replace("'", "").replace(" ", "")

        # Accounting negative: (1234.56) -> -1234.56
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        # Trailing negative
        if s.endswith("-"):
            s = "-" + s[:-1]

        try:
            df.at[i, "price_clean"] = float(s)
        except ValueError:
            df.at[i, "price_flag"] = "unparseable"

    return df


# ============================================================================
# 7. Whitespace Chaos
# ============================================================================

def clean_whitespace_chaos(df: pd.DataFrame) -> pd.DataFrame:
    """Strip all invisible/whitespace characters, normalize to NFC."""
    df = df.copy()
    df["name_clean"] = df["name"].apply(_normalize_whitespace)
    return df


# ============================================================================
# 8. Mojibake
# ============================================================================

def clean_mojibake(df: pd.DataFrame) -> pd.DataFrame:
    """Fix UTF-8 mojibake by re-encoding latin-1 -> utf-8."""
    df = df.copy()

    def fix_mojibake(s):
        if not isinstance(s, str):
            return s
        # Detect mojibake: Ã followed by certain bytes is the smoking gun
        if "Ã" not in s:
            return s
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s  # not actually mojibake

    df["city_clean"] = df["city"].apply(fix_mojibake)
    return df


# ============================================================================
# 9. Field Swap Name/Email
# ============================================================================

def clean_field_swap_name_email(df: pd.DataFrame) -> pd.DataFrame:
    """Detect PII and non-name data in the name field."""
    df = df.copy()
    df["name_issue"] = ""

    email_re = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")
    ssn_re = re.compile(r"^\d{3}-\d{2}-\d{4}$")
    partial_email_re = re.compile(r"@$|^[\w.]+@$")

    for i, name in df["name"].items():
        if pd.isna(name) or str(name).strip() == "":
            df.at[i, "name_issue"] = "empty"
            continue

        name = str(name).strip()

        if ssn_re.match(name):
            df.at[i, "name_issue"] = "SSN_PII_CRITICAL"
            df.at[i, "name"] = "[REDACTED]"
        elif email_re.match(name):
            df.at[i, "name_issue"] = "email_in_name"
        elif partial_email_re.search(name):
            df.at[i, "name_issue"] = "partial_email"
        elif "(" in name and ")" in name:
            df.at[i, "name_issue"] = "has_parenthetical"
        elif "," in name:
            df.at[i, "name_issue"] = "last_first_format"

    return df


# ============================================================================
# 10. Address Field Chaos
# ============================================================================

def clean_address_field_chaos(df: pd.DataFrame) -> pd.DataFrame:
    """Flag invalid addresses, detect partial data."""
    df = df.copy()
    df["address_quality"] = "ok"

    for i, addr in df["full_address"].items():
        if pd.isna(addr) or str(addr).strip() in MISSING_STRINGS:
            df.at[i, "address_quality"] = "missing"
            continue

        addr = str(addr).strip()

        if re.match(r"^\d{5}(-\d{4})?$", addr):
            df.at[i, "address_quality"] = "zip_only"
        elif re.match(r"^[A-Z]{2}$", addr):
            df.at[i, "address_quality"] = "state_only"
        elif re.match(r"^\d+$", addr) and len(addr) >= 7:
            df.at[i, "address_quality"] = "phone_number"
        elif "." in addr and not any(c.isdigit() for c in addr.split(".")[0][-3:]):
            if re.match(r"^[\w.-]+\.\w{2,4}$", addr):
                df.at[i, "address_quality"] = "url"
        elif addr.lower().startswith("same as"):
            df.at[i, "address_quality"] = "cross_reference"
        elif "\n" in addr:
            df.at[i, "address_quality"] = "multiline"
        elif len(addr) < 10 and "," not in addr and not re.search(r"\d", addr):
            df.at[i, "address_quality"] = "partial"

    # Normalize excessive whitespace
    df["full_address"] = df["full_address"].apply(
        lambda x: re.sub(r"\s+", " ", str(x)).strip() if pd.notna(x) else x
    )
    return df


# ============================================================================
# 11. Boolean Chaos
# ============================================================================

def clean_boolean_chaos(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all boolean representations to True/False."""
    df = df.copy()
    df["is_active_clean"] = df["is_active"].apply(_to_bool)
    return df


# ============================================================================
# 12. Categorical Inconsistency
# ============================================================================

def clean_categorical_inconsistency(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize country names/codes to ISO 2-letter codes."""
    df = df.copy()

    COUNTRY_MAP = {
        "united states": "US", "us": "US", "usa": "US", "u.s.": "US",
        "u.s.a.": "US", "united states of america": "US", "u s a": "US",
        "unied states": "US", "untied states": "US", "united sates": "US",
        "germany": "DE", "de": "DE", "deu": "DE", "deutschland": "DE",
        "japan": "JP", "jp": "JP", "jpn": "JP", "日本": "JP",
        "united kingdom": "GB", "uk": "GB", "gb": "GB", "gbr": "GB",
        "england": "GB",  # Note: England != UK, but mapping to GB by convention
    }

    def normalize_country(val):
        if pd.isna(val):
            return pd.NA
        s = str(val).strip().lower().replace(".", "").strip()
        return COUNTRY_MAP.get(s, val)

    df["country_clean"] = df["country"].apply(normalize_country)
    return df


# ============================================================================
# 13. Excel Artifacts
# ============================================================================

def clean_excel_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """Detect and categorize Excel artifacts."""
    df = df.copy()
    df["value_clean"] = df["value"].copy()
    df["value_issue"] = ""

    excel_errors = {"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}

    for i, val in df["value"].items():
        if pd.isna(val):
            continue
        s = str(val).strip()

        if s in excel_errors:
            df.at[i, "value_clean"] = pd.NA
            df.at[i, "value_issue"] = f"excel_error:{s}"
        elif s.startswith("="):
            df.at[i, "value_clean"] = pd.NA
            df.at[i, "value_issue"] = "leaked_formula"
        elif s == "###":
            df.at[i, "value_clean"] = pd.NA
            df.at[i, "value_issue"] = "display_artifact"
        elif s == "General":
            df.at[i, "value_clean"] = pd.NA
            df.at[i, "value_issue"] = "format_name_leaked"
        elif s in ("TRUE", "FALSE"):
            df.at[i, "value_clean"] = s == "TRUE"
            df.at[i, "value_issue"] = "excel_boolean"

    return df


# ============================================================================
# 14. Mixed Units
# ============================================================================

def clean_mixed_units(df: pd.DataFrame) -> pd.DataFrame:
    """Extract numeric values and convert to standard units (kg, cm)."""
    df = df.copy()
    df["weight_kg"] = np.nan
    df["weight_flag"] = ""
    df["height_cm"] = np.nan
    df["height_flag"] = ""

    def parse_weight_to_kg(raw):
        if pd.isna(raw):
            return np.nan, "missing"
        s = str(raw).strip().lower()

        # Flag approximate/range
        flag = ""
        if s.startswith(("about", "~", "<", ">")):
            flag = "approximate"
            s = re.sub(r"^(about|~|[<>])\s*", "", s)
        if "-" in s and "kg" in s:
            flag = "range"
            s = s.split("-")[0].strip()  # take lower bound

        # Compound: "11 lbs 8 oz"
        m = re.match(r"([\d.]+)\s*lbs?\s+([\d.]+)\s*oz", s)
        if m:
            return float(m[1]) * 0.453592 + float(m[2]) * 0.0283495, flag or "compound"

        # Extract number and unit
        m = re.match(r"([\d,.]+)\s*(kg|kilograms?|lbs?|pounds?|g|grams?|oz|ounces?|tonnes?|mg)?", s)
        if not m:
            return np.nan, "unparseable"

        num = float(m[1].replace(",", ""))
        unit = (m[2] or "").lower()

        conversions = {
            "": num,  # bare number, assume kg
            "kg": num, "kilogram": num, "kilograms": num,
            "lb": num * 0.453592, "lbs": num * 0.453592,
            "pound": num * 0.453592, "pounds": num * 0.453592,
            "g": num / 1000, "gram": num / 1000, "grams": num / 1000,
            "oz": num * 0.0283495, "ounce": num * 0.0283495, "ounces": num * 0.0283495,
            "tonne": num * 1000, "tonnes": num * 1000,
            "mg": num / 1_000_000,
        }

        kg = conversions.get(unit)
        if kg is None:
            return np.nan, "unknown_unit"
        return kg, flag or ("bare_number" if unit == "" else "")

    for i, raw in df["weight"].items():
        kg, flag = parse_weight_to_kg(raw)
        df.at[i, "weight_kg"] = kg
        df.at[i, "weight_flag"] = flag

    # Height parsing to cm — abbreviated for brevity, same pattern
    def parse_height_to_cm(raw):
        if pd.isna(raw):
            return np.nan, "missing"
        s = str(raw).strip().lower()

        flag = ""
        if s.startswith(("~", "about")):
            flag = "approximate"
            s = re.sub(r"^(about|~)\s*", "", s)

        # Feet and inches: 5'11" or 5 ft 11 in
        m = re.match(r"""(\d+)['\s]*(?:ft|foot|feet)?\s*(\d+)?["\s]*(?:in|inch|inches)?""", s)
        if m and ("'" in str(raw) or "ft" in s or "foot" in s or "feet" in s):
            ft = int(m[1])
            inches = int(m[2]) if m[2] else 0
            return (ft * 12 + inches) * 2.54, flag

        # Extract number and unit
        m = re.match(r"([\d,.]+)\s*(cm|m|mm|km|in|inch|inches)?", s)
        if not m:
            return np.nan, "unparseable"

        num = float(m[1].replace(",", ""))
        unit = (m[2] or "").lower()

        conversions = {
            "": num,  # assume cm
            "cm": num, "m": num * 100, "mm": num / 10, "km": num * 100000,
            "in": num * 2.54, "inch": num * 2.54, "inches": num * 2.54,
        }

        cm = conversions.get(unit)
        if cm is None:
            return np.nan, "unknown_unit"
        return cm, flag or ("bare_number" if unit == "" else "")

    for i, raw in df["height"].items():
        cm, flag = parse_height_to_cm(raw)
        df.at[i, "height_cm"] = cm
        df.at[i, "height_flag"] = flag

    return df


# ============================================================================
# 15. Copy-Paste Artifacts
# ============================================================================

def clean_copy_paste_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """Strip HTML, markdown, null bytes, ANSI codes; sanitize CSV injection."""
    df = df.copy()

    def clean_text(s):
        if pd.isna(s):
            return s
        s = str(s)
        # Remove null bytes
        s = s.replace("\x00", "")
        # Remove ANSI escape codes
        s = re.sub(r"\x1b\[[0-9;]*m", "", s)
        # Strip HTML tags
        s = re.sub(r"<[^>]+>", "", s)
        # Decode HTML entities
        import html
        s = html.unescape(s)
        # Strip markdown formatting
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        # CSV injection sanitization: prefix dangerous chars with single quote
        if s and s[0] in ("=", "+", "-", "@", "\t"):
            if not re.match(r"^-?\d", s):  # don't touch negative numbers
                s = "'" + s
        return s.strip()

    df["description_clean"] = df["description"].apply(clean_text)
    return df


# ============================================================================
# 16. Near Duplicates
# ============================================================================

def clean_near_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Identify duplicate and near-duplicate records."""
    df = df.copy()

    # Normalize phone for comparison
    df["phone_normalized"] = df["phone"].apply(
        lambda x: re.sub(r"[^\d]", "", str(x)) if pd.notna(x) else ""
    )

    # Normalize name for comparison
    df["name_normalized"] = df["name"].str.strip().str.lower()

    # Normalize email for comparison
    df["email_normalized"] = df["email"].str.strip().str.lower()

    # Group by customer_id to find duplicates
    df["duplicate_group"] = df.groupby("customer_id").cumcount()

    # Flag exact and near duplicates
    df["is_duplicate"] = df["duplicate_group"] > 0

    # Within each customer_id group, check if records differ
    df["differs_from_first"] = False
    for cid, group in df.groupby("customer_id"):
        if len(group) > 1:
            first = group.iloc[0]
            for idx in group.index[1:]:
                if (df.at[idx, "name_normalized"] != first["name_normalized"] or
                        df.at[idx, "email_normalized"] != first["email_normalized"]):
                    df.at[idx, "differs_from_first"] = True

    return df


# ============================================================================
# 17. Floating Point Issues
# ============================================================================

def clean_floating_point_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Flag special float values; round to practical precision."""
    df = df.copy()
    df["amount_clean"] = df["amount"].copy()
    df["amount_flag"] = ""

    for i, val in df["amount"].items():
        if np.isinf(val):
            df.at[i, "amount_clean"] = np.nan
            df.at[i, "amount_flag"] = "infinity"
        elif np.isnan(val):
            df.at[i, "amount_flag"] = "nan"
        elif val == 0 and np.signbit(val):
            df.at[i, "amount_clean"] = 0.0
            df.at[i, "amount_flag"] = "negative_zero"
        elif abs(val) > 1e15:
            df.at[i, "amount_flag"] = "very_large"
        elif 0 < abs(val) < 1e-10:
            df.at[i, "amount_flag"] = "near_zero"

    return df


# ============================================================================
# 18. Jagged Schema
# ============================================================================

def clean_jagged_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Drop artifact columns, coerce types, flag non-parseable values."""
    df = df.copy()

    # Drop unnamed artifact columns
    artifact_cols = [c for c in df.columns if c.startswith("Unnamed:")]
    df = df.drop(columns=artifact_cols)

    # Clean age: extract numbers, flag text
    df["age_clean"] = pd.to_numeric(df["age"], errors="coerce")
    df["age_flag"] = df.apply(
        lambda r: str(r["age"]) if pd.isna(r["age_clean"]) and pd.notna(r["age"]) else "",
        axis=1,
    )

    # Clean salary
    df["salary_clean"] = pd.to_numeric(df["salary"], errors="coerce")
    df["salary_flag"] = df.apply(
        lambda r: str(r["salary"]) if pd.isna(r["salary_clean"]) and pd.notna(r["salary"]) else "",
        axis=1,
    )

    # Clean department: empty string -> None
    df["department"] = df["department"].replace("", pd.NA)

    # Clean start_date
    df["start_date_clean"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["start_date_flag"] = df.apply(
        lambda r: str(r["start_date"]) if pd.isna(r["start_date_clean"]) and pd.notna(r["start_date"]) else "",
        axis=1,
    )

    return df


# ============================================================================
# 19. Cross-Field Inconsistencies
# ============================================================================

def clean_cross_field_inconsistencies(df: pd.DataFrame) -> pd.DataFrame:
    """Validate field relationships and flag contradictions."""
    df = df.copy()
    df["issues"] = ""

    ref_year = 2024  # reference year for age calculation

    for i in df.index:
        issues = []

        # Age vs birth_date
        try:
            birth_year = pd.to_datetime(df.at[i, "birth_date"]).year
            expected_age = ref_year - birth_year
            actual_age = df.at[i, "age"]
            if actual_age < 0:
                issues.append("negative_age")
            elif abs(expected_age - actual_age) > 1:
                issues.append(f"age_mismatch(expected~{expected_age},got={actual_age})")
        except Exception:
            pass

        # State vs zip (simplified check)
        state = df.at[i, "state"]
        zip_code = str(df.at[i, "zip"])
        if state == "ZZ":
            issues.append("invalid_state")
        if zip_code == "00000":
            issues.append("invalid_zip")
        # Basic state-zip validation (first digit of zip -> region)
        zip_state_map = {"0": ["CT", "MA", "ME", "NH", "NJ", "NY", "PR", "RI", "VT"],
                         "3": ["AL", "FL", "GA", "MS", "TN"],
                         "6": ["IA", "IL", "KS", "MN", "MO", "NE", "ND", "SD"],
                         "7": ["AR", "LA", "OK", "TX"],
                         "9": ["AK", "AZ", "CA", "HI", "ID", "NV", "OR", "UT", "WA"]}
        first_digit = zip_code[0] if zip_code else ""
        if first_digit in zip_state_map and state not in zip_state_map[first_digit]:
            if state not in ("ZZ", ""):
                issues.append(f"zip_state_mismatch({zip_code},{state})")

        # Order vs ship date
        try:
            order_dt = pd.to_datetime(df.at[i, "order_date"])
            ship_dt = pd.to_datetime(df.at[i, "ship_date"])
            if ship_dt < order_dt:
                issues.append("shipped_before_ordered")
        except Exception:
            pass

        df.at[i, "issues"] = "; ".join(issues)

    return df


# ============================================================================
# 20. Mixed Numeric Scales
# ============================================================================

def clean_mixed_numeric_scales(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize values to a standard scale per metric using magnitude heuristics."""
    df = df.copy()
    df["value_normalized"] = df["value"].copy()
    df["inferred_scale"] = ""

    # Define expected ranges for each metric (in standard units)
    # Revenue: dollars, Conversion: decimal (0-1), Users: count,
    # Latency: milliseconds, Disk: percentage (0-100)
    scale_rules = {
        "revenue": [
            (lambda v: v > 100000, 1, "dollars"),        # already in dollars
            (lambda v: 100 < v < 100000, 1000, "thousands"),    # thousands
            (lambda v: v < 100, 1000000, "millions"),    # millions
        ],
        "conversion_rate": [
            (lambda v: v < 1, 1, "decimal"),             # already decimal
            (lambda v: 1 <= v < 100, 0.01, "percentage"),  # convert % to decimal
            (lambda v: v >= 100, 0.0001, "basis_points"),
        ],
        "users": [
            (lambda v: v > 10000, 1, "count"),
            (lambda v: 10 < v < 10000, 1000, "thousands"),
            (lambda v: v < 10, 1000000, "millions"),
        ],
        "latency_ms": [
            (lambda v: v < 1, 1000, "seconds"),          # convert s to ms
            (lambda v: 1 <= v < 10000, 1, "milliseconds"),
            (lambda v: v >= 10000, 0.001, "microseconds"),
        ],
        "disk_usage": [
            (lambda v: v < 1, 100, "decimal_fraction"),  # 0.85 -> 85%
            (lambda v: 1 <= v <= 100, 1, "percentage"),
            (lambda v: v > 100, 1, "absolute_unknown"),  # can't normalize
        ],
    }

    for i in df.index:
        metric = df.at[i, "metric"]
        val = df.at[i, "value"]
        rules = scale_rules.get(metric, [])
        for condition, multiplier, label in rules:
            if condition(val):
                df.at[i, "value_normalized"] = val * multiplier
                df.at[i, "inferred_scale"] = label
                break

    return df


# ============================================================================
# 21. Timezone Chaos
# ============================================================================

def clean_timezone_chaos(df: pd.DataFrame) -> pd.DataFrame:
    """Parse timestamps to UTC, flag ambiguous timezones."""
    df = df.copy()
    df["timestamp_utc"] = pd.NaT
    df["tz_flag"] = ""

    for i, raw in df["timestamp"].items():
        if pd.isna(raw):
            continue
        s = str(raw).strip()

        # Unix timestamp (10 digits = seconds, 13 = milliseconds)
        if re.match(r"^\d{10}$", s):
            df.at[i, "timestamp_utc"] = pd.Timestamp(int(s), unit="s", tz="UTC")
            df.at[i, "tz_flag"] = "from_unix_seconds"
            continue
        if re.match(r"^\d{13}$", s):
            df.at[i, "timestamp_utc"] = pd.Timestamp(int(s), unit="ms", tz="UTC")
            df.at[i, "tz_flag"] = "from_unix_ms"
            continue

        # Ambiguous abbreviations
        for abbr in ["CST", "IST", "EST", "PST", "ET"]:
            if abbr in s:
                df.at[i, "tz_flag"] = f"ambiguous_tz:{abbr}"

        # Normalize common patterns
        s = s.replace(" UTC", "+00:00")
        s = s.replace(" EST", "-05:00")
        s = s.replace(" CST", "-06:00")  # assuming US Central
        s = s.replace(" IST", "+05:30")  # assuming India
        s = s.replace(" PST", "-08:00")
        s = re.sub(r"\s*AM\s+ET$", " -05:00", s)
        s = re.sub(r"^(\w+ \d+, \d+ [\d:]+) GMT([+-]\d{4})$", r"\1\2", s)

        try:
            dt = pd.to_datetime(s, utc=True)
            df.at[i, "timestamp_utc"] = dt
        except Exception:
            try:
                dt = pd.to_datetime(s)
                df.at[i, "timestamp_utc"] = dt
                if not df.at[i, "tz_flag"]:
                    df.at[i, "tz_flag"] = "assumed_naive"
            except Exception:
                df.at[i, "tz_flag"] = "unparseable"

    return df


# ============================================================================
# 22. Column Name Chaos
# ============================================================================

def clean_column_name_chaos(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to clean snake_case, deduplicate."""
    column_map = {}
    seen = set()

    for col in df.columns:
        # Strip whitespace and special chars
        clean = str(col).strip()
        # Remove non-alphanumeric (keep unicode letters)
        clean = re.sub(r"[^\w]+", "_", clean)
        # To lower snake_case
        clean = re.sub(r"([a-z])([A-Z])", r"\1_\2", clean).lower()
        # Remove leading/trailing underscores
        clean = clean.strip("_")
        # Handle empty
        if not clean:
            clean = "unnamed"

        # Deduplicate
        base = clean
        counter = 2
        while clean in seen:
            clean = f"{base}_{counter}"
            counter += 1
        seen.add(clean)
        column_map[col] = clean

    df = df.rename(columns=column_map)

    # Drop columns that are entirely null (artifact columns)
    df = df.dropna(axis=1, how="all")
    return df


# ============================================================================
# 23. Survey Freetext in Structured
# ============================================================================

def clean_survey_freetext_in_structured(df: pd.DataFrame) -> pd.DataFrame:
    """Extract numeric values from freetext survey responses where possible."""
    df = df.copy()

    # Age: try to extract a number
    def parse_age(val):
        if pd.isna(val):
            return pd.NA, "missing"
        s = str(val).strip().lower()
        # Direct number
        try:
            return float(s), ""
        except ValueError:
            pass
        # Range: take midpoint
        m = re.match(r"(\d+)\s*-\s*(\d+)", s)
        if m:
            return (int(m[1]) + int(m[2])) / 2, "midpoint_of_range"
        # "born in YYYY"
        m = re.search(r"born in (\d{4})", s)
        if m:
            return 2024 - int(m[1]), "from_birth_year"
        # Known refusals/non-answers
        if any(kw in s for kw in ["prefer not", "old enough", "gen z",
                                   "millennial", "¯"]):
            return pd.NA, "non_answer"
        # Number with suffix
        m = re.match(r"(\d+)\+?$", s)
        if m:
            return float(m[1]), "lower_bound" if "+" in s else ""
        # "about N"
        m = re.search(r"about\s+(\d+)", s)
        if m:
            return float(m[1]), "approximate"
        return pd.NA, "unparseable"

    ages = df["age"].apply(parse_age)
    df["age_clean"] = [a[0] for a in ages]
    df["age_flag"] = [a[1] for a in ages]

    # Would recommend: normalize to True/False/None
    def parse_recommend(val):
        if pd.isna(val):
            return pd.NA
        s = str(val).strip().lower()
        positives = {"yes", "1", "true", "absolutely", "yes!!!", "👍"}
        negatives = {"no", "0", "false", "nah"}
        if s.rstrip("!") in positives or s in positives:
            return True
        if s in negatives:
            return False
        if s.startswith("yes"):
            return True  # "yes, but with caveats" is still yes
        return pd.NA  # maybe, depends, not sure, ask me later

    df["would_recommend_clean"] = df["would_recommend"].apply(parse_recommend)

    return df


# ============================================================================
# 24. Log Data in Table
# ============================================================================

def clean_log_data_in_table(df: pd.DataFrame) -> pd.DataFrame:
    """Fix timestamps, remove operational notes, normalize NULL strings."""
    df = df.copy()

    # Fix "NULL" string -> actual null
    df = df.replace("NULL", pd.NA)

    # Flag and clean contaminated timestamps
    df["timestamp_clean"] = pd.NaT
    df["is_data_row"] = True

    ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}")

    for i, raw in df["timestamp"].items():
        if pd.isna(raw):
            df.at[i, "is_data_row"] = False
            continue

        s = str(raw).strip()

        # Operational notes
        if s.startswith("---") or not ts_pattern.match(s):
            df.at[i, "is_data_row"] = False
            continue

        # Extract just the timestamp portion (first 23 chars)
        ts_str = s[:23]
        try:
            df.at[i, "timestamp_clean"] = pd.to_datetime(ts_str)
        except Exception:
            df.at[i, "is_data_row"] = False

    return df


# ============================================================================
# 25. Financial Data Edge Cases
# ============================================================================

def clean_financial_data_edge_cases(df: pd.DataFrame) -> pd.DataFrame:
    """Round amounts per currency, flag precision issues."""
    df = df.copy()

    # Currency decimal places
    decimals = {"USD": 2, "EUR": 2, "GBP": 2, "JPY": 0,
                "KWD": 3, "BTC": 8, "ETH": 18}

    df["amount_clean"] = df["amount"].copy()
    df["amount_flag"] = ""

    from decimal import Decimal, ROUND_HALF_EVEN

    for i in df.index:
        val = df.at[i, "amount"]
        ccy = df.at[i, "currency"]
        dp = decimals.get(ccy, 2)

        if np.isnan(val):
            df.at[i, "amount_flag"] = "missing"
            continue
        if np.isinf(val):
            df.at[i, "amount_clean"] = np.nan
            df.at[i, "amount_flag"] = "infinity"
            continue

        # Negative zero
        if val == 0 and np.signbit(val):
            df.at[i, "amount_clean"] = 0.0
            df.at[i, "amount_flag"] = "was_negative_zero"

        # Round using Decimal for correct banker's rounding
        d = Decimal(str(val)).quantize(Decimal(10) ** -dp, rounding=ROUND_HALF_EVEN)
        df.at[i, "amount_clean"] = float(d)

        # Flag sub-minor-unit precision
        if val != float(d) and abs(val - float(d)) > 10 ** -(dp + 2):
            if not df.at[i, "amount_flag"]:
                df.at[i, "amount_flag"] = "had_excess_precision"

    return df


# ============================================================================
# 26. Structured Data in Cells
# ============================================================================

def clean_structured_data_in_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Parse config to dict, tags to list."""
    import ast
    import json

    df = df.copy()
    df["config_parsed"] = None
    df["config_format"] = ""
    df["tags_list"] = None

    for i, raw in df["config"].items():
        if pd.isna(raw) or str(raw).strip().lower() == "none":
            df.at[i, "config_format"] = "null"
            continue

        s = str(raw).strip()

        # Try JSON
        try:
            parsed = json.loads(s)
            df.at[i, "config_parsed"] = str(parsed)
            df.at[i, "config_format"] = "json"
            continue
        except (json.JSONDecodeError, ValueError):
            pass

        # Try Python literal
        try:
            parsed = ast.literal_eval(s)
            df.at[i, "config_parsed"] = str(parsed)
            df.at[i, "config_format"] = "python_literal"
            continue
        except (ValueError, SyntaxError):
            pass

        # Key=value or key: value
        if re.search(r"^\w+\s*[=:]\s*\S", s, re.MULTILINE):
            df.at[i, "config_format"] = "key_value"
        elif s.startswith("<"):
            df.at[i, "config_format"] = "xml"
        else:
            df.at[i, "config_format"] = "other"

    # Parse tags
    for i, raw in df["tags"].items():
        if pd.isna(raw) or str(raw).strip() == "":
            df.at[i, "tags_list"] = "[]"
            continue

        s = str(raw).strip()

        # JSON array
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                df.at[i, "tags_list"] = str(parsed)
                continue
        except (json.JSONDecodeError, ValueError):
            pass

        # Detect delimiter and split
        s_clean = re.sub(r"^#", "", s)
        for delim in [";", "|", ",", "/", " #", " "]:
            if delim in s:
                tags = [t.strip().lstrip("#") for t in s.split(delim) if t.strip()]
                df.at[i, "tags_list"] = str(tags)
                break
        else:
            df.at[i, "tags_list"] = str([s])

    return df


# ============================================================================
# 27. Truncation and Overflow
# ============================================================================

def clean_truncation_and_overflow(df: pd.DataFrame) -> pd.DataFrame:
    """Flag truncated, placeholder, and sentinel values."""
    df = df.copy()
    df["name_flag"] = ""
    df["description_flag"] = ""

    placeholder_patterns = [
        re.compile(r"^lorem ipsum", re.I),
        re.compile(r"^test$", re.I),
        re.compile(r"^asdf", re.I),
        re.compile(r"^xxx+$", re.I),
    ]

    sentinel_values = {"REDACTED", "[FILTERED]", "N/A", "NULL",
                       "See attachment", "TBD", "..."}

    for col, flag_col in [("name", "name_flag"), ("description", "description_flag")]:
        for i, val in df[col].items():
            if pd.isna(val) or str(val).strip() == "":
                df.at[i, flag_col] = "empty"
                continue

            s = str(val).strip()

            if s in sentinel_values or s.startswith(("TBD", "See ", "[FILTERED")):
                df.at[i, flag_col] = "sentinel"
            elif s.endswith("..."):
                df.at[i, flag_col] = "truncated_ellipsis"
            elif len(s) in (40, 255) or (len(s) > 30 and not s[-1].isalpha() and not s.endswith(".")):
                df.at[i, flag_col] = "possibly_truncated"
            elif ";" in s and col == "name":
                df.at[i, flag_col] = "multi_value"
            elif any(p.match(s) for p in placeholder_patterns):
                df.at[i, flag_col] = "placeholder"

    return df


# ============================================================================
# 28. Mixed ID Formats
# ============================================================================

def clean_mixed_id_formats(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize user IDs to a canonical form."""
    df = df.copy()
    df["user_id_clean"] = ""
    df["user_id_type"] = ""

    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    email_re = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")

    for i, raw in df["user_id"].items():
        if pd.isna(raw):
            df.at[i, "user_id_type"] = "missing"
            continue

        s = str(raw).strip().rstrip("\n")

        if uuid_re.match(s):
            df.at[i, "user_id_clean"] = s.lower()
            df.at[i, "user_id_type"] = "uuid"
            continue

        if email_re.match(s):
            df.at[i, "user_id_clean"] = s.lower()
            df.at[i, "user_id_type"] = "email"
            continue

        # Strip known prefixes
        numeric_part = s
        for prefix in ["LEGACY-", "USR-", "usr_", "#"]:
            if numeric_part.upper().startswith(prefix.upper()):
                numeric_part = numeric_part[len(prefix):]

        # Handle scientific notation
        if "E+" in numeric_part.upper():
            try:
                numeric_part = str(int(float(numeric_part)))
            except ValueError:
                pass

        # Strip .0 suffix
        if numeric_part.endswith(".0"):
            numeric_part = numeric_part[:-2]

        # Remove commas
        numeric_part = numeric_part.replace(",", "")

        # Strip leading zeros (but preserve at least 1 digit)
        numeric_part = numeric_part.lstrip("0") or "0"

        df.at[i, "user_id_clean"] = numeric_part
        df.at[i, "user_id_type"] = "numeric"

    return df


# ============================================================================
# 29. Timeseries Anomalies
# ============================================================================

def clean_timeseries_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Flag anomalies in daily sales: spikes, flat-lines, sign flips, saturation."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["anomaly_flag"] = ""

    sales = df["daily_sales"].copy()

    # Rolling stats (30-day window)
    rolling_mean = sales.rolling(30, center=True, min_periods=10).mean()
    rolling_std = sales.rolling(30, center=True, min_periods=10).std()

    for i in df.index:
        val = sales.iloc[i]
        flags = []

        if pd.isna(val):
            flags.append("missing")
        elif val < 0:
            flags.append("negative")
        elif val == 0:
            # Check if surrounded by non-zero values
            prev_val = sales.iloc[i - 1] if i > 0 else np.nan
            next_val = sales.iloc[i + 1] if i < len(sales) - 1 else np.nan
            if (pd.notna(prev_val) and prev_val > 100) or (pd.notna(next_val) and next_val > 100):
                flags.append("suspicious_zero")
        elif val == 999999:
            flags.append("system_cap")
        elif pd.notna(rolling_mean.iloc[i]) and pd.notna(rolling_std.iloc[i]):
            if rolling_std.iloc[i] > 0:
                z = abs(val - rolling_mean.iloc[i]) / rolling_std.iloc[i]
                if z > 5:
                    flags.append("extreme_outlier")
                elif z > 3:
                    flags.append("outlier")

        # Flat-line detection
        if i >= 2:
            if (sales.iloc[i] == sales.iloc[i - 1] == sales.iloc[i - 2]
                    and pd.notna(val) and val != 0):
                flags.append("flat_line")

        df.at[i, "anomaly_flag"] = "; ".join(flags)

    return df


# ============================================================================
# 30. Medical Data Entry
# ============================================================================

def clean_medical_data_entry(df: pd.DataFrame) -> pd.DataFrame:
    """Parse blood pressure, normalize temperature, validate weight."""
    df = df.copy()

    # Blood pressure
    df["systolic"] = np.nan
    df["diastolic"] = np.nan
    df["bp_flag"] = ""

    for i, raw in df["blood_pressure"].items():
        if pd.isna(raw):
            continue
        s = str(raw).strip()

        if s.lower() in ("n/a", "normal", "high", "low", "pending", ""):
            df.at[i, "bp_flag"] = "qualitative"
            continue

        # Verbose: "systolic: 120, diastolic: 80"
        m = re.search(r"systolic[:\s]+(\d+)[,\s]+diastolic[:\s]+(\d+)", s, re.I)
        if m:
            df.at[i, "systolic"] = int(m[1])
            df.at[i, "diastolic"] = int(m[2])
            continue

        # Standard: 120/80 (with optional stuff after)
        m = re.match(r"(\d+)\s*[/\\-]\s*(\d+)(?:\s*[/\\-]\s*\d+)?", s)
        if m:
            sys_val, dia_val = int(m[1]), int(m[2])
            # Detect reversal
            if sys_val < dia_val:
                df.at[i, "bp_flag"] = "reversed"
                sys_val, dia_val = dia_val, sys_val
            # European shorthand (12/8 -> 120/80)
            if sys_val < 30:
                sys_val *= 10
                dia_val *= 10
                df.at[i, "bp_flag"] = "european_shorthand"
            df.at[i, "systolic"] = sys_val
            df.at[i, "diastolic"] = dia_val
            continue

        # Single number: "12080" -> 120/80
        if re.match(r"^\d{5,6}$", s):
            # Assume first 3 digits are systolic if 5 digits, first 3 if 6
            if len(s) == 5:
                df.at[i, "systolic"] = int(s[:3])
                df.at[i, "diastolic"] = int(s[3:])
            elif len(s) == 6:
                df.at[i, "systolic"] = int(s[:3])
                df.at[i, "diastolic"] = int(s[3:])
            df.at[i, "bp_flag"] = "missing_delimiter"

    # Temperature: normalize to Fahrenheit
    df["temp_f"] = np.nan
    df["temp_flag"] = ""

    for i, raw in df["temperature"].items():
        if pd.isna(raw):
            continue
        s = str(raw).strip()

        if s.lower() in ("afebrile", "normal", "wnl", "pending", ""):
            df.at[i, "temp_flag"] = "qualitative"
            continue

        # Remove method prefixes
        s = re.sub(r"^(oral|tympanic|rectal|axillary)[:\s]+", "", s, flags=re.I)
        # Remove unit labels
        is_celsius = bool(re.search(r"[°]?\s*[cC](?:elsius)?", s))
        is_fahrenheit = bool(re.search(r"[°]?\s*[fF](?:ahrenheit)?", s))
        s = re.sub(r"[°]?\s*(celsius|fahrenheit|[cfCF])$", "", s).strip().rstrip("°")

        # Range
        if "-" in s and not s.startswith("-"):
            parts = s.split("-")
            try:
                s = str((float(parts[0]) + float(parts[1])) / 2)
                df.at[i, "temp_flag"] = "range_midpoint"
            except ValueError:
                continue

        try:
            val = float(s)
        except ValueError:
            df.at[i, "temp_flag"] = "unparseable"
            continue

        # Missing decimal: 986 -> 98.6
        if val > 200:
            val = val / 10
            df.at[i, "temp_flag"] = "fixed_missing_decimal"

        # Infer scale from magnitude
        if is_celsius or (not is_fahrenheit and val < 50):
            df.at[i, "temp_f"] = val * 9 / 5 + 32
        else:
            df.at[i, "temp_f"] = val

    # Weight validation (kg column)
    df["weight_kg_clean"] = np.nan
    df["weight_flag"] = ""

    for i, raw in df["weight_kg"].items():
        if pd.isna(raw):
            continue

        s = str(raw).strip()

        # Qualitative
        if s.lower() in ("unknown", "obese", "underweight", "pending", ""):
            df.at[i, "weight_flag"] = "qualitative"
            continue

        # Extract number
        m = re.match(r"~?([\d.]+)\s*(kg|lbs?|pounds?)?", s, re.I)
        if not m:
            df.at[i, "weight_flag"] = "unparseable"
            continue

        val = float(m[1])
        unit = (m[2] or "").lower()

        if val < 0:
            df.at[i, "weight_flag"] = "negative"
            continue
        if val == 9999:
            df.at[i, "weight_flag"] = "sentinel_value"
            continue

        # Convert lbs to kg
        if unit.startswith("lb") or unit == "pounds":
            val = val * 0.453592
            df.at[i, "weight_flag"] = "converted_from_lbs"
        # Detect lbs in kg column (adults don't weigh > 120kg usually)
        elif not unit and val > 120:
            val = val * 0.453592
            df.at[i, "weight_flag"] = "likely_lbs_converted"
        elif val < 1:
            df.at[i, "weight_flag"] = "suspiciously_small"

        df.at[i, "weight_kg_clean"] = round(val, 1)

    return df


# ============================================================================
# 31. Geocoordinate Errors
# ============================================================================

def clean_geocoordinate_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and fix coordinates: range, swaps, string parsing."""
    df = df.copy()
    df["lat_clean"] = np.nan
    df["lon_clean"] = np.nan
    df["geo_flag"] = ""

    for i in df.index:
        lat = df.at[i, "latitude"]
        lon = df.at[i, "longitude"]
        flags = []

        # Parse string coordinates
        def parse_coord(val):
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).strip()
            m = re.match(r"([-\d.]+)\s*°?\s*([NSEW])?", s)
            if m:
                num = float(m[1])
                direction = m[2]
                if direction in ("S", "W"):
                    num = -abs(num)
                return num
            return np.nan

        lat = parse_coord(lat)
        lon = parse_coord(lon)

        # Out of range
        if abs(lat) > 90:
            if abs(lat) <= 180 and abs(lon) <= 90:
                # Likely swapped
                lat, lon = lon, lat
                flags.append("swapped_and_fixed")
            else:
                flags.append("lat_out_of_range")
        if abs(lon) > 180:
            flags.append("lon_out_of_range")

        # Null Island
        if lat == 0 and lon == 0:
            flags.append("null_island")

        # Excess precision: round to 6 decimal places
        lat = round(lat, 6) if not np.isnan(lat) else lat
        lon = round(lon, 6) if not np.isnan(lon) else lon

        df.at[i, "lat_clean"] = lat
        df.at[i, "lon_clean"] = lon
        df.at[i, "geo_flag"] = "; ".join(flags)

    return df


# ============================================================================
# 32. Multilingual / Homoglyph Mixing
# ============================================================================

def clean_multilingual_mixing(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Unicode: NFKC, strip zero-width chars, collapse whitespace."""
    df = df.copy()

    def normalize_unicode(s):
        if not isinstance(s, str):
            return s
        # NFKC: fullwidth -> ASCII, decompose + compose
        s = unicodedata.normalize("NFKC", s)
        # Remove zero-width characters
        s = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", s)
        # Replace all Unicode whitespace with regular space
        s = re.sub(r"[\s\xa0\u2002\u2003\u2007\u2008\u2009\u200a]+", " ", s)
        # Strip trademark etc
        s = s.replace("™", "").replace("®", "").replace("©", "")
        return s.strip()

    df["product_name_clean"] = df["product_name"].apply(normalize_unicode)
    return df


# ============================================================================
# 33. OCR Artifacts
# ============================================================================

def clean_ocr_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """Fix systematic O/0, l/1, Z/2, B/8 confusion in numeric contexts."""
    df = df.copy()

    def fix_ocr_numeric(s):
        """Apply OCR corrections in contexts where digits are expected."""
        if not isinstance(s, str):
            return s
        s = s.replace("O", "0").replace("o", "0")
        s = s.replace("l", "1").replace("I", "1")
        s = s.replace("Z", "2")
        s = s.replace("B", "8")
        return s

    def fix_ocr_id(s):
        """Fix OCR in invoice IDs: only fix digits in the numeric parts."""
        if not isinstance(s, str):
            return s
        # Normalize dashes
        s = s.replace("—", "-").replace("–", "-")
        # Fix 'l' at start (should be 'I' for INV)
        if s.startswith("l"):
            s = "I" + s[1:]
        # Split on dashes, fix numeric segments
        parts = s.split("-")
        fixed = []
        for part in parts:
            if part.startswith(("INV", "inv")):
                fixed.append(part)
            else:
                fixed.append(fix_ocr_numeric(part))
        return "-".join(fixed)

    df["invoice_no_clean"] = df["invoice_no"].apply(fix_ocr_id)
    df["amount_clean"] = df["amount"].apply(fix_ocr_numeric)
    df["date_clean"] = df["date"].apply(fix_ocr_numeric)

    return df


# ============================================================================
# 34. Temporal Overlap
# ============================================================================

def clean_temporal_overlap(df: pd.DataFrame) -> pd.DataFrame:
    """Detect overlapping date ranges per employee."""
    df = df.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["temporal_issue"] = ""

    for emp_id, group in df.groupby("employee_id"):
        group = group.sort_values("start_date")
        indices = group.index.tolist()

        # Check for overlaps
        for j in range(1, len(indices)):
            prev_idx = indices[j - 1]
            curr_idx = indices[j]

            prev_end = df.at[prev_idx, "end_date"]
            curr_start = df.at[curr_idx, "start_date"]

            if pd.isna(prev_end):
                # Previous record still active when new one starts
                df.at[curr_idx, "temporal_issue"] = "overlap_with_open_record"
                df.at[prev_idx, "temporal_issue"] = "has_successor_while_open"
            elif curr_start <= prev_end:
                df.at[curr_idx, "temporal_issue"] = "overlap"

            # Gap detection
            elif (curr_start - prev_end).days > 1:
                df.at[curr_idx, "temporal_issue"] = (
                    df.at[curr_idx, "temporal_issue"] or ""
                ) + f"gap_{(curr_start - prev_end).days}d"

        # Check for multiple active (null end_date) records
        active = group[group["end_date"].isna()]
        if len(active) > 1:
            for idx in active.index:
                existing = df.at[idx, "temporal_issue"]
                df.at[idx, "temporal_issue"] = (
                    (existing + "; " if existing else "") + "multiple_active"
                )

    return df


# ============================================================================
# 35. Large Integer Precision
# ============================================================================

def clean_large_integer_precision(df: pd.DataFrame) -> pd.DataFrame:
    """Convert large integers to strings to preserve precision."""
    df = df.copy()
    df["big_id_str"] = df["big_id"].apply(
        lambda x: str(int(x)) if isinstance(x, (int, float)) and not np.isnan(float(x)) else str(x)
    )
    df["precision_safe"] = df["big_id"].apply(
        lambda x: abs(float(x)) <= 2**53 if isinstance(x, (int, float)) else True
    )
    return df
