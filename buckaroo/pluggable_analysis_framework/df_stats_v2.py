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
from .polars_stat_pipeline import PolarsStatPipeline
from .stat_pipeline import StatPipeline, errors_to_errdict
from .utils import FAST_SUMMARY_WHEN_GREATER
from .safe_summary_df import output_full_reproduce


class DfStatsV2:
    """Tie a StatPipeline to a DataFrame, exposing ``.sdf`` and ``.errs``.

    Used by DataFlow, autocleaning, and other consumers as the pandas
    summary-stats executor.
    """

    ap_class = StatPipeline

    @classmethod
    def verify_analysis_objects(cls, col_analysis_objs: AObjs) -> None:
        """Validate analysis objects without processing data."""
        cls.ap_class(col_analysis_objs)

    def __init__(self, df_stats_df: pd.DataFrame, col_analysis_objs: AObjs, operating_df_name: str = None,
            debug: bool = False, skip_columns=None) -> None:
        self.df = self.get_operating_df(df_stats_df, force_full_eval=False)
        self.col_order = self.df.columns
        self.ap = self.ap_class(col_analysis_objs)
        self.operating_df_name = operating_df_name
        self.debug = debug

        self.sdf, errors = self.ap.process_df(self.df, self.debug, skip_columns=skip_columns)
        self.errs = errors_to_errdict(errors)
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
        self.sdf, self.stat_errors = self.ap.process_df(self.df, debug=True)
        self.errs = errors_to_errdict(self.stat_errors)

        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")

        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)


class PlDfStatsV2:
    """Polars summary-stats executor: ``PolarsStatPipeline`` over the whole frame.

    No sampling (#999): the batch select handles big frames, and a stat that
    doesn't scale carries ``max_rows``. ``gated_keys`` lists the keys that
    gate left ``NOT_COMPUTED`` on this frame.
    """

    @classmethod
    def verify_analysis_objects(cls, objs):
        PolarsStatPipeline(objs, unit_test=False)

    def __init__(self, df, col_analysis_objs, operating_df_name=None, debug=False, skip_columns=None):
        self.df = df
        self.ap = PolarsStatPipeline(col_analysis_objs, unit_test=False)
        self.sdf, errors = self.ap.process_df(self.df, debug, skip_columns=skip_columns)
        self.gated_keys = self.ap.gated_keys
        self.errs = errors_to_errdict(errors)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        """Add a new analysis class interactively."""
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.stat_errors = self.ap.process_df(self.df, debug=True)
        self.gated_keys = self.ap.gated_keys
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")
        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)
