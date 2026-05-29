Height Modes
============

Buckaroo controls grid height at two levels: the **outer container** (the
embed footprint in your page) and ``component_config.dfvHeight`` (the pixel
height of the AG Grid viewport inside). Getting them to match is the key to a
well-sized widget.

The interactive demo below walks through every height configuration —
click a button to switch modes and read the explanation panel.

.. raw:: html

   <p style="margin: 1em 0">
     <a href="../height-modes/"
        style="display: inline-block; padding: 8px 18px; background: #1a73e8;
               color: #fff; border-radius: 4px; font-weight: 600;
               text-decoration: none; font-size: 14px;">
       Open interactive demo ↗
     </a>
   </p>

   <p style="font-size: 13px; color: #666; margin: 0.5em 0 1.5em;">
     The demo is a single-page app — multiple Buckaroo instances share the
     same DOM (no iframes). Height modes that depend on
     <code>window.innerHeight</code> behave exactly as they would in your
     own embed.
   </p>


How height is decided
---------------------

``heightStyle()`` in ``gridUtils.ts`` runs on every render:

1. **Special environments** (Google Colab, VS Code, tiny iframe) → always
   ``height: 500, domLayout: "normal"``.

2. **``component_config.dfvHeight``** — explicit pixel height. Overrides
   ``height_fraction``. Absent: ``dfvHeight = window.innerHeight / (height_fraction || 2)``.

3. **``autoHeight`` prop** on ``BuckarooServerView`` / ``DFViewerInfiniteDS``
   — ``true`` stamps ``layoutType: "autoHeight"``; ``false`` stamps
   ``"normal"``; ``undefined`` (default) lets Buckaroo auto-detect.
   See :ref:`autoheight-prop`.

4. **Auto-detect (shortMode)** — if ``numRows + pinnedRowLen`` fits without
   a scrollbar, grid switches to ``domLayout: "autoHeight"`` automatically.


Quick reference
---------------

.. list-table::
   :header-rows: 1
   :widths: 28 18 54

   * - Config
     - Mode
     - When to use
   * - No ``component_config``
     - auto-detect
     - Let Buckaroo decide; works for most cases
   * - ``dfvHeight: N``
     - normal
     - Fixed-height panel, predictable across screen sizes
   * - ``height_fraction: N``
     - normal
     - Proportional to the browser window; good for full-page embeds
   * - ``layoutType: "autoHeight"``
     - autoHeight
     - Force grow-to-content even for large datasets
   * - ``layoutType: "normal"``
     - normal
     - Force fixed height even for small datasets
   * - ``autoHeight={false}`` prop
     - normal
     - Override a server-sent ``"autoHeight"`` from a React embed

.. _autoheight-prop:

The autoHeight prop (issue #862)
---------------------------------

Before version 0.14.9, passing ``autoHeight={false}`` to
``BuckarooServerView`` had no effect: the server's
``component_config.layoutType`` always won. The prop now takes precedence:

.. code-block:: tsx

   // Force normal mode regardless of what the server sends:
   <BuckarooServerView
     wsUrl="ws://localhost:8700/ws/my-session"
     autoHeight={false}
   />

   // Force autoHeight (grow to content):
   <BuckarooServerView wsUrl="..." autoHeight={true} />

   // Undefined (default): server value wins.
   <BuckarooServerView wsUrl="..." />

The same prop is available on ``DFViewerInfiniteDS`` for static embeds.
