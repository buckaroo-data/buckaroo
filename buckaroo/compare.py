"""DataFrame comparison utilities.

``col_join_dfs`` — join two DataFrames and produce a Buckaroo-styled
merged frame with per-column diff statistics (existing API).

``stats_diff*`` / ``head_diff*`` / ``key_diff*`` — compute per-column
summary statistics and outer-join diffs across three backends:

  pandas  — default; vectorised over all columns in three batch passes.
  polars  — three .select() calls; head_diff reads only N rows lazily.
  xorq    — one ibis aggregate expression per parquet file; nothing
            larger than a scalar summary row is materialised.

Polars functions require ``buckaroo[polars]``.
Xorq functions require ``buckaroo[xorq]``.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import polars as pl


# ---------------------------------------------------------------------------
# shared utility
# ---------------------------------------------------------------------------


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# pandas backend
# ---------------------------------------------------------------------------


def _column_summaries_pd(df: pd.DataFrame) -> dict[str, dict]:
    """Three vectorised passes instead of per-column loops.

    Old approach called mean/min/max/sum individually for each column
    (N_cols * 4 scans).  This version does one isnull pass, one nunique
    pass, and one numeric agg across all numeric columns at once.
    """
    n = len(df)
    null_counts = df.isnull().sum()
    distinct_counts = df.nunique(dropna=True)

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    num_agg = df[numeric_cols].agg(["mean", "min", "max", "sum"]) if numeric_cols else pd.DataFrame()

    result: dict[str, dict] = {}
    for col in df.columns:
        num = None
        if col in num_agg.columns:
            col_agg = num_agg[col]
            num = {"mean": _safe_float(col_agg["mean"]), "min": _safe_float(col_agg["min"]),
                "max": _safe_float(col_agg["max"]), "sum": _safe_float(col_agg["sum"])}
        result[col] = {"count": n, "nulls": int(null_counts[col]), "distinct": int(distinct_counts[col]),
            "numeric": num}
    return result


def _infer_keys(a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """Heuristic: shared non-numeric low-cardinality columns are likely keys."""
    shared_non_numeric = [
        c for c in a.columns
        if c in b.columns and not pd.api.types.is_numeric_dtype(a[c])
    ]
    if not shared_non_numeric:
        return []
    counts = a[shared_non_numeric].nunique(dropna=False)
    return [c for c in shared_non_numeric if counts[c] <= max(20, int(len(a) * 0.5))]


def head_diff(a: pd.DataFrame, b: pd.DataFrame, n: int = 10) -> dict:
    """Side-by-side first-N rows as HTML tables (pandas backend)."""
    return {"before": a.head(n).to_html(classes="data-table", index=False, border=0),
        "after": b.head(n).to_html(classes="data-table", index=False, border=0), "n": n, "a_total": len(a),
        "b_total": len(b)}


def stats_diff(a: pd.DataFrame, b: pd.DataFrame) -> list[dict]:
    """Per-column count / nulls / distinct / numeric summary (pandas backend)."""
    cols = list(dict.fromkeys(list(a.columns) + list(b.columns)))
    a_s = _column_summaries_pd(a)
    b_s = _column_summaries_pd(b)
    return [{"name": col, "before": a_s.get(col), "after": b_s.get(col)} for col in cols]


def key_diff(a: pd.DataFrame, b: pd.DataFrame) -> dict | None:
    """Outer-join on inferred keys; show per-key value changes (pandas backend)."""
    keys = _infer_keys(a, b)
    if not keys:
        return None
    try:
        merged = a.merge(b, on=keys, how="outer", suffixes=("_before", "_after"), indicator=True)
    except Exception:
        return None
    only_left = int((merged["_merge"] == "left_only").sum())
    only_right = int((merged["_merge"] == "right_only").sum())
    both = int((merged["_merge"] == "both").sum())
    merged = merged.drop(columns=["_merge"])
    return {"keys": keys, "only_before": only_left, "only_after": only_right, "matched": both,
        "table_html": merged.head(50).to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# polars backend  (requires buckaroo[polars])
# ---------------------------------------------------------------------------


def _column_summaries_polars(df: "pl.DataFrame") -> dict[str, dict]:
    """Three .select() calls — null counts, distinct counts, numeric aggs."""
    import polars as pl

    n = len(df)
    nulls = df.select(pl.all().null_count()).row(0, named=True)
    distincts = df.select(pl.all().n_unique()).row(0, named=True)

    num_cols = [c for c in df.columns if df.schema[c].is_numeric()]
    if num_cols:
        num_row = df.select(
            [pl.col(c).mean().alias(f"{c}__mean") for c in num_cols]
            + [pl.col(c).min().alias(f"{c}__min") for c in num_cols]
            + [pl.col(c).max().alias(f"{c}__max") for c in num_cols]
            + [pl.col(c).sum().alias(f"{c}__sum") for c in num_cols]).row(0, named=True)
    else:
        num_row = {}

    result: dict[str, dict] = {}
    for col in df.columns:
        num = None
        if col in num_cols:
            num = {"mean": _safe_float(num_row.get(f"{col}__mean")), "min": _safe_float(num_row.get(f"{col}__min")),
                "max": _safe_float(num_row.get(f"{col}__max")), "sum": _safe_float(num_row.get(f"{col}__sum"))}
        result[col] = {"count": n, "nulls": nulls[col], "distinct": distincts[col], "numeric": num}
    return result


def _infer_keys_polars(a: "pl.DataFrame", b: "pl.DataFrame") -> list[str]:
    import polars as pl

    shared = [c for c in a.columns if c in b.columns and not a.schema[c].is_numeric()]
    if not shared:
        return []
    counts = a.select(pl.col(shared).n_unique()).row(0, named=True)
    return [c for c in shared if counts[c] <= max(20, int(len(a) * 0.5))]


def head_diff_polars(a_path: Path, b_path: Path, n: int = 10) -> dict:
    """Read only N rows from each parquet via lazy scan (polars backend)."""
    import polars as pl

    a_df = pl.scan_parquet(a_path).head(n).collect()
    b_df = pl.scan_parquet(b_path).head(n).collect()
    a_total = pl.scan_parquet(a_path).select(pl.len()).collect()[0, 0]
    b_total = pl.scan_parquet(b_path).select(pl.len()).collect()[0, 0]
    return {"before": a_df.to_pandas().to_html(classes="data-table", index=False, border=0),
        "after": b_df.to_pandas().to_html(classes="data-table", index=False, border=0), "n": n, "a_total": a_total,
        "b_total": b_total}


def stats_diff_polars(a: "pl.DataFrame", b: "pl.DataFrame") -> list[dict]:
    """Per-column stats (polars backend)."""
    cols = list(dict.fromkeys(list(a.columns) + list(b.columns)))
    a_s = _column_summaries_polars(a)
    b_s = _column_summaries_polars(b)
    return [{"name": col, "before": a_s.get(col), "after": b_s.get(col)} for col in cols]


def key_diff_polars(a: "pl.DataFrame", b: "pl.DataFrame") -> dict | None:
    """Outer join on inferred keys (polars backend)."""
    keys = _infer_keys_polars(a, b)
    if not keys:
        return None
    try:
        merged = a.join(b, on=keys, how="full", suffix="_after", coalesce=True)
    except Exception:
        return None
    a_only_col = next((c for c in a.columns if c not in keys), None)
    b_col_after = f"{a_only_col}_after" if a_only_col else None
    if a_only_col and b_col_after in merged.columns:
        only_before = int(merged[b_col_after].is_null().sum())
        only_after = int(merged[a_only_col].is_null().sum())
        both = len(merged) - only_before - only_after
    else:
        only_before = only_after = 0
        both = len(merged)
    return {"keys": keys, "only_before": only_before, "only_after": only_after, "matched": both,
        "table_html": merged.head(50).to_pandas().to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# xorq backend  (requires buckaroo[xorq])
# ---------------------------------------------------------------------------


def _column_summaries_xorq(path: Path) -> dict[str, dict]:
    """One ibis aggregate expression covering every column, executed once.

    Nothing larger than the single scalar summary row is materialised.
    """
    import xorq.api as xo

    expr = xo.deferred_read_parquet(str(path))
    schema = expr.schema()

    agg: list = [expr.count().name("__total__")]
    for col_name, dtype in schema.items():
        agg.append(expr[col_name].isnull().sum().cast("int64").name(f"{col_name}__nulls"))
        agg.append(expr[col_name].nunique().name(f"{col_name}__distinct"))
        if dtype.is_numeric():
            agg.append(expr[col_name].mean().name(f"{col_name}__mean"))
            agg.append(expr[col_name].min().cast("float64").name(f"{col_name}__min"))
            agg.append(expr[col_name].max().cast("float64").name(f"{col_name}__max"))
            agg.append(expr[col_name].sum().cast("float64").name(f"{col_name}__sum"))

    row = expr.aggregate(agg).execute().iloc[0]
    total = int(row["__total__"])

    result: dict[str, dict] = {}
    for col_name, dtype in schema.items():
        num = None
        if dtype.is_numeric():
            num = {"mean": _safe_float(row[f"{col_name}__mean"]), "min": _safe_float(row[f"{col_name}__min"]),
                "max": _safe_float(row[f"{col_name}__max"]), "sum": _safe_float(row[f"{col_name}__sum"])}
        result[col_name] = {"count": total, "nulls": int(row[f"{col_name}__nulls"]),
            "distinct": int(row[f"{col_name}__distinct"]), "numeric": num}
    return result


def _infer_keys_xorq(a_path: Path, b_path: Path) -> list[str]:
    """Infer key columns by querying both parquets via DuckDB."""
    import duckdb
    import xorq.api as xo

    a_schema = xo.deferred_read_parquet(str(a_path)).schema()
    b_schema = xo.deferred_read_parquet(str(b_path)).schema()
    shared = [c for c in a_schema if c in b_schema and not a_schema[c].is_numeric()]
    if not shared:
        return []
    con = duckdb.connect()
    row = con.execute(
        "SELECT " + ", ".join(f'COUNT(DISTINCT "{c}") AS "{c}"' for c in shared)
        + f" FROM '{a_path}'").fetchone()
    total = con.execute(f"SELECT COUNT(*) FROM '{a_path}'").fetchone()[0]
    threshold = max(20, int(total * 0.5))
    return [c for c, v in zip(shared, row) if v <= threshold]


def head_diff_xorq(a_path: Path, b_path: Path, n: int = 10) -> dict:
    """LIMIT-N query on each parquet — no full table scan (xorq backend)."""
    import duckdb
    import xorq.api as xo

    a_df = xo.deferred_read_parquet(str(a_path)).limit(n).execute()
    b_df = xo.deferred_read_parquet(str(b_path)).limit(n).execute()
    con = duckdb.connect()
    a_total = con.execute(f"SELECT COUNT(*) FROM '{a_path}'").fetchone()[0]
    b_total = con.execute(f"SELECT COUNT(*) FROM '{b_path}'").fetchone()[0]
    return {"before": a_df.to_html(classes="data-table", index=False, border=0),
        "after": b_df.to_html(classes="data-table", index=False, border=0), "n": n, "a_total": a_total,
        "b_total": b_total}


def stats_diff_xorq(a_path: Path, b_path: Path) -> list[dict]:
    """Per-column stats computed directly on parquet files (xorq backend).

    Each side is one aggregate query — no DataFrame materialisation.
    """
    import xorq.api as xo

    a_schema = xo.deferred_read_parquet(str(a_path)).schema()
    b_schema = xo.deferred_read_parquet(str(b_path)).schema()
    cols = list(dict.fromkeys(list(a_schema) + list(b_schema)))
    a_s = _column_summaries_xorq(a_path)
    b_s = _column_summaries_xorq(b_path)
    return [{"name": col, "before": a_s.get(col), "after": b_s.get(col)} for col in cols]


def key_diff_xorq(a_path: Path, b_path: Path) -> dict | None:
    """Outer-join on inferred keys using DuckDB SQL (xorq backend)."""
    import duckdb

    keys = _infer_keys_xorq(a_path, b_path)
    if not keys:
        return None

    con = duckdb.connect()
    con.execute(f"CREATE VIEW a AS SELECT * FROM '{a_path}'")
    con.execute(f"CREATE VIEW b AS SELECT * FROM '{b_path}'")

    a_cols = [r[0] for r in con.execute("DESCRIBE a").fetchall()]
    b_cols = [r[0] for r in con.execute("DESCRIBE b").fetchall()]
    a_non_keys = [c for c in a_cols if c not in keys]
    b_non_keys = [c for c in b_cols if c not in keys]

    key_sel = ", ".join(f'COALESCE(a."{k}", b."{k}") AS "{k}"' for k in keys)
    a_sel = ", ".join(f'a."{c}" AS "{c}_before"' for c in a_non_keys)
    b_sel = ", ".join(f'b."{c}" AS "{c}_after"' for c in b_non_keys)
    on_clause = " AND ".join(f'a."{k}" = b."{k}"' for k in keys)
    select_parts = [p for p in [key_sel, a_sel, b_sel] if p]
    sql_join = f"SELECT {', '.join(select_parts)} FROM a FULL OUTER JOIN b ON {on_clause}"

    try:
        con.execute(f"CREATE VIEW merged AS {sql_join}")
        if a_non_keys and b_non_keys:
            counts = con.execute(f"""
                SELECT
                    SUM(CASE WHEN "{a_non_keys[0]}_before" IS NULL THEN 1 ELSE 0 END) AS only_after,
                    SUM(CASE WHEN "{b_non_keys[0]}_after"  IS NULL THEN 1 ELSE 0 END) AS only_before,
                    COUNT(*) AS total
                FROM merged
            """).fetchone()
            only_after, only_before, total = int(counts[0]), int(counts[1]), int(counts[2])
            both = total - only_before - only_after
        else:
            only_before = only_after = 0
            both = con.execute("SELECT COUNT(*) FROM merged").fetchone()[0]
        preview = con.execute("SELECT * FROM merged LIMIT 50").df()
    except Exception:
        return None

    return {"keys": keys, "only_before": only_before, "only_after": only_after, "matched": both,
        "table_html": preview.to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# existing join-diff API (unchanged)
# ---------------------------------------------------------------------------


def col_join_dfs(df1, df2, join_columns, how):
    """Join two DataFrames and compute column-level diff statistics.

    Parameters
    ----------
    df1, df2 : pd.DataFrame
        The two DataFrames to compare.
    join_columns : str or list[str]
        Column name(s) to join on.
    how : str
        Join type passed to ``pd.merge`` (e.g. 'inner', 'outer', 'left', 'right').

    Returns
    -------
    m_df : pd.DataFrame
        Merged DataFrame with membership and equality columns.
    column_config_overrides : dict
        Buckaroo column config for styling.
    eqs : dict
        Per-column diff summary.
    """
    # Normalize join_columns to list
    if isinstance(join_columns, str):
        join_columns = [join_columns]

    df2_suffix = "|df2"
    _indicator_col = "__buckaroo_merge"
    _sentinels = [df2_suffix, _indicator_col]
    for col in list(df1.columns) + list(df2.columns):
        if isinstance(col, str) and any(s in col for s in _sentinels):
            raise ValueError(
                f"|df2 and {_indicator_col} are sentinel column names used by this tool, "
                f"and can't be used in a dataframe passed in, {col} violates that constraint")

    df1_name, df2_name = "df_1", "df_2"

    # Validate join keys are unique in each dataframe to prevent cartesian explosion
    if df1[join_columns].duplicated().any():
        raise ValueError(
            f"Duplicate join keys found in df1 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison.")
    if df2[join_columns].duplicated().any():
        raise ValueError(
            f"Duplicate join keys found in df2 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison.")

    # Merge first so diff stats are computed on key-aligned rows
    m_df = pd.merge(df1, df2, on=join_columns, how=how, suffixes=["", df2_suffix], indicator=_indicator_col)

    # Compute membership from merge indicator
    # 1 = df1 only, 2 = df2 only, 3 = both
    membership_map = {"left_only": 1, "right_only": 2, "both": 3}
    m_df["membership"] = m_df[_indicator_col].map(membership_map).astype("Int8")
    m_df = m_df.drop(columns=[_indicator_col])

    # Build unified column order
    col_order = df1.columns.to_list()
    for col in df2.columns:
        if col not in col_order:
            col_order.append(col)

    # Compute diff stats from merged, key-aligned rows
    eqs = {}
    both_mask = m_df["membership"] == 3
    for col in col_order:
        if col in join_columns:
            eqs[col] = {"diff_count": "join_key"}
        elif col in df1.columns and col in df2.columns:
            df2_col = f"{col}{df2_suffix}"
            if df2_col in m_df.columns:
                # Use the column name as it appears in the merged frame
                # (pandas may coerce non-string labels to strings when adding suffixes)
                m_df_col = df2_col.removesuffix(df2_suffix)
                eqs[col] = {
                    "diff_count": int(
                        (m_df.loc[both_mask, m_df_col] != m_df.loc[both_mask, df2_col]).sum())}
            else:
                eqs[col] = {"diff_count": 0}
        else:
            if col in df1.columns:
                eqs[col] = {"diff_count": df1_name}
            else:
                eqs[col] = {"diff_count": df2_name}

    column_config_overrides = {}
    eq_map = ["pink", "#73ae80", "#90b2b3", "#6c83b5"]

    column_config_overrides["membership"] = {"merge_rule": "hidden"}

    both_columns = [c for c in m_df.columns if isinstance(c, str) and c.endswith(df2_suffix)]
    for b_col in both_columns:
        a_col = b_col.removesuffix(df2_suffix)
        col_neq = (m_df[a_col] == m_df[b_col]).astype("Int8") * 4
        eq_col = f"{a_col}|eq"
        m_df[eq_col] = col_neq + m_df["membership"]

        column_config_overrides[b_col] = {"merge_rule": "hidden"}
        column_config_overrides[eq_col] = {"merge_rule": "hidden"}
        column_config_overrides[a_col] = {
            "tooltip_config": {"tooltip_type": "simple", "val_column": b_col},
            "color_map_config": {
                "color_rule": "color_categorical",
                "map_name": eq_map,
                "val_column": eq_col,
            },
        }

    # Join key columns get a distinct static colour so they stand out clearly
    # from the data-diff columns (which use membership-based categorical colours).
    # Use color_categorical with a constant-color map so it works with the
    # compiled JS without requiring a rebuild.  color_static is the cleaner
    # long-term solution once the JS is rebuilt.
    pk_color = "#6c5fc7"
    pk_map = [pk_color, pk_color, pk_color, pk_color]
    for jc in join_columns:
        column_config_overrides[jc] = {
            "color_map_config": {"color_rule": "color_categorical", "map_name": pk_map, "val_column": "membership"}}

    return m_df, column_config_overrides, eqs
