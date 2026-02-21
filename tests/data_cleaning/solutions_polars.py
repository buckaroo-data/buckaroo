"""
Data Cleaning Solutions — polars

Each function takes a dirty DataFrame (as loaded from the test case parquet)
and returns a cleaned DataFrame. Where cleaning is lossy or ambiguous, a
secondary column of flags/issues is included.

NOTE: Polars is strict about types and doesn't have per-row iteration by
default. Many of these solutions use map_elements() for complex per-cell
logic. In production, prefer vectorized expressions where possible.
"""

import re
import unicodedata
from datetime import datetime, timezone

import polars as pl


# ============================================================================
# Helpers
# ============================================================================

PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?"
    r"(?:\(?\d{3}\)?[\s.-]?)"
    r"\d{3}[\s.-]?\d{4}"
    r"|1-\d{3}-[A-Z]{7}"
)

MISSING_STRINGS = {
    "", " ", "  ", "N/A", "n/a", "NA", "na", "NULL", "null", "Null",
    "None", "none", "NONE", "-", "--", "---", ".", "..", "...",
    "?", "??", "???", "TBD", "TBA", "#N/A", "#NULL!", "#VALUE!",
    "NaN", "nan",
}

TRUTHY = {"true", "yes", "y", "t", "on", "1"}
FALSY = {"false", "no", "n", "f", "off", "0"}


def _to_bool(val) -> bool | None:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in TRUTHY:
        return True
    if s in FALSY:
        return False
    return None


def _normalize_ws(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", s)
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\s\xa0]+", " ", s)
    return s.strip()


# ============================================================================
# 1. Phone in Address
# ============================================================================

def clean_phone_in_address(df: pl.DataFrame) -> pl.DataFrame:
    def classify(addr):
        if addr is None:
            return {"clean_addr": None, "is_phone": False, "extracted_phone": None}
        match = PHONE_RE.search(addr)
        if match:
            remainder = (addr[:match.start()] + addr[match.end():]).strip().strip(",").strip()
            return {
                "clean_addr": remainder if len(remainder) >= 5 else None,
                "is_phone": len(remainder) < 5,
                "extracted_phone": match.group(),
            }
        return {"clean_addr": addr, "is_phone": False, "extracted_phone": None}

    results = [classify(a) for a in df["address"].to_list()]
    return df.with_columns(
        pl.Series("address_clean", [r["clean_addr"] for r in results]),
        pl.Series("address_is_phone", [r["is_phone"] for r in results]),
        pl.Series("extracted_phone_from_address", [r["extracted_phone"] for r in results]),
    )


# ============================================================================
# 2. Mixed Date Formats
# ============================================================================

def clean_mixed_date_formats(df: pl.DataFrame) -> pl.DataFrame:
    from datetime import timedelta

    def parse_date(raw):
        if raw is None or str(raw).strip() == "":
            return None, "empty"
        raw = str(raw).strip()

        # Unix timestamp
        if re.match(r"^\d{10}$", raw):
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m-%d"), "unix_seconds"
        if re.match(r"^\d{13}$", raw):
            return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d"), "unix_ms"

        # Excel serial date
        if re.match(r"^\d{5}$", raw):
            from datetime import date, timedelta
            base = date(1899, 12, 30)
            dt = base + timedelta(days=int(raw))
            return dt.isoformat(), "excel_serial"

        # Compact YYYYMMDD
        if re.match(r"^\d{8}$", raw):
            try:
                dt = datetime.strptime(raw, "%Y%m%d")
                return dt.strftime("%Y-%m-%d"), "compact"
            except ValueError:
                pass

        # Quarter / Week
        if re.match(r"^Q\d\s+\d{4}$", raw) or re.match(r"^Week\s+\d", raw):
            return None, "period_not_date"

        # Remove ordinal suffixes
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw)

        # Try common formats
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y",
                     "%d-%b-%Y", "%Y/%m/%d", "%Y.%m.%d", "%d %B %Y",
                     "%B %d, %Y", "%a %b %d %Y", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%dT%H:%M:%S.%fZ", "%m-%d-%Y %I:%M %p",
                     "%m/%d/%y", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d"), "parsed"
            except ValueError:
                continue

        return None, "unparseable"

    results = [parse_date(d) for d in df["date"].to_list()]
    return df.with_columns(
        pl.Series("parsed_date", [r[0] for r in results]),
        pl.Series("date_parse_method", [r[1] for r in results]),
    )


# ============================================================================
# 3. Impossible Dates
# ============================================================================

def clean_impossible_dates(df: pl.DataFrame) -> pl.DataFrame:
    def validate(raw):
        if raw is None or str(raw).strip() == "":
            return False, "missing"
        raw = str(raw).strip()
        if raw == "0000-00-00":
            return False, "null_sentinel"
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00").split(" ")[0])
        except ValueError:
            return False, "unparseable"

        if dt.year > 2025:
            return False, "future_date"
        if dt.year < 1900:
            return False, "before_1900"
        if dt.year == 9999:
            return False, "max_date_sentinel"
        if dt.year == 1970 and dt.month == 1 and dt.day == 1:
            return True, "suspicious_epoch"
        return True, ""

    results = [validate(d) for d in df["birth_date"].to_list()]
    return df.with_columns(
        pl.Series("birth_date_valid", [r[0] for r in results]),
        pl.Series("birth_date_issue", [r[1] for r in results]),
    )


# ============================================================================
# 4. Mostly Int with Strings
# ============================================================================

def clean_mostly_int_with_strings(df: pl.DataFrame) -> pl.DataFrame:
    def parse_qty(val):
        if val is None:
            return None, "missing"
        s = str(val).strip()
        if s.lower() in {"n/a", "null", "unknown", "-", "tbd", "none"}:
            return None, f"missing:{s}"
        if s.startswith("#"):
            return None, f"excel_error:{s}"
        if re.search(r"[a-df-zA-DF-Z]", s):
            return None, f"freetext:{s}"
        try:
            cleaned = s.replace(",", "").strip()
            num = float(cleaned)
            if num == int(num):
                return int(num), ""
            return num, "float_in_int_col"
        except ValueError:
            return None, f"unparseable:{s}"

    results = [parse_qty(v) for v in df["quantity"].to_list()]
    # Use Float64 to handle mixed int/float/None
    return df.with_columns(
        pl.Series("quantity_clean", [float(r[0]) if r[0] is not None else None for r in results], dtype=pl.Float64),
        pl.Series("quantity_flag", [r[1] for r in results]),
    )


# ============================================================================
# 5. Missing Value Zoo
# ============================================================================

def clean_missing_value_zoo(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col("value").alias("value_was"),
        pl.col("value").map_elements(
            lambda v: None if v is None or (isinstance(v, str) and v.strip() in MISSING_STRINGS) else v,
            return_dtype=pl.Utf8,
        ).alias("value_clean"),
    )


# ============================================================================
# 6. Formatted Numbers
# ============================================================================

def clean_formatted_numbers(df: pl.DataFrame) -> pl.DataFrame:
    def parse_price(raw):
        if raw is None:
            return None, ""
        s = str(raw).strip()
        flag = ""

        if s.startswith(("~", "<", ">", "≈")):
            flag = "approximate"
            s = re.sub(r"^[~<>≈]\s*", "", s)
        if s.endswith("+"):
            flag = "lower_bound"
            s = s[:-1].strip()

        m = re.match(r"^(\d+)/(\d+)$", s)
        if m:
            return int(m[1]) / int(m[2]), "fraction"

        if s.endswith("%"):
            try:
                return float(s[:-1]), "percentage"
            except ValueError:
                pass

        s = re.sub(r"[$€£¥₹]", "", s).strip()
        s = re.sub(r"\s*(USD|EUR|GBP|JPY)\s*$", "", s, flags=re.I).strip()

        if re.match(r"^[\d.]+,\d{2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "").replace("'", "").replace(" ", "")

        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        if s.endswith("-"):
            s = "-" + s[:-1]

        try:
            return float(s), flag
        except ValueError:
            return None, "unparseable"

    results = [parse_price(p) for p in df["price"].to_list()]
    return df.with_columns(
        pl.Series("price_clean", [r[0] for r in results], dtype=pl.Float64),
        pl.Series("price_flag", [r[1] for r in results]),
    )


# ============================================================================
# 7. Whitespace Chaos
# ============================================================================

def clean_whitespace_chaos(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col("name").map_elements(_normalize_ws, return_dtype=pl.Utf8).alias("name_clean"),
    )


# ============================================================================
# 8. Mojibake
# ============================================================================

def clean_mojibake(df: pl.DataFrame) -> pl.DataFrame:
    def fix(s):
        if not isinstance(s, str) or "Ã" not in s:
            return s
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s

    return df.with_columns(
        pl.col("city").map_elements(fix, return_dtype=pl.Utf8).alias("city_clean"),
    )


# ============================================================================
# 9. Field Swap Name/Email
# ============================================================================

def clean_field_swap_name_email(df: pl.DataFrame) -> pl.DataFrame:
    email_re = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")
    ssn_re = re.compile(r"^\d{3}-\d{2}-\d{4}$")

    def classify(name):
        if name is None or str(name).strip() == "":
            return "", "empty"
        name = str(name).strip()
        if ssn_re.match(name):
            return "[REDACTED]", "SSN_PII_CRITICAL"
        if email_re.match(name):
            return name, "email_in_name"
        if "(" in name and ")" in name:
            return name, "has_parenthetical"
        if "," in name:
            return name, "last_first_format"
        return name, ""

    results = [classify(n) for n in df["name"].to_list()]
    return df.with_columns(
        pl.Series("name_clean", [r[0] for r in results]),
        pl.Series("name_issue", [r[1] for r in results]),
    )


# ============================================================================
# 10. Address Field Chaos
# ============================================================================

def clean_address_field_chaos(df: pl.DataFrame) -> pl.DataFrame:
    def classify(addr):
        if addr is None or str(addr).strip() in MISSING_STRINGS:
            return "missing"
        addr = str(addr).strip()
        if re.match(r"^\d{5}(-\d{4})?$", addr):
            return "zip_only"
        if re.match(r"^[A-Z]{2}$", addr):
            return "state_only"
        if re.match(r"^\d{7,}$", addr):
            return "phone_number"
        if re.match(r"^[\w.-]+\.\w{2,4}$", addr):
            return "url"
        if addr.lower().startswith("same as"):
            return "cross_reference"
        if "\n" in addr:
            return "multiline"
        return "ok"

    quality = [classify(a) for a in df["full_address"].to_list()]
    clean_addr = [
        re.sub(r"\s+", " ", str(a)).strip() if a is not None else None
        for a in df["full_address"].to_list()
    ]
    return df.with_columns(
        pl.Series("full_address_clean", clean_addr),
        pl.Series("address_quality", quality),
    )


# ============================================================================
# 11. Boolean Chaos
# ============================================================================

def clean_boolean_chaos(df: pl.DataFrame) -> pl.DataFrame:
    results = [_to_bool(v) for v in df["is_active"].to_list()]
    return df.with_columns(
        pl.Series("is_active_clean", results, dtype=pl.Boolean),
    )


# ============================================================================
# 12. Categorical Inconsistency
# ============================================================================

def clean_categorical_inconsistency(df: pl.DataFrame) -> pl.DataFrame:
    COUNTRY_MAP = {
        "united states": "US", "us": "US", "usa": "US", "u.s.": "US",
        "u.s.a.": "US", "united states of america": "US", "u s a": "US",
        "unied states": "US", "untied states": "US", "united sates": "US",
        "germany": "DE", "de": "DE", "deu": "DE", "deutschland": "DE",
        "japan": "JP", "jp": "JP", "jpn": "JP", "日本": "JP",
        "united kingdom": "GB", "uk": "GB", "gb": "GB", "gbr": "GB",
        "england": "GB",
    }

    def norm(val):
        if val is None:
            return None
        s = str(val).strip().lower().replace(".", "").strip()
        return COUNTRY_MAP.get(s, val)

    return df.with_columns(
        pl.col("country").map_elements(norm, return_dtype=pl.Utf8).alias("country_clean"),
    )


# ============================================================================
# 13. Excel Artifacts
# ============================================================================

def clean_excel_artifacts(df: pl.DataFrame) -> pl.DataFrame:
    excel_errors = {"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}

    def classify(val):
        if val is None:
            return None, ""
        s = str(val).strip()
        if s in excel_errors:
            return None, f"excel_error:{s}"
        if s.startswith("="):
            return None, "leaked_formula"
        if s == "###":
            return None, "display_artifact"
        if s == "General":
            return None, "format_name_leaked"
        if s in ("TRUE", "FALSE"):
            return str(s == "TRUE"), "excel_boolean"
        return s, ""

    results = [classify(v) for v in df["value"].to_list()]
    return df.with_columns(
        pl.Series("value_clean", [r[0] for r in results]),
        pl.Series("value_issue", [r[1] for r in results]),
    )


# ============================================================================
# 14. Mixed Units
# ============================================================================

def clean_mixed_units(df: pl.DataFrame) -> pl.DataFrame:
    def parse_weight_to_kg(raw):
        if raw is None:
            return None, "missing"
        s = str(raw).strip().lower()
        flag = ""
        if s.startswith(("about", "~", "<", ">")):
            flag = "approximate"
            s = re.sub(r"^(about|~|[<>])\s*", "", s)
        if "-" in s and "kg" in s:
            flag = "range"
            s = s.split("-")[0].strip()

        m = re.match(r"([\d.]+)\s*lbs?\s+([\d.]+)\s*oz", s)
        if m:
            return float(m[1]) * 0.453592 + float(m[2]) * 0.0283495, flag or "compound"

        m = re.match(r"([\d,.]+)\s*(kg|kilograms?|lbs?|pounds?|g|grams?|oz|ounces?|tonnes?|mg)?", s)
        if not m:
            return None, "unparseable"

        num = float(m[1].replace(",", ""))
        unit = (m[2] or "").lower()
        conv = {"": num, "kg": num, "kilogram": num, "kilograms": num,
                "lb": num * 0.453592, "lbs": num * 0.453592,
                "pound": num * 0.453592, "pounds": num * 0.453592,
                "g": num / 1000, "gram": num / 1000, "grams": num / 1000,
                "oz": num * 0.0283495, "ounce": num * 0.0283495,
                "tonne": num * 1000, "tonnes": num * 1000,
                "mg": num / 1_000_000}
        kg = conv.get(unit)
        return (kg, flag or ("bare_number" if unit == "" else "")) if kg is not None else (None, "unknown_unit")

    weight_results = [parse_weight_to_kg(w) for w in df["weight"].to_list()]
    return df.with_columns(
        pl.Series("weight_kg", [r[0] for r in weight_results], dtype=pl.Float64),
        pl.Series("weight_flag", [r[1] for r in weight_results]),
    )


# ============================================================================
# 15. Copy-Paste Artifacts
# ============================================================================

def clean_copy_paste_artifacts(df: pl.DataFrame) -> pl.DataFrame:
    import html as html_mod

    def clean_text(s):
        if s is None:
            return s
        s = str(s)
        s = s.replace("\x00", "")
        s = re.sub(r"\x1b\[[0-9;]*m", "", s)
        s = re.sub(r"<[^>]+>", "", s)
        s = html_mod.unescape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        if s and s[0] in ("=", "+", "@", "\t"):
            s = "'" + s
        elif s and s[0] == "-" and not re.match(r"^-?\d", s):
            s = "'" + s
        return s.strip()

    cleaned = [clean_text(d) for d in df["description"].to_list()]
    return df.with_columns(pl.Series("description_clean", cleaned))


# ============================================================================
# 16. Near Duplicates
# ============================================================================

def clean_near_duplicates(df: pl.DataFrame) -> pl.DataFrame:
    phone_norm = [re.sub(r"[^\d]", "", str(p)) for p in df["phone"].to_list()]
    name_norm = [str(n).strip().lower() for n in df["name"].to_list()]
    email_norm = [str(e).strip().lower() for e in df["email"].to_list()]

    # Duplicate group by customer_id
    dup_group = []
    seen_ids: dict[int, int] = {}
    for cid in df["customer_id"].to_list():
        count = seen_ids.get(cid, 0)
        seen_ids[cid] = count + 1
        dup_group.append(count)

    return df.with_columns(
        pl.Series("phone_normalized", phone_norm),
        pl.Series("name_normalized", name_norm),
        pl.Series("email_normalized", email_norm),
        pl.Series("duplicate_group", dup_group),
        pl.Series("is_duplicate", [g > 0 for g in dup_group]),
    )


# ============================================================================
# 17. Floating Point Issues
# ============================================================================

def clean_floating_point_issues(df: pl.DataFrame) -> pl.DataFrame:
    import math

    def classify(val):
        if val is None:
            return None, "missing"
        if math.isinf(val):
            return None, "infinity"
        if math.isnan(val):
            return None, "nan"
        if val == 0 and math.copysign(1, val) < 0:
            return 0.0, "negative_zero"
        if abs(val) > 1e15:
            return val, "very_large"
        if 0 < abs(val) < 1e-10:
            return val, "near_zero"
        return val, ""

    results = [classify(v) for v in df["amount"].to_list()]
    return df.with_columns(
        pl.Series("amount_clean", [r[0] for r in results], dtype=pl.Float64),
        pl.Series("amount_flag", [r[1] for r in results]),
    )


# ============================================================================
# 18. Jagged Schema
# ============================================================================

def clean_jagged_schema(df: pl.DataFrame) -> pl.DataFrame:
    # Drop artifact columns
    artifact_cols = [c for c in df.columns if c.startswith("Unnamed:")]
    df = df.drop(artifact_cols)

    # Age: try to parse as int
    def parse_age(val):
        if val is None:
            return None, ""
        try:
            return int(float(str(val))), ""
        except (ValueError, TypeError):
            return None, str(val)

    age_results = [parse_age(v) for v in df["age"].to_list()]

    # Salary
    def parse_salary(val):
        if val is None:
            return None, ""
        try:
            return float(str(val)), ""
        except (ValueError, TypeError):
            return None, str(val)

    salary_results = [parse_salary(v) for v in df["salary"].to_list()]

    return df.with_columns(
        pl.Series("age_clean", [r[0] for r in age_results], dtype=pl.Int64),
        pl.Series("age_flag", [r[1] for r in age_results]),
        pl.Series("salary_clean", [r[0] for r in salary_results], dtype=pl.Float64),
        pl.Series("salary_flag", [r[1] for r in salary_results]),
        pl.when(pl.col("department") == "").then(None).otherwise(pl.col("department")).alias("department_clean"),
    )


# ============================================================================
# 19. Cross-Field Inconsistencies
# ============================================================================

def clean_cross_field_inconsistencies(df: pl.DataFrame) -> pl.DataFrame:
    ref_year = 2024

    def validate_row(birth_date, age, state, zip_code, order_date, ship_date):
        issues = []
        # Age vs birth_date
        try:
            birth_year = datetime.fromisoformat(str(birth_date)).year
            expected_age = ref_year - birth_year
            if age < 0:
                issues.append("negative_age")
            elif abs(expected_age - age) > 1:
                issues.append(f"age_mismatch(expected~{expected_age},got={age})")
        except (ValueError, TypeError):
            pass

        if str(state) == "ZZ":
            issues.append("invalid_state")
        if str(zip_code) == "00000":
            issues.append("invalid_zip")

        try:
            o = datetime.fromisoformat(str(order_date))
            s = datetime.fromisoformat(str(ship_date))
            if s < o:
                issues.append("shipped_before_ordered")
        except (ValueError, TypeError):
            pass

        return "; ".join(issues)

    rows = df.to_dicts()
    flags = [validate_row(r["birth_date"], r["age"], r["state"], r["zip"],
                          r["order_date"], r["ship_date"]) for r in rows]
    return df.with_columns(pl.Series("issues", flags))


# ============================================================================
# 20. Mixed Numeric Scales
# ============================================================================

def clean_mixed_numeric_scales(df: pl.DataFrame) -> pl.DataFrame:
    scale_rules = {
        "revenue": [(lambda v: v > 100000, 1, "dollars"),
                     (lambda v: 100 < v <= 100000, 1000, "thousands"),
                     (lambda v: v <= 100, 1000000, "millions")],
        "conversion_rate": [(lambda v: v < 1, 1, "decimal"),
                             (lambda v: 1 <= v < 100, 0.01, "percentage"),
                             (lambda v: v >= 100, 0.0001, "basis_points")],
        "users": [(lambda v: v > 10000, 1, "count"),
                   (lambda v: 10 < v <= 10000, 1000, "thousands"),
                   (lambda v: v <= 10, 1000000, "millions")],
        "latency_ms": [(lambda v: v < 1, 1000, "seconds"),
                        (lambda v: 1 <= v < 10000, 1, "milliseconds"),
                        (lambda v: v >= 10000, 0.001, "microseconds")],
        "disk_usage": [(lambda v: v < 1, 100, "decimal_fraction"),
                        (lambda v: 1 <= v <= 100, 1, "percentage"),
                        (lambda v: v > 100, 1, "absolute_unknown")],
    }

    rows = df.to_dicts()
    norm_vals = []
    scale_labels = []
    for r in rows:
        metric = r["metric"]
        val = r["value"]
        rules = scale_rules.get(metric, [])
        found = False
        for cond, mult, label in rules:
            if cond(val):
                norm_vals.append(val * mult)
                scale_labels.append(label)
                found = True
                break
        if not found:
            norm_vals.append(val)
            scale_labels.append("")

    return df.with_columns(
        pl.Series("value_normalized", norm_vals, dtype=pl.Float64),
        pl.Series("inferred_scale", scale_labels),
    )


# ============================================================================
# 21. Timezone Chaos
# ============================================================================

def clean_timezone_chaos(df: pl.DataFrame) -> pl.DataFrame:
    from datetime import datetime as dt, timezone as tz, timedelta

    def parse_ts(raw):
        if raw is None:
            return None, ""
        s = str(raw).strip()

        if re.match(r"^\d{10}$", s):
            return dt.fromtimestamp(int(s), tz=tz.utc).isoformat(), "from_unix_seconds"
        if re.match(r"^\d{13}$", s):
            return dt.fromtimestamp(int(s) / 1000, tz=tz.utc).isoformat(), "from_unix_ms"

        flag = ""
        for abbr in ["CST", "IST", "EST", "PST", "ET"]:
            if abbr in s:
                flag = f"ambiguous_tz:{abbr}"

        s = s.replace(" UTC", "+00:00")
        s = s.replace(" EST", "-05:00").replace(" CST", "-06:00")
        s = s.replace(" IST", "+05:30").replace(" PST", "-08:00")
        s = re.sub(r"\s*AM\s+ET$", " -05:00", s)
        s = re.sub(r"^(\w+ \d+, \d+ [\d:]+) GMT([+-]\d{4})$", r"\1\2", s)

        try:
            parsed = dt.fromisoformat(s)
            return parsed.isoformat(), flag or ""
        except ValueError:
            pass

        # Try with Z suffix
        s2 = s.replace("Z", "+00:00")
        try:
            parsed = dt.fromisoformat(s2)
            return parsed.isoformat(), flag or ""
        except ValueError:
            return None, flag or "unparseable"

    results = [parse_ts(t) for t in df["timestamp"].to_list()]
    return df.with_columns(
        pl.Series("timestamp_parsed", [r[0] for r in results]),
        pl.Series("tz_flag", [r[1] for r in results]),
    )


# ============================================================================
# 22. Column Name Chaos
# ============================================================================

def clean_column_name_chaos(df: pl.DataFrame) -> pl.DataFrame:
    renames = {}
    seen = set()

    for col in df.columns:
        clean = str(col).strip()
        clean = re.sub(r"[^\w]+", "_", clean)
        clean = re.sub(r"([a-z])([A-Z])", r"\1_\2", clean).lower()
        clean = clean.strip("_")
        if not clean:
            clean = "unnamed"

        base = clean
        counter = 2
        while clean in seen:
            clean = f"{base}_{counter}"
            counter += 1
        seen.add(clean)
        renames[col] = clean

    df = df.rename(renames)
    # Drop all-null columns
    null_cols = [c for c in df.columns if df[c].null_count() == len(df)]
    return df.drop(null_cols)


# ============================================================================
# 23. Survey Freetext in Structured
# ============================================================================

def clean_survey_freetext_in_structured(df: pl.DataFrame) -> pl.DataFrame:
    def parse_age(val):
        if val is None:
            return None, "missing"
        s = str(val).strip().lower()
        try:
            return float(s), ""
        except ValueError:
            pass
        m = re.match(r"(\d+)\s*-\s*(\d+)", s)
        if m:
            return (int(m[1]) + int(m[2])) / 2, "midpoint_of_range"
        m = re.search(r"born in (\d{4})", s)
        if m:
            return 2024 - int(m[1]), "from_birth_year"
        if any(kw in s for kw in ["prefer not", "old enough", "gen z", "millennial", "¯"]):
            return None, "non_answer"
        m = re.match(r"(\d+)\+?$", s)
        if m:
            return float(m[1]), "lower_bound" if "+" in s else ""
        m = re.search(r"about\s+(\d+)", s)
        if m:
            return float(m[1]), "approximate"
        return None, "unparseable"

    def parse_recommend(val):
        if val is None:
            return None
        s = str(val).strip().lower()
        positives = {"yes", "1", "true", "absolutely", "yes!!!", "👍"}
        negatives = {"no", "0", "false", "nah"}
        if s.rstrip("!") in positives or s in positives:
            return True
        if s in negatives:
            return False
        if s.startswith("yes"):
            return True
        return None

    age_results = [parse_age(a) for a in df["age"].to_list()]
    rec_results = [parse_recommend(r) for r in df["would_recommend"].to_list()]

    return df.with_columns(
        pl.Series("age_clean", [r[0] for r in age_results], dtype=pl.Float64),
        pl.Series("age_flag", [r[1] for r in age_results]),
        pl.Series("would_recommend_clean", rec_results, dtype=pl.Boolean),
    )


# ============================================================================
# 24. Log Data in Table
# ============================================================================

def clean_log_data_in_table(df: pl.DataFrame) -> pl.DataFrame:
    ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}")

    def classify_ts(raw):
        if raw is None or str(raw).strip() == "NULL":
            return None, False
        s = str(raw).strip()
        if s.startswith("---") or not ts_pattern.match(s):
            return None, False
        return s[:23], True

    results = [classify_ts(t) for t in df["timestamp"].to_list()]

    # Fix NULL strings in level/message
    levels = [None if v == "NULL" or v is None else v for v in df["level"].to_list()]
    messages = [None if v == "NULL" or v is None else v for v in df["message"].to_list()]

    return df.with_columns(
        pl.Series("timestamp_clean", [r[0] for r in results]),
        pl.Series("is_data_row", [r[1] for r in results]),
        pl.Series("level_clean", levels),
        pl.Series("message_clean", messages),
    )


# ============================================================================
# 25. Financial Data Edge Cases
# ============================================================================

def clean_financial_data_edge_cases(df: pl.DataFrame) -> pl.DataFrame:
    import math
    from decimal import Decimal, ROUND_HALF_EVEN

    decimals = {"USD": 2, "EUR": 2, "GBP": 2, "JPY": 0,
                "KWD": 3, "BTC": 8, "ETH": 18}

    def clean_amount(val, ccy):
        if val is None or math.isnan(val):
            return None, "missing"
        if math.isinf(val):
            return None, "infinity"
        dp = decimals.get(ccy, 2)
        flag = ""
        if val == 0 and math.copysign(1, val) < 0:
            val = 0.0
            flag = "was_negative_zero"
        d = Decimal(str(val)).quantize(Decimal(10) ** -dp, rounding=ROUND_HALF_EVEN)
        result = float(d)
        if val != result and abs(val - result) > 10 ** -(dp + 2):
            flag = flag or "had_excess_precision"
        return result, flag

    rows = df.to_dicts()
    results = [clean_amount(r["amount"], r["currency"]) for r in rows]
    return df.with_columns(
        pl.Series("amount_clean", [r[0] for r in results], dtype=pl.Float64),
        pl.Series("amount_flag", [r[1] for r in results]),
    )


# ============================================================================
# 26. Structured Data in Cells
# ============================================================================

def clean_structured_data_in_cells(df: pl.DataFrame) -> pl.DataFrame:
    import ast
    import json

    def parse_config(raw):
        if raw is None or str(raw).strip().lower() == "none":
            return "null"
        s = str(raw).strip()
        try:
            json.loads(s)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            ast.literal_eval(s)
            return "python_literal"
        except (ValueError, SyntaxError):
            pass
        if re.search(r"^\w+\s*[=:]\s*\S", s, re.MULTILINE):
            return "key_value"
        if s.startswith("<"):
            return "xml"
        return "other"

    def parse_tags(raw):
        if raw is None or str(raw).strip() == "":
            return []
        s = str(raw).strip()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        for delim in [";", "|", ",", "/", " #", " "]:
            if delim in s:
                return [t.strip().lstrip("#") for t in s.split(delim) if t.strip()]
        return [s]

    config_formats = [parse_config(c) for c in df["config"].to_list()]
    tag_lists = [str(parse_tags(t)) for t in df["tags"].to_list()]

    return df.with_columns(
        pl.Series("config_format", config_formats),
        pl.Series("tags_list", tag_lists),
    )


# ============================================================================
# 27. Truncation and Overflow
# ============================================================================

def clean_truncation_and_overflow(df: pl.DataFrame) -> pl.DataFrame:
    sentinel_values = {"REDACTED", "[FILTERED]", "N/A", "NULL",
                       "See attachment", "TBD", "..."}
    placeholder_pats = [re.compile(r"^lorem ipsum", re.I),
                        re.compile(r"^test$", re.I),
                        re.compile(r"^asdf", re.I)]

    def flag_text(val, col):
        if val is None or str(val).strip() == "":
            return "empty"
        s = str(val).strip()
        if s in sentinel_values or s.startswith(("TBD", "See ", "[FILTERED")):
            return "sentinel"
        if s.endswith("..."):
            return "truncated_ellipsis"
        if len(s) in (40, 255):
            return "possibly_truncated"
        if ";" in s and col == "name":
            return "multi_value"
        if any(p.match(s) for p in placeholder_pats):
            return "placeholder"
        return ""

    name_flags = [flag_text(n, "name") for n in df["name"].to_list()]
    desc_flags = [flag_text(d, "description") for d in df["description"].to_list()]

    return df.with_columns(
        pl.Series("name_flag", name_flags),
        pl.Series("description_flag", desc_flags),
    )


# ============================================================================
# 28. Mixed ID Formats
# ============================================================================

def clean_mixed_id_formats(df: pl.DataFrame) -> pl.DataFrame:
    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    email_re = re.compile(r"^[\w.+-]+@[\w.-]+\.\w+$")

    def normalize_id(raw):
        if raw is None:
            return "", "missing"
        s = str(raw).strip().rstrip("\n")
        if uuid_re.match(s):
            return s.lower(), "uuid"
        if email_re.match(s):
            return s.lower(), "email"
        numeric_part = s
        for prefix in ["LEGACY-", "USR-", "usr_", "#"]:
            if numeric_part.upper().startswith(prefix.upper()):
                numeric_part = numeric_part[len(prefix):]
        if "E+" in numeric_part.upper():
            try:
                numeric_part = str(int(float(numeric_part)))
            except ValueError:
                pass
        if numeric_part.endswith(".0"):
            numeric_part = numeric_part[:-2]
        numeric_part = numeric_part.replace(",", "")
        numeric_part = numeric_part.lstrip("0") or "0"
        return numeric_part, "numeric"

    results = [normalize_id(uid) for uid in df["user_id"].to_list()]
    return df.with_columns(
        pl.Series("user_id_clean", [r[0] for r in results]),
        pl.Series("user_id_type", [r[1] for r in results]),
    )


# ============================================================================
# 29. Timeseries Anomalies
# ============================================================================

def clean_timeseries_anomalies(df: pl.DataFrame) -> pl.DataFrame:
    sales = df["daily_sales"].to_list()
    n = len(sales)
    flags = [""] * n

    # Simple rolling stats (manual, since we need per-element access)
    import math
    window = 30
    for i in range(n):
        val = sales[i]
        if val is None or (isinstance(val, float) and math.isnan(val)):
            flags[i] = "missing"
            continue
        if val < 0:
            flags[i] = "negative"
            continue
        if val == 999999:
            flags[i] = "system_cap"
            continue

        # Check for suspicious zero
        if val == 0:
            prev = sales[i - 1] if i > 0 else None
            nxt = sales[i + 1] if i < n - 1 else None
            if (prev is not None and prev > 100) or (nxt is not None and nxt > 100):
                flags[i] = "suspicious_zero"
                continue

        # Flat-line
        if i >= 2 and val != 0:
            if sales[i] == sales[i - 1] == sales[i - 2]:
                flags[i] = "flat_line"
                continue

        # Simple outlier detection using neighbors
        start = max(0, i - window // 2)
        end = min(n, i + window // 2)
        neighbors = [s for s in sales[start:end]
                     if s is not None and not (isinstance(s, float) and math.isnan(s))
                     and s != 999999 and s >= 0]
        if len(neighbors) > 5:
            mean = sum(neighbors) / len(neighbors)
            std = (sum((x - mean) ** 2 for x in neighbors) / len(neighbors)) ** 0.5
            if std > 0 and abs(val - mean) / std > 5:
                flags[i] = "extreme_outlier"
            elif std > 0 and abs(val - mean) / std > 3:
                flags[i] = "outlier"

    return df.with_columns(pl.Series("anomaly_flag", flags))


# ============================================================================
# 30. Medical Data Entry
# ============================================================================

def clean_medical_data_entry(df: pl.DataFrame) -> pl.DataFrame:
    def parse_bp(raw):
        if raw is None:
            return None, None, ""
        s = str(raw).strip()
        if s.lower() in ("n/a", "normal", "high", "low", "pending", ""):
            return None, None, "qualitative"

        m = re.search(r"systolic[:\s]+(\d+)[,\s]+diastolic[:\s]+(\d+)", s, re.I)
        if m:
            return int(m[1]), int(m[2]), ""

        m = re.match(r"(\d+)\s*[/\\-]\s*(\d+)", s)
        if m:
            sys_v, dia_v = int(m[1]), int(m[2])
            flag = ""
            if sys_v < dia_v:
                sys_v, dia_v = dia_v, sys_v
                flag = "reversed"
            if sys_v < 30:
                sys_v *= 10
                dia_v *= 10
                flag = "european_shorthand"
            return sys_v, dia_v, flag

        if re.match(r"^\d{5,6}$", s):
            return int(s[:3]), int(s[3:]), "missing_delimiter"

        return None, None, "unparseable"

    def parse_temp(raw):
        if raw is None:
            return None, ""
        s = str(raw).strip()
        if s.lower() in ("afebrile", "normal", "wnl", "pending", ""):
            return None, "qualitative"
        s = re.sub(r"^(oral|tympanic|rectal|axillary)[:\s]+", "", s, flags=re.I)
        is_c = bool(re.search(r"[°]?\s*[cC](?:elsius)?", s))
        s = re.sub(r"[°]?\s*(celsius|fahrenheit|[cfCF])$", "", s).strip().rstrip("°")
        try:
            val = float(s)
        except ValueError:
            return None, "unparseable"
        if val > 200:
            val = val / 10
        if is_c or (val < 50 and not re.search(r"[fF]", str(raw))):
            return val * 9 / 5 + 32, ""
        return val, ""

    bp_results = [parse_bp(b) for b in df["blood_pressure"].to_list()]
    temp_results = [parse_temp(t) for t in df["temperature"].to_list()]

    return df.with_columns(
        pl.Series("systolic", [r[0] for r in bp_results], dtype=pl.Int64),
        pl.Series("diastolic", [r[1] for r in bp_results], dtype=pl.Int64),
        pl.Series("bp_flag", [r[2] for r in bp_results]),
        pl.Series("temp_f", [r[0] for r in temp_results], dtype=pl.Float64),
        pl.Series("temp_flag", [r[1] for r in temp_results]),
    )


# ============================================================================
# 31. Geocoordinate Errors
# ============================================================================

def clean_geocoordinate_errors(df: pl.DataFrame) -> pl.DataFrame:
    import math

    def parse_coord(val):
        if isinstance(val, (int, float)) and not math.isnan(val):
            return float(val)
        s = str(val).strip()
        m = re.match(r"([-\d.]+)\s*°?\s*([NSEW])?", s)
        if m:
            num = float(m[1])
            if m[2] in ("S", "W"):
                num = -abs(num)
            return num
        return float("nan")

    rows = df.to_dicts()
    results = []
    for r in rows:
        lat = parse_coord(r["latitude"])
        lon = parse_coord(r["longitude"])
        flags = []

        if abs(lat) > 90:
            if abs(lat) <= 180 and abs(lon) <= 90:
                lat, lon = lon, lat
                flags.append("swapped_and_fixed")
            else:
                flags.append("lat_out_of_range")
        if abs(lon) > 180:
            flags.append("lon_out_of_range")
        if lat == 0 and lon == 0:
            flags.append("null_island")

        lat = round(lat, 6) if not math.isnan(lat) else None
        lon = round(lon, 6) if not math.isnan(lon) else None
        results.append((lat, lon, "; ".join(flags)))

    return df.with_columns(
        pl.Series("lat_clean", [r[0] for r in results], dtype=pl.Float64),
        pl.Series("lon_clean", [r[1] for r in results], dtype=pl.Float64),
        pl.Series("geo_flag", [r[2] for r in results]),
    )


# ============================================================================
# 32. Multilingual / Homoglyph Mixing
# ============================================================================

def clean_multilingual_mixing(df: pl.DataFrame) -> pl.DataFrame:
    def normalize(s):
        if not isinstance(s, str):
            return s
        s = unicodedata.normalize("NFKC", s)
        s = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", s)
        s = re.sub(r"[\s\xa0\u2002\u2003\u2007\u2008\u2009\u200a]+", " ", s)
        s = s.replace("™", "").replace("®", "").replace("©", "")
        return s.strip()

    cleaned = [normalize(p) for p in df["product_name"].to_list()]
    return df.with_columns(pl.Series("product_name_clean", cleaned))


# ============================================================================
# 33. OCR Artifacts
# ============================================================================

def clean_ocr_artifacts(df: pl.DataFrame) -> pl.DataFrame:
    def fix_ocr_numeric(s):
        if s is None:
            return s
        return str(s).replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1").replace("Z", "2").replace("B", "8")

    def fix_ocr_id(s):
        if s is None:
            return s
        s = str(s).replace("—", "-").replace("–", "-")
        if s.startswith("l"):
            s = "I" + s[1:]
        parts = s.split("-")
        fixed = []
        for part in parts:
            if part.upper().startswith("INV"):
                fixed.append(part)
            else:
                fixed.append(fix_ocr_numeric(part))
        return "-".join(fixed)

    return df.with_columns(
        pl.col("invoice_no").map_elements(fix_ocr_id, return_dtype=pl.Utf8).alias("invoice_no_clean"),
        pl.col("amount").map_elements(fix_ocr_numeric, return_dtype=pl.Utf8).alias("amount_clean"),
        pl.col("date").map_elements(fix_ocr_numeric, return_dtype=pl.Utf8).alias("date_clean"),
    )


# ============================================================================
# 34. Temporal Overlap
# ============================================================================

def clean_temporal_overlap(df: pl.DataFrame) -> pl.DataFrame:
    # Convert dates — end_date may have "None" strings from str-cast
    df = df.with_columns(
        pl.col("start_date").str.to_date("%Y-%m-%d", strict=False).alias("start_dt"),
        pl.col("end_date").str.to_date("%Y-%m-%d", strict=False).alias("end_dt"),
    )

    rows = df.to_dicts()
    flags = [""] * len(rows)

    # Group by employee
    from collections import defaultdict
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r["employee_id"]].append(i)

    for emp_id, indices in groups.items():
        # Sort by start_date
        indices.sort(key=lambda idx: rows[idx]["start_dt"])

        for j in range(1, len(indices)):
            prev_idx = indices[j - 1]
            curr_idx = indices[j]
            prev_end = rows[prev_idx]["end_dt"]
            curr_start = rows[curr_idx]["start_dt"]

            if prev_end is None:
                flags[curr_idx] = "overlap_with_open_record"
                flags[prev_idx] = flags[prev_idx] or "has_successor_while_open"
            elif curr_start <= prev_end:
                flags[curr_idx] = "overlap"

        # Multiple active
        active_indices = [idx for idx in indices if rows[idx]["end_dt"] is None]
        if len(active_indices) > 1:
            for idx in active_indices:
                flags[idx] = (flags[idx] + "; " if flags[idx] else "") + "multiple_active"

    return df.with_columns(pl.Series("temporal_issue", flags))


# ============================================================================
# 35. Large Integer Precision
# ============================================================================

def clean_large_integer_precision(df: pl.DataFrame) -> pl.DataFrame:
    big_ids = df["big_id"].to_list()
    str_ids = [str(int(float(x))) if not isinstance(x, str) else x for x in big_ids]
    safe = [abs(float(x)) <= 2**53 if not isinstance(x, str) else True for x in big_ids]

    return df.with_columns(
        pl.Series("big_id_str", str_ids),
        pl.Series("precision_safe", safe),
    )
