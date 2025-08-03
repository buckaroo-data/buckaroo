import pandas as pd
import numpy as np




def filter_outliers(df):
    """
    Filter DataFrame to keep only rows where values fall in the 1st or 99th percentile
    for any numeric column.

    Parameters:
    -----------
    df : pandas.DataFrame
        Input DataFrame to filter

    Returns:
    --------
    pandas.DataFrame
        Filtered DataFrame containing only rows with values in 1st or 99th percentile
        for any numeric column
    """
    # Get only numeric columns
    numeric_cols = df.select_dtypes(include=["int64", "float64"]).columns

    # Initialize mask as all False
    mask = pd.Series(False, index=df.index)

    # For each numeric column
    for col in numeric_cols:
        # Calculate 1st and 99th percentiles
        p1 = df[col].quantile(0.01)
        p99 = df[col].quantile(0.99)

        # Update mask to include rows where values are in 1st or 99th percentile
        mask |= (df[col] <= p1) | (df[col] >= p99)

    # Return filtered DataFrame
    return df[mask]

def test_outliers_filter():
    # Example usage
    df = pd.DataFrame({
        "A": range(100),
        "B": np.random.normal(0, 1, 100),
        "C": ["text"] * 100,  # non-numeric column will be ignored
        }
    )
    filtered_df = filter_outliers(df)
    assert filtered_df
