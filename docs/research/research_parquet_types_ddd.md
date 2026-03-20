---
name: Parquet types vs DDD serialization research
description: Comprehensive mapping of parquet's native type system, DDD DataFrame column types, and how buckaroo's 3 serialization paths coerce non-parquet types
type: reference
---

# Parquet Type System vs DDD Serialization

## Parquet's Native Type System

Parquet has 7 physical types with logical annotations layered on top:

| Physical Type | Logical Annotations |
|---|---|
| BOOLEAN | — |
| INT32 | INT8, INT16, INT32, UINT8, UINT16, UINT32, DATE, TIME_MILLIS, DECIMAL |
| INT64 | INT64, UINT64, TIMESTAMP_MILLIS/MICROS/NANOS, TIME_MICROS/NANOS, DECIMAL |
| FLOAT | — |
| DOUBLE | — |
| BYTE_ARRAY | STRING (UTF8), ENUM, JSON, BSON, DECIMAL, UUID |
| FIXED_LEN_BYTE_ARRAY | DECIMAL, UUID, FLOAT16, INTERVAL |

### What parquet does NOT have native support for
- **Period** (pandas-specific concept — monthly/quarterly/yearly periods)
- **Interval** (pandas-specific — open/closed range pairs like `(0, 1]`)
- **Categorical** as a logical type (parquet uses dictionary encoding at the physical level, but this is a compression strategy, not a semantic type)
- **Mixed-type columns** (every column must be homogeneous)

### What parquet handles well
- All integer widths (8/16/32/64, signed and unsigned)
- Float/Double
- Boolean
- Strings (UTF-8 byte arrays)
- Timestamps with timezone (TIMESTAMP with isAdjustedToUTC + timezone metadata)
- Date (INT32 days since epoch)
- Time (INT32 millis or INT64 micros/nanos)
- Duration/Timedelta (INT64 with DURATION annotation — added in parquet-format 2.10/parquet-mr, but support varies by library)
- Decimal (fixed-point via INT32/INT64/FIXED_LEN_BYTE_ARRAY)
- Binary (raw BYTE_ARRAY)
- UUID (FIXED_LEN_BYTE_ARRAY, 16 bytes)
- Nested types (LIST, MAP, STRUCT via repeated/group encoding)

---

## DDD DataFrame Column Types

### Pandas Weird Types (`ddd_library.py:df_with_weird_types()`)

| Column | Pandas dtype | Example values |
|---|---|---|
| `categorical` | Categorical | 'red', 'green', 'blue' |
| `timedelta` | timedelta64[ns] | '1 days 02:03:04', '0 days 00:00:01' |
| `period` | PeriodDtype(freq='M') | '2021-01', '2021-02', ... '2021-05' |
| `interval` | IntervalDtype | (0,1], (1,2], ... (4,5] |
| `int_col` | int64 | 10, 20, 30, 40, 50 |

### Polars Weird Types (`ddd_library.py:pl_df_with_weird_types()`)

| Column | Polars dtype | Example values |
|---|---|---|
| `duration` | Duration('us') | 100_000µs, 3_723_000_000µs |
| `time` | Time | 14:30:00, 9:15:30 |
| `categorical` | Categorical | 'red', 'green', 'blue' |
| `decimal` | Decimal(10,2) | 100.50, 200.75, 0.01 |
| `binary` | Binary | b'hello', b'\x00\x01\x02' |
| `int_col` | Int64 | 10, 20, 30, 40, 50 |

### Other DDD DataFrames (structural edge cases, not type edge cases)

- `df_with_infinity()` — NaN, inf, -inf
- `df_with_really_big_number()` — 9999999999999999999 (BigInt territory)
- `get_multiindex_cols_df()` — MultiIndex columns (2 levels)
- `get_multiindex_index_df()` — MultiIndex rows (2 levels)
- `get_multiindex3_index_df()` — 3-level MultiIndex rows
- `df_with_col_named_index()` — column literally named 'index'

---

## Buckaroo's 3 Serialization Paths

### Path 1: Widget Main Data (`pd_to_obj` in `serialization_utils.py`)

**Used by:** anywidget (Jupyter/Marimo), server mode

**Pipeline:**
1. `prepare_df_for_serialization()` — renames columns to a,b,c..., flattens index
2. `_coerce_for_json()` — converts non-JSON-safe types to strings:
   - `PeriodDtype` → `str` (e.g. '2021-01')
   - `IntervalDtype` → `str` (e.g. '(0, 1]')
   - `timedelta64` → `str` (e.g. '1 days 02:03:04')
   - `bytes` in object columns → `hex()` (e.g. '68656c6c6f')
3. `df.to_json(orient='table', default_handler=str)` — pandas JSON serialization

**Output format:** JSON dict with 'data' key

### Path 2: Summary Stats (`sd_to_parquet_b64` in `serialization_utils.py`)

**Used by:** `all_stats` in widget data dict

**Pipeline:**
1. Every cell value is JSON-encoded via `_json_encode_cell()`:
   - `_make_json_safe()` recursively converts non-serializable keys/values
   - `json.dumps(val, default=str)` as final fallback
2. All columns become pure string columns
3. Serialized via **pyarrow** engine (not fastparquet — mixed-type columns break fastparquet)
4. Falls back to JSON if parquet fails

**Output format:** `{'format': 'parquet_b64', 'data': '<base64>'}`

**Key insight:** Types don't matter here since everything becomes a JSON string before touching parquet.

### Path 3: Static Artifact Embedding (`_df_to_parquet_b64_tagged` in `artifact.py`)

**Used by:** `prepare_buckaroo_artifact()` for self-contained HTML embeds

**Pipeline:**
1. `prepare_df_for_serialization()` — column renaming, index flattening
2. `_coerce_for_json()` — same Period/Interval/Timedelta/bytes coercion as Path 1
3. Convert PyArrow-backed string columns to object dtype (pandas 3.0+)
4. JSON-encode only object/category columns (except index columns) via `_json_encode_cell()`
5. Numeric columns preserved as-is in parquet
6. Serialized via **pyarrow** engine

**Output format:** `{'format': 'parquet_b64', 'data': '<base64>'}`

### Polars Path (`polars_buckaroo.py:to_parquet`)

**Used by:** Polars widget serialization

**Pipeline:** `df.write_parquet()` — Polars handles all types natively, no coercion needed.

---

## Parquet Compatibility Matrix

| Type | Parquet native? | Pandas path | Polars path | JS decode (hyparquet) |
|---|---|---|---|---|
| int64 | ✅ INT64 | Direct | Direct | Number (or BigInt if >2^53) |
| float64 | ✅ DOUBLE | Direct | Direct | Number |
| boolean | ✅ BOOLEAN | Direct | Direct | boolean |
| string | ✅ BYTE_ARRAY+STRING | JSON-encoded | Direct | JSON.parse per cell |
| datetime | ✅ TIMESTAMP | Direct | Direct | ISO string |
| categorical | ⚠️ dict encoding | JSON-encoded as str | Native dict encoding | JSON.parse |
| timedelta | ⚠️ varies by library | **→ str coercion** | Native Duration | string |
| period | ❌ | **→ str coercion** | N/A | string |
| interval | ❌ | **→ str coercion** | N/A | string |
| time | ✅ TIME | N/A (not in pandas DDD) | Native | string |
| decimal | ✅ DECIMAL | N/A (not in pandas DDD) | Native | Number |
| binary | ✅ BYTE_ARRAY | **→ hex() str** | Native | bytes |
| NaN/inf | ✅ (float special values) | Direct | Direct | Number |
| BigInt | ✅ INT64 | Direct | Direct | Number if safe, else string |

### Key Problem Types (require coercion before parquet)
1. **Period** — pandas-only, no parquet equivalent, stringified
2. **Interval** — pandas-only, no parquet equivalent, stringified
3. **Timedelta** — parquet DURATION annotation exists but pyarrow/fastparquet support is inconsistent; buckaroo stringifies in pandas path
4. **bytes** — parquet-native as BYTE_ARRAY, but JSON serialization path can't handle raw bytes; hex-encoded

### Types that round-trip cleanly through parquet
- All numeric types (int, float, decimal, boolean)
- Strings
- Datetimes (with timezone handling caveats)
- Date, Time
- Duration (Polars path only)
- Binary (Polars path only)

---

## JS-Side Deserialization (`resolveDFData.ts`)

The JavaScript side uses **hyparquet** to decode parquet:
1. Detects `{format: 'parquet_b64', data: '...'}` payloads
2. Base64-decodes → parquet bytes → column arrays via hyparquet
3. `parseParquetRow()` — JSON.parse per string cell to recover typed values
4. BigInt handling: safe INT64 (≤2^53) → Number, else → string
5. Column type detection (`_type` from summary stats) drives display formatters

### hyparquet limitations
- Does not support all parquet logical types (e.g. INTERVAL)
- BigInt values require explicit conversion
- All string cells need JSON.parse since buckaroo JSON-encodes before parquet
