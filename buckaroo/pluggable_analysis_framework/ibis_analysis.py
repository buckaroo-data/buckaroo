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
    histogram_query_fns: List[Any] = []


class IbisAnalysisPipeline:
    """Pipeline for executing Ibis-based analysis.

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
        if not HAS_IBIS:
            raise ImportError(
                "ibis-framework is required for IbisAnalysisPipeline. "
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
            ibis expression that computes all stats, or None if no expressions
        """
        agg_exprs = []
        for col in columns:
            for expr_fn in self._expressions:
                try:
                    expr = expr_fn(table, col)
                    if expr is not None:
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
        schema = table.schema()
        # Pre-seed with schema metadata so computed_summary can access dtype
        stats: SDType = {
            col: {'dtype': str(schema[col]), 'orig_col_name': col}
            for col in columns
        }

        query = self.build_query(table, columns)
        if query is not None:
            # Execute via backend or directly
            if self.backend is not None:
                result_df = self.backend.execute(query)
            else:
                result_df = query.execute()

            # Parse results into SDType format
            # Expression names follow the "column|stat" convention
            for col_stat_name in result_df.columns:
                if '|' in col_stat_name:
                    col_name, stat_name = col_stat_name.split('|', 1)
                    if col_name in stats:
                        stats[col_name][stat_name] = result_df[col_stat_name].iloc[0]

        # Run computed_summary phase
        for obj in self.analysis_objects:
            for col_name in stats:
                try:
                    computed = obj.computed_summary(stats[col_name])
                    if computed:
                        stats[col_name].update(computed)
                except Exception:
                    continue

        # Run histogram queries (need computed stats like is_numeric, min, max)
        for obj in self.analysis_objects:
            for fn in getattr(obj, 'histogram_query_fns', []):
                for col_name in stats:
                    try:
                        query = fn(table, col_name, stats[col_name])
                        if query is None:
                            continue
                        if self.backend is not None:
                            result = self.backend.execute(query)
                        else:
                            result = query.execute()
                        stats[col_name]['histogram'] = _parse_histogram(
                            result, col_name, stats[col_name])
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


def _parse_histogram(result_df, col_name, col_stats):
    """Convert a GROUP BY result DataFrame into buckaroo's histogram format.

    For numeric columns (bucketed): list of {'name': bucket_label, 'cat_pop': pct}
    For categorical columns (topk):  list of {'name': value, 'cat_pop': pct}
    """
    if result_df is None or len(result_df) == 0:
        return []

    total = result_df['count'].sum()
    if total == 0:
        return []

    histogram = []
    is_numeric = col_stats.get('is_numeric', False)
    is_bool = col_stats.get('is_bool', False)

    if is_numeric and not is_bool and 'bucket' in result_df.columns:
        # Numeric bucketed histogram
        min_val = col_stats.get('min', 0)
        max_val = col_stats.get('max', 1)
        bucket_width = (max_val - min_val) / 10
        for _, row in result_df.iterrows():
            bucket_idx = int(row['bucket'])
            low = min_val + bucket_idx * bucket_width
            high = low + bucket_width
            histogram.append({
                'name': f"{low:.2g}-{high:.2g}",
                'cat_pop': row['count'] / total,
            })
    else:
        # Categorical histogram
        for _, row in result_df.iterrows():
            histogram.append({
                'name': str(row[col_name]) if col_name in result_df.columns else str(row.iloc[0]),
                'cat_pop': row['count'] / total,
            })

    return histogram
