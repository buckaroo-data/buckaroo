"""Polars frame suite for the perf/memory smoke harness.

``run_perf_smoke`` is engine-agnostic: pass ``PL_SMOKE_FRAME_MAKERS`` as its
``frames`` with a polars stat list (``PL_ANALYSIS_V2``) and the same wrap,
scales and limits apply — polars stats run through the same ``StatPipeline``.
Peak-memory findings on polars rely on the native RSS tracker in
``perf_smoke``; tracemalloc cannot see polars' Rust-side allocations.

Frames mirror ``SMOKE_FRAME_MAKERS`` via ``pl.from_pandas`` so both engines
see the same data. The shapes translate to native polars dtypes: unhashable
cells become ``List``/``Struct`` columns, Decimal becomes ``pl.Decimal``,
categorical becomes ``pl.Categorical``.
"""
from typing import Callable, Dict

import polars as pl

from .perf_smoke import DEFAULT_ROWS, SMOKE_FRAME_MAKERS


def _from_pandas_maker(pd_maker: Callable) -> Callable:
    def make(rows: int = DEFAULT_ROWS, seed: int = 42) -> pl.DataFrame:
        return pl.from_pandas(pd_maker(rows, seed))
    return make


PL_SMOKE_FRAME_MAKERS: Dict[str, Callable[..., pl.DataFrame]] = {
    name: _from_pandas_maker(maker) for name, maker in SMOKE_FRAME_MAKERS.items()}
