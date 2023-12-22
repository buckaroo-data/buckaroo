.. _using:

Related projects
================

Other jupyter widgets
---------------------

There are a couple of projects like Buckaroo that aim to provide a better table widget and pandas editing experience.

#. `Mito <https://github.com/mito-ds/monorepo>`_.  Source Available table/code editing widget for Jupyter.  More aimed at easing transition to pandas from excel users.  GNU Affero licensed
#. `Microsoft DataWrangler <https://github.com/microsoft/vscode-data-wrangler>`_ .  Closed source, provides a very similar experience inside of VSCode's notebook experience.  Only works inside of VSCode by the `VS Marketplace Terms of Use <https://cdn.vsassets.io/v/M190_20210811.1/_content/Microsoft-Visual-Studio-Marketplace-Terms-of-Use.pdf>`_
#. `IpyDatagrid <https://github.com/bloomberg/ipydatagrid>`_.  Open source.  Bloomberg's Jupyter table widget. I used the ipydatagrid repo structure as the basis for buckaroo (js build setup only)
#. `IPyAgGrid <https://github.com/widgetti/ipyaggrid>`_ .  Open source.  Wraps `AG Grid <https://www.ag-grid.com/>`_  in a jupyter widget.  Buckaroo also uses AG Grid.
#. `Bamboolib <https://github.com/tkrabel/bamboolib>`_  An originally open source tool aimed at building a similar experience, more aimed as a low-code tool for beginners.  The parent company 8080labs was acquired by Databricks.  Code no longer available.
#. `QGrid <https://github.com/quantopian/qgrid>`_.  Open source, unmaintained.  A slick table widget built by Quantopian, no code gen or data manipulation features


To be clear, I had the idea for building Buckaroo like this before I saw any of the other projects... But they are all open source and we can learn from each other.  If Buckaroo doesn't quite do what you want, check out one of the others.


Other exploratory data analysis tools
--------------------------------------

These tools are aimed at doing more comprehensive stastical analysis of data

#. `Dtale <https://github.com/man-group/dtale>`_
#. `YData profiling <https://github.com/ydataai/ydata-profiling>`_


Other data tables
-----------------

#. `ITables <https://github.com/mwouts/itables>`_  focusses on well styled static tables for Pandas/Jupyter
#. `PrettyTables.jl  <https://github.com/ronisbr/PrettyTables.jl>`_ A terminal/text only table for julia.  Wildly ambitious for pushing the limits on terminal UI.

Other js data tables
--------------------

JS Table widgets.  These are the core interactive tables that modern table expereinces are built around.  A lot of engineering goes into making a web browser handle large scrolling tables performantly

#. `AG-Grid <https://www.ag-grid.com/>`_ The most popular high performance JS data table in use.  Buckaroo is built on top of the open source version of AG-Grid.  The closed source version offers additional features.
#. `Finos Perspective table <https://perspective.finos.org/block/?example=streaming>`_ The highest performance JS Table that I have seen.  Works via a complete rendering engine that writes pixels to a canvas. Open source.
#. `Glide Data grid <https://github.com/glideapps/glide-data-grid>`_  Relatively new.  Claims to be doing canvas rendering.  Looks impressive and fast, less features than AG-Grid.  Developed as a side project from a VC funded pre-revenue company, longterm future isn't certain.


Why list potential competitors
------------------------------

Software is complex, picking open source packages is difficult, even understanding the landscape of possible solutions is difficult.  If you landed on this page, and Buckaroo doesn't suit your needs, hopefully ony of these great other projects will.
 
