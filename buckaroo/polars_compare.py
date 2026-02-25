import polars as pl


# Polars uses "full" instead of "outer"
_HOW_MAP = {"outer": "full", "full": "full", "inner": "inner", "left": "left", "right": "right"}


def col_join_dfs(df1, df2, join_columns, how):
    """Join two Polars DataFrames and compute column-level diff statistics.

    Parameters
    ----------
    df1, df2 : pl.DataFrame
        The two DataFrames to compare.
    join_columns : str or list[str]
        Column name(s) to join on.
    how : str
        Join type ('inner', 'outer', 'left', 'right').

    Returns
    -------
    m_df : pl.DataFrame
        Merged DataFrame with membership and equality columns.
    column_config_overrides : dict
        Buckaroo column config for styling.
    eqs : dict
        Per-column diff summary.
    """
    if isinstance(join_columns, str):
        join_columns = [join_columns]

    df2_suffix = "|df2"
    for col in df1.columns + df2.columns:
        if df2_suffix in col:
            raise ValueError(
                f"|df2 is a sentinel column name used by this tool, "
                f"and can't be used in a dataframe passed in, {col} violates that constraint"
            )

    df1_name, df2_name = "df_1", "df_2"

    # Validate join keys are unique to prevent cartesian explosion
    if not df1.select(pl.struct(join_columns).is_unique().all()).item():
        raise ValueError(
            f"Duplicate join keys found in df1 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison."
        )
    if not df2.select(pl.struct(join_columns).is_unique().all()).item():
        raise ValueError(
            f"Duplicate join keys found in df2 on columns {join_columns}. "
            "Join keys must be unique in each dataframe for a valid comparison."
        )

    pl_how = _HOW_MAP.get(how, how)

    # Join with coalesce=False so we can detect membership via null patterns on join keys
    m_df = df1.join(df2, on=join_columns, how=pl_how, suffix=df2_suffix, coalesce=False)

    # Compute membership from null patterns on the first join key
    # left key null => df2 only (2), right key null => df1 only (1), both non-null => both (3)
    left_key = join_columns[0]
    right_key = f"{left_key}{df2_suffix}"
    m_df = m_df.with_columns(
        pl.when(pl.col(left_key).is_not_null() & pl.col(right_key).is_not_null())
        .then(3)
        .when(pl.col(left_key).is_not_null())
        .then(1)
        .otherwise(2)
        .cast(pl.Int8)
        .alias("membership")
    )

    # Coalesce join keys and drop suffixed copies
    for jc in join_columns:
        jc_right = f"{jc}{df2_suffix}"
        if jc_right in m_df.columns:
            m_df = m_df.with_columns(pl.coalesce(jc, jc_right).alias(jc)).drop(jc_right)

    # Build unified column order
    col_order = df1.columns.copy()
    for col in df2.columns:
        if col not in col_order:
            col_order.append(col)

    # Compute diff stats from key-aligned rows
    eqs = {}
    both_mask = m_df["membership"] == 3
    m_both = m_df.filter(both_mask)
    for col in col_order:
        if col in join_columns:
            eqs[col] = {"diff_count": "join_key"}
        elif col in df1.columns and col in df2.columns:
            df2_col = f"{col}{df2_suffix}"
            if df2_col in m_df.columns:
                eqs[col] = {
                    "diff_count": int(
                        m_both.select(pl.col(col).ne_missing(pl.col(df2_col)).sum()).item()
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

    both_columns = [c for c in m_df.columns if c.endswith(df2_suffix)]
    for b_col in both_columns:
        a_col = b_col.removesuffix(df2_suffix)
        eq_col = f"{a_col}|eq"
        m_df = m_df.with_columns(
            (pl.col(a_col).eq_missing(pl.col(b_col)).cast(pl.Int8) * 4 + pl.col("membership"))
            .alias(eq_col)
        )

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

    for jc in join_columns:
        column_config_overrides[jc] = {
            "color_map_config": {
                "color_rule": "color_categorical",
                "map_name": eq_map,
                "val_column": "membership",
            }
        }

    return m_df, column_config_overrides, eqs
