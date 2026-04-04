BuckarooCompare — Diff Your DataFrames
=======================================

When you change a pipeline, how do you know what changed in the output? When
you migrate a table from one database to another, how do you verify the data
matches? When two teams produce different versions of the same report, where
are the differences?

You diff them. But ``df1.equals(df2)`` returns a single boolean, and
``df1.compare(df2)`` only works if the DataFrames have identical shapes and
indexes. Real-world comparisons are messier: rows may be reordered, columns
may be added or removed, and the join key might not be the index.

Buckaroo's ``col_join_dfs`` function handles all of this and renders the
result as a color-coded interactive table where differences jump out
visually.


Quick start
-----------

.. code-block:: python

    from buckaroo.compare import col_join_dfs
    import pandas as pd

    df1 = pd.DataFrame({
        'id': [1, 2, 3, 4],
        'name': ['Alice', 'Bob', 'Charlie', 'Diana'],
        'score': [88.5, 92.1, 75.3, 96.7],
    })

    df2 = pd.DataFrame({
        'id': [1, 2, 3, 5],
        'name': ['Alice', 'Robert', 'Charlie', 'Eve'],
        'score': [88.5, 92.1, 80.0, 81.0],
    })

    merged_df, column_config_overrides, eqs = col_join_dfs(
        df1, df2,
        join_columns=['id'],
        how='outer'
    )

The function returns three things:

1. **merged_df**: The joined DataFrame with all rows from both inputs,
   plus hidden metadata columns for diff state
2. **column_config_overrides**: A dict of buckaroo styling config that
   color-codes each cell based on whether it matches, differs, or is
   missing from one side
3. **eqs**: A summary dict showing the diff count per column — how many
   rows differ for each column


How the diff works
------------------

``col_join_dfs`` performs a ``pd.merge`` on the join columns, then for each
data column:

- Creates a hidden ``{col}|df2`` column with the df2 value
- Creates a hidden ``{col}|eq`` column encoding the combined state:
  is the row in df1 only, df2 only, both-and-matching, or both-and-different?
- Generates a ``color_map_config`` that maps these states to colors

The color scheme:

.. list-table::
   :header-rows: 1

   * - State
     - Color
     - Meaning
   * - df1 only
     - Pink
     - Row exists in df1 but not df2
   * - df2 only
     - Green
     - Row exists in df2 but not df1
   * - Match
     - Light blue
     - Row in both, values identical
   * - Diff
     - Dark blue
     - Row in both, values differ

Join key columns are highlighted in purple so you can immediately see what
was used for matching.


The eqs summary
---------------

The third return value tells you at a glance where the differences are:

.. code-block:: python

    >>> eqs
    {
        'id': {'diff_count': 'join_key'},
        'name': {'diff_count': 2},      # 2 rows differ
        'score': {'diff_count': 1},      # 1 row differs
    }

Special values:

- ``"join_key"`` — this column was used for matching, not compared
- ``"df_1"`` — column only exists in df1
- ``"df_2"`` — column only exists in df2
- An integer — number of rows where values differ


Using it with the server
------------------------

The buckaroo server exposes a ``/load_compare`` endpoint that loads two
files, runs the diff, and pushes the styled result to any connected browser:

.. code-block:: bash

    curl -X POST http://localhost:8888/load_compare \
      -H "Content-Type: application/json" \
      -d '{
        "session": "my-session",
        "path1": "/data/report_v1.csv",
        "path2": "/data/report_v2.csv",
        "join_columns": ["id"],
        "how": "outer"
      }'

The response includes the diff summary:

.. code-block:: json

    {
      "session": "my-session",
      "rows": 5,
      "columns": ["id", "name", "score"],
      "eqs": {
        "id": {"diff_count": "join_key"},
        "name": {"diff_count": 2},
        "score": {"diff_count": 1}
      }
    }

The browser view updates immediately with the color-coded merged table.
Hover over any differing cell to see the df2 value in a tooltip.


Multi-column joins
------------------

.. code-block:: python

    merged_df, overrides, eqs = col_join_dfs(
        df1, df2,
        join_columns=['region', 'date'],
        how='inner'
    )

Composite join keys work naturally. Both ``region`` and ``date`` will be
highlighted in purple.


Use cases
---------

**Data migration validation**
    Migrating from Postgres to Snowflake? Export both tables, diff them.
    The color coding immediately shows which rows are missing and which
    values changed.

**Pipeline output comparison**
    Changed a transform? Diff the before and after. The ``eqs`` summary
    tells you exactly which columns were affected and by how many rows.

**A/B test result inspection**
    Compare experiment vs control DataFrames on a user ID join key. See
    which metrics actually differ.

**Schema evolution**
    When df2 has columns that df1 doesn't (or vice versa), those columns
    are marked as ``"df_1"`` or ``"df_2"`` in the eqs summary, so you
    can see schema changes alongside data changes.


Integration with datacompy
--------------------------

The ``docs/example-notebooks/datacompy_app.py`` example shows how to use
`datacompy <https://github.com/capitalone/datacompy>`_ for metadata-rich
comparison (column matching stats, row-level match rates) while using
buckaroo for the visual rendering.

This gives you the best of both: datacompy's statistical summary plus
buckaroo's interactive, color-coded table view.


Limitations
-----------

- Join columns must be unique in each DataFrame (no many-to-many joins).
  If duplicates are detected, ``col_join_dfs`` raises a ``ValueError``.
- Column names cannot contain ``|df2`` or ``__buckaroo_merge`` (these are
  used internally).
- Very large DataFrames (>100K rows) will work but the browser may be slow
  to render the full color-coded table.
