import numpy as np
import pandas as pd


def int_digits(n):
    if pd.isna(n):
        return 1
    if np.isnan(n):
        return 1
    if n == 0:
        return 1
    if np.sign(n) == -1:
        return int(np.floor(np.log10(np.abs(n)))) + 2
    return int(np.floor(np.log10(n)+1))