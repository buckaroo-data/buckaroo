"""
Data Cleaning Test Case Narratives

Each narrative explains a real-world scenario that produces the messy data,
why it's dangerous, and what a correct cleaning approach looks like.

This module maps test case names to their narrative descriptions.
"""

NARRATIVES = {

# ---------------------------------------------------------------------------
"phone_in_address": """
PHONE NUMBERS IN ADDRESS FIELDS

You just got a CSV export from the CRM. Sales reps were supposed to enter
customer addresses, but the address field was the first big text box on the
form, so some reps pasted phone numbers there instead. Others typed
"Call 555.012.3456 for directions" as the address. One rep entered a
1-800 vanity number as the shipping address.

This is endemic in CRM data. The address field is free-text, and humans
under time pressure will dump whatever contact info they have into whatever
field is handy. The fix needs to detect phone-number patterns (with all
their format variants: parentheses, dashes, dots, spaces, international
+1 prefix, vanity letters) and either move them to the phone column or
flag them for review. A simple regex won't cut it — you need to handle
"123 Main St\\n(503) 555-0198" where a valid address has a phone number
appended to it.
""",

# ---------------------------------------------------------------------------
"mixed_date_formats": """
MIXED DATE FORMATS

Your data pipeline ingests CSVs from 12 regional offices. The US office
writes "01/15/2024". The German office writes "15.01.2024". The UK office
writes "15/01/2024". Someone in Japan sent "20240115". The legacy system
exported Excel serial dates (45307). The API log has Unix timestamps as
strings. One intern typed "January 15th, 2024" and another wrote "Q1 2024".

The core danger: is "01/02/2024" January 2nd or February 1st? Without
knowing the source locale, it's genuinely ambiguous. Dates where day <= 12
are impossible to parse without context. The cleaning approach must:
(1) detect the format used, (2) handle true ambiguity by flagging rather
than guessing, (3) convert Unix timestamps and Excel serial numbers,
(4) decide what to do with "Q1 2024" and "Week 3, 2024" which aren't
actual dates.
""",

# ---------------------------------------------------------------------------
"impossible_dates": """
IMPOSSIBLE AND SUSPICIOUS DATES

The birth_date column looks fine at a glance, but buried in 10,000 rows
are dates that can't exist: February 30th, month 13, hour 25. There's
someone born in 2030 (future date), someone born in 1899 (possibly valid,
probably a typo), and the classic "0000-00-00" null sentinel from MySQL.
February 29, 1900 looks like a valid leap day but isn't — 1900 is NOT a
leap year (Excel gets this wrong, famously).

These slip through because most date parsers are lenient by default.
`pd.to_datetime("1990-02-30")` will raise an error, but
`pd.to_datetime("1990-02-30", errors="coerce")` silently converts it to
NaT, hiding the problem. The cleaning approach needs strict validation:
check day-of-month against the actual month length (accounting for leap
years), flag future dates, flag dates suspiciously close to epoch
boundaries (1970-01-01, 1900-01-01), and handle null sentinels.
""",

# ---------------------------------------------------------------------------
"mostly_int_with_strings": """
MOSTLY INTEGERS WITH OUTLIER STRINGS

The "quantity" column is 80% clean integers. But someone entered "N/A"
for out-of-stock items. The Excel export leaked "#REF!" from a broken
formula. A data entry person typed "see notes" and "TBD" for pending
orders. There's a "12.5" (float) where only integers should be, and
"1,234" uses comma formatting.

This is the single most common data cleaning problem in the wild. A
column that's *mostly* numeric but has a handful of string values forces
the entire column to object dtype, breaking all numeric operations.
The temptation is `pd.to_numeric(col, errors="coerce")` — but that
silently converts "see notes" to NaN, hiding potentially important data.
The proper approach: categorize the non-numeric values (missing
indicators vs errors vs real data), handle each category appropriately,
and only then cast to numeric.
""",

# ---------------------------------------------------------------------------
"missing_value_zoo": """
EVERY KIND OF MISSING VALUE

You merged data from 8 different source systems. System A uses NULL.
System B uses empty string. System C uses "N/A". System D uses a dash.
System E uses "None" (the string, not Python None). System F uses "??"
for unknown. System G uses "TBD" for pending. System H uses "#N/A"
because it came from Excel.

This dataset has 31 different representations of "this data is missing,"
and they all need to be recognized and normalized. The tricky part:
some of these might be valid data in context. A "-" might mean "not
applicable" (which is different from "unknown"). "TBD" might mean
"this will be filled in later" (which you might want to preserve as a
distinct state). And there's a difference between empty string (field
was there but empty) and None/null (field wasn't captured). Cleaning
requires domain knowledge about which "missing" values are truly
equivalent.
""",

# ---------------------------------------------------------------------------
"formatted_numbers": """
NUMERIC STRINGS WITH LOCALE-SPECIFIC FORMATTING

Your international team reported Q4 numbers. The US team wrote "$1,234.56".
The German team wrote "1.234,56" (period for thousands, comma for decimal).
The French team wrote "1 234,56" (space for thousands). The Swiss team
wrote "1'234.56" (apostrophe for thousands). The accountant used "(1,234.56)"
for negative numbers. Someone copied "1,23,456.78" from an Indian-formatted
spreadsheet.

The danger: naively removing commas and parsing will turn the German
"1.234,56" (one thousand two hundred thirty-four and 56 cents) into
"1.23456" (one point two three). The decimal separator is locale-dependent,
and getting it wrong silently corrupts values by 1000x. Fractions ("1/4"),
approximations ("~1200"), and comparison operators ("> 1000") are valid
in source but need special handling for numeric processing.
""",

# ---------------------------------------------------------------------------
"whitespace_chaos": """
WHITESPACE AND INVISIBLE CHARACTERS

Copy-paste from a web page brought in non-breaking spaces (U+00A0) that
look like regular spaces but aren't. An export from a rich-text system
embedded zero-width spaces (U+200B) that are completely invisible. Someone
pasted from a terminal and brought in ANSI escape sequences. There are
tabs inside names, newlines inside single fields, and a BOM character
hiding at the start of one entry.

This is insidious because it's invisible. `"Alice" != "Alice"` when
one of them has a zero-width space after the 'e'. String comparisons,
deduplication, and joins will silently fail. `.strip()` only removes
standard whitespace — it won't catch non-breaking spaces, zero-width
characters, or BOM. You need Unicode-aware normalization: strip all
Unicode whitespace categories, remove zero-width characters, normalize
to NFC form.
""",

# ---------------------------------------------------------------------------
"mojibake": """
ENCODING MOJIBAKE

Someone opened a UTF-8 CSV file in Excel on a European Windows machine,
which defaulted to Latin-1 (ISO-8859-1) encoding. Every multi-byte UTF-8
character got mangled: "São Paulo" became "SÃ£o Paulo", "München" became
"MÃ¼nchen", "Café" became "CafÃ©". The dataset is a mix of corrupted
and correct entries, because some records were entered after the encoding
was fixed.

The systematic pattern: every UTF-8 sequence gets interpreted byte-by-byte
as Latin-1. The fix is to detect mojibake patterns (Ã followed by another
character is the smoking gun) and re-encode: take the corrupted string,
encode it as Latin-1 (to get back the original bytes), then decode as
UTF-8. But you must be careful not to double-fix strings that are already
correct. The `ftfy` library handles this well, but understanding the
mechanism matters for edge cases.
""",

# ---------------------------------------------------------------------------
"field_swap_name_email": """
NAME FIELD CONTAMINATION

The "name" field is supposed to contain a person's name. Instead you'll
find: email addresses (someone pasted their email into the name field),
a Social Security Number (critical PII leak!), usernames that aren't
real names, department info appended in parentheses, names in
"Last, First" format mixed with "First Last", and an empty string.

The SSN-in-name-field case is the scariest. If this data gets exported
to a report or shared externally, you've just leaked PII. The cleaning
approach must: (1) detect and quarantine PII patterns (SSN, email, phone),
(2) separate prefix/suffix titles from the actual name, (3) handle
multiple name formats, (4) flag entries that aren't names at all. This
is a case where detection is more important than correction — it's
better to flag "123-45-6789" for human review than to silently drop it.
""",

# ---------------------------------------------------------------------------
"address_field_chaos": """
ADDRESS FIELD CHAOS

The "full_address" field contains everything from complete valid addresses
to just a zip code, just a state abbreviation, a phone number, a URL,
the text "same as above", and a multiline address crammed into one field.
The split fields (city, state, zip) are sometimes populated and sometimes
empty, with no consistency about which parts exist.

This happens when address data is aggregated from multiple sources with
different schemas. Source A had a single "address" text field. Source B
had structured city/state/zip. The merge just concatenated what was
available. Cleaning requires: address parsing (splitting "123 Main St,
Springfield, IL 62704" into components), validation (does this zip
match this state?), PO Box detection, and handling the truly invalid
entries (phone numbers, URLs, cross-references). Libraries like
`usaddress` help with US addresses but international addresses are much
harder.
""",

# ---------------------------------------------------------------------------
"boolean_chaos": """
BOOLEAN COLUMN WITH 30 REPRESENTATIONS

The "is_active" column should be True or False. Instead it contains:
Python booleans (True/False), integers (1/0), strings in every
conceivable case ("true", "True", "TRUE", "yes", "Yes", "YES"),
single-character codes ("Y", "N", "T", "F"), and toggle words
("on", "off").

This happens when data comes from different systems: a database (1/0),
a Java API ("true"/"false"), a human-entered spreadsheet ("Yes"/"No"),
a legacy COBOL system ("Y"/"N"), and a web form checkbox ("on"/"off").
The fix is straightforward — build a mapping of all truthy/falsy
values — but you must handle it explicitly rather than relying on
Python's truthiness rules, because `bool("false")` is `True` (non-empty
string), and `bool(0)` is `False` but `bool("0")` is `True`.
""",

# ---------------------------------------------------------------------------
"categorical_inconsistency": """
CATEGORICAL DATA WITH INCONSISTENT NAMING

The "country" column should contain standardized country names or codes.
Instead, the same country appears as: "United States", "US", "USA",
"U.S.", "U.S.A.", "united states", "UNITED STATES", "United States of
America", plus typos like "Unied States" and "Untied States". Germany
appears as "Germany", "DE", "DEU", and "Deutschland" (the German name).
Japan is also "日本" (Japanese characters).

There's also a subtle semantic error: "England" is not the same as
"United Kingdom" — England is a constituent country of the UK. Should
they be merged or kept separate? That's a domain decision, not a
technical one.

The fix requires: case normalization, whitespace stripping, fuzzy matching
for typos (Levenshtein distance), a lookup table for abbreviations and
native-language names, and explicit business rules for semantic ambiguity
(England vs UK). ISO 3166 country codes are the standard normalization
target.
""",

# ---------------------------------------------------------------------------
"excel_artifacts": """
EXCEL ARTIFACTS

Someone opened the CSV in Excel, "fixed" a few cells, and saved it.
Now you have: error codes (#REF!, #N/A, #VALUE!, #DIV/0!, #NAME?,
#NULL!, #NUM!) where there should be data, raw formulas (=SUM(A1:A10))
that leaked into the export, scientific notation ("1.23457E+12") from
Excel's display format, "###" from a column that was too narrow, and
a zip code "01234" that lost its leading zero because Excel treated it
as a number.

The leading-zero problem is the worst because it's silent. Zip code
"01234" (Massachusetts) becomes "1234" (not a valid zip) and you only
notice when geocoding fails. The Excel epoch date "1/1/1900" might be
a real date or might be Excel's epoch artifact. And "TRUE" might be an
Excel boolean or might be actual text. The cleaning approach should
recognize all Excel error patterns, detect leaked formulas, and restore
leading zeros where the column semantics require them.
""",

# ---------------------------------------------------------------------------
"mixed_units": """
MIXED UNITS IN MEASUREMENT COLUMNS

The "weight" column contains: "5.2 kg", "11.5 lbs", "5200 g",
"184 oz", "0.0052 tonnes", "11 lbs 8 oz" (compound unit!),
"about 5 kg" (approximate), "5-6 kg" (range), "< 10 kg" (bound),
and bare numbers with no unit at all. The "height" column is equally
chaotic: "180 cm", "5'11\\"", "5 ft 11 in", "1.80 m", "five eleven"
(spelled out!).

Compound units like "11 lbs 8 oz" or "5 ft 11 in" are especially
tricky because they require decomposing and converting two values.
The spelled-out "five eleven" is a common verbal convention for height
that no regex will catch. The cleaning approach: (1) extract the
numeric value and unit separately, (2) convert everything to a standard
unit (kg, cm), (3) handle compound units, (4) flag approximate values
and ranges, (5) decide what to do with bare numbers (assume the most
common unit? flag for review?).
""",

# ---------------------------------------------------------------------------
"copy_paste_artifacts": """
COPY-PASTE AND MARKUP ARTIFACTS

Someone copied descriptions from a web page and got HTML tags:
"<b>Bold description</b>", "&amp; &lt; &gt;". Another copied from a
wiki and brought markdown: "**Bold** and *italic*". There are TSV
tab artifacts, doubled CSV quote escaping ('""Double quoted""'), and
null bytes from a binary file that got concatenated.

The dangerous one: "=cmd|'/C calc'!A0" is a CSV injection / formula
injection attack. If someone opens the cleaned CSV in Excel, this
formula will execute a system command. Any data that might end up in a
spreadsheet must be sanitized against formula injection by prefixing
cells that start with =, +, -, @, or \\t with a single quote.

The cleaning approach: strip HTML tags (use a proper parser, not regex),
decode HTML entities, strip markdown formatting, remove null bytes and
ANSI escape codes, and sanitize against CSV injection.
""",

# ---------------------------------------------------------------------------
"near_duplicates": """
NEAR-DUPLICATE RECORDS

Customer 101 appears three times: "John Smith", "John Smith" (exact
duplicate), and "JOHN SMITH" (case variation). Customer 103 is "Robert
Johnson" and also "Rob Johnson" (nickname). Customer 105 is "Sarah
Wilson" and "Sara Wilson" (typo — missing 'h'). Their phone numbers
match but are formatted differently: "555-0101", "(555) 010-1", "555.0101".

Entity resolution is one of the hardest problems in data cleaning.
Exact-match deduplication catches customer 101's first two records but
misses the CAPS version. Fuzzy matching catches Sara/Sarah but might
also match unrelated similar names. The phone number is the strongest
signal — normalize phone formats first, then use phone + fuzzy name as
a composite key. But what about customers whose data actually changed
between records (different email because they changed providers)?
Deduplication here requires a scoring model, not a simple rule.
""",

# ---------------------------------------------------------------------------
"floating_point_issues": """
FLOATING POINT EDGE CASES

The classic: 0.1 + 0.2 = 0.30000000000000004. But also: float('inf'),
float('nan'), negative zero (-0.0), machine epsilon
(2.2204460492503131e-16), and the max safe integer boundary (2^53) where
integers silently lose precision.

Most of these won't cause errors — they'll cause subtle incorrectness.
Sorting a column with NaN gives unpredictable results (NaN != NaN).
Summing a column with inf gives inf. Comparing with negative zero:
(-0.0 == 0.0) is True but they have different bit patterns. And
9007199254740993 stored as float64 quietly becomes 9007199254740992 —
off by one, undetectable unless you know to look.

The cleaning approach: replace inf with NaN or a sentinel, round
appropriately for the domain (2 decimal places for currency),
use Decimal for financial calculations, and store large integers
as strings or in int64 columns (never float64).
""",

# ---------------------------------------------------------------------------
"jagged_schema": """
JAGGED SCHEMA FROM MERGED EXPORTS

You concatenated employee CSVs from 2020, 2021, and 2023. The 2023
export added a new "role" column that doesn't exist in earlier data.
The 2020 export had a trailing comma that created an "Unnamed: 6"
column full of nulls. The "age" column has "unknown" and "N/A" because
different years handled missing data differently. The "salary" column
has "confidential" and "entry_level" because HR changed the policy on
what to export. One date field says "hired in 2020" instead of an
actual date.

This is what happens when schemas evolve over time and nobody maintains
a migration log. The cleaning approach: (1) drop entirely-null artifact
columns (Unnamed: 6), (2) merge the new column with NaN for old records,
(3) separate the string-contaminated numeric columns into actual values
vs flags/notes, (4) parse what dates you can and flag the rest, (5)
document which source contributed which records so you can trace issues.
""",

# ---------------------------------------------------------------------------
"cross_field_inconsistencies": """
CROSS-FIELD INCONSISTENCIES

Row by row, the data looks fine. But cross-field validation reveals:
someone's age is 25 but their birth_date makes them 39. Another person
has a negative age (-5). An employee with birth_date 1960 has age 150.
The zip code 90210 (Beverly Hills, CA) is paired with state "IL".
Three orders shipped before they were placed (ship_date < order_date).

These pass single-column validation but fail business rule checks.
Age should equal (today - birth_date) within 1 year. State and zip
must match (there are lookup tables for this). Ship date must be >=
order date. The cleaning approach: (1) compute expected age from
birth_date and flag discrepancies > 1 year, (2) validate state-zip
pairs against a reference, (3) flag temporal impossibilities,
(4) decide which field to trust when two conflict (usually the more
specific one — trust birth_date over age, trust zip over state).
""",

# ---------------------------------------------------------------------------
"mixed_numeric_scales": """
MIXED NUMERIC SCALES

Three teams reported Q4 revenue. Team A: 1,200,000 (actual dollars).
Team B: 1,200 (thousands). Team C: 1.2 (millions). The dashboard
shows them side by side. Your total: $1,201,201.20. The real total:
$3,600,000.

This also happens with conversion rates (0.034 vs 3.4% vs 34 basis
points), latency (150ms vs 0.15s vs 150,000μs), and user counts (50,000
actual vs 50K vs 0.05M). Without a units/scale column, you have to
infer from magnitude — and that's only possible if you know the expected
range for each metric.

The fix: add explicit unit/scale metadata to every metric. For cleaning
existing data: group by metric name, look at the magnitude distribution,
identify clusters (a cluster near 1M and a cluster near 1K probably
means thousands vs actual), and normalize. But this requires domain
knowledge — the code can't know that revenue should be in dollars, not
millions.
""",

# ---------------------------------------------------------------------------
"timezone_chaos": """
TIMEZONE CHAOS

Fifteen events that all happened at roughly the same moment, but the
timestamp column is a mess: naive datetimes (no timezone info), "UTC"
suffix, "Z" suffix, "+00:00" offset, "-05:00" (EST), "-08:00" (PST),
Unix seconds, Unix milliseconds, and ambiguous abbreviations.

"CST" is Central Standard Time (US, UTC-6), or China Standard Time
(UTC+8), or Cuba Standard Time (UTC-5). "IST" is India Standard Time,
Israel Standard Time, or Irish Standard Time. These abbreviations are
genuinely ambiguous — the same three letters mean different timezones
depending on the source.

The fix: (1) parse each format variant, (2) convert everything to UTC
with explicit offsets, (3) for ambiguous abbreviations, determine the
source system and hard-code the mapping, (4) for naive datetimes,
document the assumed timezone rather than guessing, (5) distinguish
Unix seconds from milliseconds (seconds are 10 digits, millis are 13
digits for current-era timestamps).
""",

# ---------------------------------------------------------------------------
"column_name_chaos": """
COLUMN NAME CHAOS

You received a DataFrame with these column names: "First Name",
"first_name", "firstName", "FIRST_NAME" — four columns that all mean
the same thing. There's " Last Name " with leading/trailing spaces,
"Unnamed: 5" from a CSV artifact, an empty string as a column name,
and "col with\\nnewline" with an actual newline character in the name.

"field.with.dots" will break in systems that use dots for nested
access (MongoDB, JSON paths, PySpark). "amount ($)" will break in SQL
queries. The four "first name" variants will cause confusion and
silently wrong joins.

The fix: (1) strip whitespace, (2) normalize to a consistent case
convention (snake_case), (3) detect and merge semantic duplicates,
(4) drop artifact columns (Unnamed: N, empty names), (5) replace
special characters, (6) add a column mapping log so downstream code
can still reference old names during migration.
""",

# ---------------------------------------------------------------------------
"survey_freetext_in_structured": """
SURVEY FREETEXT IN STRUCTURED FIELDS

The age field was supposed to be a dropdown. Instead it's a free-text
box, and respondents entered: "thirty-two", "18-24" (a range), "Gen Z",
"old enough", "prefer not to say", "born in 1990", and "¯\\_(ツ)_/¯".
The income field has "$50,000-$75,000", "six figures", "enough",
"per year or per month?", and "negative (debt)". Satisfaction was rated
as "4/5", "80%", "8 out of 10", "★★★★☆", "B+", "meh", and "😊".

This is what happens when survey tools allow free-text where structured
input was intended. The cleaning is mostly lossy — you can extract
the numeric value from "thirty-two" (32) and "4/5" (0.8), convert
ranges to midpoints ("18-24" → 21), and map "yes"/"no" variants for
would_recommend. But "prefer not to say" is a legitimate response that
should be preserved as a category, and "meh" is qualitative data that
loses meaning when forced into a numeric scale. Some of this data
simply can't be cleaned without losing information.
""",

# ---------------------------------------------------------------------------
"log_data_in_table": """
LOG DATA CRUDELY TABULARIZED

Someone ran `grep | awk` on server logs and pasted the result into a
spreadsheet. One timestamp has a log line leaked into it:
"2024-03-15 10:30:01.678 [WARN] Connection timeout after 30s". There's
"--- server restart ---" as an operational note that became a data row.
The "NULL" string appeared where an actual null should be. Timestamps go
backwards at one point (08:31 after 10:31 — probably a timezone switch).

Log data in tabular format is fragile. The cleaning approach: (1) extract
just the timestamp portion from contaminated cells (first 23 characters
if the format is consistent), (2) identify and remove or flag operational
notes (rows where timestamp doesn't parse), (3) convert "NULL" string
to actual null, (4) detect and flag time-going-backwards (clock skew
or timezone change), (5) flag exact duplicate timestamps, (6) redact
IP addresses if the data will be shared.
""",

# ---------------------------------------------------------------------------
"financial_data_edge_cases": """
FINANCIAL DATA PRECISION ISSUES

Transaction amounts that look innocent but hide floating-point traps:
100.1 + 100.2 = 200.30000000000001. The classic round(2.675, 2) returns
2.67, not 2.68 (because 2.675 can't be represented exactly in binary).
There are sub-cent amounts (0.001), negative zero (-0.00), and NaN
for missing transactions.

Mixed currencies add another dimension: USD has 2 decimal places, JPY
has 0 (¥100 means 100, not 1.00), KWD has 3 (Kuwaiti Dinar), and BTC
has 8. Applying 2-decimal rounding to a JPY transaction or an 8-decimal
BTC transaction will silently destroy data.

The fix for financial data: NEVER use float64. Use Decimal (Python)
or integer cents (store $1.23 as 123). Round according to the currency's
minor unit. For existing float data: round immediately on load,
convert to Decimal or integer representation, and validate that NaN
doesn't mean a transaction was lost.
""",

# ---------------------------------------------------------------------------
"structured_data_in_cells": """
STRUCTURED DATA STUFFED INTO CELLS

The "config" column contains: JSON objects, Python dict repr (single
quotes — not valid JSON!), XML fragments, YAML snippets, key=value
pairs, CSV-within-a-cell, and even a JS object literal. The "tags"
column has lists delimited by commas, semicolons, pipes, spaces, slashes,
and hashtag-style (#web #api).

This happens when a relational schema tries to store hierarchical or
list data. Instead of a proper config table with key/value rows or a
tags junction table, someone crammed everything into a text column.

The fix: parse each format (JSON, XML, YAML, key=value), extract into
proper columns or a normalized table. For the Python dict repr, use
`ast.literal_eval` (not `eval`!). For tags, detect the delimiter and
split. Beware: the JSON array '["web", "api"]' is valid JSON, the
Python dict "{'host': 'localhost'}" is not. Test each parser in order
(JSON first, then YAML, then regex for key=value, then fallback).
""",

# ---------------------------------------------------------------------------
"truncation_and_overflow": """
DATA TRUNCATION AND OVERFLOW

Names cut off at exactly 40 characters (a VARCHAR(40) field). A
description cut off at 255 characters (classic VARCHAR(255)). Truncation
with ellipsis ("Hernández Lop...") vs without ("was clearly trunca").
Multiple values crammed into one field because someone hit a column
limit ("Jake Taylor; Sarah Wilson; Bob Smith"). And placeholder data
that leaked into production: "Lorem ipsum dolor sit amet", "test",
"asdfghjkl" (keyboard smash).

The 255-char truncation is the most common — it silently destroys data
during migration between systems with different field limits. The fix:
(1) detect truncation (strings ending at suspiciously round lengths, or
ending with "..." or mid-word), (2) flag truncated records for manual
review or re-extraction from source, (3) detect and remove placeholder
text ("Lorem ipsum", "test", keyboard patterns), (4) detect multi-value
cells and split them, (5) remove sentinel strings ("REDACTED",
"[FILTERED]", "See attachment").
""",

# ---------------------------------------------------------------------------
"mixed_id_formats": """
MIXED IDENTIFIER FORMATS

After three system migrations, the user_id column is a mess: plain
numbers ("12345"), prefixed IDs ("USR-12345"), float-ified numbers
("12345.0" — Excel or pandas auto-conversion), scientific notation
("1.2345E+04" — also Excel), UUIDs, email addresses used as IDs, and
a legacy format with zero-padded numbers ("LEGACY-00012345").

The core question: which IDs refer to the same entity? "12345",
"USR-12345", "12345.0", "1.2345E+04", " 12345", and "012345" might
all be the same user, or they might not. Leading zeros might be
significant (bank account numbers) or might be formatting artifacts.

The fix: (1) strip whitespace and trailing newlines, (2) detect and
reverse scientific notation, (3) strip ".0" suffix from float-ified
ints, (4) decide on a canonical format (with or without prefix),
(5) separate UUID-style IDs from numeric IDs (different ID generation
era), (6) create a mapping table from all variant forms to the
canonical ID.
""",

# ---------------------------------------------------------------------------
"timeseries_anomalies": """
TIME SERIES WITH ANOMALIES

365 days of daily sales with a clear seasonal pattern (sine wave) and
upward trend. Hidden in the data: a sudden 5x spike on days 30-31
(a real event, or a data entry error?), a negative value on day 60
(impossible for sales — probably a sign flip), exact zeros on days
340-344 (holiday shutdown recorded as 0 instead of null), a week of
missing data (days 150-156), a flat-line on days 180-182 (sensor
stuck or system down), and system-max saturation (999,999) on days
200-209.

Day 300 is off by a factor of 100 — a unit error where someone entered
daily sales in cents instead of dollars, or quarterly instead of daily.

The cleaning approach: (1) seasonal decomposition to establish the
expected range, (2) flag values outside 3σ of the seasonal component,
(3) distinguish missing (NaN) from zero (might be legitimate or might
be a missing-value sentinel), (4) detect flat-lines (consecutive
identical values), (5) detect system caps (values at exactly round
numbers like 999999), (6) check for sign flips and scale errors.
""",

# ---------------------------------------------------------------------------
"medical_data_entry": """
MEDICAL DATA ENTRY ERRORS

Blood pressure recorded as: "120/80" (correct), "12080" (missing
delimiter), "80/120" (systolic and diastolic reversed — this means
hyPOtension instead of normal!), "12/8" (European shorthand where you
multiply by 10), "systolic: 120, diastolic: 80" (verbose), "normal"
(qualitative), and "pending" (not yet taken).

Temperature mixes Fahrenheit and Celsius without labels: 98.6 and 37.0
are the same temperature but look very different. "986" is almost
certainly 98.6 with a missing decimal. Weight has 154.0 in a kg column
— that's 154 lbs mislabeled as kg. Dosing a medication for a 154kg
patient instead of a 70kg patient could be fatal.

Medical data errors can kill people. The cleaning approach must be
conservative: (1) parse BP with any delimiter, detect and flag
reversals (systolic < diastolic), (2) infer temperature scale from
magnitude (> 50 = Fahrenheit), (3) detect weight unit errors (values
> 120 in a kg column are likely lbs), (4) NEVER silently coerce —
flag everything for clinical review, (5) preserve original values
alongside cleaned values.
""",

# ---------------------------------------------------------------------------
"geocoordinate_errors": """
GEOGRAPHIC COORDINATE ERRORS

Latitude 91.0 (impossible — valid range is -90 to 90). Latitude and
longitude swapped (New York at lat=-73.9857, lon=40.7128 would be in
Antarctica). Null Island: coordinates (0, 0) which is a point in the
Gulf of Guinea — when geocoding fails, many systems default to 0,0.
String coordinates with degree symbols ("40.7128° N").

The insidious one: excess precision. "40.712800000001" suggests false
precision — GPS is accurate to about 5 decimal places (1 meter), so
15 decimal places is noise. Truncated coordinates ("40.7" — only 1
decimal place, ~11km precision) might be intentionally rounded or
accidentally truncated.

The fix: (1) validate ranges (lat: -90 to 90, lon: -180 to 180),
(2) detect swaps (if |lat| > 90 but |lon| <= 90, they're swapped),
(3) flag (0, 0) coordinates, (4) parse string coordinates with degree
symbols and cardinal directions, (5) round to appropriate precision
(6 decimal places = ~0.1m, sufficient for all purposes),
(6) reverse-geocode to validate that coordinates match expected
locations.
""",

# ---------------------------------------------------------------------------
"multilingual_mixing": """
HOMOGLYPHS AND UNICODE DECEPTION

"Widget Pro" appears 15 times in the product_name column. They all
LOOK identical. They're all different strings. One uses Cyrillic 'і'
(U+0456) and 'Р' (U+0420) instead of Latin 'i' and 'P'. One uses
Cherokee 'Ꮃ' (U+13C3) instead of Latin 'W'. One uses fullwidth
characters 'Ｗｉｄｇｅｔ' from a Japanese keyboard. Several have
zero-width spaces, en-spaces, or other invisible Unicode between
the words.

This is a deduplication nightmare and a security concern. Homoglyph
attacks use visually identical characters from different scripts to
bypass content filters, impersonate brands, or create phishing URLs.
A string equality check says these are 15 different products; a human
sees the same product name 15 times.

The fix: Unicode normalization (NFKC form) collapses fullwidth to
ASCII and decomposes accented characters. Confusable detection (the
Unicode Consortium publishes a confusables.txt mapping) catches
Cyrillic/Cherokee/etc. lookalikes. Strip all characters in categories
Cf (format) and Zs (space separator) except regular space.
""",

# ---------------------------------------------------------------------------
"ocr_artifacts": """
OCR / PDF EXTRACTION CHARACTER CONFUSION

Invoice data extracted by OCR (Optical Character Recognition) from
scanned PDFs. The systematic errors: O (letter O) where 0 (zero)
should be, l (lowercase L) where 1 (one) should be, Z where 2
should be, B where 8 should be. "INV-2O24-OO2" should be
"INV-2024-002". "l,234.56" should be "1,234.56".

The em-dash "—" vs hyphen "-" confusion comes from PDF text
extraction, where the character encoding of dashes is ambiguous.

OCR errors are systematic within a document — if the font confused
O and 0 once, it confused them everywhere. The fix: (1) build a
character substitution map (O→0, l→1, Z→2, B→8 in numeric contexts),
(2) apply substitutions only where the character appears in a
position that should be numeric (don't change "O" in "INVOICE"),
(3) validate the result (does the date parse? does the amount parse?),
(4) normalize dashes (em-dash, en-dash, minus → hyphen).
""",

# ---------------------------------------------------------------------------
"temporal_overlap": """
SLOWLY CHANGING DIMENSIONS WITH OVERLAPS

Employee 101 was in Engineering, moved to Sales, then came back to
Engineering. The history has three records with start/end dates.
Employee 105 has two records where the date ranges overlap: one
ending 2021-12-31 and another starting 2020-06-01. Both have null
end_dates in their current record, meaning two "active" records exist.

This is the Slowly Changing Dimension (SCD) problem from data
warehousing. Type 2 SCDs track history with start/end dates, but
data quality issues create overlaps, gaps, and multiple "current"
records. Employee 102 has two records for Marketing with no department
change — a duplicate from a system migration.

The fix: (1) sort by employee + start_date, (2) detect overlaps
(previous end_date > current start_date), (3) detect gaps (previous
end_date < current start_date - 1 day), (4) enforce single active
record (only one null end_date per employee), (5) detect no-op
changes (same department in consecutive records), (6) decide a
merge strategy for overlaps (which record wins?).
""",

# ---------------------------------------------------------------------------
"large_integer_precision": """
LARGE INTEGERS AND PRECISION LOSS

The big_id column contains integers larger than 2^53
(9,007,199,254,740,992). At this boundary, float64 can no longer
represent consecutive integers. 9007199254740993 stored as float64
silently becomes 9007199254740992. This means two different IDs
map to the same value, causing silent data corruption in joins.

This matters for: Twitter/X snowflake IDs, MongoDB ObjectIds
converted to integers, database bigints, and any system that uses
64-bit integer identifiers. JSON serialization has the same problem:
JSON numbers are IEEE 754 doubles, so `JSON.parse("9007199254740993")`
returns 9007199254740992 in JavaScript.

The fix: (1) store large IDs as strings, not numbers, (2) in parquet,
use int64 (which preserves full precision) but be aware that consumers
(JavaScript, JSON, pandas with default settings) may convert to float,
(3) validate round-trip: write the ID, read it back, compare as
strings to detect precision loss, (4) if you must use numeric types,
use Python's arbitrary-precision integers and avoid numpy/pandas
float64 intermediaries.
""",

# ---------------------------------------------------------------------------
"boolean_chaos": """
(See above — duplicated in alphabetical order in the registry)
""",

}
