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

from typing import Any, Dict, Type

import numpy as np
import pandas as pd

from .col_analysis import AObjs, ColAnalysis
from .stat_pipeline import StatPipeline, errors_to_errdict
from .utils import FAST_SUMMARY_WHEN_GREATER
from .safe_summary_df import output_full_reproduce
try:
    from .polars_utils import batch_value_counts
except ImportError:
    # pandas-only install: PlDfStatsV2 is never constructed without polars.
    batch_value_counts = None


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
    """Polars summary-stats executor. Uses StatPipeline with @stat polars functions.

    ``value_counts`` for every column is computed up front in one
    ``pl.collect_all`` (``batch_column_stats``) and seeded into each column's
    accumulator, so polars runs the group-bys across columns in parallel
    instead of one Series at a time (#997). The pipeline's own
    ``value_counts`` provider is skipped for those columns.
    """

    @classmethod
    def verify_analysis_objects(cls, objs):
        StatPipeline(objs)

    def get_operating_df(self, df):
        rows, cols = len(df), len(df.columns)
        if rows * cols > FAST_SUMMARY_WHEN_GREATER:
            return df.sample(n=min(50_000, rows), seed=42)
        return df

    def batch_column_stats(self, df, skip_columns=None) -> Dict[Any, Dict[str, Any]]:
        """Stats computed for all columns at once, keyed by column name, for
        ``StatPipeline.process_df``'s ``column_initial_stats``.

        Only runs when the pipeline would compute ``value_counts`` itself. If
        the batch raises, the columns fall back to the per-Series stat, which
        reports its error per column.
        """
        if 'value_counts' not in self.ap.provided_summary_facts_set:
            return {}
        skip = set(skip_columns or ())
        columns = [c for c in df.columns if c not in skip]
        try:
            batched = batch_value_counts(df, columns)
        except Exception:
            return {}
        return {col: {'value_counts': vc} for col, vc in batched.items()}

    def __init__(self, df, col_analysis_objs, operating_df_name=None, debug=False, skip_columns=None):
        self.df = self.get_operating_df(df)
        self.ap = StatPipeline(col_analysis_objs, unit_test=False)
        self.column_stats = self.batch_column_stats(self.df, skip_columns)
        self.sdf, errors = self.ap.process_df(self.df, debug, skip_columns=skip_columns,
            column_initial_stats=self.column_stats)
        self.errs = errors_to_errdict(errors)
        self.stat_errors = []
        if self.errs:
            output_full_reproduce(self.errs, self.sdf, operating_df_name)

    def add_analysis(self, a_obj):
        """Add a new analysis class interactively."""
        passed, errors = self.ap.add_stat(a_obj)
        self.sdf, self.stat_errors = self.ap.process_df(self.df, debug=True, column_initial_stats=self.column_stats)
        self.errs = errors_to_errdict(self.stat_errors)
        if not passed:
            print("Unit tests failed")
        if self.errs:
            print("Errors on original dataframe")
        if errors or self.stat_errors:
            self.ap.print_errors(errors + self.stat_errors)
