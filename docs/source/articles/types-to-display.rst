How Types and Data Move from Engine to Browser
================================================

You have a DataFrame in Python. Moments later it's rendered in a
browser — scrollable, formatted, with histograms in the summary row.
What happened in between?

This article traces the full path: column renaming, type coercion,
Parquet encoding, base64 transport, hyparquet decoding, and finally the
displayer/formatter system that turns raw values into what you see on
screen.


Column renaming: why everything becomes ``a, b, c``
-----------------------------------------------------

The very first thing buckaroo does when serializing a DataFrame is
rename every column. The original column ``"revenue"`` becomes ``a``.
``"cost"`` becomes ``b``. The 27th column becomes ``aa``, then ``ab``,
``ac``, and so on — base-26 using lowercase ASCII.

.. code-block:: python

    # buckaroo/df_util.py
    def to_chars(n: int) -> str:
        digits = to_digits(n, 26)
        return "".join(map(lambda x: chr(x + 97), digits))

    def old_col_new_col(df):
        return [(orig, to_chars(i)) for i, orig in enumerate(df.columns)]

Why? Three reasons:

1. **Column names can be anything.** Tuples (from MultiIndex), integers,
   strings with spaces and special characters, even a column literally
   called ``"index"``. Parquet column names must be strings. AG-Grid
   field names should be simple identifiers. Renaming to ``a, b, c``
   sidesteps every edge case at once.

2. **Collision avoidance.** When a DataFrame has a column named
   ``"index"`` and we need to serialize the actual index as a column
   too, there's a name collision. Renaming to short opaque names means
   the index columns (``index``, ``index_a``, ``index_b`` for
   MultiIndex levels) never collide with data columns.

3. **Smaller payloads.** The column name is repeated in every row of the
   JSON/Parquet output. ``"a"`` is smaller than
   ``"quarterly_revenue_usd"``.

The original name is preserved in the ``column_config`` that travels
alongside the data. On the JS side, each column's ``header_name``
(or ``col_path`` for MultiIndex) tells AG-Grid what to display in the
header. The user never sees ``a, b, c`` — they see the real names.

.. code-block:: python

    # In styling_core.py — fix_column_config maps col→header_name
    base_cc['col_name'] = col        # "a"
    base_cc['header_name'] = str(orig_col_name)  # "revenue"


Cleaning before serialization
------------------------------

Python's type system is richer than what Parquet (or JSON) can express
directly. Before writing to Parquet, buckaroo coerces the awkward types:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Python type
     - Becomes
     - Why
   * - ``pd.Period`` (e.g. "2021-01")
     - ``str``
     - Parquet has no period type
   * - ``pd.Interval`` (e.g. ``(0, 1]``)
     - ``str``
     - Parquet has no interval type
   * - ``pd.Timedelta``
     - ``str`` (e.g. "1 days 02:03:04")
     - fastparquet can't encode timedeltas
   * - ``bytes`` (e.g. from ``pl.Binary``)
     - hex string (e.g. ``"68656c6c6f"``)
     - Parquet object columns need strings
   * - PyArrow-backed strings
     - ``object`` dtype
     - fastparquet needs object, not ArrowDtype
   * - Timezone-naive datetimes
     - UTC datetimes
     - Avoids ambiguous serialization

For the main DataFrame, this happens in ``to_parquet()``
(``serialization_utils.py``). The function also calls
``prepare_df_for_serialization()`` which does the column rename and
flattens MultiIndex levels into regular columns (``index_a``,
``index_b``, etc.).

Summary stats have an additional wrinkle: each column's stats dict
contains mixed types (strings like ``"int64"`` for dtype, floats for
mean, lists for histogram bins). fastparquet can't handle mixed-type
columns, so ``sd_to_parquet_b64()`` JSON-encodes every cell value first,
making each column a pure string column. The JS side knows to
``JSON.parse`` each cell back.

.. code-block:: python

    # Every cell becomes a JSON string before parquet encoding
    def _json_encode_cell(val):
        return json.dumps(_make_json_safe(val), default=str)


Parquet encoding and base64 transport
--------------------------------------

buckaroo uses **fastparquet** with a custom JSON codec to write the
DataFrame to an in-memory Parquet file. Categorical and object columns
get JSON-encoded within the Parquet file (fastparquet's ``object_encoding='json'``).

The raw Parquet bytes are then base64-encoded into an ASCII string:

.. code-block:: python

    def to_parquet_b64(df):
        raw_bytes = to_parquet(df)
        return base64.b64encode(raw_bytes).decode('ascii')

The result is a tagged payload:

.. code-block:: json

    {"format": "parquet_b64", "data": "UEFSMQ..."}

This travels over the wire — via Jupyter's comm protocol, a WebSocket,
or embedded directly in an HTML ``<script>`` tag for static embeds. The
format tag lets the JS side know it needs to decode Parquet rather than
expecting raw JSON arrays.

Why Parquet instead of JSON? Parquet is a columnar binary format —
it's typically 5–10x smaller than the equivalent JSON for numeric data,
and it preserves type information (int64 vs float64 vs string) that
JSON discards.


hyparquet: decoding Parquet in the browser
-------------------------------------------

On the JavaScript side, `hyparquet <https://github.com/hyparam/hyparquet>`_
is a pure-JS Parquet reader. No WASM, no server — it reads the binary
format directly in the browser.

.. code-block:: typescript

    // resolveDFData.ts
    const buf = b64ToArrayBuffer(val.data);         // base64 → ArrayBuffer
    const metadata = parquetMetadata(buf);           // read parquet footer
    parquetRead({
        file: buf,
        metadata,
        rowFormat: 'object',
        onComplete: (data) => {
            result = data.map(parseParquetRow);      // JSON.parse each cell
        },
    });

The ``parseParquetRow`` step handles two things the raw Parquet decode
doesn't:

1. **JSON-encoded cells** (from summary stats): each string cell gets
   ``JSON.parse``'d back to its real type — numbers, arrays, objects.

2. **BigInt safety**: hyparquet decodes Parquet INT64 columns as
   JavaScript ``BigInt``. If the value fits in ``Number.MAX_SAFE_INTEGER``
   (2^53 - 1), it's converted to a regular ``Number``. Otherwise it's
   stringified to preserve precision — this is why
   ``9999999999999999999`` displays correctly instead of silently rounding.

Results are cached (LRU, 8 entries) so switching between summary
stats views doesn't re-decode the same Parquet bytes.


Displayers and formatters: the last mile
------------------------------------------

At this point we have rows of data (``DFData``) and a ``column_config``
that describes how each column should look. The ``column_config`` for
each column includes a ``displayer_args`` object that names a
**displayer** — this is the bridge between "raw value" and "what the
user sees in the cell."

The Python side picks the displayer based on summary stats:

.. code-block:: python

    # In a StylingAnalysis subclass
    def style_column(cls, col, col_meta):
        dtype = col_meta.get('dtype')
        if dtype == 'float64':
            return {'displayer_args': {
                'displayer': 'float',
                'min_fraction_digits': 2,
                'max_fraction_digits': 4}}
        elif dtype == 'timedelta64[ns]':
            return {'displayer_args': {'displayer': 'duration'}}
        ...

The JS side receives this config and dispatches to the right formatter:

.. code-block:: typescript

    // Displayer.ts — getFormatter() is the dispatcher
    switch (fArgs.displayer) {
        case "integer":  return getIntegerFormatter(fArgs);
        case "float":    return getFloatFormatter(fArgs);
        case "string":   return getStringFormatter(fArgs);
        case "boolean":  return booleanFormatter;
        case "duration": return getDurationFormatter();
        case "obj":      return getObjectFormatter(fArgs);
        ...
    }

Each formatter is an AG-Grid ``ValueFormatterFunc`` — it receives the
raw cell value and returns the display string. Some highlights:

- **Integers** get thousands separators via ``Intl.NumberFormat`` and
  right-padding for alignment.
- **Floats** get configurable decimal places, also via
  ``Intl.NumberFormat``, with padding to align decimal points across
  rows.
- **Durations** parse pandas timedelta strings (``"1 days 02:03:04"``)
  and render as ``"1d 2h 3m 4s"``, with sub-second precision down to
  microseconds.
- **Booleans** display as Python-convention ``True``/``False``, not
  JS-convention ``true``/``false``.
- **Objects** (dicts, lists, None) get a recursive Python-like repr:
  ``{ 'key': value }``, ``[ 1, 2, 3 ]``, ``None``.

For richer displays, there are **cell renderers** instead of formatters
— these return React components rather than strings. Histograms, charts,
links, images, and SVGs all use this path.

.. code-block:: typescript

    // Cell renderers return React components
    case "histogram": return HistogramCell;
    case "linkify":   return LinkCellRenderer;
    case "chart":     return getChartCell(crArgs);


The full pipeline
------------------

Putting it all together, here's the journey of a single cell value —
say, a ``pd.Timedelta`` of "1 day, 2 hours, 3 minutes, 4 seconds":

.. code-block:: text

    Python                          Wire              Browser
    ──────                          ────              ───────
    pd.Timedelta('1d 2h 3m 4s')
        │
        ▼
    rename columns (a, b, c...)
        │
        ▼
    coerce to str: "1 days 02:03:04"
        │
        ▼
    write to Parquet (fastparquet)
        │
        ▼
    base64 encode ──────────────► {"format": "parquet_b64",
                                   "data": "UEFSMQ..."}
                                        │
                                        ▼
                                  b64 → ArrayBuffer
                                        │
                                        ▼
                                  hyparquet.parquetRead()
                                        │
                                        ▼
                                  parseParquetRow() → "1 days 02:03:04"
                                        │
                                        ▼
                                  getDurationFormatter()
                                        │
                                        ▼
                                  formatDuration() → "1d 2h 3m 4s"
                                        │
                                        ▼
                                  AG-Grid renders: │ 1d 2h 3m 4s │

The column header shows the original name from ``header_name`` in the
config. The user sees a human-readable duration in a column with its
real name. Everything in between — the rename, the coercion, the binary
encoding, the BigInt handling — is invisible.

That's the point. The pipeline exists so that every type, every edge
case, every weird DataFrame gets displayed correctly without the user
having to think about it.
