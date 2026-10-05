"""DfStatsV2 — ties the StatPipeline to a DataFrame for DataFlow consumers.

Wraps StatPipeline to provide the ``.sdf`` / ``.errs`` surface used by
DataFlow, PandasAutocleaning, and other consumers.

Usage::

    from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2

    stats = DfStatsV2(my_df, [typing_stats, base_summary_stats, histogram])
    stats.sdf  # -> SDType
    stats.errs  # -> ErrDict
"""
from __future__ import annotations

from typing import Type

import numpy as np
import pandas as pd

from .col_analysis import AObjs, ColAnalysis
from .stat_pipeline import StatPipeline, errors_to_errdict
from .stat_units import StatState, UnitStats
from .utils import FAST_SUMMARY_WHEN_GREATER
from .safe_summary_df import output_full_reproduce


class DfStatsV2(UnitStats):
    """Tie a StatPipeline to a DataFrame, exposing ``.sdf`` and ``.errs``.

    Used by DataFlow, autocleaning, and other consumers as the pandas
    summary-stats executor. ``run=False`` builds it without computing anything,
    for a caller that drives ``plan`` / ``run`` itself.
    """

    ap_class = StatPipeline

    @classmethod
    def verify_analysis_objects(cls, col_analysis_objs: AObjs) -> None:
        """Validate analysis objects without processing data."""
        cls.ap_class(col_analysis_objs)

    def __init__(self, df_stats_df: pd.DataFrame, col_analysis_objs: AObjs, operating_df_name: str = None,
            debug: bool = False, skip_columns=None, run: bool = True) -> None:
        self.df = self.get_operating_df(df_stats_df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = self.ap_class(col_analysis_objs)
        self.operating_df_name = operating_df_name
        self.debug = debug
        self.state = StatState(self.df, frozenset(skip_columns or ()))

        self.sdf = {}
        self.errs = {}
        self.stat_errors = []
        if run:
            self.sdf, errors = self.ap.process_df(self.df, self.debug, skip_columns=skip_columns)
            self.errs = errors_to_errdict(errors)

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
        self.sdf, self.stat_errors = self.ap.process_df(self.df, debug=True)
        self.errs = errors_to_errdict(self.stat_errors)

        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")

        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)


class PlDfStatsV2(UnitStats):
    """Polars summary-stats executor. Uses StatPipeline with @stat polars functions.
    ``run=False`` builds it without computing anything, as for ``DfStatsV2``."""

    @classmethod
    def verify_analysis_objects(cls, objs):
        StatPipeline(objs)

    def get_operating_df(self, df):
        rows, cols = len(df), len(df.columns)
        if rows * cols > FAST_SUMMARY_WHEN_GREATER:
            return df.sample(n=min(50_000, rows), seed=42)
        return df

    def __init__(self, df, col_analysis_objs, operating_df_name=None, debug=False, skip_columns=None, run=True):
        self.df = self.get_operating_df(df)
        self.ap = StatPipeline(col_analysis_objs, unit_test=False)
        self.state = StatState(self.df, frozenset(skip_columns or ()))
        self.sdf = {}
        self.errs = {}
        self.stat_errors = []
        if run:
            self.sdf, errors = self.ap.process_df(self.df, debug, skip_columns=skip_columns)
            self.errs = errors_to_errdict(errors)
            if self.errs:
                output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        """Add a new analysis class interactively."""
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.stat_errors = self.ap.process_df(self.df, debug=True)
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")
        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)
