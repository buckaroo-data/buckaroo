"""DfStatsV2 — drop-in replacement for DfStats using StatPipeline.

Wraps StatPipeline to match the DfStats interface used by DataFlow,
PandasAutocleaning, and other consumers.

Usage::

    from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2

    # Same interface as DfStats
    stats = DfStatsV2(my_df, [TypingStats, DefaultSummaryStats, Histogram])
    stats.sdf  # -> SDType
    stats.errs  # -> ErrDict (v1 compatible)
"""
from __future__ import annotations

from typing import Type

import numpy as np
import pandas as pd

from .col_analysis import AObjs, ColAnalysis
from .stat_pipeline import StatPipeline
from .utils import FAST_SUMMARY_WHEN_GREATER
from .safe_summary_df import output_full_reproduce


class DfStatsV2:
    """Drop-in replacement for DfStats. Uses StatPipeline internally.

    Maintains the same interface as DfStats so that DataFlow,
    autocleaning, and all other consumers work without changes.
    """

    ap_class = StatPipeline

    @classmethod
    def verify_analysis_objects(cls, col_analysis_objs: AObjs) -> None:
        """Validate analysis objects without processing data."""
        cls.ap_class(col_analysis_objs)

    def __init__(
        self,
        df_stats_df: pd.DataFrame,
        col_analysis_objs: AObjs,
        operating_df_name: str = None,
        debug: bool = False,
    ) -> None:
        self.df = self.get_operating_df(df_stats_df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = self.ap_class(col_analysis_objs)
        self.operating_df_name = operating_df_name
        self.debug = debug

        # Process using v1-compatible output format
        self.sdf, self.errs = self.ap.process_df_v1_compat(self.df, self.debug)
        self.stat_errors = []

        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def get_operating_df(self, df: pd.DataFrame, force_full_eval: bool) -> pd.DataFrame:
        """Downsample large DataFrames for performance."""
        rows = len(df)
        cols = len(df.columns)
        item_count = rows * cols

        if item_count > FAST_SUMMARY_WHEN_GREATER:
            return df.sample(np.min([50_000, len(df)]))
        return df

    def add_analysis(self, a_obj: Type[ColAnalysis]) -> None:
        """Add a new analysis class interactively."""
        passed, errors = self.ap.add_stat(a_obj)

        # Re-process with updated pipeline
        self.sdf, self.errs = self.ap.process_df_v1_compat(self.df, debug=True)
        _, self.stat_errors = self.ap.process_df(self.df, debug=True)

        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")

        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)


class PlDfStatsV2:
    """Drop-in for PlDfStats. Uses StatPipeline with @stat polars functions."""

    @classmethod
    def verify_analysis_objects(cls, objs):
        StatPipeline(objs)

    def get_operating_df(self, df):
        rows, cols = len(df), len(df.columns)
        if rows * cols > FAST_SUMMARY_WHEN_GREATER:
            return df.sample(n=min(50_000, rows), seed=42)
        return df

    def __init__(self, df, col_analysis_objs, operating_df_name=None, debug=False):
        self.df = self.get_operating_df(df)
        self.ap = StatPipeline(col_analysis_objs, unit_test=False)
        self.sdf, self.errs = self.ap.process_df_v1_compat(self.df, debug)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        """Add a new analysis class interactively."""
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.errs = self.ap.process_df_v1_compat(self.df, debug=True)
        _, self.stat_errors = self.ap.process_df(self.df, debug=True)
        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")
        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)
