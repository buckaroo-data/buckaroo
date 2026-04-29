Theme Customization
===================

Buckaroo tables automatically match your OS light/dark preference. But
sometimes you want more control — a branded dashboard, a high-contrast
accessibility mode, or just a color scheme you enjoy staring at for hours.

The ``component_config.theme`` dictionary gives you full control over the
color scheme without touching CSS. Every example on this page is a live
static embed — no server, no kernel, just HTML and JavaScript.

Quick start
-----------

.. code-block:: python

    import buckaroo

    # Jupyter / IPython — just set component_config on the widget
    w = buckaroo.BuckarooWidget(df, component_config={
        'theme': {
            'colorScheme': 'dark',
            'accentColor': '#00bcd4',
        }
    })

    # Static embed — inject theme into the artifact
    from buckaroo.artifact import prepare_buckaroo_artifact, artifact_to_json

    artifact = prepare_buckaroo_artifact(df)
    artifact['df_viewer_config'].setdefault('component_config', {})['theme'] = {
        'colorScheme': 'dark',
        'accentColor': '#00bcd4',
    }

    # MCP server — pass component_config in the /load request body
    {"session": "my-session", "path": "data.csv", "component_config": {
        "theme": {"colorScheme": "dark", "accentColor": "#00bcd4"}
    }}


ThemeConfig reference
---------------------

All properties are optional. Omitted properties use sensible defaults
based on the resolved color scheme.

Color properties
~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 22 14 50

   * - Property
     - Type
     - Description
   * - ``colorScheme``
     - ``'light'`` | ``'dark'`` | ``'auto'``
     - Override OS color scheme detection. ``'auto'`` (the default) respects
       the user's system preference.
   * - ``accentColor``
     - CSS color
     - Primary highlight color for column selection, active tabs, and buttons.
       Default: ``#2196F3`` (blue).
   * - ``accentHoverColor``
     - CSS color
     - Hover state for accent elements. Should be a darker shade of
       ``accentColor``.
   * - ``backgroundColor``
     - CSS color
     - Main table background. Default: ``#ffffff`` (light) or ``#181D1F``
       (dark).
   * - ``foregroundColor``
     - CSS color
     - Text and icon color. Passed through to AG Grid's theme system.
   * - ``oddRowBackgroundColor``
     - CSS color
     - Alternating row stripe color. Default: ``#f5f5f5`` (light) or
       ``#222628`` (dark).
   * - ``borderColor``
     - CSS color
     - Grid line and border color. Passed through to AG Grid's theme system.
   * - ``headerBorderColor``
     - CSS color
     - Border color between column headers. Controls the vertical dividers
       between columns in the header row — including MultiIndex group headers.
   * - ``headerBackgroundColor``
     - CSS color
     - Background color for all header rows. With MultiIndex columns, this
       colors both the group header row and the leaf header row.

Layout properties
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 28 10 48

   * - Property
     - Type
     - Description
   * - ``spacing``
     - number
     - Base spacing unit in pixels. Controls the overall density of the grid.
       Default: ``5``. Lower values = more compact.
   * - ``cellHorizontalPaddingScale``
     - number
     - Multiplier for horizontal cell padding. Default: ``0.3``. Use ``0.1``
       for very tight or ``1.0`` for spacious.
   * - ``rowVerticalPaddingScale``
     - number
     - Multiplier for vertical row padding. Default: ``0.5``. Use ``0.2``
       for compact or ``1.2`` for airy.


Auto light/dark with ``light`` and ``dark`` sub-dicts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``colorScheme`` is ``'auto'``, the table follows the OS preference.
But a single set of colors can't look good in both modes. Use ``light``
and ``dark`` sub-dicts to define separate palettes:

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'auto',
        'light': {
            'accentColor': '#e65100',
            'backgroundColor': '#fff8f0',
            'foregroundColor': '#3e2723',
            'oddRowBackgroundColor': '#fff3e0',
            'borderColor': '#ffe0b2',
        },
        'dark': {
            'accentColor': '#ffab40',
            'backgroundColor': '#1a1209',
            'foregroundColor': '#ffe0b2',
            'oddRowBackgroundColor': '#2a1e0f',
            'borderColor': '#4e342e',
        },
    }}

The resolution order is: **scheme-specific override > top-level color >
built-in default**. This means you can set shared properties at the top
level and override only what differs per scheme:

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'auto',
        'spacing': 8,                     # shared — same in light and dark
        'headerBorderColor': '#7c4dff',   # shared
        'light': {
            'accentColor': '#7c4dff',
            'backgroundColor': '#faf8ff',
        },
        'dark': {
            'accentColor': '#b388ff',
            'backgroundColor': '#1a1028',
        },
    }}

Both ``light`` and ``dark`` accept all color and layout properties from
``ThemeColorConfig``.


CSS custom properties
~~~~~~~~~~~~~~~~~~~~~

Theme properties are injected as CSS custom properties on the wrapper
``div``, so they cascade into all child components:

- ``--bk-accent-color`` — accent color
- ``--bk-accent-hover-color`` — accent hover color
- ``--bk-bg-color`` — background color (always set, with scheme-based fallback)
- ``--bk-fg-color`` — foreground color


Theme gallery
-------------

Each table below renders the same 10-row cities dataset with a different
theme configuration. Click a column to see the accent color in action.


Default (Light)
~~~~~~~~~~~~~~~

No theme overrides. Uses the OS-detected color scheme with built-in defaults.

.. code-block:: python

    component_config = {}  # no theme key needed

.. raw:: html

   <iframe src="../themes/default-light.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Default (Dark)
~~~~~~~~~~~~~~

Force dark mode with just ``colorScheme``. All other colors use the
built-in dark defaults — no need to specify ``backgroundColor`` or
``oddRowBackgroundColor``.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
    }}

.. raw:: html

   <iframe src="../themes/default-dark.html"
           style="width:100%; height:280px; border:1px solid #333; border-radius:4px; margin:1em 0;">
   </iframe>


..
   Custom Accent Color
   ~~~~~~~~~~~~~~~~~~~

   Override just the accent color. Everything else stays default. This is the
   most common customization — match your brand without changing the overall
   look.

   .. code-block:: python

       component_config = {'theme': {
           'accentColor': '#ff6600',      # orange — click a column to see it
           'accentHoverColor': '#cc5200', # darker orange — command UI buttons
       }}

   .. raw:: html

      <iframe src="../themes/accent-color.html"
              style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
      </iframe>


Ocean Dark
~~~~~~~~~~

A deep ocean-inspired dark theme with cyan accents. Good for dashboards
with a calm, professional feel.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': '#00bcd4',
        'accentHoverColor': '#0097a7',
        'backgroundColor': '#0a1628',
        'foregroundColor': '#b0bec5',
        'oddRowBackgroundColor': '#0d2137',
        'borderColor': '#1a3a5c',
    }}

.. raw:: html

   <iframe src="../themes/ocean-dark.html"
           style="width:100%; height:280px; border:1px solid #1a3a5c; border-radius:4px; margin:1em 0;">
   </iframe>


Warm Light
~~~~~~~~~~

A warm, earthy light theme with orange accents. Works well for data
presentations where the default blue feels too clinical.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'light',
        'accentColor': '#e65100',
        'accentHoverColor': '#bf360c',
        'backgroundColor': '#fff8f0',
        'foregroundColor': '#3e2723',
        'oddRowBackgroundColor': '#fff3e0',
        'borderColor': '#ffe0b2',
    }}

.. raw:: html

   <iframe src="../themes/warm-light.html"
           style="width:100%; height:280px; border:1px solid #ffe0b2; border-radius:4px; margin:1em 0;">
   </iframe>


Neon Dark
~~~~~~~~~

A cyberpunk-inspired dark theme with hot pink accents. The same colors
used in the Storybook ``FullCustom`` story.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': '#e91e63',
        'accentHoverColor': '#c2185b',
        'backgroundColor': '#1a1a2e',
        'foregroundColor': '#e0e0e0',
        'oddRowBackgroundColor': '#16213e',
        'borderColor': '#0f3460',
    }}

.. raw:: html

   <iframe src="../themes/neon-dark.html"
           style="width:100%; height:280px; border:1px solid #0f3460; border-radius:4px; margin:1em 0;">
   </iframe>


Forest Dark
~~~~~~~~~~~

A dark theme with forest green accents — easy on the eyes for long
data exploration sessions.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': '#66bb6a',
        'accentHoverColor': '#43a047',
        'backgroundColor': '#1b2a1b',
        'foregroundColor': '#c8e6c9',
        'oddRowBackgroundColor': '#223322',
        'borderColor': '#2e7d32',
    }}

.. raw:: html

   <iframe src="../themes/forest-dark.html"
           style="width:100%; height:280px; border:1px solid #2e7d32; border-radius:4px; margin:1em 0;">
   </iframe>


Minimal Light
~~~~~~~~~~~~~

A neutral, low-contrast light theme that keeps data front and center.
Uses only grays — no color distractions.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'light',
        'accentColor': '#9e9e9e',
        'accentHoverColor': '#757575',
        'backgroundColor': '#ffffff',
        'foregroundColor': '#212121',
        'oddRowBackgroundColor': '#fafafa',
        'borderColor': '#e0e0e0',
    }}

.. raw:: html

   <iframe src="../themes/minimal-light.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


High Contrast
~~~~~~~~~~~~~

Maximum contrast for accessibility. Bright yellow accents on pure black,
with white text and borders.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': '#ffff00',
        'accentHoverColor': '#ffd600',
        'backgroundColor': '#000000',
        'foregroundColor': '#ffffff',
        'oddRowBackgroundColor': '#1a1a1a',
        'borderColor': '#ffffff',
    }}

.. raw:: html

   <iframe src="../themes/high-contrast.html"
           style="width:100%; height:280px; border:1px solid #fff; border-radius:4px; margin:1em 0;">
   </iframe>


Auto Light/Dark (Branded)
~~~~~~~~~~~~~~~~~~~~~~~~~

Follows the OS preference with separate branded palettes for each scheme.
Toggle your OS between light and dark mode to see it switch.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'auto',
        'light': {
            'accentColor': '#e65100',
            'accentHoverColor': '#bf360c',
            'backgroundColor': '#fff8f0',
            'foregroundColor': '#3e2723',
            'oddRowBackgroundColor': '#fff3e0',
            'borderColor': '#ffe0b2',
        },
        'dark': {
            'accentColor': '#ffab40',
            'accentHoverColor': '#ff9100',
            'backgroundColor': '#1a1209',
            'foregroundColor': '#ffe0b2',
            'oddRowBackgroundColor': '#2a1e0f',
            'borderColor': '#4e342e',
        },
    }}

.. raw:: html

   <iframe src="../themes/auto-branded.html"
           style="width:100%; height:280px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


Spacious Layout
~~~~~~~~~~~~~~~

Increased spacing, padding, and a purple header border. Good for
presentations and read-only dashboards where data density isn't critical.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': '#7c4dff',
        'accentHoverColor': '#651fff',
        'spacing': 10,
        'rowVerticalPaddingScale': 1.2,
        'cellHorizontalPaddingScale': 0.8,
        'headerBorderColor': '#7c4dff',
    }}

.. raw:: html

   <iframe src="../themes/spacious.html"
           style="width:100%; height:360px; border:1px solid #7c4dff; border-radius:4px; margin:1em 0;">
   </iframe>


Compact Layout
~~~~~~~~~~~~~~

Minimal spacing for maximum data density. Fits more rows on screen — good
for power users who want to see as much data as possible.

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'light',
        'spacing': 2,
        'rowVerticalPaddingScale': 0.2,
        'cellHorizontalPaddingScale': 0.15,
        'headerBorderColor': '#bdbdbd',
    }}

.. raw:: html

   <iframe src="../themes/compact.html"
           style="width:100%; height:240px; border:1px solid #e0e0e0; border-radius:4px; margin:1em 0;">
   </iframe>


VC Pricing Page
~~~~~~~~~~~~~~~

Buckaroo's default styling is what I call **trader styling** — jam
information into every pixel, minimize whitespace, maximize data density.
This is the opposite: **VC styling**. Generous padding, pastel accents,
and three columns where the last one says "Call us for pricing".

.. code-block:: python

    # The data
    df = pd.DataFrame({
        'Feature': ['Seats', 'Storage', 'API calls/mo',
                    'SSO', 'Audit log', 'Support'],
        'Starter': ['5', '10 GB', '1,000',
                    'No', 'No', 'Email'],
        'Enterprise': ['Unlimited', 'Unlimited', 'Unlimited',
                       'Yes', 'Yes', 'Call us for pricing'],
    })

    # The theme
    component_config = {'theme': {
        'colorScheme': 'light',
        'accentColor': '#6c5ce7',
        'accentHoverColor': '#5a4bd1',
        'backgroundColor': '#ffffff',
        'foregroundColor': '#2d3436',
        'oddRowBackgroundColor': '#f8f9ff',
        'borderColor': '#e8e8f0',
        'headerBorderColor': '#6c5ce7',
        'spacing': 16,
        'rowVerticalPaddingScale': 2.0,
        'cellHorizontalPaddingScale': 1.5,
    }}

.. raw:: html

   <iframe src="../themes/vc-pricing.html"
           style="width:100%; height:700px; border:1px solid #e8e8f0; border-radius:12px; margin:1em 0;">
   </iframe>


MultiIndex Headers
~~~~~~~~~~~~~~~~~~

MultiIndex (hierarchical) column headers are common after ``pivot_table()``
and ``groupby().agg()``. Three theme properties target the header area:

- ``borderColor`` — controls all grid borders, including the thick separator
  below the header and the vertical dividers between MultiIndex group cells
- ``headerBorderColor`` — targets only the vertical dividers between column
  headers (overrides ``borderColor`` for header cells)
- ``headerBackgroundColor`` — colors all header rows, making the group
  hierarchy visually distinct from the data area

.. code-block:: python

    # The data — what pivot_table() produces
    cols = pd.MultiIndex.from_tuples([
        ('Revenue', 'Q1'), ('Revenue', 'Q2'), ('Revenue', 'Q3'),
        ('Headcount', 'Engineering'), ('Headcount', 'Sales'),
        ('Headcount', 'Support'),
    ], names=['Category', 'Detail'])
    df = pd.DataFrame(..., columns=cols)

Every property below uses a deliberately garish color so you can see
exactly what it controls:

.. code-block:: python

    component_config = {'theme': {
        'colorScheme': 'dark',
        'accentColor': 'purple',
        'accentHoverColor': 'orange',
        'backgroundColor': 'blue',
        'foregroundColor': 'teal',
        'oddRowBackgroundColor': 'red',
        'borderColor': 'pink',
        'headerBorderColor': 'green',
        'headerBackgroundColor': 'brown',
    }}

.. raw:: html

   <iframe src="../themes/multiindex-headers.html"
           style="width:100%; height:360px; border:1px solid #ff69b4; border-radius:4px; margin:1em 0;">
   </iframe>


How theming works under the hood
---------------------------------

Theme configuration flows through three layers:

1. **Python** — ``component_config['theme']`` is a dict that rides alongside
   the DataFrame display configuration. It's stored in ``df_viewer_config``
   and serialized to JSON.

2. **CSS custom properties** — The React layer reads the theme dict and
   sets ``--bk-accent-color``, ``--bk-bg-color``, etc. as inline styles
   on the wrapper ``div``. All child components inherit these variables.

3. **AG Grid theme API** — ``backgroundColor``, ``foregroundColor``,
   ``oddRowBackgroundColor``, ``borderColor``, ``spacing``, and the padding
   scale properties are passed directly to AG Grid's ``Theme.withParams()``
   method, which handles the grid's internal styling.

The ``resolveColorScheme()`` function is the single source of truth for
light/dark resolution. It checks ``themeConfig.colorScheme`` first; if
that's ``'auto'`` or absent, it falls back to the OS preference detected
via ``window.matchMedia('(prefers-color-scheme: dark)')``.

After the color scheme is resolved, ``resolveThemeColors()`` merges
the matching ``light`` or ``dark`` sub-dict (if present) with the
top-level properties. Scheme-specific values take priority, so you can
set shared defaults at the top level and only override what differs per
scheme.

In server mode (``mode="buckaroo"``), ``component_config`` is persisted
in the session state. When a user changes the cleaning method or
post-processing option, the dataflow rebuilds ``df_display_args`` from
scratch — but ``component_config`` is re-applied afterward, so the theme
survives interaction.


Building your own theme
-----------------------

Start from the closest built-in and override what you need:

.. code-block:: python

    # Start with forced dark, customize from there
    my_theme = {
        'colorScheme': 'dark',
        'accentColor': '#your-brand-color',
    }

    # Only add background/foreground/border if the defaults don't work
    # for your accent color. The built-in dark/light palettes are designed
    # to work with any accent.

Tips:

- ``accentColor`` is the highest-impact single property — it controls
  column selection highlighting, active tab backgrounds, and button colors.
- Always pair ``accentColor`` with ``accentHoverColor`` (a slightly darker
  shade) for consistent interaction feedback.
- ``oddRowBackgroundColor`` should be close to ``backgroundColor`` — just
  enough contrast to distinguish rows without creating visual noise.
- Use ``spacing``, ``rowVerticalPaddingScale``, and
  ``cellHorizontalPaddingScale`` to control density. Lower values = more
  compact. The defaults (``5``, ``0.5``, ``0.3``) are a good middle ground.
- ``headerBorderColor`` is useful when you want headers to stand out from
  data rows — set it to your accent color for a subtle branded touch.
- For auto light/dark, put shared values at the top level and
  scheme-specific colors in ``light``/``dark`` sub-dicts.
- Test with actual data. A theme that looks great on 5 rows might be
  overwhelming on 500.


Generating static theme demos
------------------------------

The embeds on this page were generated with:

.. code-block:: bash

    python scripts/generate_theme_static_html.py

This produces HTML files in ``docs/extra-html/themes/`` that reference the
shared ``static-embed.js`` and ``static-embed.css`` bundles.
