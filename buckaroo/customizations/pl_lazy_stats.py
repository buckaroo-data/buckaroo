"""Summary stats for a polars LazyFrame as one select (#993).

The eager polars path (``pl_stats_v2``) hands each @stat function a
``pl.Series``. A ``/load`` session that holds ``pl.scan_parquet`` has no
series to hand out without collecting the column, so this module computes
every per-column scalar in a single ``select`` over the scan
(:func:`lazy_stat_exprs`), collects it once with the streaming engine
(:func:`collect_lazy_stats`), and seeds ``StatPipeline.process_column``
with the result as ``initial_stats``. The @stat functions here derive the
remaining keys from those scalars instead of from a raw series, so the
styling classes see the same keys as the eager path.

Keys that need a full ``value_counts`` per column are not produced:
``value_counts`` itself and ``memory_usage``. ``most_freq``..``5th_freq``,
``mode`` and the categorical histogram come from a top-N ``value_counts``
inside the same select; ``distinct_count`` and ``unique_count`` are exact.
"""
from typing import Any, Dict, List, Tuple, TypedDict, get_type_hints

import numpy as np
import polars as pl

from buckaroo.pluggable_analysis_framework.stat_func import stat
from buckaroo.pluggable_analysis_framework.stat_pipeline import StatPipeline
from buckaroo.customizations.histogram import numeric_histogram
from buckaroo.customizations.pd_stats_v2 import _type, ComputedSummaryResult
from buckaroo.customizations.pl_stats_v2 import pl_dtype_typing, PlTypingResult

# how many of the most frequent values the select carries per column; the
# summary pinned rows show five, the categorical histogram seven
TOP_N = 7
# Object columns hold arbitrary Python values and can't be hashed into
# value_counts; List/Array/Struct can
_UNCOUNTABLE = (pl.Object,)
# the count field of value_counts, named so it can't collide with a column
_VC_COUNT = "__count"


def _alias(i: int, stat_name: str) -> str:
    # column position, not name: a column name can contain anything
    return f"{i}:{stat_name}"


def lazy_stat_exprs(schema: pl.Schema) -> List[pl.Expr]:
    """One expression per (column, stat), all reducing to a scalar so the
    whole frame's stats are a single one-row select."""
    exprs: List[pl.Expr] = []
    for i, (name, dt) in enumerate(schema.items()):
        c = pl.col(name)
        exprs += [c.len().alias(_alias(i, 'length')), c.null_count().alias(_alias(i, 'null_count'))]
        if not isinstance(dt, _UNCOUNTABLE):
            vc = c.drop_nulls().value_counts(sort=True, name=_VC_COUNT)
            exprs += [vc.len().alias(_alias(i, 'distinct_count')),
                (vc.struct.field(_VC_COUNT) == 1).sum().alias(_alias(i, 'unique_count')),
                vc.head(TOP_N).implode().alias(_alias(i, 'top_value_counts'))]
        if dt == pl.String:
            exprs.append((c == "").sum().alias(_alias(i, 'empty_count')))
        if dt.is_numeric():
            f = c.cast(pl.Float64)
            lo, hi = f.quantile(0.01), f.quantile(0.99)
            exprs += [c.min().alias(_alias(i, 'min')), c.max().alias(_alias(i, 'max')),
                f.mean().alias(_alias(i, 'mean')), f.std().alias(_alias(i, 'std')),
                f.median().alias(_alias(i, 'median')), lo.alias(_alias(i, 'low_tail')),
                hi.alias(_alias(i, 'high_tail')),
                # same "meat" as pl_histogram_series: values strictly inside the 1%/99% tails
                f.filter((f > lo) & (f < hi)).hist(bin_count=10, include_breakpoint=True).implode()
                .alias(_alias(i, 'hist'))]
        elif dt.is_temporal():
            exprs += [c.min().alias(_alias(i, 'min')), c.max().alias(_alias(i, 'max'))]
    return exprs


def _nan_if_none(val: Any) -> Any:
    return float('nan') if val is None else val


def _histogram_args(hist: Any, low_tail: Any, high_tail: Any) -> Tuple[dict, list]:
    """Rebuild ``pl_histogram_series``'s ``histogram_args`` / ``histogram_bins``
    from the imploded ``hist`` struct. polars reports each bin's upper
    breakpoint; the first bin's lower edge is one bin width below it."""
    if not hist or low_tail is None or high_tail is None:
        return {}, []
    counts = [b['count'] for b in hist]
    breakpoints = [b['breakpoint'] for b in hist]
    total = sum(counts)
    if total == 0 or len(breakpoints) < 2:
        return {}, []
    edges = [breakpoints[0] - (breakpoints[1] - breakpoints[0])] + breakpoints
    args = dict(meat_histogram=(counts, edges), normalized_populations=[n / total for n in counts],
        low_tail=low_tail, high_tail=high_tail)
    return args, edges


def _column_seed(name: str, dt: pl.DataType, vals: Dict[str, Any]) -> Dict[str, Any]:
    """The ``initial_stats`` for one column: the select's values plus the
    defaults the eager path's stat functions would have produced."""
    seed: Dict[str, Any] = {**pl_dtype_typing(dt), 'length': vals['length'], 'null_count': vals['null_count'],
        'min': float('nan'), 'max': float('nan'), 'empty_count': 0, 'histogram_args': {}, 'histogram_bins': []}
    if 'top_value_counts' in vals:
        top = [(d[name], d[_VC_COUNT]) for d in (vals['top_value_counts'] or [])]
        seed.update(top_value_counts=top, distinct_count=vals['distinct_count'],
            unique_count=vals['unique_count'], mode=top[0][0] if top else None)
    if 'empty_count' in vals:
        seed['empty_count'] = vals['empty_count']
    if dt.is_numeric():
        for key in ('min', 'max', 'mean', 'std', 'median'):
            seed[key] = _nan_if_none(vals[key])
        seed['histogram_args'], seed['histogram_bins'] = _histogram_args(
            vals['hist'], vals['low_tail'], vals['high_tail'])
    elif dt.is_temporal():
        seed['min'], seed['max'] = vals['min'], vals['max']
    return seed


def collect_lazy_stats(lf: pl.LazyFrame, engine: str = "streaming") -> Dict[str, Dict[str, Any]]:
    """``{column_name: initial_stats}`` for every column, from one collect."""
    schema = lf.collect_schema()
    exprs = lazy_stat_exprs(schema)
    if not exprs:
        return {}
    row = lf.select(exprs).collect(engine=engine).row(0, named=True)
    by_position: Dict[int, Dict[str, Any]] = {}
    for key, val in row.items():
        pos, stat_name = key.split(":", 1)
        by_position.setdefault(int(pos), {})[stat_name] = val
    return {name: _column_seed(name, dt, by_position[i]) for i, (name, dt) in enumerate(schema.items())}


# every key collect_lazy_stats can seed; LazyStatPipeline accepts them as
# providers when it validates the DAG
LAZY_SEED_KEYS = frozenset(get_type_hints(PlTypingResult)) - {'memory_usage'} | {
    'length', 'null_count', 'min', 'max', 'empty_count', 'histogram_args', 'histogram_bins',
    'top_value_counts', 'distinct_count', 'unique_count', 'mode', 'mean', 'std', 'median'}


class LazyStatPipeline(StatPipeline):
    """StatPipeline whose DAG validation accepts the seeded keys. Per
    column, only the keys the select produced count as present, so a stat
    whose seed is missing (a nested column has no value counts) is skipped."""
    SEED_KEYS = LAZY_SEED_KEYS


@stat()
def pl_lazy_computed_summary(length: int, null_count: int, distinct_count: int, unique_count: int, empty_count: int,
        top_value_counts: list) -> ComputedSummaryResult:
    """``computed_default_summary_stats`` from the seeded scalars."""
    def per(n):
        return n / length if length else float('nan')

    def nth(pos):
        return top_value_counts[pos][0] if pos < len(top_value_counts) else None

    return {'non_null_count': length - null_count, 'most_freq': nth(0), '2nd_freq': nth(1), '3rd_freq': nth(2),
        '4th_freq': nth(3), '5th_freq': nth(4), 'unique_count': unique_count, 'empty_count': empty_count,
        'distinct_count': distinct_count, 'distinct_per': per(distinct_count), 'empty_per': per(empty_count),
        'unique_per': per(unique_count), 'nan_per': per(null_count)}


def _categorical_histogram(length: int, null_count: int, unique_count: int, top_value_counts: list,
        nan_per: float) -> list:
    """``categorical_histogram`` over the top-N counts, with the long tail
    taken from the exact totals rather than from the truncated counts."""
    top = top_value_counts[:TOP_N]
    long_tail = (length - null_count - sum(n for _, n in top)) - unique_count
    histogram = []
    for val, n in top:
        percent = np.round((n / length) * 100, 0)
        if percent > .3:
            histogram.append({'name': str(val), 'cat_pop': percent})
    if long_tail > 0:
        histogram.append({'name': 'longtail', 'longtail': np.round((long_tail / length) * 100, 0)})
    if unique_count > 0:
        histogram.append({'name': 'unique', 'unique': np.round((unique_count / length) * 100, 0)})
    if nan_per > 0.0:
        histogram.append({'name': 'NA', 'NA': np.round(nan_per * 100, 0)})
    return histogram


PlLazyHistogramResult = TypedDict('PlLazyHistogramResult', {'histogram': list})


@stat()
def pl_lazy_histogram(length: int, null_count: int, nan_per: float, is_numeric: bool, distinct_count: int,
        unique_count: int, top_value_counts: list, min: Any, max: Any, histogram_args: dict) -> PlLazyHistogramResult:
    """``histogram`` from the seeded scalars: numeric bins when the select
    produced them, the top-N categorical histogram otherwise."""
    if is_numeric and distinct_count > 5 and histogram_args:
        temp_histo = numeric_histogram(histogram_args, min, max, nan_per)
        if len(temp_histo) > 5:
            return {'histogram': temp_histo}
    return {'histogram': _categorical_histogram(length, null_count, unique_count, top_value_counts, nan_per)}


PL_ANALYSIS_LAZY = [_type, pl_lazy_computed_summary, pl_lazy_histogram]
