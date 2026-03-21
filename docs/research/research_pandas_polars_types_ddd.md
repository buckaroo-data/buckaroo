# Pandas & Polars Type Coverage in Buckaroo

Tested 2026-03-20 against buckaroo on branch `docs/ddd-post`.

## Legend

- **Serializes**: Does the dtype survive `pd_to_obj` (JSON path), `_df_to_parquet_b64_tagged` (parquet path), or polars `write_parquet`?
- **In DDD**: Is there a DDD test case exercising this dtype in `ddd_library.py`?
- **In test suite**: Is there a pytest that runs this dtype through the widget?

## Pandas — Classic (NumPy-backed)

| Dtype              | JSON | Parquet | In DDD | In tests | Notes |
|--------------------|------|---------|--------|----------|-------|
| int8               | OK   | OK      | —      | —        | Covered implicitly by int64 path |
| int16              | OK   | OK      | —      | —        | |
| int32              | OK   | OK      | —      | —        | |
| int64              | OK   | OK      | Yes    | Yes      | Standard numeric, used throughout DDD |
| uint8              | OK   | OK      | —      | —        | |
| uint16             | OK   | OK      | —      | —        | |
| uint32             | OK   | OK      | —      | —        | |
| uint64             | OK   | OK      | —      | —        | Similar BigInt edge case as int |
| float16            | OK   | OK      | —      | —        | Rare in practice |
| float32            | OK   | OK      | —      | —        | |
| float64            | OK   | OK      | Yes    | Yes      | `df_with_infinity()` tests nan/inf/-inf |
| float64 + inf      | OK   | OK      | Yes    | Yes      | |
| complex128         | OK   | **FAIL** | —     | —        | ArrowNotImplementedError on parquet. JSON falls back to str |
| bool               | OK   | OK      | —      | —        | Trivial |
| object (strings)   | OK   | OK      | Yes    | Yes      | Used throughout DDD |
| object (mixed)     | OK   | OK      | —      | —        | e.g. `[1, 'foo', None, 3.14]` — no DDD case |
| datetime64[ns]     | OK   | OK      | —      | —        | Standard, well-tested outside DDD |
| timedelta64[ns]    | OK   | OK      | Yes    | Yes      | Coerced to str. `df_with_weird_types()` |
| bigint (>2^53)     | OK   | OK      | Yes    | Yes      | `df_with_really_big_number()` |

## Pandas — Extension Dtypes

| Dtype              | JSON | Parquet | In DDD | In tests | Notes |
|--------------------|------|---------|--------|----------|-------|
| Int8 (nullable)    | OK   | OK      | —      | —        | pd.NA instead of NaN |
| Int64 (nullable)   | OK   | OK      | —      | —        | |
| UInt64 (nullable)  | OK   | OK      | —      | —        | |
| Float64 (nullable) | OK   | OK      | —      | —        | |
| boolean (nullable) | OK   | OK      | —      | —        | |
| string (StringDtype)| OK  | OK      | —      | —        | |
| CategoricalDtype   | OK   | OK      | Yes    | Yes      | `df_with_weird_types()` |
| SparseDtype        | OK   | **FAIL** | —     | —        | TypeError on parquet. JSON OK via densify |
| IntervalDtype      | OK   | OK      | Yes    | Yes      | Coerced to str `(0, 1]`. `df_with_weird_types()` |
| PeriodDtype        | OK   | OK      | Yes    | Yes      | Coerced to str `'2021-01'`. `df_with_weird_types()` |
| DatetimeTZDtype    | OK   | OK      | —      | —        | No DDD case, but serializes fine |

## Pandas — Arrow-backed (pandas 2.0+)

| Dtype                | JSON | Parquet | In DDD | In tests | Notes |
|----------------------|------|---------|--------|----------|-------|
| arrow: int64         | OK   | OK      | —      | —        | |
| arrow: float64       | OK   | OK      | —      | —        | |
| arrow: bool          | OK   | OK      | —      | —        | |
| arrow: string        | OK   | OK      | —      | —        | `artifact.py` converts ArrowDtype string→object |
| arrow: large_string  | OK   | OK      | —      | —        | |
| arrow: binary        | OK   | OK      | —      | —        | |
| arrow: date32        | OK   | OK      | —      | —        | |
| arrow: timestamp(us) | OK   | OK      | —      | —        | |
| arrow: timestamp+tz  | OK   | OK      | —      | —        | |
| arrow: duration(us)  | OK   | OK      | —      | —        | |
| arrow: time64(us)    | OK   | OK      | —      | —        | |
| arrow: decimal128    | OK   | OK      | —      | —        | |
| arrow: list(int64)   | OK   | OK      | —      | —        | |
| arrow: struct        | OK   | OK      | —      | —        | |
| arrow: dictionary    | OK   | OK      | —      | —        | |

## Polars

| Dtype            | Parquet | In DDD | In tests | Notes |
|------------------|---------|--------|----------|-------|
| Int8             | OK      | —      | —        | |
| Int16            | OK      | —      | —        | |
| Int32            | OK      | —      | —        | |
| Int64            | OK      | Yes    | Yes      | `pl_df_with_weird_types()` |
| UInt8            | OK      | —      | —        | |
| UInt16           | OK      | —      | —        | |
| UInt32           | OK      | —      | —        | |
| UInt64           | OK      | —      | —        | |
| Float32          | OK      | —      | —        | |
| Float64          | OK      | —      | —        | |
| Decimal(10,2)    | OK      | Yes    | Yes      | `pl_df_with_weird_types()` |
| Boolean          | OK      | —      | —        | |
| String           | OK      | —      | —        | Standard |
| Binary           | OK      | Yes    | Yes      | `pl_df_with_weird_types()` |
| Date             | OK      | —      | —        | No DDD case |
| Time             | OK      | Yes    | Yes      | `pl_df_with_weird_types()` |
| Datetime         | OK      | —      | —        | No DDD case |
| Datetime(tz)     | OK      | —      | —        | No DDD case |
| Duration         | OK      | Yes    | Yes      | `pl_df_with_weird_types()`. Was blank before #622 |
| Categorical      | OK      | Yes    | Yes      | `pl_df_with_weird_types()` |
| Enum             | OK      | —      | —        | No DDD case |
| List(Int64)      | OK      | —      | —        | No DDD case |
| Array(Int64,2)   | OK      | —      | —        | No DDD case |
| Struct            | OK      | —      | —        | No DDD case. Nested column support in progress |
| Null             | OK      | —      | —        | All-null column. Summary stats warn but display works |

## Pandas — Structural Edge Cases

| Case                        | In DDD | In tests | Function |
|-----------------------------|--------|----------|----------|
| NaN + inf + -inf            | Yes    | Yes      | `df_with_infinity()` |
| BigInt (>2^53)              | Yes    | Yes      | `df_with_really_big_number()` |
| Column named `index`        | Yes    | Yes      | `df_with_col_named_index()` |
| Named index                 | Yes    | Yes      | `get_df_with_named_index()` |
| MultiIndex columns          | Yes    | Yes      | `get_multiindex_cols_df()` |
| MultiIndex columns w/ names | Yes    | Yes      | `get_multiindex_with_names_cols_df()` |
| Tuple columns (flattened MI)| Yes    | —        | `get_tuple_cols_df()` |
| MultiIndex rows (2-level)   | Yes    | Yes      | `get_multiindex_index_df()` |
| MultiIndex rows (3-level)   | Yes    | —        | `get_multiindex3_index_df()` |
| MultiIndex rows w/ names    | Yes    | Yes      | `get_multiindex_with_names_index_df()` |
| MultiIndex both axes        | Yes    | —        | `get_multiindex_with_names_both()` |
| None in string column       | Yes    | —        | Mixed into MI frames |
| Duplicate columns           | —      | —        | Not tested |
| Empty DataFrame (0 rows)    | —      | Yes      | `empty_df` in fixtures |
| Mixed-type object column    | —      | —        | Not tested |
| Very wide (100+ cols)       | —      | —        | Not tested |

## Serialization failures

Only two dtypes fail the parquet path:

1. **complex128** — `ArrowNotImplementedError`: PyArrow has no complex number type. JSON path works (stringified).
2. **SparseDtype** — `TypeError`: pyarrow cannot convert sparse arrays. JSON path works (densified).

Everything else serializes through both paths.
