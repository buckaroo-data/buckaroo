import polars as pl
import pytest

from buckaroo.polars_compare import col_join_dfs


def test_single_join_key():
    """col_join_dfs works with a single join key."""
    df1 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 25, 30]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert "membership" in m_df.columns
    assert (m_df["membership"] == 3).all()
    assert eqs["val"]["diff_count"] == 1
    assert eqs["id"]["diff_count"] == "join_key"


def test_multi_key_join():
    """col_join_dfs works with multiple join columns."""
    df1 = pl.DataFrame(
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 200, 300]}
    )
    df2 = pl.DataFrame(
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 250, 300]}
    )

    m_df, overrides, eqs = col_join_dfs(
        df1, df2, join_columns=["account_id", "as_of_date"], how="outer"
    )

    assert m_df.height == 3
    assert (m_df["membership"] == 3).all()
    assert eqs["amount"]["diff_count"] == 1
    assert eqs["account_id"]["diff_count"] == "join_key"
    assert eqs["as_of_date"]["diff_count"] == "join_key"
    assert "account_id" in overrides
    assert "as_of_date" in overrides


def test_outer_join_membership():
    """Rows only in one side get correct membership values."""
    df1 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [2, 3, 4], "val": [20, 30, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert m_df.height == 4
    rows = {row["id"]: row["membership"] for row in m_df.iter_rows(named=True)}
    assert rows[1] == 1  # df1 only
    assert rows[2] == 3  # both
    assert rows[3] == 3  # both
    assert rows[4] == 2  # df2 only


def test_reordered_rows():
    """Diff stats are correct even when row order differs."""
    df1 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [3, 1, 2], "val": [30, 10, 20]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert eqs["val"]["diff_count"] == 0
    assert (m_df["membership"] == 3).all()


def test_one_sided_extra_columns():
    """Columns only in one df are reported correctly."""
    df1 = pl.DataFrame({"id": [1, 2], "x": [10, 20]})
    df2 = pl.DataFrame({"id": [1, 2], "y": [30, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert eqs["x"]["diff_count"] == "df_1"
    assert eqs["y"]["diff_count"] == "df_2"


def test_string_join_columns_normalized():
    """A single string join_columns is accepted."""
    df1 = pl.DataFrame({"key": [1, 2], "val": [10, 20]})
    df2 = pl.DataFrame({"key": [1, 2], "val": [10, 25]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns="key", how="inner")

    assert eqs["val"]["diff_count"] == 1


def test_sentinel_column_rejected():
    """DataFrames containing '|df2' in column names are rejected."""
    df1 = pl.DataFrame({"id": [1], "bad|df2": [10]})
    df2 = pl.DataFrame({"id": [1], "val": [20]})

    with pytest.raises(ValueError, match="\\|df2"):
        col_join_dfs(df1, df2, join_columns=["id"], how="outer")


def test_inner_join():
    """Inner join only keeps matched rows."""
    df1 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [2, 3, 4], "val": [20, 35, 40]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="inner")

    assert m_df.height == 2
    assert (m_df["membership"] == 3).all()
    assert eqs["val"]["diff_count"] == 1


def test_null_values_in_data():
    """Null-heavy comparisons don't crash and report diffs."""
    df1 = pl.DataFrame({"id": [1, 2, 3], "val": [None, 20, None]})
    df2 = pl.DataFrame({"id": [1, 2, 3], "val": [None, None, 30]})

    m_df, overrides, eqs = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    assert (m_df["membership"] == 3).all()
    assert eqs["val"]["diff_count"] >= 2


def test_duplicate_join_keys_rejected():
    """Duplicate join keys raise ValueError."""
    df1 = pl.DataFrame({"id": [1, 1, 2], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})

    with pytest.raises(ValueError, match="Duplicate join keys"):
        col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    df1_ok = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    df2_dup = pl.DataFrame({"id": [1, 1, 2], "val": [10, 20, 30]})

    with pytest.raises(ValueError, match="Duplicate join keys"):
        col_join_dfs(df1_ok, df2_dup, join_columns=["id"], how="outer")


def test_how_outer_alias():
    """Both 'outer' and 'full' are accepted as how values."""
    df1 = pl.DataFrame({"id": [1, 2], "val": [10, 20]})
    df2 = pl.DataFrame({"id": [2, 3], "val": [20, 30]})

    m1, _, _ = col_join_dfs(df1, df2, join_columns=["id"], how="outer")
    m2, _, _ = col_join_dfs(df1, df2, join_columns=["id"], how="full")

    assert m1.height == m2.height == 3


def test_nullable_join_key_membership():
    """Membership is correct when the join key itself contains nulls.

    Polars does not match null keys (null != null in join semantics),
    so null-keyed rows appear as one-sided. The marker-based membership
    detection must still classify them correctly as df1-only / df2-only.
    """
    df1 = pl.DataFrame({"id": [None, 2, 3], "val": [10, 20, 30]})
    df2 = pl.DataFrame({"id": [None, 3, 4], "val": [10, 30, 40]})

    m_df, _, _ = col_join_dfs(df1, df2, join_columns=["id"], how="outer")

    rows_by_id = {}
    for row in m_df.iter_rows(named=True):
        key = (row["id"], row["membership"])
        rows_by_id[key] = True

    assert (3, 3) in rows_by_id   # both
    assert (2, 1) in rows_by_id   # df1 only
    assert (4, 2) in rows_by_id   # df2 only
    # Null keys don't match in polars joins — each null-keyed row is one-sided
    assert (None, 1) in rows_by_id  # df1's null key → df1 only
    assert (None, 2) in rows_by_id  # df2's null key → df2 only
