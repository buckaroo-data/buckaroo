import pandas as pd
import pytest

from buckaroo.compare import col_join_dfs


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
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 200, 300]}
    )
    df2 = pd.DataFrame(
        {"account_id": [1, 1, 2], "as_of_date": ["2024-01", "2024-02", "2024-01"], "amount": [100, 250, 300]}
    )

    m_df, overrides, eqs = col_join_dfs(
        df1, df2, join_columns=["account_id", "as_of_date"], how="outer"
    )

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
