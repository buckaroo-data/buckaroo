import polars as pl

from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.polars_commands import (
    Search)


def _pl_lazy_enter(df):
    return df.lazy()


def _pl_lazy_exit(df):
    # GroupBy.transform calls .collect() mid-pipeline, so anything
    # downstream of a groupby is already an eager DataFrame by the time
    # we see it here. Only collect if we're still lazy.
    return df.collect() if isinstance(df, pl.LazyFrame) else df


class NoCleaningConfPl(AutocleaningConfig):
    #just run the interpreter
    autocleaning_analysis_klasses = []
    command_klasses = [Search]
    quick_command_klasses = [Search]
    name=""
    lazy_enter = staticmethod(_pl_lazy_enter)
    lazy_exit = staticmethod(_pl_lazy_exit)


