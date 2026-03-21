The Dastardly DataFrame Dataset
================================

Every DataFrame viewer works fine on ``pd.DataFrame({'a': [1, 2, 3]})``.
The question is what happens when the data gets weird.

Displaying DataFrames in all their wonderfully variant splendor is quite a
challenge. DataFrames come in many forms and there is little you can depend
on when you want to serialize or display them. Through building Buckaroo I
have tripped across many types of bugs from DataFrames that I didn't expect.

So I compiled a set of the weirdest DataFrames I have seen in the wild — the
ones that caused hard to debug errors, the ones that were hard to support —
and reduced them to limited test cases. I call this the `Dastardly DataFrame
Dataset <https://github.com/buckaroo-data/buckaroo/blob/main/buckaroo/ddd_library.py>`_
(DDD). MultiIndex columns, NaN mixed with infinity, columns
literally named ``index``, integers too large for JavaScript, types that most
tools pretend don't exist. Through hard fought experience, Buckaroo has dealt
with bugs or edge cases related to each one.

The naming and early shape of the DDD was heavily influenced by an exchange
with `Cecil Curry <https://github.com/leycec>`_, the author of
`beartype <https://github.com/beartype/beartype>`_, on
`beartype#529 <https://github.com/beartype/beartype/issues/529>`_. That guy
is awesome. Be more like that guy. Seriously the most enjoyable bug report
interaction I have ever had.

This page shows each DDD member rendered live in buckaroo's static embed. No
Jupyter kernel, no server — just HTML and JavaScript.

Why this matters
----------------

Buckaroo has the philosophy that every DataFrame should be displayable, at
least in some form. Capabilities can be reduced — it's fine for ``mean`` to
fail if there is a ``NaN`` in a column — but that failure can't cause
Buckaroo to display nothing.

If you build dashboards, you choose what data goes into your table. You
control the types, the column names, the index. But if you're doing
exploratory data analysis — loading CSVs from vendors, joining tables from
different systems, debugging a pipeline that produces unexpected output —
you don't control any of that. The data is what it is. And who knows
what an LLM will produce — code-generating agents can create DataFrames
with column types you've never seen in your own code. Same goes for
inherited data pipelines: someone else built it, you're debugging it,
and the DataFrame you're staring at has types and structures you didn't
choose.

``df.head()`` hides the problem. It shows you 5 rows and lets you believe
everything is fine. Buckaroo is built for the opposite workflow: show you
everything, especially the parts that are surprising.

The Dastardly DataFrames
------------------------

The DDD is used extensively in Buckaroo's unit test suite. At a minimum,
all DataFrames display in some way unless otherwise noted. Most display with
full features — there are a couple of rough edges, but having a comprehensive
test set is a very helpful start.

Each section below shows the exact function from ``buckaroo.ddd_library``
that creates the DataFrame, explains why it's tricky, and renders it live
in a buckaroo static embed.

.. code-block:: bash

    pip install buckaroo

.. code-block:: python

    from buckaroo.ddd_library import *


Infinity and NaN
~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def df_with_infinity() -> pd.DataFrame:
        return pd.DataFrame({'a': [np.nan, np.inf, np.inf * -1]})

    df_with_infinity()

Three non-numeric values that pop up in numeric columns: a missing value, positive
infinity, and negative infinity. Many viewers display all three as blank or
"NaN". Buckaroo distinguishes them.

This also tests whether summary stats (mean, min, max) handle infinity
correctly — they should, because ``np.inf`` is a valid float, not missing
data.

.. raw:: html

   <iframe src="../ddd/infinity.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Really Big Numbers
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def df_with_really_big_number() -> pd.DataFrame:
        return pd.DataFrame({"col1": [9999999999999999999, 1]})

    df_with_really_big_number()

Python integers have arbitrary precision. JavaScript's ``Number`` type has
53 bits of integer precision (``Number.MAX_SAFE_INTEGER`` = 9007199254740991).
The value 9999999999999999999 exceeds this — if you naively convert it to a
JS number, it silently rounds to 10000000000000000000.

Buckaroo detects values above ``MAX_SAFE_INTEGER`` and preserves them as
strings to maintain exact precision. This matters for database primary keys,
blockchain transaction IDs, and any system that uses 64-bit integers.

.. raw:: html

   <iframe src="../ddd/big-numbers.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Column Named "index"
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def df_with_col_named_index() -> pd.DataFrame:
        return pd.DataFrame({
            'a':     ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"],
            'index': ["7777", "ooooo", "--- -", "33333", "assdf"]})

    df_with_col_named_index()

When you call ``df.reset_index()``, pandas creates a column called ``index``.
Many widgets break because they confuse this column with the DataFrame's
actual index. Buckaroo handles the ambiguity by internally renaming columns
to ``a, b, c...`` and mapping back via ``orig_col_name``.

.. raw:: html

   <iframe src="../ddd/col-named-index.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Named Index
~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def get_df_with_named_index() -> pd.DataFrame:
        """someone put the effort into naming the index,
        you'd probably want to display that"""
        return pd.DataFrame(
            {'a': ["asdf", "foo_b", "bar_a", "bar_b", "bar_c"]},
            index=pd.Index([10, 20, 30, 40, 50], name='foo'))

    get_df_with_named_index()

Someone took the time to name this index ``foo``. That name carries meaning —
it might be a join key, a time series frequency, or a categorical grouping.
Buckaroo displays named indexes as a distinct pinned column so the name is
visible.

.. raw:: html

   <iframe src="../ddd/named-index.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


MultiIndex Columns
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def get_multiindex_with_names_cols_df(rows=15) -> pd.DataFrame:
        cols = pd.MultiIndex.from_tuples(
            [('foo', 'a'), ('foo', 'b'), ('bar', 'a'),
             ('bar', 'b'), ('bar', 'c')],
            names=['level_a', 'level_b'])
        return pd.DataFrame(
            [["asdf", "foo_b", "bar_a", "bar_b", "bar_c"]] * rows,
            columns=cols)

    get_multiindex_with_names_cols_df(rows=6)

Hierarchical column headers are common after ``.pivot_table()`` and
``.groupby().agg()``. Most viewers either crash or flatten them into ugly
tuple strings like ``('foo', 'a')``. Buckaroo flattens them into readable
headers while preserving the level information.

.. raw:: html

   <iframe src="../ddd/multiindex-cols.html"
           style="width:100%; height:360px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


MultiIndex on Rows
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def get_multiindex_index_df() -> pd.DataFrame:
        row_index = pd.MultiIndex.from_tuples([
            ('foo', 'a'), ('foo', 'b'),
            ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
            ('baz', 'a')])
        return pd.DataFrame({
            'foo_col': [10, 20, 30, 40, 50, 60],
            'bar_col': ['foo', 'bar', 'baz', 'quux', 'boff', None]},
            index=row_index)

    get_multiindex_index_df()

Multi-level row indexes are the counterpart to MultiIndex columns. They
appear after ``.groupby()`` without ``.reset_index()``, or when loading
data from hierarchical sources. The tricky part: each index level becomes
an additional column that has to be displayed alongside the data columns
without breaking the column count.

.. raw:: html

   <iframe src="../ddd/multiindex-rows.html"
           style="width:100%; height:360px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Three-Level MultiIndex
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def get_multiindex3_index_df() -> pd.DataFrame:
        row_index = pd.MultiIndex.from_tuples([
            ('foo', 'a', 3), ('foo', 'b', 2),
            ('bar', 'a', 1), ('bar', 'b', 3), ('bar', 'c', 5),
            ('baz', 'a', 6)])
        return pd.DataFrame({
            'foo_col': [10, 20, 30, 40, 50, 60],
            'bar_col': ['foo', 'bar', 'baz', 'quux', 'boff', None]},
            index=row_index)

    get_multiindex3_index_df()

If two levels are hard, three levels are harder. This exercises the
column-renaming logic that has to handle an arbitrary number of index levels
without collision.

.. raw:: html

   <iframe src="../ddd/multiindex-3-level.html"
           style="width:100%; height:360px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


MultiIndex on Both Axes
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def get_multiindex_with_names_both() -> pd.DataFrame:
        row_index = pd.MultiIndex.from_tuples([
            ('foo', 'a'), ('foo', 'b'),
            ('bar', 'a'), ('bar', 'b'), ('bar', 'c'),
            ('baz', 'a')],
            names=['index_name_1', 'index_name_2'])
        cols = pd.MultiIndex.from_tuples(
            [('foo', 'a'), ('foo', 'b'), ('bar', 'a'),
             ('bar', 'b'), ('bar', 'c'), ('baz', 'a')],
            names=['level_a', 'level_b'])
        return pd.DataFrame([
            [10, 20, 30, 40, 50, 60]] * 6,
            columns=cols, index=row_index)

    get_multiindex_with_names_both()

The boss fight: hierarchical headers on both axes, with named levels on
both sides. This is what ``pd.pivot_table()`` produces on complex groupings.
Everything about column counting, index handling, and header rendering gets
tested simultaneously. There are still improvements planned here — the
spacing is odd, the thick borders aren't in the correct place — but it
displays, which is more than most viewers manage.

.. raw:: html

   <iframe src="../ddd/multiindex-both.html"
           style="width:100%; height:360px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Weird Types (Pandas)
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def df_with_weird_types() -> pd.DataFrame:
        """DataFrame with unusual dtypes that historically broke rendering.
        Exercises: categorical, timedelta, period, interval."""
        return pd.DataFrame({
            'categorical': pd.Categorical(
                ['red', 'green', 'blue', 'red', 'green']),
            'timedelta': pd.to_timedelta(
                ['1 days 02:03:04', '0 days 00:00:01',
                 '365 days', '0 days 00:00:00.001',
                 '0 days 00:00:00.000100']),
            'period': pd.Series(
                pd.period_range('2021-01', periods=5, freq='M')),
            'interval': pd.Series(
                pd.arrays.IntervalArray.from_breaks([0, 1, 2, 3, 4, 5])),
            'int_col': [10, 20, 30, 40, 50],
        })

    df_with_weird_types()

Four types that most viewers ignore:

- **Categorical**: Has a fixed set of allowed values. Not a string.
- **Timedelta**: A duration, not a timestamp. "1 day, 2 hours, 3 minutes,
  4 seconds" is a single value.
- **Period**: A span of time ("January 2021"), not a point in time.
- **Interval**: A range like ``(0, 1]``. Common in ``pd.cut()`` output.

Buckaroo detects each type and applies the appropriate formatter. Timedeltas
display as human-readable durations ("1d 2h 3m 4s"), not raw microsecond
counts.

.. raw:: html

   <iframe src="../ddd/weird-types-pandas.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Weird Types (Polars)
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # from buckaroo/ddd_library.py
    def pl_df_with_weird_types():
        """Polars DataFrame with unusual dtypes that historically broke
        rendering. Exercises: Duration (#622), Time, Categorical,
        Decimal, Binary."""
        import datetime as dt
        import polars as pl
        return pl.DataFrame({
            'duration': pl.Series([100_000, 3_723_000_000,
                86_400_000_000, 500, 60_000_000],
                dtype=pl.Duration('us')),
            'time': [dt.time(14, 30), dt.time(9, 15, 30),
                     dt.time(0, 0, 1), dt.time(23, 59, 59),
                     dt.time(12, 0)],
            'categorical': pl.Series(
                ['red', 'green', 'blue', 'red', 'green']
            ).cast(pl.Categorical),
            'decimal': pl.Series(
                ['100.50', '200.75', '0.01', '99999.99', '3.14']
            ).cast(pl.Decimal(10, 2)),
            'binary': [b'hello', b'world', b'\x00\x01\x02',
                       b'test', b'\xff\xfe'],
            'int_col': [10, 20, 30, 40, 50],
        })

    pl_df_with_weird_types()

Polars has its own set of tricky types:

- **Duration**: Microsecond-precision time spans. Was completely blank before
  issue `#622 <https://github.com/buckaroo-data/buckaroo/issues/622>`_.
- **Time**: Time-of-day without a date component.
- **Decimal**: Fixed-precision decimal (not float). Important for financial data.
- **Binary**: Raw bytes. Displayed as hex strings.

Buckaroo renders both pandas and polars DataFrames with the same viewer. If
you're migrating from pandas to polars, buckaroo moves with you.

.. raw:: html

   <iframe src="../ddd/weird-types-polars.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Full dtype coverage
-------------------

The DDD focuses on the types that cause trouble, but how does buckaroo
handle *every* dtype? Here's the full picture across all three engines [1]_:

.. list-table::
   :header-rows: 1
   :widths: 18 12 12 12 14 14 18

   * - Dtype
     - Pandas
     - Pandas (Arrow)
     - Polars
     - Parquet type
     - JS type
     - Buckaroo display
   * - int8–int32
     - Yes
     - Yes
     - Yes
     - INT32
     - Number
     - ``1,234``
   * - int64
     - Yes
     - Yes
     - Yes
     - INT64
     - Number [2]_
     - ``1,234,567``
   * - uint8–uint64
     - Yes
     - Yes
     - Yes
     - INT32/INT64
     - Number [2]_
     - ``65,535``
   * - BigInt (>2\ :sup:`53`)
     - Yes
     - Yes
     - —
     - INT64
     - String [2]_
     - ``9999999999999999999`` [5]_
   * - float32
     - Yes
     - Yes
     - Yes
     - FLOAT
     - Number
     - ``2.500``
   * - float64 (incl. inf/NaN)
     - Yes
     - Yes
     - Yes
     - DOUBLE
     - Number
     - ``Infinity``
   * - complex128
     - Fail [3]_
     - —
     - —
     - —
     - —
     - —
   * - bool
     - Yes
     - Yes
     - Yes
     - BOOLEAN
     - boolean
     - ``True``
   * - string / object
     - Yes
     - Yes
     - Yes
     - BYTE_ARRAY
     - String
     - ``hello world``
   * - mixed-type object
     - Yes
     - —
     - —
     - BYTE_ARRAY
     - String
     - ``{ 'a': 1, 'b': None }``
   * - datetime
     - Yes
     - Yes
     - Yes
     - TIMESTAMP
     - Date
     - ``2021-01-15 14:30:00``
   * - datetime + tz
     - Not tested
     - Yes
     - Yes
     - TIMESTAMP+tz
     - Date
     - ``2021-01-15 14:30:00``
   * - timedelta / duration
     - Yes
     - Yes
     - Yes
     - → String [4]_
     - String
     - ``1d 2h 3m 4s``
   * - date
     - —
     - Yes
     - Not tested
     - DATE (INT32)
     - Date
     - ``2021-01-15 00:00:00``
   * - time
     - —
     - Yes
     - Yes
     - TIME (INT64)
     - String
     - ``14:30:00``
   * - Categorical
     - Yes
     - Yes
     - Yes
     - DICT encoding
     - String
     - ``red``
   * - Enum
     - —
     - —
     - Not tested
     - DICT encoding
     - String
     - ``red``
   * - Period (time span)
     - Yes
     - —
     - —
     - → String [4]_
     - String
     - ``2021-01`` [6]_
   * - Interval
     - Yes
     - —
     - —
     - → String [4]_
     - String
     - ``(0, 1]``
   * - Decimal
     - —
     - Yes
     - Yes
     - DECIMAL
     - Number
     - ``100.50``
   * - Binary
     - —
     - Yes
     - Yes
     - BYTE_ARRAY
     - String (hex)
     - ``68656c6c6f``
   * - Sparse
     - Fail [3]_
     - —
     - —
     - —
     - —
     - —
   * - Nullable int/float/bool
     - Not tested
     - —
     - —
     - INT32/INT64/BOOLEAN
     - Number/boolean
     - ``1,234`` / ``True``
   * - List / Array
     - —
     - Yes
     - Not tested
     - LIST
     - Array
     - ``[ 1, 2, 3]``
   * - Struct
     - —
     - Yes
     - Not tested
     - STRUCT
     - Object
     - ``{ 'a': 1, 'b': x }``
   * - Null (all-null column)
     - —
     - —
     - Not tested
     - BYTE_ARRAY
     - null
     - ``(empty)``

"Yes" means the dtype serializes and displays correctly. "Not tested" means
serialization succeeds but there is no DDD test case exercising it through
the full widget. "—" means the dtype does not exist in that engine.

.. [1] Putting together this table exposed areas that still need work.
   The interaction between Python dtype, Parquet physical type, JS
   decoding, and display formatter has enough nuance for its own blog
   post. Expect one soon.

.. [2] hyparquet decodes INT64 as BigInt. Buckaroo converts to Number if
   the value is ≤ ``Number.MAX_SAFE_INTEGER`` (2\ :sup:`53` - 1), otherwise
   stringifies to preserve precision.

.. [3] ``complex128`` and ``SparseDtype`` fail the Parquet path — Arrow
   has no complex number type and can't convert sparse arrays. The JSON
   path works with string fallback, but that path is being phased out.

.. [4] ``→ String`` means the type has no native Parquet equivalent.
   Buckaroo coerces it to a string before writing Parquet. Period becomes
   ``'2021-01'``, Interval becomes ``'(0, 1]'``, timedelta becomes
   ``'1 days 02:03:04'`` (pandas path only — Polars Duration is native).

.. [5] Values above ``Number.MAX_SAFE_INTEGER`` are stringified on the JS
   side to preserve exact precision, so they display without commas. The
   value ``1`` in the same column still gets the integer formatter: ``1``.
   This means a single column can show two different display styles depending
   on whether each value fits in 53 bits.

.. [6] A pandas ``Period`` is a *time span*, not a range between two dates.
   ``Period('2021-01', 'M')`` means "the month of January 2021". Buckaroo
   stringifies it because Parquet has no Period type. Don't confuse it with
   ``Interval``, which is a numeric range like ``(0, 1]``.


How this demo was built
-----------------------

Every table on this page is a **static embedding** of the full buckaroo
widget. There is no Python kernel running. Here's what happened:

1. A Python script called ``buckaroo.artifact.to_html()`` on each DataFrame
2. The function serialized the data to base64-encoded Parquet (compact binary)
3. The summary stats (dtype, mean, histogram, etc.) were computed and serialized
4. Everything was embedded in an HTML file as a JSON ``<script>`` tag
5. The ``static-embed.js`` bundle (1.3 MB) decodes the Parquet, renders
   AG-Grid, and draws histograms — all client-side

No server required. The file can be hosted on any static file server, CDN,
or even opened from disk. The tables on this page are iframes pointing to
standalone HTML files that share a single copy of the JS bundle.

For details on how to create your own static embeds, see the
:doc:`embedding-guide`.


Try it yourself
---------------

.. code-block:: python

    from buckaroo.ddd_library import *
    from buckaroo.artifact import to_html
    from pathlib import Path
    import shutil, buckaroo

    # Generate a static HTML page for any DataFrame
    html = to_html(df_with_weird_types(), title="Weird Types Demo")
    with open('weird-types.html', 'w') as f:
        f.write(html)

    # Copy the JS/CSS assets alongside the HTML (see #643 for self-contained mode)
    static = Path(buckaroo.__file__).parent / 'static'
    for name in ('static-embed.js', 'static-embed.css'):
        shutil.copy(static / name, '.')

Or in a Jupyter notebook, just::

    import buckaroo
    from buckaroo.ddd_library import df_with_weird_types
    df_with_weird_types()  # renders inline

The Dastardly DataFrame Dataset is also available as an interactive tour
in Marimo — see ``docs/example-notebooks/marimo-wasm/buckaroo_ddd_tour.py``
in the repository.
