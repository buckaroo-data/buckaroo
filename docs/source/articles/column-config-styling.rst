Column Config Styling
=====================

Buckaroo tables can be extensively styled per column — number formats,
date locales, link rendering, inline histograms and charts, embedded
images, conditional cell backgrounds, tooltips. Every example on this
page is a live static embed: no server, no kernel, just HTML and
JavaScript.

The single entry point is the ``column_config_overrides`` argument:

.. code-block:: python

    import buckaroo

    buckaroo.BuckarooInfiniteWidget(df, column_config_overrides={
        "float_col": {
            "displayer_args": {
                "displayer": "float",
                "min_fraction_digits": 1,
                "max_fraction_digits": 3,
            }
        }
    })

Three independent properties can be set per column — they compose:

- ``displayer_args`` — how cell values are *rendered* (number formatting,
  date locales, link / image / histogram / chart).
- ``color_map_config`` — conditional cell *background colors*, optionally
  driven by another column.
- ``tooltip_config`` — hover content, typically pulled from another column.

Plus the structural ``merge_rule: "hidden"`` for dropping a column from
view (commonly used together with ``color_map_config`` so the source
column doesn't show up in the table).

The same configs work in every entry point — widget, static artifact,
or server:

.. code-block:: python

    # Jupyter / IPython
    w = buckaroo.BuckarooWidget(df, column_config_overrides={...})

    # Static embed — same shape
    from buckaroo.artifact import prepare_buckaroo_artifact
    artifact = prepare_buckaroo_artifact(df, column_config_overrides={...})

    # MCP / server — pass in the /load request body
    {"session": "...", "path": "data.csv", "component_config": {...},
     "column_config_overrides": {...}}

For programmatic styling (functions that look at summary stats and
return configs per column) see the
`Styling-Howto notebook
<https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Styling-Howto.ipynb>`_.


Displayer gallery
-----------------

Each table below renders a small fixture with a different
``displayer_args`` config. The code block above each iframe is the exact
``column_config_overrides`` that produced it.


Datetime displayers
~~~~~~~~~~~~~~~~~~~

Datetime columns can be rendered with the default formatter, Python's
``str()`` (via ``obj``), or any
`Intl.DateTimeFormat <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat>`_
locale.

.. code-block:: typescript

    interface DatetimeDefaultDisplayerA {
        displayer: 'datetimeDefault';
    }
    interface DatetimeLocaleDisplayerA {
        displayer: 'datetimeLocaleString';
        locale: 'en-US' | 'en-GB' | 'en-CA' | 'fr-FR' | 'es-ES' | 'de-DE' | 'ja-JP';
        args: Intl.DateTimeFormatOptions;
    }

.. code-block:: python

    column_config_overrides = {
        "obj":         {"displayer_args": {"displayer": "obj"}},
        "default":     {"displayer_args": {"displayer": "datetimeDefault"}},
        "en-US":       {"displayer_args": {"displayer": "datetimeLocaleString",
                                            "locale": "en-US"}},
        "en-US-long":  {"displayer_args": {"displayer": "datetimeLocaleString",
                                            "locale": "en-US",
                                            "args": {"weekday": "long"}}},
        "en-GB":       {"displayer_args": {"displayer": "datetimeLocaleString",
                                            "locale": "en-GB"}},
    }

.. raw:: html

   <iframe src="../styling/datetime.html"
           style="width:100%; height:260px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


String displayer
~~~~~~~~~~~~~~~~

The ``string`` displayer accepts a ``max_length`` that truncates long
values with an ellipsis. The full value is still available via tooltip
(see `Tooltip`_ below). Compare against ``obj`` (Python ``repr``-style)
and the bare ``string`` form (no truncation).

.. code-block:: typescript

    interface StringDisplayerA {
        displayer: 'string';
        max_length?: number;
    }

.. code-block:: python

    column_config_overrides = {
        "string_max_len_35": {"displayer_args": {"displayer": "string",
                                                  "max_length": 35}},
        "obj_displayer":     {"displayer_args": {"displayer": "obj"}},
        "string_displayer":  {"displayer_args": {"displayer": "string"}},
    }

.. raw:: html

   <iframe src="../styling/string.html"
           style="width:100%; height:260px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Float displayer
~~~~~~~~~~~~~~~

The ``float`` displayer controls digits after the decimal point. Min
and max fraction digits work like
`Intl.NumberFormat <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat>`_
— ``(1, 3)`` shows at least 1 and up to 3, ``(3, 3)`` always shows 3.

.. code-block:: typescript

    interface FloatDisplayerA {
        displayer: 'float';
        min_fraction_digits: number;
        max_fraction_digits: number;
    }

.. code-block:: python

    column_config_overrides = {
        "obj_displayer": {"displayer_args": {"displayer": "obj"}},
        "float_1_3":     {"displayer_args": {"displayer": "float",
                                              "min_fraction_digits": 1,
                                              "max_fraction_digits": 3}},
        "float_0_3":     {"displayer_args": {"displayer": "float",
                                              "min_fraction_digits": 0,
                                              "max_fraction_digits": 3}},
        "float_3_3":     {"displayer_args": {"displayer": "float",
                                              "min_fraction_digits": 3,
                                              "max_fraction_digits": 3}},
        "float_3_13":    {"displayer_args": {"displayer": "float",
                                              "min_fraction_digits": 3,
                                              "max_fraction_digits": 13}},
    }

.. raw:: html

   <iframe src="../styling/float.html"
           style="width:100%; height:260px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Link displayer
~~~~~~~~~~~~~~

Turns a string column into a clickable link.

.. code-block:: typescript

    interface LinkifyDisplayerA {
        displayer: 'linkify';
    }

.. code-block:: python

    column_config_overrides = {
        "linkify": {"displayer_args": {"displayer": "linkify"}},
    }

.. raw:: html

   <iframe src="../styling/link.html"
           style="width:100%; height:200px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Histogram displayer
~~~~~~~~~~~~~~~~~~~

Histograms normally live in summary stats and pinned rows, but the same
shape can be rendered inline in a data column. Each cell holds a list
of ``{name, ...}`` objects — buckaroo's histogram conventions:

- ``cat_pop`` — population of a category
- ``unique`` — population of unique values
- ``longtail`` — population of long-tail buckets
- ``NA`` — population of null values

.. code-block:: typescript

    interface HistogramDisplayerA {
        displayer: 'histogram';
    }

.. code-block:: python

    column_config_overrides = {
        "histogram_props": {"displayer_args": {"displayer": "histogram"}},
    }

.. raw:: html

   <iframe src="../styling/histogram.html"
           style="width:100%; height:240px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Chart displayer
~~~~~~~~~~~~~~~

The ``chart`` displayer is a richer version of the histogram: line,
area, and bar series can be combined per cell. Series names with the
prefixes ``line``, ``area``, and ``bar`` are recognized; the suffix
controls the color. Pass a ``colors`` dict to remap the custom
(``barCustom1`` / ``barCustom2`` / ``barCustom3``) palette.

.. code-block:: python

    column_config_overrides = {
        "chart": {"displayer_args": {"displayer": "chart"}},
        "chart_custom_colors": {"displayer_args": {
            "displayer": "chart",
            "colors": {"custom1_color": "pink",
                       "custom2_color": "brown",
                       "custom3_color": "beige"},
        }},
    }

.. raw:: html

   <iframe src="../styling/chart.html"
           style="width:100%; height:240px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Image displayer
~~~~~~~~~~~~~~~

``Base64PNGImageDisplayer`` decodes a base64 PNG payload into an
``<img>``. Pair it with an ``ag_grid_specs.width`` so the column is wide
enough for the image. The same column can be displayed as a raw string
in another column to show the underlying payload.

.. code-block:: typescript

    interface Base64PNGImageDisplayerA {
        displayer: 'Base64PNGImageDisplayer';
    }

.. code-block:: python

    column_config_overrides = {
        "raw": {"displayer_args": {"displayer": "string",
                                    "max_length": 40}},
        "image": {"displayer_args": {"displayer": "Base64PNGImageDisplayer"},
                  "ag_grid_specs": {"width": 150}},
    }

.. raw:: html

   <iframe src="../styling/image.html"
           style="width:100%; height:240px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Color rules
-----------

``color_map_config`` controls cell *background* color. It composes with
``displayer_args`` — you can format numbers *and* color them at the
same time.

The ``color_rule`` field selects between four strategies described below.


Color map (continuous)
~~~~~~~~~~~~~~~~~~~~~~

``color_rule: "color_map"`` interpolates a built-in or custom palette
across the column's value range. The optional ``val_column`` lets one
column be colored based on values from another (e.g. ``float_col``
shaded by ``int_col``).

Built-in maps: ``BLUE_TO_YELLOW``, ``DIVERGING_RED_WHITE_BLUE``.
Custom: pass a list of CSS colors.

.. code-block:: typescript

    type ColorMap = 'BLUE_TO_YELLOW' | 'DIVERGING_RED_WHITE_BLUE' | string[];
    interface ColorMapRules {
        color_rule: 'color_map';
        map_name: ColorMap;
        val_column?: string;  // column whose values drive the gradient
    }

.. code-block:: python

    column_config_overrides = {
        "float_col": {"color_map_config": {
            "color_rule": "color_map",
            "map_name": "BLUE_TO_YELLOW",
            "val_column": "int_col",
        }},
    }

.. raw:: html

   <iframe src="../styling/color-map-continuous.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Color map (explicit palette)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pass an explicit list of CSS colors as ``map_name``. The palette is
distributed across the value range — useful for flagging values from a
discrete set of categories.

This example shows the same data with two palette lengths (5 vs 10) and
two value ranges (5 vs 10 distinct values) to make the distribution
visible.

.. code-block:: python

    colors_10 = ["green", "blue", "red", "orange", "purple",
                 "brown", "pink", "beige", "teal", "gray"]
    colors_5  = ["green", "blue", "red", "orange", "purple"]

    column_config_overrides = {
        "ten_vals_10_colors":  {"color_map_config": {"color_rule": "color_map",
                                                      "map_name": colors_10}},
        "ten_vals_5_colors":   {"color_map_config": {"color_rule": "color_map",
                                                      "map_name": colors_5}},
        "five_vals_10_colors": {"color_map_config": {"color_rule": "color_map",
                                                      "map_name": colors_10}},
        "five_vals_5_colors":  {"color_map_config": {"color_rule": "color_map",
                                                      "map_name": colors_5}},
    }

.. raw:: html

   <iframe src="../styling/color-map-explicit.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Color from column
~~~~~~~~~~~~~~~~~

``color_rule: "color_from_column"`` reads a literal CSS color from
another column for each row. Useful when colors are precomputed (e.g.
mapped from a category by an upstream process).

.. code-block:: typescript

    interface ColorFromColumn {
        color_rule: 'color_from_column';
        val_column: string;  // column holding CSS color strings
    }

.. code-block:: python

    column_config_overrides = {
        "a": {"color_map_config": {
            "color_rule": "color_from_column",
            "val_column": "a_colors",
        }},
    }

.. raw:: html

   <iframe src="../styling/color-from-column.html"
           style="width:100%; height:180px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Error highlighting (``color_not_null``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``color_rule: "color_not_null"`` colors a cell when an *adjacent*
column has a non-null value. The classic shape is: a data column plus
an error-message column. Show the data, color it red when there's an
error, surface the message in the tooltip, and hide the message column
itself so it doesn't clutter the view.

This combines three properties on the same column:

.. code-block:: typescript

    interface ColorWhenNotNullRules {
        color_rule: 'color_not_null';
        conditional_color: string;  // any CSS color
        exist_column: string;        // null-check this column
    }

.. code-block:: python

    column_config_overrides = {
        "a": {
            "color_map_config": {
                "color_rule": "color_not_null",
                "conditional_color": "red",
                "exist_column": "err_messages",
            },
            "tooltip_config": {
                "tooltip_type": "simple",
                "val_column": "err_messages",
            },
        },
        "err_messages": {"merge_rule": "hidden"},
    }

.. raw:: html

   <iframe src="../styling/error-highlight.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Tooltip
-------

``tooltip_config`` populates the hover tooltip from another column.
Useful when the visible column is truncated (``max_length`` on a
``string`` displayer) but you want the full value reachable on hover,
or when one column annotates another.

.. code-block:: typescript

    interface SimpleTooltip {
        tooltip_type: 'simple';
        val_column: string;
    }

.. code-block:: python

    column_config_overrides = {
        "str_col": {"tooltip_config": {
            "tooltip_type": "simple",
            "val_column": "int_col",
        }},
    }

.. raw:: html

   <iframe src="../styling/tooltip.html"
           style="width:100%; height:320px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


How styling is applied
----------------------

For each visible column, buckaroo computes a ``column_config`` dict in
three layers, last writer wins:

1. **Default styling** — picks a displayer based on the inferred type
   (``string`` for objects, ``float`` for floats, etc.) and attaches a
   default tooltip and column width.
2. **Summary-stat-aware styling** — analysis classes can override the
   default based on what's in the column (e.g. ``Base64PNGImageDisplayer``
   when the value looks like a PNG payload).
3. **``column_config_overrides``** — the dict passed at widget
   construction. Per-key shallow merge into the result of (1)+(2).

So overrides win, but you don't have to specify every property —
the defaults fill in the gaps. ``merge_rule: "hidden"`` is special:
it removes the column from the result rather than overriding its
``column_config``.

In server mode, ``column_config_overrides`` rides alongside the
DataFrame display configuration in the session state. When the user
changes the cleaning method or post-processing option, the dataflow
rebuilds ``df_display_args`` from scratch — but ``column_config_overrides``
is re-applied afterwards so per-column styling survives interaction.


Building your own styling functions
-----------------------------------

The static ``column_config_overrides`` dict covers most cases. For
styling that depends on column *content* (e.g. "color any int column
whose max value is over 1000"), write a styling function that reads
summary stats and returns a config dict. See the
`Styling-Howto notebook
<https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Styling-Howto.ipynb>`_
for the full pattern, plus the
`Styling-Gallery-Pandas
<https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Styling-Gallery-Pandas.ipynb>`_
and `Styling-Gallery-Polars
<https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Styling-Gallery-Polars.ipynb>`_
notebooks for backend-specific examples.


Generating these embeds
-----------------------

The static embeds on this page were generated with:

.. code-block:: bash

    python scripts/generate_column_config_static_html.py

This produces HTML files in ``docs/extra-html/styling/`` that reference
the shared ``static-embed.js`` and ``static-embed.css`` bundles
(produced by ``scripts/full_build.sh``).
