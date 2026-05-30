import pandas as pd
import pytest

from buckaroo.compare import col_join_dfs


# ---------------------------------------------------------------------------
# _detect_pk_xorq — streaming primary-key detection over a parquet file
# ---------------------------------------------------------------------------


def _write_parquet(tmp_path, df):
    pytest.importorskip("pyarrow")
    path = tmp_path / "t.parquet"
    df.to_parquet(path)
    return path


def test_detect_pk_single_column(tmp_path):
    """A single unique column is found (and preferred over composites)."""
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq

    n = 20_000
    df = pd.DataFrame({"ride_id": [f"R{i:08d}" for i in range(n)], "member_casual": (["member", "casual"] * (n // 2)),
        "rideable_type": (["classic", "electric", "docked"] * (n // 3 + 1))[:n]})
    path = _write_parquet(tmp_path, df)
    assert _detect_pk_xorq(path) == ["ride_id"]


def test_detect_pk_none_for_low_cardinality(tmp_path):
    """No near-unique key → None (the citibike cartesian-blowup guard).

    Old _infer_keys would pick a low-cardinality categorical (e.g.
    member_casual) and produce a many-to-many join.
    """
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq

    n = 20_000
    df = pd.DataFrame({"member_casual": (["member", "casual"] * (n // 2)),
        "rideable_type": (["classic", "electric", "docked"] * (n // 3 + 1))[:n],
        "duration": [i % 600 for i in range(n)]})
    path = _write_parquet(tmp_path, df)
    assert _detect_pk_xorq(path) is None


def test_detect_pk_composite(tmp_path):
    """A key unique only in combination is found; neither column alone is."""
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq

    # station_id x as_of_date: 100 stations over 50 dates, one row each.
    rows = [(s, d) for s in range(100) for d in range(50)]
    df = pd.DataFrame({"station_id": [r[0] for r in rows], "as_of_date": [f"2024-{r[1]:02d}" for r in rows],
        "reading": [r[0] + r[1] for r in rows]})
    path = _write_parquet(tmp_path, df)
    assert _detect_pk_xorq(path) == ["station_id", "as_of_date"]


def test_detect_pk_empty(tmp_path):
    """An empty frame yields no key rather than crashing."""
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq

    df = pd.DataFrame({"a": pd.Series([], dtype="int64"), "b": pd.Series([], dtype="str")})
    path = _write_parquet(tmp_path, df)
    assert _detect_pk_xorq(path) is None


def test_detect_pk_approximate_tolerance(tmp_path):
    """An approximate key (a few duplicates) is accepted below threshold 1.0."""
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq

    # 10_000 rows, 100 keys duplicated once each → distinct 9_900, uniqueness 0.99.
    # "v" is a low-cardinality filler so "k" is the only near-key candidate.
    n = 10_000
    ids = list(range(n - 100)) + list(range(100))
    df = pd.DataFrame({"k": ids, "v": [i % 10 for i in range(n)]})
    path = _write_parquet(tmp_path, df)

    assert _detect_pk_xorq(path, threshold=1.0) is None        # not an exact PK
    assert _detect_pk_xorq(path, threshold=0.98) == ["k"]      # but a usable near-key


def test_detect_pk_max_group_guard(tmp_path):
    """A high-uniqueness but skewed key is rejected when its biggest group is too large."""
    pytest.importorskip("xorq")
    from buckaroo.compare import _detect_pk_xorq, _rank_pk_xorq

    # 10_000 rows: 9_500 unique values + one sentinel covering 500 rows.
    n = 10_000
    ids = [f"K{i:06d}" for i in range(n - 500)] + ["DUP"] * 500
    df = pd.DataFrame({"k": ids})
    path = _write_parquet(tmp_path, df)

    # Uniqueness clears 0.95, but one value covers 500 rows → would blow up a join.
    ranked = _rank_pk_xorq(path, threshold=0.95, max_group=None)
    assert ranked["keys"] == ["k"] and ranked["max_group"] == 500

    assert _detect_pk_xorq(path, threshold=0.95, max_group=100) is None      # guarded out
    assert _detect_pk_xorq(path, threshold=0.95, max_group=1_000) == ["k"]   # within cap


def test_xorq_diff_accepts_expressions(tmp_path):
    """The xorq diff composes expr1 ⋈ expr2 — not just parquet paths.

    Passing expressions (each of which could carry its own .cache() node) must
    give the same result as passing the file paths.
    """
    pytest.importorskip("xorq")
    import xorq.api as xo
    from buckaroo.compare import key_diff_xorq, stats_diff_xorq, head_diff_xorq

    n = 1_500
    base = pd.DataFrame({"ride_id": [f"R{i:05d}" for i in range(n)], "minutes": [i % 60 for i in range(n)]})
    a_path = tmp_path / "a.parquet"
    base.to_parquet(a_path)
    b = base.copy()
    b.loc[0, "minutes"] = 999
    b_path = tmp_path / "b.parquet"
    b.to_parquet(b_path)

    a_expr = xo.deferred_read_parquet(str(a_path))
    b_expr = xo.deferred_read_parquet(str(b_path))

    keyed = key_diff_xorq(a_expr, b_expr)
    assert keyed["keys"] == ["ride_id"]
    assert keyed["matched"] == n and keyed["only_before"] == 0 and keyed["only_after"] == 0
    # same as via paths
    assert key_diff_xorq(a_path, b_path)["matched"] == n
    # stats / head also accept expressions
    assert any(s["name"] == "minutes" for s in stats_diff_xorq(a_expr, b_expr))
    assert head_diff_xorq(a_expr, b_expr)["a_total"] == n


def test_key_diff_xorq_uses_detected_pk(tmp_path):
    """key_diff_xorq joins on the detected PK, not a low-card categorical.

    With a real unique key present, matched rows align 1:1 (no blowup);
    with only low-card columns, it declines to join (returns None).
    """
    pytest.importorskip("xorq")
    from buckaroo.compare import key_diff_xorq

    n = 2_000
    base = pd.DataFrame({"ride_id": [f"R{i:06d}" for i in range(n)], "member_casual": (["member", "casual"] * (n // 2)),
        "minutes": [i % 60 for i in range(n)]})
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a_path = tmp_path / "a" / "t.parquet"
    b_path = tmp_path / "b" / "t.parquet"
    base.to_parquet(a_path)
    b = base.copy()
    b.loc[0, "minutes"] = 999  # one changed row
    b.to_parquet(b_path)

    keyed = key_diff_xorq(a_path, b_path)
    assert keyed is not None
    assert keyed["keys"] == ["ride_id"]
    # 1:1 alignment — matched count equals row count, no cartesian explosion.
    assert keyed["matched"] == n
    assert keyed["only_before"] == 0
    assert keyed["only_after"] == 0


# ---------------------------------------------------------------------------
# pandas / polars key detection — the same algorithm as the xorq backend, so
# all three pick the same key (or decline) on the same data.
# ---------------------------------------------------------------------------


def _pk_frames():
    n = 4_000
    uniq = pd.DataFrame({"ride_id": [f"R{i:06d}" for i in range(n)],
        "member_casual": (["member", "casual"] * (n // 2)),
        "rideable_type": (["classic", "electric", "docked"] * (n // 3 + 1))[:n]})
    lowcard = pd.DataFrame({"member_casual": (["member", "casual"] * (n // 2)),
        "rideable_type": (["classic", "electric", "docked"] * (n // 3 + 1))[:n],
        "duration": [i % 600 for i in range(n)]})
    rows = [(s, d) for s in range(80) for d in range(50)]
    comp = pd.DataFrame({"station_id": [r[0] for r in rows], "as_of_date": [f"2024-{r[1]:02d}" for r in rows],
        "reading": [r[0] + r[1] for r in rows]})
    return uniq, lowcard, comp


def _detect(backend, df, **kw):
    from buckaroo import compare as C
    if backend == "pandas":
        return C._detect_pk_pd(df, **kw)
    pl = pytest.importorskip("polars")
    return C._detect_pk_polars(pl.from_pandas(df), **kw)


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_detect_pk_contract(backend):
    """Single unique col wins; low-cardinality declines (None); composite found —
    matching the xorq _detect_pk tests above."""
    uniq, lowcard, comp = _pk_frames()
    assert _detect(backend, uniq) == ["ride_id"]
    assert _detect(backend, lowcard) is None
    assert _detect(backend, comp) == ["station_id", "as_of_date"]


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_detect_pk_approximate_and_max_group(backend):
    n = 4_000
    approx = pd.DataFrame({"k": list(range(n - 40)) + list(range(40)), "v": [i % 10 for i in range(n)]})
    assert _detect(backend, approx, threshold=1.0) is None     # 40 dups -> not exact
    assert _detect(backend, approx, threshold=0.98) == ["k"]   # but a usable near-key

    skew = pd.DataFrame({"k": [f"K{i:06d}" for i in range(n - 200)] + ["DUP"] * 200})
    assert _detect(backend, skew, threshold=0.95, max_group=50) is None       # one value covers 200 rows
    assert _detect(backend, skew, threshold=0.95, max_group=1_000) == ["k"]   # within cap


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_key_diff_uses_detected_pk_or_stops(backend):
    """key_diff joins on the detected unique key (1:1, no blowup); with only
    low-cardinality columns it stops and returns None."""
    from buckaroo import compare as C
    n = 2_000
    a = pd.DataFrame({"id": range(n), "cat": [i % 10 for i in range(n)], "val": list(range(n))})
    b = a.copy()
    b.loc[0, "val"] = 999
    lowcard = pd.DataFrame({"cat": [i % 5 for i in range(n)], "grp": [i % 7 for i in range(n)]})
    if backend == "pandas":
        kd, wrap = C.key_diff, (lambda df: df)
    else:
        pl = pytest.importorskip("polars")
        kd, wrap = C.key_diff_polars, (lambda df: pl.from_pandas(df))
    keyed = kd(wrap(a), wrap(b))
    assert keyed is not None and keyed["keys"] == ["id"]
    assert keyed["matched"] == n and keyed["only_before"] == 0 and keyed["only_after"] == 0
    assert kd(wrap(lowcard), wrap(lowcard)) is None  # no simple PK -> stop, do not explode


@pytest.mark.parametrize("backend", ["pandas", "polars", "xorq"])
def test_key_diff_membership_null_safe(backend, tmp_path):
    """A genuine null in a matched row's shared column must not be miscounted as
    a non-matching row (regression for the first-non-key-column null probe)."""
    from buckaroo import compare as C
    n = 100
    a = pd.DataFrame({"id": [f"k{i}" for i in range(n)], "val": [None] + list(range(n - 1))})
    b = a.copy()
    b.loc[0, "val"] = 1000
    if backend == "pandas":
        res = C.key_diff(a, b)
    elif backend == "polars":
        pl = pytest.importorskip("polars")
        res = C.key_diff_polars(pl.from_pandas(a), pl.from_pandas(b))
    else:
        pytest.importorskip("xorq")
        ap, bp = tmp_path / "a.parquet", tmp_path / "b.parquet"
        a.to_parquet(ap)
        b.to_parquet(bp)
        res = C.key_diff_xorq(ap, bp)
    assert res["matched"] == n and res["only_before"] == 0 and res["only_after"] == 0


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_probe_diff_gates(backend):
    """probe_diff says can_diff only when a simple primary key exists."""
    from buckaroo.compare import probe_diff
    n = 1_000
    keyed = pd.DataFrame({"id": range(n), "cat": [i % 10 for i in range(n)]})
    lowcard = pd.DataFrame({"cat": [i % 5 for i in range(n)], "grp": [i % 7 for i in range(n)]})
    if backend == "polars":
        pl = pytest.importorskip("polars")
        keyed, lowcard = pl.from_pandas(keyed), pl.from_pandas(lowcard)
    good = probe_diff(keyed, keyed)
    assert good["can_diff"] is True and good["keys"] == ["id"]
    bad = probe_diff(lowcard, lowcard)
    assert bad["can_diff"] is False and bad["keys"] is None


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_stats_diff_distinct_excludes_null(backend):
    """distinct excludes null on pandas and polars alike (matches xorq nunique)."""
    from buckaroo import compare as C
    df = pd.DataFrame({"g": ["x", "y", None, None, "x"], "v": [1, 2, 3, 4, 5]})
    if backend == "pandas":
        rows = C.stats_diff(df, df)
    else:
        pl = pytest.importorskip("polars")
        rows = C.stats_diff_polars(pl.from_pandas(df), pl.from_pandas(df))
    g = next(r for r in rows if r["name"] == "g")["before"]
    assert g["distinct"] == 2 and g["nulls"] == 2


def test_probe_diff_rejects_mismatched_backends():
    """probe_diff raises a clear error (not an opaque crash) on mixed inputs."""
    pl = pytest.importorskip("polars")
    from buckaroo.compare import probe_diff
    a = pd.DataFrame({"id": [1, 2, 3]})
    with pytest.raises(ValueError, match="same backend"):
        probe_diff(a, pl.from_pandas(a))


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_key_diff_bad_explicit_key_raises(backend):
    """An explicit key absent from a side is a clear error, not a silent None."""
    from buckaroo import compare as C
    a = pd.DataFrame({"id": [1, 2, 3], "v": [1, 2, 3]})
    b = pd.DataFrame({"id": [1, 2, 3], "v": [1, 2, 9]})
    if backend == "pandas":
        kd, wrap = C.key_diff, (lambda d: d)
    else:
        pl = pytest.importorskip("polars")
        kd, wrap = C.key_diff_polars, (lambda d: pl.from_pandas(d))
    with pytest.raises(ValueError, match="not present in both"):
        kd(wrap(a), wrap(b), keys=["nope"])


def test_single_non_a_join_key():
    """col_join_dfs works with a join key that is not named 'a'."""
    df1 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 25, 30]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert "membership" in m_df.columns
    # All rows matched
    assert (m_df["membership"] == 3).all()
    # One diff in 'val' (row where id=2)
    assert eqs["val"]["diff_count"] == 1
    assert eqs["id"]["diff_count"] == "join_key"


def test_multi_key_join():
    """col_join_dfs works with multiple join columns."""
    df1 = pd.DataFrame(
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 200, 300]})
    df2 = pd.DataFrame(
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 250, 300]})

    m_df, overrides, eqs = col_join_dfs(
        df1, df2, join_columns=["account_id", "as_of_date"], how="outer")

    assert len(m_df) == 3
    assert (m_df["membership"] == 3).all()
    assert eqs["amount"]["diff_count"] == 1
    # Both join columns reported as join_key
    assert eqs["account_id"]["diff_count"] == "join_key"
    assert eqs["as_of_date"]["diff_count"] == "join_key"
    # Each join column gets its own color config
    assert "account_id" in overrides
    assert "as_of_date" in overrides


def test_outer_join_membership():
    """Rows only in one side get correct membership values."""
    df1 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pd.DataFrame({"id": [2, 3, 4], "val": [20, 30, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert len(m_df) == 4  # ids 1,2,3,4
    membership = m_df.set_index("id")["membership"]
    assert membership[1] == 1  # df1 only
    assert membership[2] == 3  # both
    assert membership[3] == 3  # both
    assert membership[4] == 2  # df2 only


def test_reordered_rows():
    """Diff stats are correct even when row order differs between df1 and df2."""
    df1 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pd.DataFrame({"id": [3, 1, 2], "val": [30, 10, 20]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    # No diffs — values match after key alignment
    assert eqs["val"]["diff_count"] == 0
    assert (m_df["membership"] == 3).all()


def test_one_sided_extra_rows():
    """Extra columns only in one df are reported correctly."""
    df1 = pd.DataFrame({"id": [1, 2], "x": [10, 20]})
    df2 = pd.DataFrame({"id": [1, 2], "y": [30, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert eqs["x"]["diff_count"] == "df_1"
    assert eqs["y"]["diff_count"] == "df_2"


def test_string_join_columns_normalized():
    """A single string join_columns is accepted and normalized to a list."""
    df1 = pd.DataFrame({"key": [1, 2], "val": [10, 20]})
    df2 = pd.DataFrame({"key": [1, 2], "val": [10, 25]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns="key", how="inner")

    assert eqs["val"]["diff_count"] == 1


def test_sentinel_column_rejected():
    """DataFrames containing '|df2' in column names are rejected."""
    df1 = pd.DataFrame({"id": [1], "bad|df2": [10]})
    df2 = pd.DataFrame({"id": [1], "val": [20]})

    with pytest.raises(ValueError, match="\\|df2"):
        col_join_dfs(df1, df2, join_columns=["id"], how="outer")


def test_inner_join():
    """Inner join only keeps matched rows."""
    df1 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pd.DataFrame({"id": [2, 3, 4], "val": [20, 35, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="inner")

    assert len(m_df) == 2  # ids 2, 3
    assert (m_df["membership"] == 3).all()
    # id=3: val 30 vs 35 → 1 diff
    assert eqs["val"]["diff_count"] == 1


def test_null_values_in_data():
    """Null-heavy comparisons don't crash and report diffs."""
    df1 = pd.DataFrame({"id": [1, 2, 3], "val": [None, 20, None]})
    df2 = pd.DataFrame({"id": [1, 2, 3], "val": [None, None, 30]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert (m_df["membership"] == 3).all()
    # At least some diffs expected (rows 2 and 3 differ)
    assert eqs["val"]["diff_count"] >= 2


def test_non_string_column_labels():
    """Non-string column labels (e.g. integers) don't crash sentinel check."""
    df1 = pd.DataFrame({0: [1, 2], 1: [10, 20]})
    df2 = pd.DataFrame({0: [1, 2], 1: [10, 25]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=[0], how="outer")

    assert (m_df["membership"] == 3).all()


def test_duplicate_join_keys_rejected():
    """Duplicate join keys in either dataframe raise ValueError."""
    df1 = pd.DataFrame({"id": [1, 1, 2], "val": [10, 20, 30]})
    df2 = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})

    with pytest.raises(ValueError, match="Duplicate join keys"):
        col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    # Also reject duplicates in df2
    df1_ok = pd.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2_dup = pd.DataFrame({"id": [1, 1, 2], "val": [10, 20, 30]})

    with pytest.raises(ValueError, match="Duplicate join keys"):
        col_join_dfs(df1_ok, df2_dup, join_columns=["id"], how="outer")


def test_merge_column_in_input_rejected():
    """A column named __buckaroo_merge in the input is rejected."""
    df1 = pd.DataFrame({"id": [1], "__buckaroo_merge": [10]})
    df2 = pd.DataFrame({"id": [1], "val": [20]})

    with pytest.raises(ValueError, match="__buckaroo_merge"):
        col_join_dfs(df1, df2, join_columns=["id"], how="outer")
