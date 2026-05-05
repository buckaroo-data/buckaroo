.. _xorq_stats:

============================================
Push-down stats with the xorq stat pipeline
============================================

The pluggable analysis framework (see :ref:`using`) is built around
``ColAnalysis`` objects that operate on pandas Series. That works well
when the data already fits in memory. ``XorqStatPipeline`` is the same
idea — a DAG of typed stat functions, error capture, ``add_analysis``
on the fly — except every stat compiles to a `xorq
<https://github.com/xorq-labs/xorq>`_ expression and executes on the
backend (DuckDB, Postgres, Snowflake, DataFusion, …). buckaroo never
materialises the table.

Install with ``pip install 'buckaroo[xorq]'``.


Why push the stats down?
========================

The pandas ``DfStats`` path summarises a 50M-row table by loading 50M
rows into memory. For anything bigger than the laptop, that's the end
of the road — every column's null_count, distinct_count, mean, median,
and histogram has to come back out as native data.

A xorq expression knows nothing about pandas. ``expr.aggregate(...)``
compiles to a single SQL query, and the only thing that comes back to
Python is the row of scalars. The histogram is a second pass — ten
``GROUP BY`` queries, again on the backend — but no row-level data
ever leaves the engine.

The pipeline is also the same shape as ``StatPipeline`` (pandas) and
``PlDfStatsV2`` (polars), so DataFlow, ``CustomizableDataflow``, and
the autocleaning code keep working without changes.


In Action
=========

Build a xorq expression, hand it to ``XorqStatPipeline``, get the
same ``{column: {stat: value}}`` dict you'd get from pandas:

.. code-block:: python

    import xorq.api as xo
    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqStatPipeline
    from buckaroo.customizations.xorq_stats_v2 import XORQ_STATS_V2

    expr = xo.memtable({
        'price':    [12.5, 18.9, 7.4, 22.1, None, 14.0, 9.9, 31.2, 11.5, 19.8],
        'qty':      [1, 2, 1, 3, 1, 2, 4, 1, 2, 5],
        'category': ['a', 'b', 'a', 'c', 'a', 'b', 'b', 'c', 'a', 'b'],
        'is_promo': [True, False, False, True, False, False, True, True, False, True],
    })

    pipeline = XorqStatPipeline(XORQ_STATS_V2)
    summary, errors = pipeline.process_table(expr)
    summary['price']
    # {'_type': 'float', 'length': 10, 'null_count': 1, 'distinct_count': 9,
    #  'min': 7.4, 'max': 31.2, 'mean': 16.367..., 'std': 7.05..., 'median': 14.0,
    #  'non_null_count': 9, 'nan_per': 0.1, 'distinct_per': 0.9, 'histogram': [...]}

``XORQ_STATS_V2`` is the convenience list of @stat functions in
``buckaroo/customizations/xorq_stats_v2.py`` — drop it in for the
default panel, or compose your own.


Two-phase execution
===================

Each ``@stat`` function declares what it needs through its parameter
types. ``XorqStatPipeline`` looks at those types and decides which
phase the stat belongs to:

1. **Batch aggregate.** Stats whose only inputs are ``XorqColumn``
   (or framework-provided keys) return an ibis expression. The
   pipeline collects every such expression across every column,
   names each one ``"<col>|<stat>"``, and folds them into a single
   ``expr.aggregate(...)`` call. **One round-trip** to the backend
   per table.

2. **Per-column post-batch.** Stats with ``XorqExpr`` parameters need
   their own query — histograms, for instance, can't be folded into
   the batch because they ``GROUP BY`` on the data. They run after
   the batch lands, with the batch results already in the per-column
   accumulator (so a histogram stat can read ``min`` / ``max``
   without recomputing them).

Computed stats with no raw deps (``non_null_count``, ``distinct_per``,
…) run in phase 2 too, but they're cheap dict math — no query.

Marker types live in
``buckaroo.pluggable_analysis_framework.stat_func``:

==================  ===========================================================
``XorqColumn``      ``expr[col]`` — a single column expression. Stats taking
                    this return an ibis expression that the pipeline folds
                    into the batch aggregate.
``XorqExpr``        the full xorq expression. For stats that issue their own
                    per-column query.
``XorqExecute``     a 1-arg callable that runs an expression against the
                    pipeline's backend (or ``expr.execute()`` if no backend
                    was passed). Stats that issue their own queries must
                    use this so a user-supplied backend isn't bypassed.
==================  ===========================================================


Adding a custom stat
====================

Same ergonomics as the pandas ``@stat`` decorator: function signature
is the contract. Parameter names become inputs in the DAG; the
function name becomes the output key.

.. code-block:: python

    from buckaroo.pluggable_analysis_framework.stat_func import stat, XorqColumn

    @stat(column_filter=lambda dt: dt.is_numeric())
    def value_range(col: XorqColumn) -> float:
        return (col.max() - col.min()).cast('float64')

    @stat(column_filter=lambda dt: dt.is_numeric() and not dt.is_boolean())
    def cv(mean: float, std: float) -> float:
        if mean is None or std is None or mean == 0:
            return None
        return std / mean

    extended = [*XORQ_STATS_V2, value_range, cv]
    summary, _ = XorqStatPipeline(extended).process_table(expr)

``value_range`` takes an ``XorqColumn`` and returns an ibis expression
— it joins the batch aggregate. ``cv`` reads ``mean`` and ``std``
(already in the accumulator from the batch) and runs as cheap Python
math in phase 2. The DAG figures out the order; ``column_filter``
keeps both stats from running on string columns.

For stats that should write more than one accumulator key, return a
``MultipleProvides`` (a ``TypedDict`` alias) — the pipeline expands
each field into its own ``StatKey``:

.. code-block:: python

    from buckaroo.pluggable_analysis_framework.stat_func import MultipleProvides, stat

    class TypingResult(MultipleProvides):
        is_numeric: bool
        is_integer: bool
        is_float: bool

    @stat()
    def typing_stats(dtype: str) -> TypingResult:
        return {'is_numeric': ..., 'is_integer': ..., 'is_float': ...}


Histograms
==========

Numeric columns get ten equal-width buckets between ``min`` and
``max``. Non-numeric columns — and numeric columns with five or fewer
distinct values — get the top-10 categorical histogram instead. The
threshold mirrors ``pd_stats_v2``: ten quantile buckets over five
distinct values is mostly empty bars.

Both branches go through ``execute: XorqExecute`` so a backend passed
to the pipeline (``XorqStatPipeline(stats, backend=con)``) is honoured.


DataFlow integration
====================

``XorqDfStatsV2`` mirrors the ``DfStatsV2`` / ``PlDfStatsV2`` interface
(``.sdf``, ``.errs``, ``.add_analysis``) so anything wired up for
pandas/polars works against a xorq expression unchanged:

.. code-block:: python

    from buckaroo.pluggable_analysis_framework.xorq_stat_pipeline import XorqDfStatsV2

    stats = XorqDfStatsV2(expr, XORQ_STATS_V2)
    stats.sdf      # SDType — same shape as DfStatsV2.sdf
    stats.errs     # ErrDict — same shape as DfStatsV2.errs

    @stat(column_filter=lambda dt: dt.is_numeric())
    def value_range(col: XorqColumn) -> float:
        return (col.max() - col.min()).cast('float64')

    stats.add_analysis(value_range)
    stats.sdf['price']['value_range']

``XorqDfStatsV2`` lives in ``xorq_stat_pipeline`` rather than
``df_stats_v2`` so the generic DfStats module never imports xorq —
buckaroo without ``[xorq]`` keeps working.


Bring your own backend
======================

By default, ``XorqStatPipeline`` calls ``query.execute()`` on each
expression, which uses whatever backend xorq inferred when the
expression was built (DataFusion for ``xo.memtable``). Pass
``backend=`` to route every query — the batch aggregate and every
per-column histogram — through a specific connection:

.. code-block:: python

    con = xo.connect('duckdb://')
    table = con.read_parquet('s3://.../events.parquet')
    pipeline = XorqStatPipeline(XORQ_STATS_V2, backend=con)
    summary, errors = pipeline.process_table(table)

Useful when the table is unbound, or when you want to force execution
on a specific engine (Postgres for prod data, DuckDB for ad-hoc, …).


Errors and validation
=====================

``XorqStatPipeline`` follows the same rules as ``StatPipeline``:

* The DAG is validated at construction. A missing dependency or a
  cycle raises ``DAGConfigError`` immediately, not at first call.
* A construction-time smoke test runs the pipeline against
  ``PERVERSE_DF`` (wrapped as a xorq memtable) so typos and
  wrong-dtype assumptions surface before real data hits.
* Per-column failures land in the ``errors`` list as ``StatError``
  objects with reproduction code; the rest of the pipeline keeps
  going.
* ``add_stat`` / ``add_analysis`` revalidate and report; the pipeline
  state only updates on success.

The notebook example at
`docs/example-notebooks/Xorq-Stats.ipynb
<https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Xorq-Stats.ipynb>`_
runs the full flow end-to-end and prints the SQL each phase emits.
