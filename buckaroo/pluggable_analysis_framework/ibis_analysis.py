"""Ibis/xorq analysis backend for the pluggable analysis framework.

xorq as a COMPUTE backend (not caching):
  - Execute analysis expressions against remote data sources
    (DuckDB files, Postgres, Snowflake) without materializing data locally
  - Ibis as the expression language — portable across backends

What xorq does NOT replace:
  - Column-level caching stays in SQLiteFileCache + PAFColumnExecutor
  - DAG ordering and error model are framework concerns

Optional dependency: install with `buckaroo[xorq]`.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from .col_analysis import ColAnalysis, SDType, ErrDict


# Guard optional imports
try:
    import xorq  # noqa: F401
    HAS_XORQ = True
except ImportError:
    HAS_XORQ = False

try:
    import ibis  # noqa: F401
    HAS_IBIS = True
except ImportError:
    HAS_IBIS = False


class IbisAnalysis(ColAnalysis):
    """Base class for Ibis-expression-based analysis.

    Analogous to PolarsAnalysis.select_clauses, but using Ibis expressions
    that can be executed via xorq against any supported backend.

    Subclass this and define ``ibis_expressions`` to register Ibis-based stats::

        class BasicIbisStats(IbisAnalysis):
            ibis_expressions = [
                lambda t, col: t[col].count().name(f"{col}|length"),
                lambda t, col: t[col].isnull().sum().name(f"{col}|null_count"),
            ]
            provides_defaults = {'length': 0, 'null_count': 0}

    Each expression is a callable ``(table, column_name) -> ibis.Expr``
    that produces a named scalar expression.
    """
    ibis_expressions: List[Any] = []


class IbisAnalysisPipeline:
    """Pipeline for executing Ibis-based analysis via xorq.

    Collects all ``ibis_expressions`` from IbisAnalysis subclasses,
    builds a single Ibis query, and executes it against the configured
    backend.

    The computed_summary stage is identical to the pandas path
    (dict in, dict out).
    """

    def __init__(self, analysis_objects: list, backend=None):
        """
        Args:
            analysis_objects: list of IbisAnalysis subclasses
            backend: xorq/ibis backend connection (e.g., xorq.connect())
        """
        if not HAS_XORQ:
            raise ImportError(
                "xorq is required for IbisAnalysisPipeline. "
                "Install with: pip install buckaroo[xorq]"
            )

        self.analysis_objects = analysis_objects
        self.backend = backend

        # Collect all ibis expressions
        self._expressions = []
        for obj in analysis_objects:
            if hasattr(obj, 'ibis_expressions'):
                self._expressions.extend(obj.ibis_expressions)

    def build_query(self, table, columns: List[str]):
        """Build a single Ibis aggregation query from all expressions.

        Args:
            table: ibis Table expression
            columns: list of column names to analyze

        Returns:
            ibis expression that computes all stats
        """
        agg_exprs = []
        for col in columns:
            for expr_fn in self._expressions:
                try:
                    expr = expr_fn(table, col)
                    agg_exprs.append(expr)
                except Exception:
                    continue

        if not agg_exprs:
            return None

        return table.aggregate(agg_exprs)

    def execute(self, table, columns: List[str]) -> SDType:
        """Execute the analysis pipeline against an Ibis table.

        Args:
            table: ibis Table expression
            columns: list of column names to analyze

        Returns:
            SDType dict mapping column names to their stats
        """
        query = self.build_query(table, columns)
        if query is None:
            return {}

        # Execute via xorq backend
        if self.backend is not None:
            result_df = self.backend.execute(query)
        else:
            result_df = query.execute()

        # Parse results into SDType format
        # Expression names follow the "column|stat" convention
        stats: SDType = {}
        for col_stat_name in result_df.columns:
            if '|' in col_stat_name:
                col_name, stat_name = col_stat_name.split('|', 1)
                if col_name not in stats:
                    stats[col_name] = {}
                stats[col_name][stat_name] = result_df[col_stat_name].iloc[0]

        # Run computed_summary phase
        for obj in self.analysis_objects:
            for col_name in stats:
                try:
                    computed = obj.computed_summary(stats[col_name])
                    stats[col_name].update(computed)
                except Exception:
                    continue

        return stats

    def process_df(self, table, columns: List[str] = None) -> Tuple[SDType, ErrDict]:
        """Process a table (ibis Table or xorq-wrapped).

        Args:
            table: ibis Table expression
            columns: optional list of columns (defaults to all)

        Returns:
            (SDType, ErrDict) matching the AnalysisPipeline interface
        """
        if columns is None:
            columns = table.columns

        try:
            stats = self.execute(table, columns)
            return stats, {}
        except Exception as e:
            return {}, {("__ibis__", "execute"): (e, IbisAnalysis)}
