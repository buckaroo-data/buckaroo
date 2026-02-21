"""
Data Cleaning Test Case Generator

Generates parquet files representing real-world messy data scenarios.
Each test case includes metadata describing the issues present.

Usage:
    python -m tests.data_cleaning.generate_testcases [output_dir]
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def _meta(
    *,
    name: str,
    description: str,
    category: str,
    tags: list[str],
    affected_columns: list[str],
    row_count: int,
    difficulty: str,  # "easy", "medium", "hard"
    expected_issues: list[str],
    notes: str = "",
) -> dict:
    return dict(
        name=name,
        description=description,
        category=category,
        tags=tags,
        affected_columns=affected_columns,
        row_count=row_count,
        difficulty=difficulty,
        expected_issues=expected_issues,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 1. PHONE NUMBERS IN ADDRESS FIELDS
# ---------------------------------------------------------------------------

def phone_in_address():
    df = pd.DataFrame({
        "name": [
            "Alice Johnson", "Bob Smith", "Carol Davis", "Dan Lee",
            "Eve Martinez", "Frank Wilson", "Grace Kim", "Hank Brown",
            "Ivy Chen", "Jake Taylor",
        ],
        "address": [
            "123 Main St, Springfield, IL 62704",
            "(555) 867-5309",                          # phone number
            "456 Oak Ave, Portland, OR 97201",
            "555-0142",                                 # phone number
            "789 Pine Rd\n(503) 555-0198",             # address + phone jammed together
            "1-800-FLOWERS",                            # vanity phone number
            "101 Elm St, Austin, TX 78701",
            "+1 212 555 0173",                          # international format
            "202 Birch Ln, Denver, CO 80202",
            "Call 555.012.3456 for directions",         # phone embedded in text
        ],
        "phone": [
            "(217) 555-0101", "(555) 867-5309", "(503) 555-0134", "555-0142",
            "(503) 555-0198", "1-800-356-9377", "(512) 555-0156", "+1 212 555 0173",
            "(303) 555-0189", "(415) 555-0167",
        ],
    })
    meta = _meta(
        name="phone_in_address",
        description="Phone numbers stored in address fields instead of phone column",
        category="field_contamination",
        tags=["phone", "address", "wrong_field", "PII"],
        affected_columns=["address"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Phone number as entire address value",
            "Phone number appended to valid address",
            "Vanity phone number in address",
            "International phone format in address",
            "Phone embedded in natural language directions",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 2. MIXED DATE FORMATS
# ---------------------------------------------------------------------------

def mixed_date_formats():
    df = pd.DataFrame({
        "event": [f"Event_{i}" for i in range(20)],
        "date": [
            "2024-01-15",              # ISO
            "01/15/2024",              # US
            "15/01/2024",              # European
            "Jan 15, 2024",            # human-readable
            "15-Jan-2024",             # another human format
            "20240115",                # compact
            "1705276800",              # Unix timestamp (string)
            "45307",                   # Excel serial date (2024-01-15)
            "January 15th, 2024",      # long form with ordinal
            "2024/01/15",              # slash ISO
            "2024.01.15",              # dot-separated
            "15 January 2024",         # European long
            "Mon Jan 15 2024",         # ctime-ish
            "2024-01-15T10:30:00Z",    # ISO 8601 with time
            "01-15-2024 10:30 AM",     # US with time
            "1/15/24",                 # 2-digit year
            "2024-1-15",               # no zero-padding
            "Q1 2024",                 # quarterly
            "Week 3, 2024",            # weekly
            "",                        # blank
        ],
    })
    meta = _meta(
        name="mixed_date_formats",
        description="Single date column with 15+ different date formats intermixed",
        category="date_chaos",
        tags=["dates", "mixed_formats", "parsing"],
        affected_columns=["date"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "ISO vs US vs European date ambiguity (01/02 = Jan 2 or Feb 1?)",
            "Unix timestamp as string",
            "Excel serial date number",
            "Ordinal suffix (15th)",
            "Two-digit year ambiguity",
            "Quarterly and weekly references (not actual dates)",
            "Empty string instead of null",
            "Mixed delimiters (-, /, .)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 3. IMPOSSIBLE / SUSPICIOUS DATES
# ---------------------------------------------------------------------------

def impossible_dates():
    df = pd.DataFrame({
        "person": [f"Person_{i}" for i in range(15)],
        "birth_date": [
            "1990-06-15",
            "2030-01-01",              # future birth date
            "1899-12-31",              # suspiciously old
            "0000-00-00",              # null sentinel
            "1990-02-30",              # Feb 30 doesn't exist
            "1990-13-01",              # month 13
            "1990-00-15",              # month 0
            "1969-12-31",              # Unix epoch boundary
            "9999-12-31",              # max date
            "1990-06-31",              # June has 30 days
            "2000-02-29",              # valid leap day
            "1900-02-29",              # invalid leap day (1900 not leap)
            "2024-04-31",              # April has 30 days
            "1990-06-15 25:00:00",     # hour 25
            "1970-01-01",              # suspiciously exactly epoch
        ],
        "hire_date": [
            "2020-03-15", "2019-11-01", "2021-06-30", "2018-01-15",
            "2024-12-25", "2015-08-20", "2023-02-14", "2017-09-10",
            "2022-07-04", "2016-03-22", "2020-10-31", "2019-04-15",
            "2023-08-08", "2021-01-01", "2014-05-05",
        ],
    })
    meta = _meta(
        name="impossible_dates",
        description="Dates that are logically impossible, suspicious, or edge-case",
        category="date_chaos",
        tags=["dates", "validation", "impossible_values", "edge_cases"],
        affected_columns=["birth_date"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Future birth dates",
            "Dates before 1900",
            "0000-00-00 as null sentinel",
            "Non-existent days (Feb 30, Jun 31, Apr 31)",
            "Invalid month (13, 0)",
            "Invalid leap day (1900-02-29)",
            "Hour > 23",
            "Suspiciously exactly Unix epoch",
            "Max date 9999-12-31",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 4. MOSTLY INTEGERS WITH OUTLIER STRINGS
# ---------------------------------------------------------------------------

def mostly_int_with_strings():
    values = list(range(1, 51))
    # Sprinkle in string outliers at specific positions
    outliers = {
        3: "N/A",
        7: "unknown",
        12: "#REF!",
        18: "null",
        22: "-",
        27: "TBD",
        31: "see notes",
        36: "999999999",       # suspiciously large but valid int-string
        40: "12.5",            # float in an int column
        44: " 15 ",            # int with whitespace
        48: "1,234",           # comma-formatted number
    }
    col = []
    for i in range(1, 51):
        if i in outliers:
            col.append(outliers[i])
        else:
            col.append(i * 10)
    df = pd.DataFrame({
        "id": list(range(1, 51)),
        "quantity": col,
    })
    meta = _meta(
        name="mostly_int_with_strings",
        description="Numeric column that is ~80% integers but has various string outliers",
        category="mixed_types",
        tags=["integers", "strings", "mixed_types", "null_representations"],
        affected_columns=["quantity"],
        row_count=len(df),
        difficulty="easy",
        expected_issues=[
            "N/A, null, unknown, TBD as missing-data strings",
            "#REF! from Excel error",
            "Dash as missing value",
            "Free-text in numeric column",
            "Float in integer column",
            "Whitespace-padded number",
            "Comma-formatted number",
            "Very large number as string",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 5. EVERY KIND OF MISSING VALUE
# ---------------------------------------------------------------------------

def missing_value_zoo():
    missing_representations = [
        None, np.nan, "", " ", "  ", "N/A", "n/a", "NA", "na",
        "NULL", "null", "Null", "None", "none", "NONE",
        "-", "--", "---", ".", "..", "...",
        "?", "??", "???", "TBD", "TBA",
        "#N/A", "#NULL!", "#VALUE!", "NaN", "nan",
    ]
    n = len(missing_representations)
    df = pd.DataFrame({
        "id": list(range(1, n + 1)),
        "value": missing_representations,
        "notes": [
            "Python None", "numpy NaN", "empty string", "single space",
            "double space", "N/A uppercase", "n/a lowercase", "NA no slash",
            "na lowercase no slash", "NULL uppercase", "null lowercase",
            "Null mixed case", "None string", "none lowercase", "NONE uppercase",
            "single dash", "double dash", "triple dash", "single dot",
            "double dot", "triple dot", "single question mark", "double question mark",
            "triple question mark", "TBD", "TBA",
            "Excel #N/A", "Excel #NULL!", "Excel #VALUE!", "NaN string", "nan string",
        ],
    })
    meta = _meta(
        name="missing_value_zoo",
        description="Every known representation of missing/null data in one column",
        category="missing_data",
        tags=["null", "missing", "sentinel_values", "NaN"],
        affected_columns=["value"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "30 different missing value representations",
            "Python None vs numpy NaN vs string 'None'",
            "Empty string vs whitespace-only strings",
            "Excel error codes as strings",
            "Placeholder strings (TBD, TBA)",
            "Punctuation as missing indicators (-, ., ?)",
            "Case variations of null/none/na",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 6. NUMERIC STRINGS WITH FORMATTING
# ---------------------------------------------------------------------------

def formatted_numbers():
    df = pd.DataFrame({
        "id": list(range(1, 21)),
        "price": [
            "1234.56",
            "$1,234.56",            # USD with comma
            "1.234,56",             # European (period=thousands, comma=decimal)
            "€1.234,56",            # Euro with European formatting
            "£1,234.56",            # GBP
            "¥123456",              # JPY (no decimals)
            "1 234,56",             # French spacing
            "1'234.56",             # Swiss apostrophe
            "(1,234.56)",           # accounting negative
            "-$1,234.56",           # negative with currency
            "1234.56 USD",          # currency suffix
            "$1,234.56-",           # trailing negative
            "1.23456e3",            # scientific notation
            "1,23,456.78",          # Indian numbering
            "12.34%",               # percentage
            "1/4",                  # fraction
            "~1200",                # approximate
            "> 1000",               # comparison
            "1000+",                # plus suffix
            "$  1,234.56",          # extra spaces after currency
        ],
        "locale_hint": [
            "plain", "US", "DE/FR", "DE/FR", "UK", "JP",
            "FR", "CH", "US_accounting", "US", "US_suffix",
            "US_trailing_neg", "scientific", "IN", "percent",
            "fraction", "approximate", "comparison", "plus", "US_padded",
        ],
    })
    meta = _meta(
        name="formatted_numbers",
        description="Numeric values with every kind of formatting from different locales",
        category="numeric_formats",
        tags=["numbers", "currency", "locale", "formatting"],
        affected_columns=["price"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Currency symbols ($ € £ ¥) mixed in",
            "Thousands separators: comma, period, space, apostrophe",
            "Decimal separators: period vs comma (locale-dependent)",
            "Accounting-style negatives with parentheses",
            "Trailing negative sign",
            "Scientific notation",
            "Indian numbering system (1,23,456)",
            "Percentage as string",
            "Fraction as string",
            "Approximate/comparison operators in value",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 7. WHITESPACE AND INVISIBLE CHARACTERS
# ---------------------------------------------------------------------------

def whitespace_chaos():
    df = pd.DataFrame({
        "id": list(range(1, 16)),
        "name": [
            "Alice",                        # clean
            " Alice",                       # leading space
            "Alice ",                       # trailing space
            "  Alice  ",                    # both
            "Ali\tce",                      # tab in middle
            "Alice\nJohnson",               # newline in middle
            "Alice\r\nJohnson",             # CRLF
            "Alice\xa0Johnson",             # non-breaking space (0xA0)
            "Alice\u200bJohnson",           # zero-width space
            "Alice\u200dJohnson",           # zero-width joiner
            "Alice\ufeffJohnson",           # BOM character
            "Alice​Johnson",               # zero-width space (HTML entity embedded)
            "\t\tAlice\t\t",               # surrounded by tabs
            "Alice     Johnson",            # multiple spaces
            "Alice\x0bJohnson",            # vertical tab
        ],
        "description": [
            "clean",
            "leading space",
            "trailing space",
            "leading and trailing spaces",
            "tab in middle",
            "newline in middle",
            "CRLF in middle",
            "non-breaking space U+00A0",
            "zero-width space U+200B",
            "zero-width joiner U+200D",
            "BOM character U+FEFF",
            "zero-width space (copy-paste artifact)",
            "surrounded by tabs",
            "multiple consecutive spaces",
            "vertical tab",
        ],
    })
    meta = _meta(
        name="whitespace_chaos",
        description="Strings contaminated with various invisible and whitespace characters",
        category="encoding_whitespace",
        tags=["whitespace", "invisible_chars", "unicode", "encoding"],
        affected_columns=["name"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Leading/trailing whitespace",
            "Tab characters inside strings",
            "Newline/CRLF inside single field values",
            "Non-breaking space (looks like space, isn't)",
            "Zero-width characters (completely invisible)",
            "BOM character inside string",
            "Multiple consecutive spaces",
            "Vertical tab",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 8. ENCODING / MOJIBAKE
# ---------------------------------------------------------------------------

def mojibake():
    df = pd.DataFrame({
        "id": list(range(1, 16)),
        "city": [
            "New York",                    # clean ASCII
            "São Paulo",                   # correct UTF-8
            "SÃ£o Paulo",                  # mojibake: UTF-8 read as latin-1
            "München",                     # correct
            "MÃ¼nchen",                   # mojibake
            "Zürich",                      # correct
            "ZÃ¼rich",                    # mojibake
            "Québec",                      # correct
            "QuÃ©bec",                    # mojibake
            "Kraków",                      # correct
            "KrakÃ³w",                    # mojibake
            "Ã\x89douard",               # severe mojibake of Édouard
            "CafÃ©",                      # common mojibake of Café
            "naÃ¯ve",                     # mojibake of naïve
            "rÃ©sumÃ©",                  # double mojibake of résumé
        ],
        "expected_clean": [
            "New York", "São Paulo", "São Paulo", "München", "München",
            "Zürich", "Zürich", "Québec", "Québec", "Kraków", "Kraków",
            "Édouard", "Café", "naïve", "résumé",
        ],
    })
    meta = _meta(
        name="mojibake",
        description="UTF-8 text that was read with wrong encoding, producing mojibake artifacts",
        category="encoding_whitespace",
        tags=["encoding", "mojibake", "utf8", "latin1", "unicode"],
        affected_columns=["city"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "UTF-8 bytes interpreted as Latin-1 producing Ã sequences",
            "Mixed clean and corrupted entries for same cities",
            "Double-byte mojibake (Ã© instead of é)",
            "Some entries correct, some corrupted",
        ],
        notes="Classic symptom: UTF-8 file opened as Latin-1/Windows-1252. "
              "Fix: re-encode corrupted strings from latin-1 back to UTF-8.",
    )
    return df, meta


# ---------------------------------------------------------------------------
# 9. EMAIL IN NAME FIELD / NAME IN EMAIL FIELD
# ---------------------------------------------------------------------------

def field_swap_name_email():
    df = pd.DataFrame({
        "name": [
            "Alice Johnson",
            "alice.johnson@example.com",       # email in name field
            "Bob Smith",
            "ROBERT SMITH III ESQ.",            # over-formatted
            "carol@bigcorp.net",               # email in name field
            "Dan",                              # first name only
            "Ms. Eve Martinez-García PhD",     # tons of titles/suffixes
            "",                                 # blank
            "frank_wilson_2024",                # username, not real name
            "Grace Kim (Marketing)",            # department appended
            "hank.brown",                       # looks like email local part
            "Ivy Chen 陈",                     # mixed scripts
            "jake@",                            # partial email
            "123-45-6789",                      # SSN in name field!
            "O'Brien, Kathleen",               # last, first with apostrophe
        ],
        "email": [
            "alice.johnson@example.com",
            "alice.johnson@example.com",
            "bob.smith@example.com",
            "robert.smith@example.com",
            "carol@bigcorp.net",
            "dan@example.com",
            "eve.martinez@example.com",
            "unknown@example.com",
            "frank.wilson@example.com",
            "grace.kim@example.com",
            "hank.brown@example.com",
            "ivy.chen@example.com",
            "jake.taylor@example.com",
            "unknown2@example.com",
            "kathleen.obrien@example.com",
        ],
    })
    meta = _meta(
        name="field_swap_name_email",
        description="Name field contaminated with emails, usernames, SSNs, and formatting artifacts",
        category="field_contamination",
        tags=["PII", "email", "name", "wrong_field", "SSN"],
        affected_columns=["name"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Full email address in name field",
            "Username (not real name) in name field",
            "SSN in name field (critical PII leak)",
            "Over-formatted names with titles/suffixes",
            "Department info appended to name",
            "Mixed character scripts",
            "Last, First format mixed with First Last",
            "Empty/blank name",
            "Partial email fragments",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 10. ADDRESS FIELD CHAOS
# ---------------------------------------------------------------------------

def address_field_chaos():
    df = pd.DataFrame({
        "full_address": [
            "123 Main St, Springfield, IL 62704",          # correct
            "Springfield",                                   # city only
            "62704",                                         # zip only
            "IL",                                            # state only
            "123 Main St",                                   # street only
            "123 Main St, Springfield, IL 62704, USA",      # with country
            "PO Box 456, Springfield, IL 62704",            # PO box
            "Apt 2B, 789 Oak Ave, Portland, OR 97201",     # apartment
            "N/A",                                           # missing
            "123 Main St\nSpringfield, IL 62704",           # multiline
            "same as above",                                 # reference to prev
            "1234567890",                                    # phone number??
            "austin tx",                                     # no punctuation, no zip
            "   456 Elm St,   Austin,   TX   78701   ",    # excessive whitespace
            "google.com",                                    # URL in address field
        ],
        "city": [
            "Springfield", "Springfield", "", "", "",
            "Springfield", "Springfield", "Portland", "", "Springfield",
            "", "", "austin", "Austin", "",
        ],
        "state": [
            "IL", "IL", "", "IL", "",
            "IL", "IL", "OR", "", "IL",
            "", "", "tx", "TX", "",
        ],
        "zip": [
            "62704", "", "62704", "", "",
            "62704", "62704", "97201", "", "62704",
            "", "", "", "78701", "",
        ],
    })
    meta = _meta(
        name="address_field_chaos",
        description="Address data split inconsistently across fields, with partial and corrupted entries",
        category="field_contamination",
        tags=["address", "partial_data", "wrong_field", "geocoding"],
        affected_columns=["full_address", "city", "state", "zip"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Partial address (only city, only zip, only state)",
            "Phone number in address field",
            "URL in address field",
            "Reference text ('same as above')",
            "Multiline address in single field",
            "Inconsistent casing and punctuation",
            "Excessive whitespace",
            "Duplicate data across full_address and split fields",
            "PO Box addresses",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 11. BOOLEAN COLUMN CHAOS
# ---------------------------------------------------------------------------

def boolean_chaos():
    n = 30
    bool_representations = [
        True, False, 1, 0, "1", "0",
        "true", "false", "True", "False", "TRUE", "FALSE",
        "yes", "no", "Yes", "No", "YES", "NO",
        "Y", "N", "y", "n",
        "T", "F", "t", "f",
        "on", "off", "ON", "OFF",
    ]
    df = pd.DataFrame({
        "id": list(range(1, n + 1)),
        "is_active": bool_representations,
        "description": [
            "Python True", "Python False", "int 1", "int 0",
            "string '1'", "string '0'",
            "string 'true'", "string 'false'", "string 'True'", "string 'False'",
            "string 'TRUE'", "string 'FALSE'",
            "string 'yes'", "string 'no'", "string 'Yes'", "string 'No'",
            "string 'YES'", "string 'NO'",
            "string 'Y'", "string 'N'", "string 'y'", "string 'n'",
            "string 'T'", "string 'F'", "string 't'", "string 'f'",
            "string 'on'", "string 'off'", "string 'ON'", "string 'OFF'",
        ],
    })
    meta = _meta(
        name="boolean_chaos",
        description="A single boolean column expressed 30 different ways",
        category="categorical_inconsistency",
        tags=["boolean", "mixed_types", "inconsistent_coding"],
        affected_columns=["is_active"],
        row_count=len(df),
        difficulty="easy",
        expected_issues=[
            "Python bool vs int vs string representations",
            "Case variations (true/True/TRUE)",
            "yes/no vs true/false vs 1/0 vs Y/N vs on/off",
            "Single-character abbreviations",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 12. CATEGORICAL INCONSISTENCY (same value, many spellings)
# ---------------------------------------------------------------------------

def categorical_inconsistency():
    df = pd.DataFrame({
        "id": list(range(1, 31)),
        "country": [
            "United States", "US", "USA", "U.S.", "U.S.A.",
            "united states", "UNITED STATES", "United States of America",
            "US ", " US", "  United States  ",  # whitespace
            "Unied States",                      # typo
            "Untied States",                     # typo
            "United Sates",                      # typo
            "U S A",                             # spaces instead of dots
            "Germany", "DE", "DEU", "germany", "Deutschland",
            "Japan", "JP", "JPN", "japan", "日本",
            "United Kingdom", "UK", "GB", "GBR", "England",  # England != UK
        ],
        "expected_normalized": [
            "US"] * 15 + ["DE"] * 5 + ["JP"] * 5 + ["GB"] * 5,
    })
    meta = _meta(
        name="categorical_inconsistency",
        description="Country names expressed in dozens of different ways, with typos and abbreviations",
        category="categorical_inconsistency",
        tags=["categorical", "normalization", "typos", "abbreviations", "i18n"],
        affected_columns=["country"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Full name vs 2-letter vs 3-letter ISO codes",
            "Case variations",
            "Leading/trailing whitespace",
            "Common typos (Unied, Untied, Sates)",
            "Native language names (Deutschland, 日本)",
            "Semantic ambiguity (England vs United Kingdom)",
            "Dots vs no dots in abbreviations",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 13. EXCEL ARTIFACTS
# ---------------------------------------------------------------------------

def excel_artifacts():
    df = pd.DataFrame({
        "id": list(range(1, 21)),
        "value": [
            "42",                          # normal
            "#REF!",                       # broken reference
            "#N/A",                        # not available
            "#VALUE!",                     # wrong value type
            "#DIV/0!",                     # division by zero
            "#NAME?",                      # unrecognized formula name
            "#NULL!",                      # incorrect range
            "#NUM!",                       # invalid numeric value
            "=SUM(A1:A10)",                # un-evaluated formula
            "=VLOOKUP(B2,Sheet2!A:B,2,0)",# complex formula leaked
            "1.23457E+12",                 # Excel scientific display
            "12345678901",                 # long number (might lose precision)
            "00042",                       # leading zeros stripped then re-added
            "1/1/1900",                    # Excel epoch date
            "TRUE",                        # Excel boolean
            "01234",                       # zip code that lost leading zero
            "4.16666666666667E-02",        # 1/24 as float
            "General",                     # format name leaked into data
            "###",                         # column too narrow display artifact
            "$1,234.56",                   # formatted number
        ],
        "source_cell": [
            "A1", "B2", "C3", "D4", "E5", "F6", "G7", "H8",
            "I9", "J10", "K11", "L12", "M13", "N14", "O15",
            "P16", "Q17", "R18", "S19", "T20",
        ],
    })
    meta = _meta(
        name="excel_artifacts",
        description="Data exported from Excel containing formula errors, leaked formulas, and format artifacts",
        category="source_artifacts",
        tags=["excel", "formulas", "errors", "formatting"],
        affected_columns=["value"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Excel error codes (#REF!, #N/A, #VALUE!, #DIV/0!, #NAME?, #NULL!, #NUM!)",
            "Raw formulas leaked into data (=SUM, =VLOOKUP)",
            "Scientific notation from Excel display",
            "Long numbers that may have lost precision",
            "Leading zeros stripped (zip codes)",
            "Excel epoch date (1/1/1900)",
            "Format name 'General' leaked into data",
            "### display artifact (column too narrow)",
            "Formatted numbers with $ and commas",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 14. MIXED UNITS
# ---------------------------------------------------------------------------

def mixed_units():
    df = pd.DataFrame({
        "item": [f"Item_{i}" for i in range(1, 21)],
        "weight": [
            "5.2 kg", "11.5 lbs", "5200 g", "5.2", "11.5",
            "5,200g", "5.2 KG", "5.2kg", "11.5 lb", "11.5 pounds",
            "184 oz", "0.0052 tonnes", "5200000 mg",
            "5.2 kilograms", "11 lbs 8 oz",     # compound unit
            "about 5 kg", "5-6 kg",              # range
            "< 10 kg", "> 5 kg",                 # comparison
            "5.2 kg (approx)",                   # with qualifier
        ],
        "height": [
            "180 cm", "5'11\"", "5 ft 11 in", "1.80 m", "180",
            "71 inches", "71 in", "71in", "5'11", "5 foot 11",
            "1800 mm", "0.0018 km", "180cm", "5.917 ft", "71\"",
            "180 CM", "5 ft 11 inches", "five eleven", "~180 cm", "180 cm (barefoot)",
        ],
    })
    meta = _meta(
        name="mixed_units",
        description="Measurements with inconsistent units, formats, and qualifiers",
        category="unit_inconsistency",
        tags=["units", "measurement", "conversion", "formatting"],
        affected_columns=["weight", "height"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Mixed metric and imperial units",
            "Units sometimes attached, sometimes separated",
            "Case variations (kg, KG, Kg)",
            "Abbreviated vs full unit names",
            "Compound units (5 ft 11 in, 11 lbs 8 oz)",
            "Range values (5-6 kg)",
            "Comparison operators (< 10 kg)",
            "Qualifiers (approx, barefoot)",
            "No unit specified (bare numbers)",
            "Spelled-out numbers (five eleven)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 15. COPY-PASTE HTML / MARKDOWN ARTIFACTS
# ---------------------------------------------------------------------------

def copy_paste_artifacts():
    df = pd.DataFrame({
        "id": list(range(1, 16)),
        "description": [
            "Normal description",
            "<b>Bold description</b>",                     # HTML
            "Description with <br/> line break",           # HTML br
            "Click <a href='http://example.com'>here</a>",# HTML link
            "&amp; &lt; &gt; &quot;",                     # HTML entities
            "**Bold** and *italic*",                       # Markdown
            "- bullet point\n- another bullet",            # Markdown list
            "Description\t\twith\t\ttabs",                 # TSV artifact
            '"Quoted description"',                        # spurious quotes
            '""Double quoted""',                           # escaped CSV quotes
            "Description, with, commas, everywhere",       # CSV parsing issue
            'He said "hello, world" to everyone',         # quotes + comma
            "Line 1\x00Line 2",                           # null byte
            "Description\x1b[31m with ANSI codes\x1b[0m",# terminal escape codes
            "=cmd|'/C calc'!A0",                          # CSV injection attempt
        ],
        "category": [
            "clean", "html", "html", "html", "html_entities",
            "markdown", "markdown", "tsv_artifact", "csv_artifact",
            "csv_artifact", "csv_artifact", "csv_artifact",
            "null_byte", "ansi_escape", "csv_injection",
        ],
    })
    meta = _meta(
        name="copy_paste_artifacts",
        description="Text fields with HTML tags, markdown, CSV artifacts, and injection attempts",
        category="source_artifacts",
        tags=["html", "markdown", "csv", "injection", "encoding"],
        affected_columns=["description"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "HTML tags in plain text fields",
            "HTML entities (&amp;, &lt;)",
            "Markdown formatting in plain text",
            "Tab characters from TSV copy-paste",
            "Spurious or doubled CSV quote escaping",
            "Commas that confuse CSV parsers",
            "Null bytes in strings",
            "ANSI terminal escape codes",
            "CSV injection / formula injection attempts",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 16. DUPLICATE VARIATIONS
# ---------------------------------------------------------------------------

def near_duplicates():
    df = pd.DataFrame({
        "customer_id": [
            101, 102, 103, 101, 102,
            104, 105, 103, 106, 107,
            101, 108, 109, 105, 110,
        ],
        "name": [
            "John Smith",
            "Jane Doe",
            "Robert Johnson",
            "John Smith",             # exact dupe (same id)
            "Jane M. Doe",            # middle initial added (same id)
            "Michael Brown",
            "Sarah Wilson",
            "Rob Johnson",            # nickname (same id as Robert)
            "David Lee",
            "Emily Davis",
            "JOHN SMITH",             # case variation (same id)
            "James Taylor",
            "Lisa Anderson",
            "Sara Wilson",            # typo: Sara vs Sarah (same id)
            "Chris Martinez",
        ],
        "email": [
            "john.smith@gmail.com",
            "jane.doe@yahoo.com",
            "rob.johnson@hotmail.com",
            "jsmith@gmail.com",           # different email, same person
            "jane.doe@yahoo.com",         # same email
            "mbrown@outlook.com",
            "sarah.wilson@gmail.com",
            "rob.johnson@hotmail.com",    # same email, diff name format
            "dlee@company.com",
            "emily.d@company.com",
            "john.smith@gmail.com",       # same email
            "jtaylor@company.com",
            "lisa.a@company.com",
            "sarah.wilson@gmail.com",     # same email as Sarah (typo Sara)
            "chris.m@company.com",
        ],
        "phone": [
            "555-0101", "555-0102", "555-0103", "(555) 010-1", "555-0102",
            "555-0104", "555-0105", "5550103", "555-0106", "555-0107",
            "555.0101", "555-0108", "555-0109", "555-0105", "555-0110",
        ],
    })
    meta = _meta(
        name="near_duplicates",
        description="Records that are duplicates or near-duplicates with variations in formatting, nicknames, and typos",
        category="duplicates",
        tags=["deduplication", "fuzzy_matching", "entity_resolution"],
        affected_columns=["customer_id", "name", "email", "phone"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Exact duplicate records",
            "Same person with different email addresses",
            "Name variations: full name vs nickname (Robert/Rob)",
            "Name with added middle initial",
            "Case variations (John Smith / JOHN SMITH)",
            "Typo in name (Sarah/Sara)",
            "Phone number formatting differences for same number",
            "Same customer_id appearing with different data",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 17. NUMERIC PRECISION / FLOATING POINT ISSUES
# ---------------------------------------------------------------------------

def floating_point_issues():
    df = pd.DataFrame({
        "id": list(range(1, 21)),
        "amount": [
            0.1 + 0.2,                     # 0.30000000000000004
            1/3,                            # 0.333333...
            math.pi,                        # many decimals
            1e-15,                          # very small
            1e15,                           # very large
            float('inf'),                   # infinity
            float('-inf'),                  # negative infinity
            float('nan'),                   # NaN
            -0.0,                           # negative zero
            999999999999999.0,              # at precision limit
            0.1 + 0.1 + 0.1,              # 0.30000000000000004 again
            2.2204460492503131e-16,         # machine epsilon
            9007199254740992.0,             # 2^53 (max safe integer as float)
            9007199254740993.0,             # 2^53 + 1 (loses precision!)
            1.7976931348623157e+308,        # near max float
            5e-324,                         # near min positive float
            42.0,                           # clean
            100.00,                         # trailing zeros
            -0.001,                         # small negative
            12345.6789012345678,            # precision beyond float64
        ],
        "description": [
            "0.1 + 0.2 != 0.3",
            "1/3 repeating decimal",
            "pi",
            "very small positive",
            "very large",
            "positive infinity",
            "negative infinity",
            "NaN",
            "negative zero",
            "at float64 precision limit",
            "0.1 + 0.1 + 0.1",
            "machine epsilon",
            "2^53 max safe integer",
            "2^53 + 1 precision loss",
            "near max float64",
            "near min positive float64",
            "clean value",
            "trailing zeros",
            "small negative",
            "excess precision (truncated by float64)",
        ],
    })
    meta = _meta(
        name="floating_point_issues",
        description="Numeric column with floating point edge cases: precision, infinity, NaN, epsilon",
        category="numeric_edge_cases",
        tags=["float", "precision", "NaN", "infinity", "ieee754"],
        affected_columns=["amount"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Classic 0.1 + 0.2 != 0.3",
            "Infinity and negative infinity",
            "NaN (not equal to itself)",
            "Negative zero (-0.0 == 0.0 but different bits)",
            "Precision loss at 2^53 boundary",
            "Machine epsilon values",
            "Very large/small values near float64 limits",
            "Repeating decimal representation",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 18. MIXED SCHEMAS / JAGGED DATA
# ---------------------------------------------------------------------------

def jagged_schema():
    """Simulates data from merged CSVs with different schemas."""
    df = pd.DataFrame({
        "name": [
            "Alice", "Bob", "Carol", "Dan", "Eve",
            "Frank", "Grace", "Hank", "Ivy", "Jake",
        ],
        "age": [30, 25, "unknown", 45, 28, None, 35, "N/A", 22, 41],
        "salary": [
            50000, 60000, 55000, None, 48000,
            "confidential", 72000, 65000, "entry_level", 58000,
        ],
        "department": [
            "Engineering", "Sales", "Engineering", "HR", "Marketing",
            None, "Sales", "Engineering", "", "HR",
        ],
        "start_date": [
            "2020-01-15", "2019-06-01", "2021-03-10", "2015-11-20", "2022-08-05",
            "2018-04-12", "2023-01-30", "2017-07-25", None, "hired in 2020",
        ],
        "extra_col_from_2023_export": [
            None, None, None, None, None,
            "team_lead", "senior", "principal", "junior", "manager",
        ],
        "Unnamed: 6": [None] * 10,  # pandas artifact from CSV with trailing comma
    })
    meta = _meta(
        name="jagged_schema",
        description="Data merged from multiple CSV exports with different schemas and conventions",
        category="schema_issues",
        tags=["schema", "merged_data", "mixed_types", "missing"],
        affected_columns=["age", "salary", "department", "start_date",
                         "extra_col_from_2023_export", "Unnamed: 6"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "String values in numeric columns (age='unknown', salary='confidential')",
            "Column only populated for half the rows (schema change over time)",
            "Unnamed column from trailing CSV comma",
            "Free text in date field ('hired in 2020')",
            "Mixed None and empty string for missing values",
            "Qualitative values in quantitative columns ('entry_level' for salary)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 19. CROSS-FIELD INCONSISTENCIES
# ---------------------------------------------------------------------------

def cross_field_inconsistencies():
    df = pd.DataFrame({
        "birth_date": [
            "1990-06-15", "2005-03-22", "1985-11-30", "2010-01-10",
            "1975-08-05", "1999-12-25", "2001-07-04", "1960-04-20",
            "1995-09-15", "2015-02-28",
        ],
        "age": [
            34,     # correct (for 2024)
            19,     # correct
            25,     # wrong! should be ~39
            14,     # correct
            49,     # correct
            -5,     # negative age!
            23,     # correct
            150,    # impossibly old for birth_date
            29,     # correct
            5,      # wrong! should be ~9
        ],
        "state": [
            "IL", "CA", "NY", "TX", "FL",
            "IL", "CA", "NY", "TX", "ZZ",  # ZZ is not a state
        ],
        "zip": [
            "62704", "90210", "10001", "75001", "33101",
            "90210", "62704", "10001", "75001", "00000",  # row 5: CA zip with IL state
                                                           # row 6: IL zip with CA state
        ],
        "order_date": [
            "2024-03-15", "2024-03-16", "2024-03-17", "2024-03-14",
            "2024-03-18", "2024-03-19", "2024-03-20", "2024-03-21",
            "2024-03-22", "2024-03-23",
        ],
        "ship_date": [
            "2024-03-17", "2024-03-18", "2024-03-16", "2024-03-16",
            "2024-03-20", "2024-03-15", "2024-03-22", "2024-03-23",
            "2024-03-21", "2024-03-25",
        ],
        # Row 2: ship_date before order_date
        # Row 5: ship_date before order_date
        # Row 8: ship_date before order_date (close, but 21 < 22? no 23 > 22 ok)
    })
    meta = _meta(
        name="cross_field_inconsistencies",
        description="Records where fields contradict each other (age vs birth_date, state vs zip, order vs ship)",
        category="cross_field",
        tags=["validation", "consistency", "business_rules", "contradictions"],
        affected_columns=["age", "birth_date", "state", "zip", "order_date", "ship_date"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Age doesn't match birth_date (off by years)",
            "Negative age",
            "Impossibly high age for given birth_date",
            "State doesn't match zip code (CA zip with IL state)",
            "Invalid state code (ZZ)",
            "Invalid zip code (00000)",
            "Ship date before order date",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 20. MIXED NUMERIC SCALES (thousands vs units vs percentages)
# ---------------------------------------------------------------------------

def mixed_numeric_scales():
    df = pd.DataFrame({
        "metric": [
            "revenue", "revenue", "revenue",
            "conversion_rate", "conversion_rate", "conversion_rate",
            "users", "users", "users",
            "latency_ms", "latency_ms", "latency_ms",
            "disk_usage", "disk_usage", "disk_usage",
        ],
        "value": [
            1200000,       # dollars
            1200,          # thousands of dollars (K)
            1.2,           # millions of dollars (M)
            0.034,         # as decimal (3.4%)
            3.4,           # as percentage
            34,            # as basis points? or wrong?
            50000,         # actual count
            50,            # in thousands
            0.05,          # in millions
            150,           # milliseconds
            0.15,          # seconds
            150000,        # microseconds
            85,            # percentage
            0.85,          # decimal fraction
            850,           # GB? MB? unclear
        ],
        "source": [
            "team_A", "team_B", "team_C",
            "team_A", "team_B", "team_C",
            "team_A", "team_B", "team_C",
            "team_A", "team_B", "team_C",
            "team_A", "team_B", "team_C",
        ],
    })
    meta = _meta(
        name="mixed_numeric_scales",
        description="Same metrics reported at different scales by different teams (units vs K vs M, decimal vs percent)",
        category="unit_inconsistency",
        tags=["scale", "units", "aggregation_error", "reporting"],
        affected_columns=["value"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Revenue: dollars vs thousands vs millions",
            "Conversion rate: decimal (0.034) vs percentage (3.4) vs basis points (34)",
            "User counts: actual vs thousands vs millions",
            "Latency: milliseconds vs seconds vs microseconds",
            "Disk usage: percentage vs decimal fraction vs absolute (unclear unit)",
            "No unit column — must infer from magnitude + metric name",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 21. TIMEZONE CHAOS
# ---------------------------------------------------------------------------

def timezone_chaos():
    df = pd.DataFrame({
        "event": [f"Event_{i}" for i in range(1, 16)],
        "timestamp": [
            "2024-03-15 10:30:00",                # naive (no timezone)
            "2024-03-15 10:30:00 UTC",             # UTC suffix
            "2024-03-15 10:30:00Z",                # Z suffix
            "2024-03-15 10:30:00+00:00",           # explicit UTC offset
            "2024-03-15 10:30:00-05:00",           # EST
            "2024-03-15 10:30:00-08:00",           # PST
            "2024-03-15 10:30:00 EST",             # ambiguous abbreviation
            "2024-03-15 10:30:00 CST",             # CST = Central US or China?
            "2024-03-15 10:30:00 IST",             # IST = India or Israel or Ireland?
            "2024-03-15T10:30:00.000Z",            # ISO 8601 with millis
            "2024-03-15T10:30:00.000000+05:30",    # ISO with microseconds, India
            "1710499800",                           # Unix timestamp
            "1710499800000",                        # Unix milliseconds
            "2024-03-15 10:30 AM ET",              # 12-hour with ambiguous timezone
            "Mar 15, 2024 10:30:00 GMT+0530",      # GMT offset format
        ],
    })
    meta = _meta(
        name="timezone_chaos",
        description="Timestamps with mixed timezone representations, ambiguous abbreviations, and naive datetimes",
        category="date_chaos",
        tags=["timezone", "datetime", "ambiguous", "UTC"],
        affected_columns=["timestamp"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Naive datetime (no timezone info)",
            "Multiple timezone representation formats",
            "Ambiguous abbreviations (CST, IST have multiple meanings)",
            "Unix timestamp in seconds vs milliseconds",
            "12-hour clock with ambiguous timezone abbreviation",
            "Mixed precision (seconds, millis, microseconds)",
            "Z vs +00:00 vs UTC for same timezone",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 22. COLUMN NAME CHAOS
# ---------------------------------------------------------------------------

def column_name_chaos():
    df = pd.DataFrame({
        "First Name": ["Alice", "Bob", "Carol"],
        "first_name": ["Alice", "Bob", "Carol"],           # duplicate semantics
        "firstName": ["Alice", "Bob", "Carol"],             # camelCase dupe
        "FIRST_NAME": ["Alice", "Bob", "Carol"],            # UPPER dupe
        " Last Name ": ["Johnson", "Smith", "Davis"],       # spaces in name
        "Unnamed: 5": [None, None, None],                   # pandas artifact
        "": ["x", "y", "z"],                                # empty column name
        "col with\nnewline": [1, 2, 3],                     # newline in col name
        "amount ($)": [100, 200, 300],                      # special chars
        "created_at (UTC)": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "field.with.dots": ["a", "b", "c"],                 # dots (JSON path confusion)
        "__dunder__": [True, False, True],                   # Python dunder-ish
    })
    meta = _meta(
        name="column_name_chaos",
        description="DataFrame with problematic column names: duplicates, special chars, spaces, empty names",
        category="schema_issues",
        tags=["column_names", "schema", "normalization"],
        affected_columns=list(df.columns),
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Semantically duplicate columns (First Name, first_name, firstName, FIRST_NAME)",
            "Leading/trailing spaces in column names",
            "Empty column name",
            "Newline in column name",
            "Special characters ($, parentheses) in column names",
            "Unnamed: N artifact from pandas CSV reading",
            "Dots in column names (conflicts with JSON paths, SQL)",
            "Python dunder-style name",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 23. SURVEY RESPONSE FREETEXT IN STRUCTURED FIELDS
# ---------------------------------------------------------------------------

def survey_freetext_in_structured():
    df = pd.DataFrame({
        "respondent_id": list(range(1, 16)),
        "age": [
            "25", "thirty-two", "18-24", "25-34", "42",
            "prefer not to say", "old enough", "21+", "29.5", "about 40",
            "born in 1990", "Gen Z", "millennial", "65+", "¯\\_(ツ)_/¯",
        ],
        "income": [
            "50000", "$50,000-$75,000", "50K", "low", "six figures",
            "prefer not to say", "enough", "100000+", "50k-75k", "~60000",
            "per year or per month?", "0 (student)", "negative (debt)", "75,000", "N/A",
        ],
        "satisfaction": [
            "5", "very satisfied", "4/5", "80%", "8 out of 10",
            "meh", "could be better", "10", "★★★★☆", "B+",
            "above average", "3.5", "4 (but only because...)", "not applicable", "😊",
        ],
        "would_recommend": [
            "yes", "Yes", "no", "maybe", "probably",
            "depends", "not sure", "1", "absolutely", "nah",
            "yes, but with caveats", "YES!!!", "ask me later", "true", "👍",
        ],
    })
    meta = _meta(
        name="survey_freetext_in_structured",
        description="Survey responses where freetext answers ended up in structured/numeric fields",
        category="mixed_types",
        tags=["survey", "freetext", "numeric", "categorical", "human_input"],
        affected_columns=["age", "income", "satisfaction", "would_recommend"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Spelled-out numbers (thirty-two)",
            "Age ranges instead of values (18-24, 25-34)",
            "Generational labels instead of age (Gen Z, millennial)",
            "Emoji and unicode art in responses",
            "Income as ranges, relative terms, or ambiguous units",
            "Satisfaction on different scales (1-5, 1-10, percentage, letter grade, stars)",
            "Yes/no with qualifiers and enthusiasm markers",
            "Reflexive/meta-answers (per year or per month?, ask me later)",
            "Refusals (prefer not to say)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 24. LOG-LIKE DATA MIXED INTO TABULAR FORMAT
# ---------------------------------------------------------------------------

def log_data_in_table():
    df = pd.DataFrame({
        "timestamp": [
            "2024-03-15 10:30:00.123",
            "2024-03-15 10:30:00.456",
            "2024-03-15 10:30:00.789",
            "2024-03-15 10:30:01.012",
            "2024-03-15 10:30:01.345",
            "2024-03-15 10:30:01.678 [WARN] Connection timeout after 30s",  # log line leaked
            "2024-03-15 10:30:02.901",
            "--- server restart ---",                   # operational note
            "2024-03-15 10:31:15.000",
            "2024-03-15 10:31:15.000",                  # exact duplicate timestamp
            "2024-03-15 10:31:15.001",
            "NULL",
            "2024-03-15 10:31:16.500",
            "2024-03-15 08:31:17.000",                  # went backwards! (timezone switch?)
            "2024-03-15 10:31:18.000",
        ],
        "level": [
            "INFO", "INFO", "DEBUG", "INFO", "ERROR",
            "WARN", "INFO", None, "INFO", "INFO",
            "DEBUG", None, "CRITICAL", "INFO", "INFO",
        ],
        "message": [
            "Request received",
            "Processing started",
            "Cache miss for key=abc123",
            "Processing completed in 45ms",
            "NullPointerException at com.example.Service.process(Service.java:42)",
            "Connection pool exhausted",
            "Request received",
            None,
            "Request received",
            "Request received",     # duplicate
            "Memory usage: 85%",
            None,
            "DISK FULL - /dev/sda1 at 100%",
            "Request from 192.168.1.100",  # IP address in log
            "Response sent: 200 OK",
        ],
    })
    meta = _meta(
        name="log_data_in_table",
        description="Server log data crudely converted to tabular format with operational notes and artifacts",
        category="source_artifacts",
        tags=["logs", "time_series", "operational", "unstructured"],
        affected_columns=["timestamp", "level", "message"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Log line leaked into timestamp field",
            "Operational notes as data rows (--- server restart ---)",
            "Timestamps going backwards (timezone or clock issue)",
            "Exact duplicate timestamps",
            "NULL string instead of null value",
            "Stack traces in message field",
            "IP addresses in log messages (PII)",
            "Mixed granularity (milliseconds)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 25. FINANCIAL DATA EDGE CASES
# ---------------------------------------------------------------------------

def financial_data_edge_cases():
    df = pd.DataFrame({
        "transaction_id": [f"TXN-{i:04d}" for i in range(1, 21)],
        "amount": [
            100.00,
            -50.00,           # refund
            0.00,             # zero
            0.001,            # sub-cent
            1e-10,            # rounding artifact
            99999999.99,      # near overflow
            100.005,          # rounds to .00 or .01?
            float('nan'),     # missing
            -0.00,            # negative zero
            100.1 + 100.2,    # float imprecision: 200.30000000000001
            1/3 * 3,          # should be 1.0, might not be
            2.675,            # infamous rounding case: round(2.675, 2) = 2.67 not 2.68
            10.00,
            10.00,
            10.00,            # duplicate transactions
            -100.00,          # large refund
            0.10,
            0.20,
            0.30,             # 0.1 + 0.2 situation
            1000000.01,       # large with cents
        ],
        "currency": [
            "USD", "USD", "USD", "USD", "USD",
            "USD", "USD", "USD", "USD", "USD",
            "USD", "USD", "JPY", "EUR", "GBP",
            "USD", "BTC", "ETH", "USD", "KWD",  # BTC/ETH have 8/18 decimals, KWD has 3
        ],
        "description": [
            "Purchase", "Refund", "Zero amount", "Sub-cent precision",
            "Rounding artifact", "Large transaction", "Banker's rounding edge case",
            "Missing amount", "Negative zero", "Float addition imprecision",
            "1/3 * 3 roundtrip", "Round half-even edge", "JPY no decimals",
            "EUR transaction", "GBP transaction",
            "Large refund", "Bitcoin (8 decimal places)",
            "Ethereum (18 decimal places)", "0.1 + 0.2 issue",
            "KWD (3 decimal places)",
        ],
    })
    meta = _meta(
        name="financial_data_edge_cases",
        description="Financial transactions with precision issues, mixed currencies, and edge cases",
        category="numeric_edge_cases",
        tags=["financial", "precision", "currency", "rounding"],
        affected_columns=["amount", "currency"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Sub-cent amounts and rounding artifacts",
            "Floating point imprecision in financial calculations",
            "Banker's rounding edge case (2.675)",
            "Negative zero amount",
            "NaN as missing transaction amount",
            "Mixed currencies with different decimal conventions (JPY=0, KWD=3, BTC=8)",
            "Duplicate transactions (potential double-charge)",
            "Very large amounts near float precision limits",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 26. MULTILINE / EMBEDDED STRUCTURED DATA IN CELLS
# ---------------------------------------------------------------------------

def structured_data_in_cells():
    df = pd.DataFrame({
        "id": list(range(1, 11)),
        "config": [
            '{"host": "localhost", "port": 8080}',          # JSON
            "host=localhost\nport=8080",                      # key=value config
            "<config><host>localhost</host></config>",        # XML
            "host: localhost\nport: 8080",                    # YAML
            "localhost:8080",                                  # compact
            "{'host': 'localhost', 'port': 8080}",           # Python dict repr (not JSON!)
            "host,port\nlocalhost,8080",                      # CSV inside cell
            "host\tlocalhost\nport\t8080",                   # TSV inside cell
            "config = {\n  host: 'localhost',\n  port: 8080\n}", # JS object
            "None",                                            # string None
        ],
        "tags": [
            "web,api,production",                 # comma-separated
            "web;api;production",                  # semicolon-separated
            "web|api|production",                  # pipe-separated
            '["web", "api", "production"]',        # JSON array
            "web api production",                  # space-separated
            "web, api, production",                # comma-space
            "#web #api #production",               # hashtag-style
            "web/api/production",                  # slash-separated
            "",                                    # empty
            "web",                                 # single value
        ],
    })
    meta = _meta(
        name="structured_data_in_cells",
        description="Cells containing embedded structured data (JSON, XML, CSV, config files)",
        category="schema_issues",
        tags=["nested_data", "json", "xml", "denormalization"],
        affected_columns=["config", "tags"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "JSON objects as string values",
            "Python dict repr (single quotes, not valid JSON)",
            "XML fragments in cells",
            "YAML/config file content in cells",
            "CSV/TSV data inside cells",
            "Multiple list delimiter conventions",
            "Hashtag-style tags",
            "String 'None' instead of null",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 27. DATA TRUNCATION / OVERFLOW
# ---------------------------------------------------------------------------

def truncation_and_overflow():
    df = pd.DataFrame({
        "id": list(range(1, 16)),
        "name": [
            "Alice",
            "Bob",
            "A very long name that was clearly trunca",     # truncated at 40 chars
            "María García de la Cruz Hernández Lop...",     # truncated with ellipsis
            "Carol",
            "Description that goes on and on and on and on and on and it keeps going and going",  # too long for name
            "Dan",
            "Eve",
            "Fra",                                           # truncated at 3 chars
            "Grace Kim (née Park) formerly of the long-named department of...", # truncated
            "Hank",
            "Ivy C",                                         # truncated mid-word
            "NULL",                                          # string NULL
            "Jake Taylor; Sarah Wilson; Bob Smith",          # multiple values jammed in
            "K",                                             # single char
        ],
        "description": [
            "Normal description",
            "Short",
            "This description was exported from a system with a 255 character limit and it goes on for quite a while providing lots of detail about the item in question including specifications measurements and other relevant attributes that someone thought would b",  # exactly 255 chars
            "Another long one that ends abrup",
            "OK",
            "",
            "N/A",
            "See attachment",                                # reference to external data
            "TBD - pending review from stakeholder meeting scheduled for next quarter",
            "...",                                           # just ellipsis
            "REDACTED",                                      # redacted
            "[FILTERED]",                                    # filtered
            "Lorem ipsum dolor sit amet",                    # placeholder text!
            "test",                                          # test data leaked to prod
            "asdfghjkl",                                     # keyboard smash
        ],
    })
    meta = _meta(
        name="truncation_and_overflow",
        description="Text fields truncated at various lengths, with overflow and placeholder artifacts",
        category="source_artifacts",
        tags=["truncation", "overflow", "placeholders", "data_quality"],
        affected_columns=["name", "description"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Truncation at fixed character limits (40, 255)",
            "Truncation with ellipsis vs without",
            "Multiple values crammed into single field",
            "Placeholder/test data (Lorem ipsum, asdfghjkl, test)",
            "References to external data (See attachment)",
            "Redacted/filtered markers",
            "Just ellipsis as entire value",
            "String NULL/N/A",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 28. MIXED ID FORMATS
# ---------------------------------------------------------------------------

def mixed_id_formats():
    df = pd.DataFrame({
        "user_id": [
            "12345",                           # plain numeric
            "USR-12345",                       # prefixed
            "usr_12345",                       # underscore prefix
            "12345.0",                         # float-ified by Excel/pandas
            " 12345",                          # leading space
            "012345",                          # leading zero
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",  # UUID
            "12345678-1234-1234-1234-123456789012",   # another UUID
            "user@example.com",                # email as ID
            "12345\n",                         # trailing newline
            "1.2345E+04",                      # scientific notation (was 12345)
            "#12345",                          # with hash prefix
            "12,345",                          # comma in ID
            "12345 ",                          # trailing space
            "LEGACY-00012345",                 # legacy system ID
        ],
        "order_id": [
            1001, 1002, 1003, 1004, 1005,
            1006, 1007, 1008, 1009, 1010,
            1011, 1012, 1013, 1014, 1015,
        ],
    })
    meta = _meta(
        name="mixed_id_formats",
        description="Identifier column with wildly inconsistent formats from system migrations",
        category="schema_issues",
        tags=["identifiers", "migration", "normalization", "UUID"],
        affected_columns=["user_id"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Plain number vs prefixed IDs",
            "Float-ified IDs (12345.0 from Excel)",
            "Scientific notation (1.2345E+04)",
            "UUID mixed with numeric IDs",
            "Email used as ID",
            "Leading zeros (may be significant)",
            "Whitespace contamination",
            "Hash prefix, comma in ID",
            "Legacy system prefix",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 29. SEASONAL / CYCLIC PATTERN BREAKS
# ---------------------------------------------------------------------------

def timeseries_anomalies():
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=365, freq="D")
    # Base pattern: seasonal sine wave + trend + noise
    base = 1000 + 200 * np.sin(np.arange(365) * 2 * np.pi / 365) + np.arange(365) * 0.5
    noise = np.random.normal(0, 20, 365)
    values = base + noise

    # Inject anomalies
    values[30] = 5000        # spike
    values[31] = 5000        # sustained spike (not just one-off)
    values[60] = -500        # negative (impossible for this metric?)
    values[90] = 0           # exact zero (suspicious)
    values[120] = np.nan     # missing
    values[150:157] = np.nan # missing week
    values[180] = values[179]# exact duplicate of previous day
    values[181] = values[179]# and again
    values[182] = values[179]# flat-line (sensor stuck?)
    values[200:210] = 999999 # system max value (capped/saturated)
    values[250] = -values[250]  # sign flip
    values[300] = values[300] * 100  # off by factor of 100 (unit error?)
    values[340:345] = 0      # holiday shutdown but entered as 0 not null

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "daily_sales": values,
    })
    meta = _meta(
        name="timeseries_anomalies",
        description="Daily time series with injected anomalies: spikes, flat-lines, missing data, unit errors",
        category="timeseries",
        tags=["time_series", "anomaly_detection", "outliers", "seasonality"],
        affected_columns=["daily_sales"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Sudden spikes (day 30-31: 5x normal)",
            "Negative value in non-negative metric (day 60)",
            "Exact zero (suspicious, day 90)",
            "Single missing day and missing week",
            "Flat-line / stuck sensor (days 180-182)",
            "Saturated at system max (days 200-210: 999999)",
            "Sign flip (day 250)",
            "Off by factor of 100 (day 300, likely unit error)",
            "Zeros during holiday (days 340-344, should be null?)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 30. MEDICAL / SCIENTIFIC DATA ENTRY ERRORS
# ---------------------------------------------------------------------------

def medical_data_entry():
    df = pd.DataFrame({
        "patient_id": [f"PT-{i:03d}" for i in range(1, 21)],
        "blood_pressure": [
            "120/80", "130/85", "12080", "120 / 80", "120-80",
            "120\\80", "systolic: 120, diastolic: 80", "80/120",  # reversed!
            "120", "80", "N/A", "normal", "high",
            "120/80 mmHg", "120/80/60",   # extra value (MAP?)
            "12/8",        # European shorthand (x10)
            "120/80 (sitting)", "120/80 (L arm)", "pending", "",
        ],
        "temperature": [
            "98.6", "37.0", "98.6 F", "37.0 C", "99",
            "100.4°F", "38°C", "986",    # missing decimal
            "37", "98.6°", "afebrile", "normal", "WNL",
            "37.0 celsius", "98.6 fahrenheit", "36.5-37.5",  # range
            "oral: 98.6", "tympanic: 99.1", "pending", "",
        ],
        "weight_kg": [
            70.0, 65.5, 154.0,    # 154 lbs, not kg!
            80.2, 0.075,           # 75g, missing x1000 — or 75kg missing decimal?
            "unknown", 90.1, 72.3,
            -5.0,                  # negative weight
            70.0, 70.0, 70.0, 70.0,  # suspiciously unchanged across visits
            9999, 55.0, 68.7,
            "72.3 kg", "159 lbs", "~80", "obese",  # qualitative
        ],
    })
    meta = _meta(
        name="medical_data_entry",
        description="Clinical data with entry errors: reversed BP, mixed F/C, lbs in kg column, qualitative values",
        category="domain_specific",
        tags=["medical", "clinical", "units", "data_entry", "patient_safety"],
        affected_columns=["blood_pressure", "temperature", "weight_kg"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Blood pressure: various delimiter formats (/, -, space, backslash)",
            "Reversed systolic/diastolic (80/120)",
            "BP as single number, qualitative, or with extra values",
            "European BP shorthand (12/8 means 120/80)",
            "Temperature: mixed Fahrenheit and Celsius",
            "Missing decimal in temperature (986 vs 98.6)",
            "Qualitative terms (afebrile, normal, WNL)",
            "Weight in lbs stored in kg column",
            "Negative weight, suspiciously static weight across visits",
            "Sentinel value 9999",
            "Units embedded in value string",
        ],
        notes="Errors in medical data can be life-threatening. "
              "A weight of 154 in a kg column likely means lbs — "
              "dosing medications at 154kg instead of 70kg is dangerous.",
    )
    return df, meta


# ---------------------------------------------------------------------------
# 31. GEOGRAPHIC COORDINATE ERRORS
# ---------------------------------------------------------------------------

def geocoordinate_errors():
    df = pd.DataFrame({
        "location_name": [
            "New York", "London", "Tokyo", "Sydney", "São Paulo",
            "Invalid 1", "Invalid 2", "Invalid 3", "Swapped",
            "Null Island", "North Pole", "Date Line",
            "Precision", "Truncated", "String coords",
        ],
        "latitude": [
            40.7128, 51.5074, 35.6762, -33.8688, -23.5505,
            91.0,              # > 90 (impossible)
            -91.0,             # < -90 (impossible)
            0.0,               # suspiciously exactly zero
            -73.9857,          # swapped with longitude!
            0.0,               # Null Island (0,0) — often a geocoding failure
            90.0,              # North Pole (valid but suspicious)
            35.6762,           # normal
            40.712800000001,   # excess precision
            40.7,              # truncated
            "40.7128° N",      # string with degree symbol
        ],
        "longitude": [
            -73.9857, -0.1278, 139.6503, 151.2093, -46.6333,
            -73.9857, -0.1278, 0.0,
            40.7128,            # swapped with latitude!
            0.0,                # Null Island
            0.0,                # North Pole
            180.0,              # Date line (valid but edge case)
            139.65030000000001, # excess precision
            139.7,              # truncated
            "139.6503° E",      # string with degree symbol
        ],
    })
    meta = _meta(
        name="geocoordinate_errors",
        description="Geographic coordinates with swapped lat/lon, impossible values, and Null Island artifacts",
        category="domain_specific",
        tags=["geospatial", "coordinates", "validation", "geocoding"],
        affected_columns=["latitude", "longitude"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Latitude outside valid range (-90 to 90)",
            "Swapped latitude and longitude",
            "Null Island (0,0) — common geocoding failure",
            "Exact zero coordinates (suspicious)",
            "Excess floating point precision",
            "Truncated coordinates (low precision)",
            "String coordinates with degree symbols",
            "Boundary values (poles, date line)",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 32. MULTILINGUAL / SCRIPT MIXING
# ---------------------------------------------------------------------------

def multilingual_mixing():
    df = pd.DataFrame({
        "id": list(range(1, 16)),
        "product_name": [
            "Widget Pro",                          # ASCII
            "Widget Pro™",                         # trademark symbol
            "Ŵîdget Prö",                        # accented lookalikes
            "Ｗｉｄｇｅｔ　Ｐｒｏ",               # fullwidth characters
            "Widget\u200bPro",                     # zero-width space
            "WIDGET PRO",                          # all caps
            "widget pro",                          # all lower
            "Ꮃidget Ꮲro",                        # Cherokee lookalikes for W and P
            "Wіdget Рro",                         # Cyrillic і and Р (homoglyphs!)
            "Widget Pro",                          # en-space instead of regular space
            "Widget​Pro",                          # zero-width space (again, different code point)
            "WidgetPro",                           # no space
            "Widget-Pro",                          # hyphenated
            "Widget_Pro",                          # underscored
            "Widget  Pro",                         # double space
        ],
        "description": [
            "Standard widget",
            "With TM symbol",
            "Accented characters",
            "Fullwidth Unicode (CJK keyboards)",
            "Zero-width space inserted",
            "Uppercased",
            "Lowercased",
            "Cherokee homoglyphs (visually identical, different codepoints)",
            "Cyrillic homoglyphs (visually identical, different codepoints)",
            "En-space instead of space",
            "Different zero-width space",
            "Missing space",
            "Hyphen separator",
            "Underscore separator",
            "Double space",
        ],
    })
    meta = _meta(
        name="multilingual_mixing",
        description="Product names using homoglyphs, fullwidth chars, and invisible Unicode — visually identical but different bytes",
        category="encoding_whitespace",
        tags=["unicode", "homoglyphs", "deduplication", "security"],
        affected_columns=["product_name"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Cyrillic/Cherokee homoglyphs (looks like ASCII but isn't)",
            "Fullwidth characters (common from CJK input methods)",
            "Zero-width spaces (invisible separators)",
            "En-space vs regular space",
            "Trademark/special symbols",
            "Accented lookalike characters",
            "All these may look identical in a UI but fail equality checks",
        ],
        notes="Homoglyph attacks are a real security concern. "
              "Cyrillic 'а' (U+0430) looks like Latin 'a' (U+0061) but is a different character.",
    )
    return df, meta


# ---------------------------------------------------------------------------
# 33. DATA FROM OCR / PDF EXTRACTION
# ---------------------------------------------------------------------------

def ocr_artifacts():
    df = pd.DataFrame({
        "invoice_no": [
            "INV-2024-001", "INV-2O24-OO2",          # O vs 0
            "INV-2024-003", "lNV-2024-004",            # l vs I
            "INV-2024-005", "INV—2024—006",            # em-dash vs hyphen
            "INV-2024-007", "INV-ZOZ4-008",            # Z vs 2
            "INV-2024-009", "INV-2024-O1O",            # O vs 0
        ],
        "amount": [
            "1,234.56", "l,234.56",      # l vs 1
            "1,234.56", "I,234.56",      # I vs 1
            "5,678.90", "5,67B.9O",      # B vs 8, O vs 0
            "9,012.34", "9,O12.34",      # O vs 0
            "3,456.78", "3.456,78",      # European format from OCR confusion
        ],
        "date": [
            "2024-01-15", "2O24-O1-15",   # O vs 0
            "2024-02-20", "2024-0Z-20",    # Z vs 2
            "2024-03-10", "2024-03-1O",    # O vs 0
            "2024-04-05", "2024-04-O5",    # O vs 0
            "2024-05-25", "ZOZ4-O5-Z5",   # extensive O/0 and Z/2 confusion
        ],
        "is_ocr_artifact": [
            False, True, False, True, False,
            True, False, True, False, True,
        ],
    })
    meta = _meta(
        name="ocr_artifacts",
        description="Data from OCR/PDF extraction with character confusion: O/0, l/1/I, Z/2, B/8",
        category="source_artifacts",
        tags=["OCR", "PDF", "character_confusion", "scanning"],
        affected_columns=["invoice_no", "amount", "date"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "O (letter) vs 0 (zero) confusion",
            "l (lowercase L) vs 1 (one) vs I (uppercase i)",
            "Z vs 2 confusion",
            "B vs 8 confusion",
            "Em-dash vs hyphen from PDF extraction",
            "European number format confusion (3.456,78 vs 3,456.78)",
        ],
        notes="OCR errors are systematic — the same document will have "
              "consistent O/0 confusion throughout. Character-level "
              "confidence scores from OCR engines can help identify these.",
    )
    return df, meta


# ---------------------------------------------------------------------------
# 34. SLOWLY CHANGING DIMENSIONS / TEMPORAL OVERLAP
# ---------------------------------------------------------------------------

def temporal_overlap():
    df = pd.DataFrame({
        "employee_id": [
            101, 101, 101,
            102, 102,
            103, 103, 103,
            104,
            105, 105,
        ],
        "department": [
            "Engineering", "Sales", "Engineering",
            "Marketing", "Marketing",
            "HR", "Engineering", "HR",
            "Sales",
            "Engineering", "Engineering",
        ],
        "start_date": [
            "2020-01-01", "2021-06-01", "2023-01-01",
            "2019-03-15", "2022-01-01",
            "2018-07-01", "2020-04-01", "2022-09-01",
            "2021-11-01",
            "2020-01-01", "2020-06-01",  # overlapping!
        ],
        "end_date": [
            "2021-05-31", "2022-12-31", None,          # None = current
            "2022-06-30", None,
            "2020-03-31", "2022-08-31", None,
            None,
            "2021-12-31", None,                         # overlap: two active records
        ],
        "salary": [
            80000, 85000, 95000,
            70000, 75000,
            65000, 72000, 78000,
            68000,
            82000, 88000,
        ],
    })
    meta = _meta(
        name="temporal_overlap",
        description="Employee history with overlapping date ranges, gaps, and multiple active records",
        category="cross_field",
        tags=["temporal", "SCD", "overlap", "history", "deduplication"],
        affected_columns=["start_date", "end_date"],
        row_count=len(df),
        difficulty="hard",
        expected_issues=[
            "Overlapping date ranges for same employee (emp 105)",
            "None/null end_date meaning 'current' (multiple active records)",
            "Employee bouncing back to previous department (emp 101, 103)",
            "Potential gap between end_date and next start_date",
            "Multiple open-ended records for same employee",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# 35. LARGE INTEGERS THAT LOSE PRECISION
# ---------------------------------------------------------------------------

def large_integer_precision():
    df = pd.DataFrame({
        "id": list(range(1, 11)),
        "big_id": [
            9007199254740992,       # 2^53 — max safe integer in JS
            9007199254740993,       # 2^53 + 1 — LOSES PRECISION in JS/JSON
            9007199254740994,
            18446744073709551615,   # uint64 max
            9999999999999999,       # 16 digits
            10000000000000001,      # 17 digits — float64 can't distinguish from 10000000000000000
            123456789012345678,     # 18 digits
            "9007199254740993",     # same value but as string (safe!)
            1,                      # normal
            0,                      # zero
        ],
        "description": [
            "2^53 (max safe JS integer)",
            "2^53 + 1 (precision lost in float64/JSON)",
            "2^53 + 2",
            "uint64 max (18446744073709551615)",
            "16-digit integer",
            "17-digit, indistinguishable from 10000000000000000 in float64",
            "18-digit integer",
            "Same as row 2 but stored as string",
            "Normal small integer",
            "Zero",
        ],
    })
    meta = _meta(
        name="large_integer_precision",
        description="Large integers that lose precision when converted to float64 or serialized through JSON",
        category="numeric_edge_cases",
        tags=["precision", "int64", "float64", "JSON", "JavaScript"],
        affected_columns=["big_id"],
        row_count=len(df),
        difficulty="medium",
        expected_issues=[
            "Integers beyond 2^53 lose precision in float64",
            "JSON serialization silently rounds large integers",
            "JavaScript Number type can't represent these exactly",
            "uint64 max value",
            "Mixed string and integer representations of same ID",
            "Parquet preserves int64 but downstream consumers may not",
        ],
    )
    return df, meta


# ---------------------------------------------------------------------------
# REGISTRY: all test case generators
# ---------------------------------------------------------------------------

ALL_GENERATORS = [
    phone_in_address,
    mixed_date_formats,
    impossible_dates,
    mostly_int_with_strings,
    missing_value_zoo,
    formatted_numbers,
    whitespace_chaos,
    mojibake,
    field_swap_name_email,
    address_field_chaos,
    boolean_chaos,
    categorical_inconsistency,
    excel_artifacts,
    mixed_units,
    copy_paste_artifacts,
    near_duplicates,
    floating_point_issues,
    jagged_schema,
    cross_field_inconsistencies,
    mixed_numeric_scales,
    timezone_chaos,
    column_name_chaos,
    survey_freetext_in_structured,
    log_data_in_table,
    financial_data_edge_cases,
    structured_data_in_cells,
    truncation_and_overflow,
    mixed_id_formats,
    timeseries_anomalies,
    medical_data_entry,
    geocoordinate_errors,
    multilingual_mixing,
    ocr_artifacts,
    temporal_overlap,
    large_integer_precision,
]


def generate_all(output_dir: str = "tests/data_cleaning/testcases"):
    """Generate all test case parquet files with sidecar metadata JSON."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = []

    for gen_fn in ALL_GENERATORS:
        name = gen_fn.__name__
        df, meta = gen_fn()

        parquet_path = out / f"{name}.parquet"
        meta_path = out / f"{name}.meta.json"

        # Write parquet — use pyarrow to handle mixed types gracefully
        # Convert all object columns to string to avoid serialization issues
        df_out = df.copy()
        for col in df_out.columns:
            if df_out[col].dtype == object:
                df_out[col] = df_out[col].astype(str)

        table = pa.Table.from_pandas(df_out, preserve_index=False)
        pq.write_table(table, str(parquet_path))

        # Write metadata
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        manifest.append({
            "name": name,
            "parquet": str(parquet_path.relative_to(out)),
            "metadata": str(meta_path.relative_to(out)),
            "category": meta["category"],
            "difficulty": meta["difficulty"],
            "tags": meta["tags"],
        })

        print(f"  {name}: {len(df)} rows -> {parquet_path.name}")

    # Write manifest
    manifest_path = out / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nGenerated {len(manifest)} test cases in {out}/")
    print(f"Manifest: {manifest_path}")
    return manifest


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "tests/data_cleaning/testcases"
    generate_all(output)
