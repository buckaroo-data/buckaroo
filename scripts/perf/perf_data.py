"""Synthetic dataframes for perf testing.

Each generator returns a pandas dataframe; convert to polars via .pl() helper.
The same numpy arrays back both so pandas/polars comparisons are fair.
"""
from __future__ import annotations

import string

import numpy as np
import pandas as pd
import polars as pl


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _unique_strings(n: int, rng: np.random.Generator) -> np.ndarray:
    """n strings, all distinct. ~16-char alnum ids."""
    alphabet = np.array(list(string.ascii_lowercase + string.digits))
    raw = rng.choice(alphabet, size=(n, 16))
    return np.array(["".join(row) for row in raw], dtype=object)


def _repeating_strings(n: int, n_distinct: int, rng: np.random.Generator) -> np.ndarray:
    """n strings drawn from a pool of n_distinct values (zipfian-ish)."""
    pool = _unique_strings(n_distinct, rng)
    weights = 1.0 / (1.0 + np.arange(n_distinct))
    weights /= weights.sum()
    idx = rng.choice(n_distinct, size=n, p=weights)
    return pool[idx]


def make_pandas(n_rows: int, *, seed: int = 42) -> pd.DataFrame:
    """Build a pandas df with a representative mix of column kinds."""
    rng = _rng(seed)
    return pd.DataFrame({
        "int_col": rng.integers(0, 1_000_000, size=n_rows),
        "float_col": rng.normal(size=n_rows),
        "float_with_nan": np.where(
            rng.random(n_rows) < 0.05,
            np.nan,
            rng.normal(size=n_rows),
        ),
        "bool_col": rng.random(n_rows) < 0.3,
        "str_unique": _unique_strings(n_rows, rng),
        "str_low_card": _repeating_strings(n_rows, 10, rng),
        "str_med_card": _repeating_strings(n_rows, 1_000, rng),
        "str_high_card": _repeating_strings(n_rows, 50_000, rng),
    })


def make_polars(n_rows: int, *, seed: int = 42) -> pl.DataFrame:
    """Build a polars df from the same arrays as make_pandas."""
    return pl.from_pandas(make_pandas(n_rows, seed=seed))


COL_KIND_LABELS = {"int_col": "int", "float_col": "float", "float_with_nan": "float (5% nan)", "bool_col": "bool",
    "str_unique": "string unique", "str_low_card": "string low-card (10)", "str_med_card": "string med-card (1k)",
    "str_high_card": "string high-card (50k)"}
