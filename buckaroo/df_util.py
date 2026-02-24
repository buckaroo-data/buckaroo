from __future__ import annotations
from typing import Iterable, Union, List, Tuple, Dict, TYPE_CHECKING
from typing_extensions import TypeAlias

if TYPE_CHECKING:
    import pandas as pd

ColIdentifier:TypeAlias = Union[Iterable[str], str]

def to_digits(n, b) -> List[int]:
    """Convert a positive number n to its digit representation in base b."""
    if n == 0:
        return [0]
    digits: List[int] = []
    while n > 0:
        digits.insert(0, n % b)
        n  = n // b
    
    return digits

def to_chars(n:int) -> str:
    digits = to_digits(n, 26)
    return "".join(map(lambda x: chr(x+97), digits))

def old_col_new_col(df:pd.DataFrame) -> List[Tuple[ColIdentifier, str]]:
    return [(orig_ser_name, to_chars(i))  for i, orig_ser_name  in enumerate(df.columns)]

def get_rewrite_dict(df:pd.DataFrame) -> Dict[str,str]:
    rewrites = dict( old_col_new_col(df))
    return rewrites
