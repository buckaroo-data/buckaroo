import pandas as pd


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
                f"and can't be used in a dataframe passed in, {col} violates that constraint"
            )

    df1_name, df2_name = "df_1", "df_2"

    # Validate join keys are unique in each dataframe to prevent cartesian explosion
    if df1[join_columns].duplicated().any():
        raise ValueError(
            f"Duplicate join keys found in df1 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison."
        )
    if df2[join_columns].duplicated().any():
        raise ValueError(
            f"Duplicate join keys found in df2 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison."
        )

    # Merge first so diff stats are computed on key-aligned rows
    m_df = pd.merge(
        df1, df2, on=join_columns, how=how, suffixes=["", df2_suffix],
        indicator=_indicator_col,
    )

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
                        (m_df.loc[both_mask, m_df_col] != m_df.loc[both_mask, df2_col]).sum()
                    )
                }
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
            "color_map_config": {
                "color_rule": "color_categorical",
                "map_name": pk_map,
                "val_column": "membership",
            }
        }

    return m_df, column_config_overrides, eqs
