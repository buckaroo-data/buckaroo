from __future__ import annotations

from typing import Any, List, Type, Dict, Callable
import json

import polars as pl
import pl_series_hash  # required to register pl.Expr.pl_series_hash

from buckaroo.file_cache.base import ColumnExecutor, ColumnResults, ColumnResult, ExecutorArgs
from buckaroo.pluggable_analysis_framework.polars_analysis_management import (
    PolarsAnalysis, polars_select_expressions, polars_series_stats_from_select_result,
)


class PAFColumnExecutor(ColumnExecutor[ExecutorArgs]):
    """
    ColumnExecutor that delegates per-column analysis to the Polars pluggable
    analysis framework. It executes provided PolarsAnalysis classes to derive
    summary stats per column, and returns ColumnResults suitable for caching.
    """

    def __init__(self, analyses: List[Type[PolarsAnalysis]]) -> None:
        self.analyses = list(analyses)

    def get_execution_args(self, existing_stats:dict[str,dict[str,object]]) -> ExecutorArgs:
        columns = list(existing_stats.keys())
        # include hash only if any column is marked missing via sentinel
        include_hash = any(bool(stats.get('__missing_hash__')) for stats in existing_stats.values())

        #FIXME: the below known_metric_builders is crap  it works for now to get around the mp failure but something more robust needs to be built
        #FIXME PAF currently has no provision to map individual expressions to values, so we always have to run all of th eexpressions.  I want to make aew iteration of PAF
        # that is based on beartype and dictionaries... I have it described in a bug report somewhere 



        base_expressions: list[pl.Expr] = polars_select_expressions(self.analyses)

        # Build safe per-column expressions based on provided defaults from analyses,
        # avoiding any .name.map(lambda ...) constructs entirely.
        known_metric_builders: Dict[str, Callable[[pl.Expr], pl.Expr]] = {
            'null_count': lambda e: e.null_count(),
            'mean': lambda e: e.mean(),
            'min': lambda e: e.min(),
            'max': lambda e: e.max(),
            'median': lambda e: e.median(),
            'std': lambda e: e.std(),
            'len': lambda e: e.len(),
            'length': lambda e: e.len(),
            'sum': lambda e: e.sum(),
        }

        provided_measures: List[str] = []
        for ak in self.analyses:
            try:
                for k in getattr(ak, "provides_defaults", {}).keys():
                    if k not in provided_measures:
                        provided_measures.append(str(k))
            except Exception:
                pass

        # If we have any recognized measures from analyses, prefer the safe per-column plan.
        safe_rewritten: list[pl.Expr] = []
        recognized = [m for m in provided_measures if m in known_metric_builders]
        if recognized:
            for col in columns:
                base = pl.col(col)
                for m in recognized:
                    safe_rewritten.append(
                        known_metric_builders[m](base).alias(json.dumps([col, m]))
                    )
            expressions = safe_rewritten
            column_specific = True
        else:
            # Fallback to original expressions if nothing recognized
            expressions = base_expressions
            column_specific = False

        return ExecutorArgs(
            columns=columns,
            column_specific_expressions=column_specific,
            include_hash=include_hash,
            expressions=expressions,
            row_start=None,
            row_end=None,
            extra=None,
        )

    def execute(self, ldf:pl.LazyFrame, execution_args:ExecutorArgs) -> ColumnResults:
        cols = execution_args.columns
        only_cols = ldf.select(cols)
        # Execute provided expressions directly (single collect)
        res = only_cols.select(*execution_args.expressions).collect()
        # Build series stats from the selection result without re-executing expressions
        schema_df = pl.DataFrame({c: [] for c in cols})
        series_stats, errs = polars_series_stats_from_select_result(res, schema_df, self.analyses, 'paf_exec', debug=False)
        # Extract hash values from result if present
        hash_values: dict[str, int] = {}
        for c in cols:
            hcol = f"{c}_hash"
            if hcol in res.columns:
                try:
                    hash_values[c] = int(res[hcol][0])
                except Exception:
                    hash_values[c] = 0
            else:
                hash_values[c] = 0
        return self._series_stats_to_results(cols, series_stats, hash_values)

    def _series_stats_to_results(self,
                                 cols: list[str],
                                 series_stats: dict[str, dict[str, Any]],
                                 hash_values: dict[str, int]) -> ColumnResults:
        # Map rewritten entries back to original columns
        orig_to_stats: dict[str, dict[str, Any]] = {}
        for _rw, stat in series_stats.items():
            if isinstance(stat, dict):
                orig = stat.get('orig_col_name')
                if isinstance(orig, str) and orig in cols:
                    stat_copy = dict(stat)
                    stat_copy.pop('orig_col_name', None)
                    stat_copy.pop('rewritten_col_name', None)
                    orig_to_stats[orig] = stat_copy

        results: ColumnResults = {}
        for c in cols:
            hash_val = hash_values.get(c, 0)
            per_col_stats = orig_to_stats.get(c, {})
            results[c] = ColumnResult(
                series_hash=hash_val,
                column_name=c,
                expressions=[],
                result=per_col_stats,
            )
        return results

