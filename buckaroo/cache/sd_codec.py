"""Lossless summary-dict (``merged_sd``) codec for the initial-load cache.

Persists ``merged_sd`` to parquet **without pickle**, round-tripping every value
type the backends emit. The trick is a type-tagged JSON encoding: JSON-native
values pass through; the rest (``pd.Timestamp`` / ``pd.Timedelta``, stdlib
``datetime`` / ``date`` / ``time`` / ``timedelta``, ``Decimal``, ``bytes``, numpy
scalars, NaN, MultiIndex tuples) are wrapped in a small ``{__bk_t__: tag, v: ...}``
envelope and reconstructed on decode. The tagged JSON is stored as a single cell
in a parquet container, honouring "persist via parquet".

``value_counts`` is dropped — nothing at replay recomputes from it and the
frontend never reads it (see #880). numpy scalars decode to native Python
(value-lossless); only types where Python-native would lose information get a
tag. See docs/initial-load-cache-design.md.
"""
import base64
import datetime
import decimal
import io
import json
import math
from typing import Any

import numpy as np
import pandas as pd

_TAG = '__bk_t__'  # distinctive sentinel; real stat keys never collide with it
_COL = 'sd_json'


def _enc(v: Any) -> Any:
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):  # before int — bool is an int subclass
        return v
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):  # np.float64 is a float subclass
        f = float(v)
        return {_TAG: 'nan'} if math.isnan(f) else f
    if isinstance(v, np.datetime64):
        return {_TAG: 'pd.Timestamp', 'v': pd.Timestamp(v).isoformat()}
    if isinstance(v, pd.Timestamp):  # before datetime — Timestamp is a datetime subclass
        return {_TAG: 'pd.Timestamp', 'v': v.isoformat()}
    if isinstance(v, pd.Timedelta):  # before timedelta — Timedelta is a timedelta subclass
        return {_TAG: 'pd.Timedelta', 'v': v.total_seconds()}
    if isinstance(v, datetime.datetime):  # before date — datetime is a date subclass
        return {_TAG: 'datetime', 'v': v.isoformat()}
    if isinstance(v, datetime.date):
        return {_TAG: 'date', 'v': v.isoformat()}
    if isinstance(v, datetime.time):
        return {_TAG: 'time', 'v': v.isoformat()}
    if isinstance(v, datetime.timedelta):
        return {_TAG: 'timedelta', 'v': v.total_seconds()}
    if isinstance(v, decimal.Decimal):
        return {_TAG: 'decimal', 'v': str(v)}
    if isinstance(v, bytes):
        return {_TAG: 'bytes', 'v': base64.b64encode(v).decode('ascii')}
    if isinstance(v, np.ndarray):
        return [_enc(x) for x in v.tolist()]
    if isinstance(v, tuple):
        return {_TAG: 'tuple', 'v': [_enc(x) for x in v]}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _enc(x) for k, x in v.items()}
    return {_TAG: 'str', 'v': str(v)}  # lossy fallback for anything exotic


def _dec(v: Any) -> Any:
    if isinstance(v, dict):
        tag = v.get(_TAG)
        if tag is None:
            return {k: _dec(x) for k, x in v.items()}
        if tag == 'nan':
            return float('nan')
        if tag == 'pd.Timestamp':
            return pd.Timestamp(v['v'])
        if tag == 'pd.Timedelta':
            return pd.Timedelta(seconds=v['v'])
        if tag == 'datetime':
            return datetime.datetime.fromisoformat(v['v'])
        if tag == 'date':
            return datetime.date.fromisoformat(v['v'])
        if tag == 'time':
            return datetime.time.fromisoformat(v['v'])
        if tag == 'timedelta':
            return datetime.timedelta(seconds=v['v'])
        if tag == 'decimal':
            return decimal.Decimal(v['v'])
        if tag == 'bytes':
            return base64.b64decode(v['v'])
        if tag == 'tuple':
            return tuple(_dec(x) for x in v['v'])
        if tag == 'str':
            return v['v']
        return v
    if isinstance(v, list):
        return [_dec(x) for x in v]
    return v


def serialize_sd(sd: dict) -> bytes:
    """Encode ``merged_sd`` (minus ``value_counts``) to parquet bytes, losslessly."""
    clean = {col: {k: val for k, val in (cm or {}).items() if k != 'value_counts'}
        for col, cm in sd.items()}
    payload = json.dumps(_enc(clean))
    buf = io.BytesIO()
    pd.DataFrame({_COL: [payload]}).to_parquet(buf, index=False)
    return buf.getvalue()


def deserialize_sd(data: bytes) -> dict:
    """Inverse of ``serialize_sd``."""
    df = pd.read_parquet(io.BytesIO(data))
    return _dec(json.loads(df[_COL].iloc[0]))
