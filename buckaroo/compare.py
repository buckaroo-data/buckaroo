"""DataFrame comparison utilities.

``col_join_dfs`` — join two DataFrames and produce a Buckaroo-styled
merged frame with per-column diff statistics (existing API).

``stats_diff*`` / ``head_diff*`` / ``key_diff*`` — compute per-column
summary statistics and outer-join diffs across three backends:

  pandas  — default; vectorised over all columns in three batch passes.
  polars  — three .select() calls; head_diff reads only N rows lazily.
  xorq    — one ibis aggregate expression per parquet file; nothing
            larger than a scalar summary row is materialised.

All three backends share one key-detection algorithm (``_rank_pk_*`` /
``_detect_pk_*``): rank candidates by uniqueness, single columns first then
small composites, accept the first that clears ``threshold`` with a bounded
largest-duplicate-group (``max_group``).  ``key_diff*`` joins on the detected
key and **stops** (returns ``None``) when no simple primary key exists, rather
than joining on a low-cardinality column and exploding into a many-to-many
product.  ``probe_diff`` exposes that decision as a cheap pre-flight check.

The three backends agree on real data.  They can differ only in two corners,
both of which make poor primary keys anyway: a float column that mixes a
genuine NaN with nulls (pandas cannot tell NaN from null, polars/xorq can), and
a key whose value is itself null (engines disagree on whether null == null
joins).

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


def _require_keys_in_both(keys: list[str], a_cols, b_cols) -> None:
    """Raise if any explicitly-supplied key is missing from either side.

    Auto-detected keys come from the shared columns and always pass; this
    guards the explicit ``keys=`` path so a typo surfaces as a clear error
    rather than being swallowed into a ``None`` ("no usable key") result.
    Note that explicit keys still skip the uniqueness / ``max_group`` guard —
    the caller is trusted to pass a real key.
    """
    a_set, b_set = set(a_cols), set(b_cols)
    missing = [k for k in keys if k not in a_set or k not in b_set]
    if missing:
        raise ValueError(f"key_diff keys not present in both inputs: {missing}")


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


def _max_group_pd(df: pd.DataFrame, combo: list[str]) -> int:
    """Largest number of rows sharing a single value of ``combo``."""
    return int(df.groupby(list(combo), dropna=False).size().max())


def _rank_pk_pd(df: pd.DataFrame, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> dict | None:
    """Best join-key candidate for a DataFrame (pandas port of :func:`_rank_pk_xorq`).

    Same search and acceptance rule as the xorq/polars backends: single columns
    most-unique-first, then composites of width 2..``max_width`` (shortest
    first); the first candidate whose uniqueness (distinct/rows) is
    ``>= threshold`` and whose largest duplicate group is ``<= max_group`` wins.
    Returns ``None`` if nothing qualifies.  See :func:`_rank_pk_xorq` for the
    meaning of ``threshold`` / ``max_group``.
    """
    from itertools import combinations

    cols = list(df.columns)
    if columns is not None:
        cols = [c for c in cols if c in columns]
    if not cols:
        return None
    n = len(df)
    if n == 0:
        return None
    distinct = {c: int(df[c].nunique(dropna=True)) for c in cols}
    need = threshold * n

    def _accept(combo: tuple[str, ...], d: int) -> dict | None:
        if d < need:
            return None
        mg = _max_group_pd(df, list(combo))
        if max_group is not None and mg > max_group:
            return None
        return {"keys": list(combo), "uniqueness": d / n, "max_group": mg, "n": n}

    # Single columns, most-unique first — a passing single beats any composite.
    for c in sorted(cols, key=lambda c: distinct[c], reverse=True):
        result = _accept((c,), distinct[c])
        if result is not None:
            return result

    # Composite keys, shortest first.  Prune with a cheap cardinality-product
    # upper bound before paying for the distinct-tuple count.
    usable = [c for c in cols if distinct[c] > 1]
    for width in range(2, max_width + 1):
        for combo in combinations(usable, width):
            bound = 1
            for c in combo:
                bound *= distinct[c]
                if bound >= need:
                    break
            if bound < need:
                continue
            d = int(len(df.drop_duplicates(subset=list(combo))))
            result = _accept(combo, d)
            if result is not None:
                return result
    return None


def _detect_pk_pd(df: pd.DataFrame, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> list[str] | None:
    """Detected (approximate) primary key for a DataFrame, or ``None``.

    Thin wrapper over :func:`_rank_pk_pd` returning just the key columns.
    """
    result = _rank_pk_pd(df, threshold=threshold, max_width=max_width, max_group=max_group, columns=columns)
    return list(result["keys"]) if result else None


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


def key_diff(a: pd.DataFrame, b: pd.DataFrame, keys: list[str] | None = None, threshold: float = 0.98,
        max_width: int = 4, max_group: int | None = 10_000) -> dict | None:
    """Outer-join two frames on a detected primary key (pandas backend).

    The key is found with :func:`_detect_pk_pd` over the shared columns
    (uniqueness ``>= threshold``, largest duplicate group ``<= max_group``) —
    the same algorithm as the polars and xorq backends.  When no such key
    exists the diff is **stopped**: it returns ``None`` rather than joining on a
    low-cardinality column and exploding into a many-to-many product.
    Membership counts come from the merge indicator, so a genuine null in a
    data column is never mistaken for a non-matching row.
    """
    if not keys:
        shared = [c for c in a.columns if c in b.columns]
        keys = (_detect_pk_pd(a, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared)
            or _detect_pk_pd(b, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared))
    if not keys:
        return None
    _require_keys_in_both(keys, a.columns, b.columns)
    try:
        merged = a.merge(b, on=keys, how="outer", suffixes=("_before", "_after"), indicator=True)
    except Exception:
        return None
    only_before = int((merged["_merge"] == "left_only").sum())
    only_after = int((merged["_merge"] == "right_only").sum())
    both = int((merged["_merge"] == "both").sum())
    merged = merged.drop(columns=["_merge"])
    return {"keys": keys, "only_before": only_before, "only_after": only_after, "matched": both,
        "table_html": merged.head(50).to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# polars backend  (requires buckaroo[polars])
# ---------------------------------------------------------------------------


def _column_summaries_polars(df: "pl.DataFrame") -> dict[str, dict]:
    """Three .select() calls — null counts, distinct counts, numeric aggs."""
    import polars as pl

    n = len(df)
    nulls = df.select(pl.all().null_count()).row(0, named=True)
    # drop_nulls before n_unique so 'distinct' excludes null, matching the
    # pandas (nunique dropna=True) and xorq (ibis nunique) backends.
    distincts = df.select(pl.all().drop_nulls().n_unique()).row(0, named=True)

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


def _as_lazy_pl(src):
    """Accept a parquet path/str, a LazyFrame, or a DataFrame -> LazyFrame.

    Mirrors :func:`_as_expr`: lets the polars key helpers take a path and push
    the uniqueness aggregates down through a lazy scan, so PK detection on a
    file far larger than memory never materialises more than a summary row.
    """
    import polars as pl

    if isinstance(src, (str, Path)):
        return pl.scan_parquet(src)
    if isinstance(src, pl.LazyFrame):
        return src
    return src.lazy()


def _max_group_pl(lf, combo: list[str]) -> int:
    """Largest number of rows sharing a single value of ``combo`` (one agg)."""
    import polars as pl

    mx = lf.group_by(list(combo)).agg(pl.len().alias("__cnt__")).select(pl.col("__cnt__").max()).collect()[0, 0]
    return int(mx) if mx is not None else 0


def _rank_pk_polars(src, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> dict | None:
    """Best join-key candidate for a DataFrame / LazyFrame / parquet path (polars).

    Polars port of :func:`_rank_pk_xorq` — identical search (single columns
    most-unique-first, then composites of width 2..``max_width``) and the same
    uniqueness ``>= threshold`` / ``max_group`` acceptance rule.  Aggregates run
    on a lazy scan, so nothing larger than a summary row is materialised.  See
    :func:`_rank_pk_xorq` for the meaning of ``threshold`` / ``max_group``.
    """
    from itertools import combinations

    import polars as pl

    lf = _as_lazy_pl(src)
    cols = list(lf.collect_schema().names())
    if columns is not None:
        cols = [c for c in cols if c in columns]
    if not cols:
        return None

    # distinct excludes nulls (drop_nulls) to match ibis/pandas nunique semantics.
    summary = lf.select(
        [pl.len().alias("__n__")] + [pl.col(c).drop_nulls().n_unique().alias(c) for c in cols]).collect()
    row = summary.row(0, named=True)
    n = int(row["__n__"])
    if n == 0:
        return None
    distinct = {c: int(row[c]) for c in cols}
    need = threshold * n

    def _accept(combo: tuple[str, ...], d: int) -> dict | None:
        if d < need:
            return None
        mg = _max_group_pl(lf, list(combo))
        if max_group is not None and mg > max_group:
            return None
        return {"keys": list(combo), "uniqueness": d / n, "max_group": mg, "n": n}

    for c in sorted(cols, key=lambda c: distinct[c], reverse=True):
        result = _accept((c,), distinct[c])
        if result is not None:
            return result

    usable = [c for c in cols if distinct[c] > 1]
    for width in range(2, max_width + 1):
        for combo in combinations(usable, width):
            bound = 1
            for c in combo:
                bound *= distinct[c]
                if bound >= need:
                    break
            if bound < need:
                continue
            d = int(lf.select(list(combo)).unique().select(pl.len()).collect()[0, 0])
            result = _accept(combo, d)
            if result is not None:
                return result
    return None


def _detect_pk_polars(src, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> list[str] | None:
    """Detected (approximate) primary key for a polars frame/path, or ``None``."""
    result = _rank_pk_polars(src, threshold=threshold, max_width=max_width, max_group=max_group, columns=columns)
    return list(result["keys"]) if result else None


def _shared_columns_polars(a, b) -> list[str]:
    """Columns present in both schemas, in ``a``'s order (frame/path)."""
    a_cols = _as_lazy_pl(a).collect_schema().names()
    b_cols = set(_as_lazy_pl(b).collect_schema().names())
    return [c for c in a_cols if c in b_cols]


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


def key_diff_polars(a, b, keys: list[str] | None = None, threshold: float = 0.98, max_width: int = 4,
        max_group: int | None = 10_000) -> dict | None:
    """Outer-join two sides on a detected primary key (polars backend).

    Same algorithm as :func:`key_diff_xorq`: the key is found with
    :func:`_detect_pk_polars` over the shared columns.  When no key reaches
    ``threshold`` (within ``max_width`` / ``max_group``) the diff is
    **stopped** — it returns ``None`` rather than joining on a low-cardinality
    column and exploding into a many-to-many product.  ``a`` / ``b`` accept a
    parquet path, a LazyFrame, or a DataFrame.
    """
    import polars as pl

    la = _as_lazy_pl(a)
    lb = _as_lazy_pl(b)
    if not keys:
        shared = _shared_columns_polars(la, lb)
        keys = (_detect_pk_polars(la, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared)
            or _detect_pk_polars(lb, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared))
    if not keys:
        return None

    a_cols = list(la.collect_schema().names())
    b_cols = list(lb.collect_schema().names())
    _require_keys_in_both(keys, a_cols, b_cols)
    a_non = [c for c in a_cols if c not in keys]
    b_non = [c for c in b_cols if c not in keys]
    try:
        # Marker columns give a null-safe membership count: a genuine null in a
        # data column must not be mistaken for a non-matching row.
        am = la.rename({c: f"{c}_before" for c in a_non}).with_columns(__a__=pl.lit(True))
        bm = lb.rename({c: f"{c}_after" for c in b_non}).with_columns(__b__=pl.lit(True))
        merged = am.join(bm, on=keys, how="full", coalesce=True).collect()
    except Exception:
        return None
    only_after = int(merged["__a__"].is_null().sum())   # a-side absent -> row only in b
    only_before = int(merged["__b__"].is_null().sum())  # b-side absent -> row only in a
    both = len(merged) - only_before - only_after
    preview = merged.drop("__a__", "__b__").head(50)
    return {"keys": keys, "only_before": only_before, "only_after": only_after, "matched": both,
        "table_html": preview.to_pandas().to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# xorq backend  (requires buckaroo[xorq])
# ---------------------------------------------------------------------------


def _as_expr(src):
    """Accept either a parquet path/str or an already-built xorq expression.

    Lets every xorq diff helper take ``expr1``/``expr2`` directly — so a diff
    composes the two entry expressions (each carrying its own ``.cache()``
    node) rather than reaching for a materialised ``result.parquet``.
    """
    import xorq.api as xo

    if isinstance(src, (str, Path)):
        return xo.deferred_read_parquet(str(src))
    return src


def _align_backends(a, b):
    """Land two expressions on one backend, but only if they differ.

    Two independently-loaded entry expressions can be bound to different
    backends, which an outer join rejects; ``into_backend`` unifies them.  When
    both already share a backend (e.g. both read parquet on the default xorq
    backend) we skip it — into_backend would force an eager transport.
    """
    try:
        con_a = a._find_backend(use_default=True)
    except Exception:
        con_a = None
    try:
        con_b = b._find_backend(use_default=True)
    except Exception:
        con_b = None
    if con_a is not None and con_b is not None and con_a is not con_b:
        b = b.into_backend(con_a)
    return a, b


def _column_summaries_xorq(src) -> dict[str, dict]:
    """One ibis aggregate expression covering every column, executed once.

    Nothing larger than the single scalar summary row is materialised.
    """
    expr = _as_expr(src)
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


def _max_group_xorq(expr, combo: list[str]) -> int:
    """Largest number of rows sharing a single value of ``combo`` (one agg)."""
    grp = expr.group_by(list(combo)).agg(__cnt__=expr.count())
    return int(grp["__cnt__"].max().execute())


def _rank_pk_xorq(src, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> dict | None:
    """Best join-key candidate for a parquet file or expression (xorq backend).

    Searches single columns (most-unique first), then composites of width
    2..``max_width`` (shortest first), and returns the first candidate whose
    *uniqueness* — distinct key tuples / row count — is ``>= threshold``::

        {"keys": [...], "uniqueness": float, "max_group": int | None, "n": int}

    Returns ``None`` if nothing reaches ``threshold``.

    All work is pushed to xorq as aggregate expressions — ``count``,
    ``nunique``, a distinct-row ``count`` per composite candidate, and (when
    ``max_group`` is set) one ``group_by``/``max``.  Nothing larger than a
    one-row summary is materialised, so this is safe on files far larger than
    memory.  It does not touch DuckDB directly; whatever backend xorq is
    configured with executes the expressions.

    Parameters
    ----------
    threshold
        Minimum distinct/rows to accept.  ``1.0`` means an exact primary key;
        a value below 1.0 accepts an *approximate* key and tolerates up to
        ``(1 - threshold)`` of the rows being duplicate-keyed (real-world data
        often has no clean PK).
    max_width
        Largest composite key to consider.
    max_group
        Reject any candidate whose largest duplicate group exceeds this.  A
        high-uniqueness key can still explode an outer join if one value (a
        null, a sentinel) covers many rows; the global ratio does not bound
        that, the biggest group does.  ``None`` skips the check.
    columns
        Restrict candidate columns to this subset (e.g. columns shared by both
        sides of a diff).  ``None`` considers every column.
    """
    from itertools import combinations

    expr = _as_expr(src)
    cols = list(expr.schema())
    if columns is not None:
        cols = [c for c in cols if c in columns]
    if not cols:
        return None

    aggs = [expr.count().name("__n__")] + [expr[c].nunique().name(c) for c in cols]
    row = expr.aggregate(aggs).execute().iloc[0]
    n = int(row["__n__"])
    if n == 0:
        return None
    distinct = {c: int(row[c]) for c in cols}
    need = threshold * n

    def _accept(combo: tuple[str, ...], d: int) -> dict | None:
        if d < need:
            return None
        mg = _max_group_xorq(expr, list(combo))
        if max_group is not None and mg > max_group:
            return None
        return {"keys": list(combo), "uniqueness": d / n, "max_group": mg, "n": n}

    # Single columns, most-unique first — a passing single beats any composite.
    for c in sorted(cols, key=lambda c: distinct[c], reverse=True):
        result = _accept((c,), distinct[c])
        if result is not None:
            return result

    # Composite keys, shortest first.  Prune with a cheap cardinality-product
    # upper bound before paying for the distinct-tuple count.
    usable = [c for c in cols if distinct[c] > 1]
    for width in range(2, max_width + 1):
        for combo in combinations(usable, width):
            bound = 1
            for c in combo:
                bound *= distinct[c]
                if bound >= need:
                    break
            if bound < need:
                continue
            d = int(expr.select(*combo).distinct().count().execute())
            result = _accept(combo, d)
            if result is not None:
                return result
    return None


def _detect_pk_xorq(src, threshold: float = 1.0, max_width: int = 4, max_group: int | None = None,
        columns: list[str] | None = None) -> list[str] | None:
    """Detected (approximate) primary key for a parquet file or expr, or ``None``.

    Thin wrapper over :func:`_rank_pk_xorq` returning just the key columns.
    See that function for the meaning of ``threshold`` / ``max_group``.
    """
    result = _rank_pk_xorq(
        src, threshold=threshold, max_width=max_width,
        max_group=max_group, columns=columns)
    return list(result["keys"]) if result else None


def _shared_columns_xorq(a, b) -> list[str]:
    """Columns present in both schemas, in ``a``'s order (path or expr)."""
    a_schema = _as_expr(a).schema()
    b_schema = _as_expr(b).schema()
    return [c for c in a_schema if c in b_schema]


def head_diff_xorq(a, b, n: int = 10) -> dict:
    """First N rows of each side + totals, all as xorq expressions."""
    a_expr = _as_expr(a)
    b_expr = _as_expr(b)
    a_df = a_expr.limit(n).execute()
    b_df = b_expr.limit(n).execute()
    a_total = int(a_expr.count().execute())
    b_total = int(b_expr.count().execute())
    return {"before": a_df.to_html(classes="data-table", index=False, border=0),
        "after": b_df.to_html(classes="data-table", index=False, border=0), "n": n, "a_total": a_total,
        "b_total": b_total}


def stats_diff_xorq(a, b) -> list[dict]:
    """Per-column stats for each side (path or expr).

    Each side is one aggregate expression — no DataFrame materialisation.
    """
    a_expr = _as_expr(a)
    b_expr = _as_expr(b)
    cols = list(dict.fromkeys(list(a_expr.schema()) + list(b_expr.schema())))
    a_s = _column_summaries_xorq(a_expr)
    b_s = _column_summaries_xorq(b_expr)
    return [{"name": col, "before": a_s.get(col), "after": b_s.get(col)} for col in cols]


def key_diff_xorq(a, b, keys: list[str] | None = None, threshold: float = 0.98, max_width: int = 4,
        max_group: int | None = 10_000) -> dict | None:
    """Outer-join two sides on a detected (approximate) key (xorq backend).

    ``a`` / ``b`` are parquet paths *or* xorq expressions — the diff composes
    ``expr1`` ⋈ ``expr2`` and lets each side resolve its own cache, never
    reaching for a materialised parquet.  The join key is inferred with
    :func:`_detect_pk_xorq` over the shared columns — preferring a true primary
    key, tolerating an approximate one down to ``threshold`` so real data
    without a clean key still aligns.  ``max_group`` rejects a key whose
    largest duplicate group would risk a many-to-many blowup.  Returns
    ``None`` when no usable key is found.

    Pure ibis: the outer join, the membership counts and the 50-row preview
    are all expressions; nothing larger than the preview is materialised.
    """
    import xorq.vendor.ibis as ibis

    a_expr = _as_expr(a)
    b_expr = _as_expr(b)
    # A caller that already knows the key (e.g. resolved + cached from lineage)
    # passes it in to skip the per-column uniqueness scan entirely.
    if not keys:
        shared = _shared_columns_xorq(a_expr, b_expr)
        keys = _detect_pk_xorq(
            a_expr, threshold=threshold, max_width=max_width,
            max_group=max_group, columns=shared)
        if not keys:
            keys = _detect_pk_xorq(
                b_expr, threshold=threshold, max_width=max_width,
                max_group=max_group, columns=shared)
    if not keys:
        return None
    _require_keys_in_both(keys, list(a_expr.schema()), list(b_expr.schema()))

    a_non_keys = [c for c in a_expr.schema() if c not in keys]
    b_non_keys = [c for c in b_expr.schema() if c not in keys]

    try:
        # The two sides may be bound to different backends (each entry
        # expression is loaded independently); land them on one backend so the
        # outer join is single-engine (no-op when they already share one).
        a_expr, b_expr = _align_backends(a_expr, b_expr)
        # Label each side's non-key columns so they don't collide on the join.
        # Marker columns give a null-safe membership count: a genuine null in a
        # data column must not be mistaken for a non-matching row.
        a_ren = a_expr.rename({f"{c}_before": c for c in a_non_keys}).mutate(__a__=ibis.literal(True))
        b_ren = b_expr.rename({f"{c}_after": c for c in b_non_keys}).mutate(__b__=ibis.literal(True))
        joined = a_ren.outer_join(b_ren, [a_ren[k] == b_ren[k] for k in keys])

        sel = [ibis.coalesce(a_ren[k], b_ren[k]).name(k) for k in keys]
        sel += [joined[f"{c}_before"] for c in a_non_keys]
        sel += [joined[f"{c}_after"] for c in b_non_keys]
        merged = joined.select(*sel)

        # a-side marker null → row only in b ("only_after"); b-side null → only in a.
        counts = joined.aggregate(only_after=joined["__a__"].isnull().sum().cast("int64"),
            only_before=joined["__b__"].isnull().sum().cast("int64"), total=joined.count()).execute().iloc[0]
        only_after = int(counts["only_after"])
        only_before = int(counts["only_before"])
        both = int(counts["total"]) - only_before - only_after
        preview = merged.limit(50).execute()
    except Exception:
        return None

    return {"keys": keys, "only_before": only_before, "only_after": only_after, "matched": both,
        "table_html": preview.to_html(classes="data-table", index=False, border=0)}


# ---------------------------------------------------------------------------
# fast probe — decide whether a key diff is worth running at all
# ---------------------------------------------------------------------------


def probe_diff(a, b, threshold: float = 0.98, max_width: int = 4, max_group: int | None = 10_000) -> dict:
    """Cheap pre-flight for a key diff: is there a simple primary key to join on?

    Runs the same uniqueness-ranked key search the diffs use, over the columns
    shared by ``a`` and ``b``, and returns a verdict the caller checks BEFORE
    paying for a full compare::

        {"can_diff": bool, "keys": list[str] | None, "reason": str}

    When ``can_diff`` is ``False`` the diff should be **stopped**: no column (or
    small composite) is unique enough to join on, so the only available join
    would be a many-to-many cartesian product.  The cost is one uniqueness pass
    per side, which a lazy/parquet backend pushes down — so this is safe to run
    on a large file before deciding whether to materialise the diff.

    The backend is chosen from the input type: pandas DataFrames use the pandas
    detector, polars frames the polars detector, and parquet paths / xorq
    expressions the xorq detector (when xorq is installed, else a polars scan).
    """
    keys = _detect_pk_either(a, b, threshold=threshold, max_width=max_width, max_group=max_group)
    if keys:
        return {"can_diff": True, "keys": keys,
            "reason": f"primary key {keys} reaches uniqueness >= {threshold}"}
    return {"can_diff": False, "keys": None,
        "reason": (f"no key with uniqueness >= {threshold} in the shared columns "
            "(within max_width/max_group) — diff stopped to avoid a many-to-many join")}


def _detect_pk_either(a, b, *, threshold: float, max_width: int, max_group: int | None) -> list[str] | None:
    """Detect a PK on ``a`` (then ``b``) using the backend implied by the input type.

    ``a`` and ``b`` must be the same backend family; a mismatch (e.g. a pandas
    frame against a polars frame or a path) raises ``ValueError`` rather than
    crashing inside a backend with an opaque error.
    """
    if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
        shared = [c for c in a.columns if c in b.columns]
        detect = _detect_pk_pd
    elif _is_polars(a) and _is_polars(b):
        shared = _shared_columns_polars(a, b)
        detect = _detect_pk_polars
    elif isinstance(a, (str, Path)) and isinstance(b, (str, Path)):
        # parquet paths: xorq when available, else a polars lazy scan
        if _has_xorq():
            shared = _shared_columns_xorq(a, b)
            detect = _detect_pk_xorq
        else:
            shared = _shared_columns_polars(a, b)
            detect = _detect_pk_polars
    elif _has_xorq() and _is_xorq_expr(a) and _is_xorq_expr(b):
        shared = _shared_columns_xorq(a, b)
        detect = _detect_pk_xorq
    else:
        raise ValueError(
            "probe_diff needs both sides on the same backend: two pandas DataFrames, two polars "
            f"frames, two parquet paths, or two xorq expressions; got {type(a).__name__} and "
            f"{type(b).__name__}")
    return (detect(a, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared)
        or detect(b, threshold=threshold, max_width=max_width, max_group=max_group, columns=shared))


def _is_xorq_expr(x) -> bool:
    # ibis/xorq expressions expose schema() as a method; polars frames expose
    # .schema as a (non-callable) property and pandas frames have neither.
    return not isinstance(x, (str, Path)) and callable(getattr(x, "schema", None))


def _is_polars(src) -> bool:
    try:
        import polars as pl
    except ImportError:
        return False
    return isinstance(src, (pl.DataFrame, pl.LazyFrame))


def _has_xorq() -> bool:
    try:
        import xorq.api  # noqa: F401
    except ImportError:
        return False
    return True


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
